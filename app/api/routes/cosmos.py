from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Any, Dict, List
from uuid import uuid4
from datetime import datetime, date
import pandas as pd
import numpy as np

from azure.cosmos import CosmosClient
from app.core.config import settings

router = APIRouter()

def get_container():
    client = CosmosClient(
        settings.COSMOS_DB_ENDPOINT,
        settings.COSMOS_DB_KEY
    )
    db = client.get_database_client(settings.COSMOS_DB_DATABASE)
    return db.get_container_client("supply_records")


@router.post("/cosmos/test")
async def test_cosmos():
    """
    Smoke‑test: write a tiny document to Cosmos and confirm it succeeded.
    """
    container = get_container()

    doc = {
        "id": "test-1",
        "batch_id": "test-batch",
        "foo": "bar"
    }
    try:
       container.upsert_item(body=doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cosmos write failed: {e}")

    return {"status": "wrote test-1"}


class BatchUploadResponse(BaseModel):
    batch_id: str
    count: int


def _write_batch(records: List[Dict[str, Any]], batch_id: str):
    """
    Background task that actually writes each record,
    stamping them with batch_id for paging later.
    Converts any datetime-like objects to ISO strings before write.
    """
    container = get_container()
    for rec in records:
        rec["batch_id"] = batch_id
        # JSON‑serialize any datetime-like values
        for k, v in list(rec.items()):
            if isinstance(v, (datetime, date, pd.Timestamp, np.datetime64)):
                # convert numpy datetime64 via pandas
                if isinstance(v, np.datetime64):
                    v = pd.to_datetime(v)
                rec[k] = v.isoformat()
        container.create_item(body=rec)


@router.post("/data/upload", response_model=BatchUploadResponse)
async def upload_records_to_cosmos(
    records: List[Dict[str, Any]],
    background: BackgroundTasks
):
    """
    Ingest a batch of parsed rows into Cosmos DB.
    Returns a batch_id you can later use for pagination.
    """
    if not records:
        raise HTTPException(status_code=400, detail="No records provided")

    batch_id = str(uuid4())
    # Kick off the actual write in the background.
    background.add_task(_write_batch, records, batch_id)

    return BatchUploadResponse(batch_id=batch_id, count=len(records))


@router.get("/data/{batch_id}", response_model=List[Dict[str, Any]])
async def get_records_by_batch(
    batch_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Retrieve a page of records for the given batch_id.
    """
    container = get_container()

    query = """
        SELECT * FROM c
        WHERE c.batch_id = @batch_id
        OFFSET @offset LIMIT @limit
    """
    params = [
        {"name": "@batch_id", "value": batch_id},
        {"name": "@offset",   "value": offset},
        {"name": "@limit",    "value": limit},
    ]

    try:
        items = list(container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True
        ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return items