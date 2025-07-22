from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from typing import Any
import tempfile, os, uuid
import pandas as pd
import numpy as np
from datetime import date, datetime

from azure.storage.blob import BlobServiceClient  
from app.core.config import settings
from app.utils.pipeline import ingest_file
from app.utils.transform import transform_data
from app.services.cosmos_service import get_cosmos_service

router = APIRouter()

class ProcessResponse(BaseModel):
    status: str
    batch_id: str
    rows_loaded: int
    filename: str

def _run_pipeline_and_write(temp_path: str, filename: str, batch_id: str):
    try:
        df = ingest_file(temp_path)
        # after df = ingest_file(temp_path)

        if settings.MAX_INGEST_ROWS:
            df = df.head(settings.MAX_INGEST_ROWS)


        required = ["TransactionID", "FacilityID", "Quantity", "PricePaid", "TotalSpend"]
        # Drop rows missing any critical field:
        df = df.dropna(subset=required)
        # Enforce numeric ranges:
        df = df[df["Quantity"].astype(float) >= 0]
        df = df[df["PricePaid"].astype(float) > 0]
        # Remove duplicate transactions:
        df = df.drop_duplicates(subset=["TransactionID"])

        df = transform_data(df)

        # normalize dates to ISO
        def normalize(val: Any) -> Any:
            if isinstance(val, (pd.Timestamp, np.datetime64, datetime, date)):
                return pd.to_datetime(val).isoformat()
            return val

        df = df.applymap(normalize)

        cosmos = get_cosmos_service()

        for rec in df.to_dict("records"):
            rec["id"]       = str(uuid.uuid4())
            rec["batch_id"] = batch_id
            cosmos.create_item(body=rec)

        print(f"✅ Batch {batch_id}: wrote {len(df)} rows for {filename}")
    except Exception as e:
        print(f"❌ Background task error for batch {batch_id}: {e}")
    finally:
        try: os.unlink(temp_path)
        except: pass

@router.post("/process", response_model=ProcessResponse)
async def process_file_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.csv', '.xlsx', '.xls'}:
        raise HTTPException(400, f"Unsupported file type {ext}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = tmp.name

    # upload raw to blob
    try:
        blob_client = (
            BlobServiceClient
            .from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            .get_container_client(settings.BLOB_CONTAINER_NAME)
            .get_blob_client(file.filename)
        )
        with open(temp_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        print(f"✅ Uploaded raw to blob: {settings.BLOB_CONTAINER_NAME}/{file.filename}")
    except Exception as be:
        print(f"⚠️ Blob upload failed: {be}")

    batch_id = str(uuid.uuid4())
    background.add_task(_run_pipeline_and_write, temp_path, file.filename, batch_id)

    return ProcessResponse(
        status="enqueued",
        batch_id=batch_id,
        rows_loaded=0,
        filename=file.filename
    )
