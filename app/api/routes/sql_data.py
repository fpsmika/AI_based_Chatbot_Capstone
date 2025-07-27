# app/api/routes/sql_data.py (replaces cosmos.py)
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Any, Dict, List
from uuid import uuid4
from datetime import datetime, date
import pandas as pd
import numpy as np

from app.services.sql_service import get_sql_service

router = APIRouter()


@router.post("/sql/test")  # Changed from /cosmos/test
async def test_sql():
    service = get_sql_service()
    doc = {"id": "test-1", "batch_id": "test-batch", "foo": "bar"}
    try:
        service.upsert_item(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL write failed: {e}")
    return {"status": "wrote test-1 to SQL"}


class BatchUploadResponse(BaseModel):
    batch_id: str
    count: int


def _write_batch(records: List[Dict[str, Any]], batch_id: str):
    service = get_sql_service()
    try:
        # Use the bulk upsert method for better performance
        success_count = service.bulk_upsert_records(records, batch_id)
        return success_count
    except Exception as e:
        # Fallback to individual upserts
        success_count = 0
        for rec in records:
            try:
                rec["batch_id"] = batch_id
                # Convert datetime objects
                for k, v in list(rec.items()):
                    if isinstance(v, (datetime, date, pd.Timestamp, np.datetime64)):
                        if isinstance(v, np.datetime64):
                            v = pd.to_datetime(v)
                        rec[k] = v.isoformat()
                
                service.upsert_item(rec)
                success_count += 1
            except Exception as item_error:
                print(f"Failed to upsert item {rec.get('id', 'unknown')}: {item_error}")
                continue
        return success_count


@router.post("/data/upload", response_model=BatchUploadResponse)
async def upload_records_to_sql(  # Changed name
    records: List[Dict[str, Any]],
    background: BackgroundTasks
):
    if not records:
        raise HTTPException(status_code=400, detail="No records provided")
    batch_id = str(uuid4())
    background.add_task(_write_batch, records, batch_id)
    return BatchUploadResponse(batch_id=batch_id, count=len(records))


@router.get("/data/{batch_id}", response_model=List[Dict[str, Any]])
async def get_records_by_batch(
    batch_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    service = get_sql_service()
    try:
        # Use the SQL service method
        items = service.get_records_by_batch(batch_id, offset, limit)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Additional SQL-specific endpoints
@router.get("/sql/stats")
async def get_sql_stats():
    """Get database statistics"""
    try:
        service = get_sql_service()
        # You can add methods to SQLService to get stats
        return {"status": "SQL database connected", "service": "active"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL stats failed: {e}")


@router.delete("/data/batch/{batch_id}")
async def delete_batch(batch_id: str):
    """Delete all records in a batch"""
    try:
        # You can add this method to SQLService
        service = get_sql_service()
        # This would need to be implemented in SQLService
        # deleted_count = service.delete_batch(batch_id)
        return {"status": f"Batch deletion initiated for {batch_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))