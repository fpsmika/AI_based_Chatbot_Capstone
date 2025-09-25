from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, List
import tempfile, os, uuid, json
import pandas as pd
import numpy as np
from datetime import date, datetime
import asyncio
import logging

from azure.storage.blob import BlobServiceClient
from app.core.config import settings
from app.utils.pipeline import ingest_file
from app.utils.transform import transform_data
from app.services.sql_service import get_sql_service

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store of how many rows were written for each batch
status_store: dict[str, int] = {}

class ProcessResponse(BaseModel):
    status: str
    batch_id: str
    rows_loaded: int
    filename: str

async def _run_pipeline_and_write(
    temp_path: str,
    filename: str,
    batch_id: str,
    embed_batch_size: int = 500  # Keep parameter for backward compatibility but don't use
) -> int:
    """
    Simplified pipeline that only processes data to SQL database
    """
    rows_loaded = 0
    try:
        logger.info(f"Starting pipeline for {filename} with batch_id {batch_id}")
        
        # 1) Ingest & clean
        df = ingest_file(temp_path)
        if settings.MAX_INGEST_ROWS:
            df = df.head(settings.MAX_INGEST_ROWS)
        
        # Clean the data
        df = df.dropna(subset=["TransactionID", "FacilityID", "Quantity", "PricePaid", "TotalSpend"])
        df = df[df["Quantity"].astype(float) >= 0]
        df = df[df["PricePaid"].astype(float) > 0]
        df = df.drop_duplicates(subset=["TransactionID"])

        logger.info(f"After cleaning: {len(df)} rows remaining")

        # 2) Transform & normalize dates
        df = transform_data(df)
        
        def normalize(v: Any) -> Any:
            if isinstance(v, (pd.Timestamp, np.datetime64, datetime, date)):
                return pd.to_datetime(v).isoformat()
            return v
        
        df = df.applymap(normalize)

        # 3) Assign stable IDs and batch ID
        df["id"] = [str(uuid.uuid4()) for _ in range(len(df))]
        df["batch_id"] = batch_id

        # Get SQL service only
        sql_service = get_sql_service()

        # 4) Bulk upsert data to SQL only (no embeddings or AI Search)
        records = df.to_dict("records")
        try:
            rows_loaded = sql_service.bulk_upsert_records(records, batch_id)
            logger.info(f"Successfully upserted {rows_loaded} records to SQL")
        except Exception as e:
            logger.error(f"Bulk upsert failed, trying individual upserts: {e}")
            # Fallback to individual upserts
            for rec in records:
                try:
                    sql_service.upsert_item(rec, table_name="supply_records")
                    rows_loaded += 1
                except Exception as upsert_error:
                    logger.error(f"Failed to upsert individual record: {upsert_error}")
                    continue

        # Notify UI that processing is done
        status_store[batch_id] = rows_loaded
        logger.info(f"Data processing complete: {rows_loaded} rows loaded")

    except Exception as e:
        logger.error(f"Pipeline error for batch {batch_id}, file {filename}: {e}")
        raise
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    return rows_loaded

# SOLUTION 1: Create a synchronous wrapper function
def run_pipeline_sync(temp_path: str, filename: str, batch_id: str, embed_batch_size: int = 500):
    """
    Synchronous wrapper that creates and runs the async pipeline
    """
    try:
        # Create a new event loop for this background task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                _run_pipeline_and_write(temp_path, filename, batch_id, embed_batch_size)
            )
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Background task error: {e}")
        raise

@router.post("/process", response_model=ProcessResponse)
async def process_file_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> ProcessResponse:
    """
    Process uploaded file and store in SQL database with AI Search embeddings
    """
    # Validate file type
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.csv', '.xlsx', '.xls'}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type {ext}")

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = tmp.name

    # Upload to Azure Blob Storage (optional)
    try:
        if hasattr(settings, 'AZURE_STORAGE_CONNECTION_STRING') and settings.AZURE_STORAGE_CONNECTION_STRING:
            blob_client = (
                BlobServiceClient
                .from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
                .get_container_client(settings.BLOB_CONTAINER_NAME)
                .get_blob_client(file.filename)
            )
            with open(temp_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            logger.info(f"File uploaded to blob storage: {file.filename}")
    except Exception as e:
        logger.warning(f"Failed to upload to blob storage: {e}")
        # Continue processing even if blob upload fails

    # Generate batch ID and start background processing
    batch_id = str(uuid.uuid4())
    
    # FIXED: Use the synchronous wrapper function
    background.add_task(
        run_pipeline_sync,
        temp_path,
        file.filename,
        batch_id,
        500
    )
    
    logger.info(f"Enqueued processing for {file.filename} with batch_id {batch_id}")

    return ProcessResponse(
        status="enqueued",
        batch_id=batch_id,
        rows_loaded=0,
        filename=file.filename
    )

# Alternative SOLUTION 2: Using asyncio.run directly in background task
def run_pipeline_with_asyncio_run(temp_path: str, filename: str, batch_id: str, embed_batch_size: int = 500):
    """
    Alternative approach using asyncio.run
    """
    try:
        return asyncio.run(
            _run_pipeline_and_write(temp_path, filename, batch_id, embed_batch_size)
        )
    except Exception as e:
        logger.error(f"Background task error: {e}")
        raise

# You can use either approach. Replace the background.add_task call with:
# background.add_task(
#     run_pipeline_with_asyncio_run,
#     temp_path,
#     file.filename,
#     batch_id,
#     500
# )

@router.get("/process/status/{batch_id}")
async def process_status(request: Request, batch_id: str):
    """
    SSE endpoint: emits a single 'rows_loaded' event as soon as the raw upsert completes.
    """
    async def event_generator():
        logger.info(f"Starting status stream for batch_id: {batch_id}")
        
        # Wait until background task writes into status_store[batch_id]
        timeout_counter = 0
        max_timeout = 300  # 5 minutes timeout
        
        while timeout_counter < max_timeout:
            if await request.is_disconnected():
                logger.info(f"Client disconnected for batch_id: {batch_id}")
                break
                
            if batch_id in status_store:
                rows_loaded = status_store.pop(batch_id)
                logger.info(f"Batch {batch_id} completed with {rows_loaded} rows")
                yield f"event: rows_loaded\ndata: {rows_loaded}\n\n"
                yield f"event: complete\ndata: Processing completed\n\n"
                break
                
            await asyncio.sleep(0.5)
            timeout_counter += 0.5
        else:
            # Timeout reached
            logger.warning(f"Timeout reached for batch_id: {batch_id}")
            yield f"event: timeout\ndata: Processing timeout\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/process/batches")
async def list_recent_batches():
    """
    List recent processing batches from SQL database
    """
    try:
        sql_service = get_sql_service()
        
        # Get unique batch IDs from recent data
        query = """
        SELECT DISTINCT batch_id, COUNT(*) as record_count, MIN(created_at) as created_at
        FROM supply_records 
        WHERE batch_id IS NOT NULL
        GROUP BY batch_id
        ORDER BY MIN(created_at) DESC
        """
        
        results = sql_service.query_items(query)
        
        return {
            "batches": results,
            "total": len(results)
        }
        
    except Exception as e:
        logger.error(f"Failed to list batches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list batches: {e}")

@router.delete("/process/batch/{batch_id}")
async def delete_batch(batch_id: str):
    """
    Delete a specific batch from SQL database only
    """
    try:
        sql_service = get_sql_service()
        
        # Delete from supply_records only
        delete_supply_query = "DELETE FROM supply_records WHERE batch_id = ?"
        sql_service.query_items(delete_supply_query, [{"name": "?", "value": batch_id}])
        
        return {"message": f"Batch {batch_id} deleted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to delete batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete batch: {e}")

@router.get("/process/health")
async def process_health():
    """
    Health check for processing service
    """
    try:
        sql_service = get_sql_service()
        sql_connection_test = sql_service.test_connection()
        
        return {
            "status": "healthy",
            "sql_connection": sql_connection_test,
            "active_batches": len(status_store)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "active_batches": len(status_store)
        }