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

from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.embedding_service import embed_bulk_text

router = APIRouter()

class ProcessResponse(BaseModel):
    status: str
    batch_id: str
    rows_loaded: int
    filename: str

def _run_pipeline_and_write(
    temp_path: str,
    filename: str,
    batch_id: str,
    embed_batch_size: int = 500
) -> int:
    rows_loaded = 0
    try:
        # 1) ingest & clean
        df = ingest_file(temp_path)
        if settings.MAX_INGEST_ROWS:
            df = df.head(settings.MAX_INGEST_ROWS)
        df = df.dropna(subset=["TransactionID","FacilityID","Quantity","PricePaid","TotalSpend"])
        df = df[df["Quantity"].astype(float) >= 0]
        df = df[df["PricePaid"].astype(float) > 0]
        df = df.drop_duplicates(subset=["TransactionID"])

        # 2) transform & normalize dates
        df = transform_data(df)
        def normalize(v: Any) -> Any:
            if isinstance(v, (pd.Timestamp, np.datetime64, datetime, date)):
                return pd.to_datetime(v).isoformat()
            return v
        df = df.applymap(normalize)

        # 3) assign stable IDs
        df["id"]       = [str(uuid.uuid4()) for _ in range(len(df))]
        df["batch_id"] = batch_id

        cosmos = get_cosmos_service()

        # 4) upsert raw
        for rec in df.to_dict("records"):
            cosmos.upsert_item(rec)
            rows_loaded += 1

        # spot‑check first id
        sample_id = df.loc[0, "id"]
        try:
            cosmos.read_item(item=sample_id, partition_key=sample_id)
        except Exception as e:
            print(f"❌ Spot‑check FAILED for id {sample_id} in {filename}: {e}")

        # 5) parse chunks (row‑by‑row fallback to debug)
        try:
            chunks = csv_to_purchase_chunks(df)
        except Exception as e:
            for i, row in enumerate(df.to_dict("records")):
                try:
                    csv_to_purchase_chunks(pd.DataFrame([row]))
                except Exception as row_e:
                    print(f"❌ Parser failed on row {i} of {filename}: {row_e}")
                    break
            else:
                print(f"❌ Parser failed on entire file {filename}: {e}")
            raise

        texts     = [c["text"]     for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        total     = len(texts)

        # 6) batch‑embed & merge back
        for start in range(0, total, embed_batch_size):
            batch_texts = texts[start:start+embed_batch_size]
            batch_metas = metadatas[start:start+embed_batch_size]
            batch_no = start // embed_batch_size + 1

            try:
                embs = embed_bulk_text(batch_texts)
            except Exception as e:
                print(f"❌ Embedding failed on batch {batch_no} of {filename}: {e}")
                continue

            for meta, vec in zip(batch_metas, embs):
                rec_id = meta.get("id")
                if not rec_id:
                    print(f"❌ Missing id in metadata on batch {batch_no}: {meta}")
                    continue
                try:
                    doc = cosmos.read_item(item=rec_id, partition_key=rec_id)
                    doc["vector"] = vec
                    cosmos.upsert_item(doc)
                except Exception as e:
                    print(f"❌ Failed to merge vector for id {rec_id} in {filename}: {e}")

    except Exception as e:
        print(f"❌ Background task error for batch {batch_id}, file {filename}: {e}")
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    return rows_loaded

@router.post("/process", response_model=ProcessResponse)
async def process_file_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> ProcessResponse:
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.csv', '.xlsx', '.xls'}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        temp_path = tmp.name

    try:
        blob = (
            BlobServiceClient
            .from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
            .get_container_client(settings.BLOB_CONTAINER_NAME)
            .get_blob_client(file.filename)
        )
        with open(temp_path, "rb") as data:
            blob.upload_blob(data, overwrite=True)
    except Exception:
        pass

    batch_id = str(uuid.uuid4())
    background.add_task(_run_pipeline_and_write, temp_path, file.filename, batch_id, 500)

    return ProcessResponse(
        status="enqueued",
        batch_id=batch_id,
        rows_loaded=0,
        filename=file.filename
    )
