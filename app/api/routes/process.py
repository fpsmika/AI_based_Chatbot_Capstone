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
from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.embedding_service import embed_bulk_text
from app.services.ai_search_service import get_ai_search_service

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
    embed_batch_size: int = 500
) -> int:
    """
    Updated pipeline that works with SQL database and AI Search
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

        # Get services
        sql_service = get_sql_service()
        ai_search = get_ai_search_service()

        # 4) Bulk upsert raw data to SQL
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

        # Notify UI that raw writes are done
        status_store[batch_id] = rows_loaded
        logger.info(f"Raw data processing complete: {rows_loaded} rows loaded")

        # 5) Upload to AI Search (without embeddings first)
        try:
            logger.info("Starting AI Search document upload...")
            upload_result = ai_search.upload_documents(records)
            logger.info(f"Successfully uploaded {upload_result['uploaded']} documents to AI Search")
        except Exception as e:
            logger.error(f"AI Search upload failed: {e}")
            # Don't fail the entire pipeline if AI Search fails
            pass

        # 6) Generate embeddings and upload with vectors to AI Search
        try:
            logger.info("Starting embedding generation and vector upload...")
            await _process_embeddings_to_ai_search(df, embed_batch_size, filename, batch_id)
            logger.info("Embedding processing completed")
                
        except Exception as e:
            logger.error(f"Embedding processing failed: {e}")
            # Don't fail the entire pipeline if embeddings fail
            pass

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

async def _process_embeddings_to_ai_search(df: pd.DataFrame, embed_batch_size: int, filename: str, batch_id: str):
    """
    Process embeddings and upload documents with vectors to AI Search
    Enhanced with comprehensive field mapping and better error handling
    """
    # Convert DataFrame to chunks for embedding with improved parser
    chunks = csv_to_purchase_chunks(df)
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    total = len(texts)

    logger.info(f"Processing {total} embeddings in batches of {embed_batch_size} for {filename}")

    # Validate chunk quality
    from app.utils.supply_data_parser import validate_chunk_data
    validation = validate_chunk_data(chunks)
    logger.info(f"Chunk validation: {validation['message']}")
    
    if not validation['valid']:
        logger.warning(f"Low quality chunks detected for {filename}, but proceeding...")

    ai_search = get_ai_search_service()

    # Process in batches
    successful_batches = 0
    total_uploaded = 0
    
    for start in range(0, total, embed_batch_size):
        batch_texts = texts[start:start + embed_batch_size]
        batch_metas = metadatas[start:start + embed_batch_size]
        batch_no = start // embed_batch_size + 1

        try:
            logger.info(f"Processing embedding batch {batch_no}/{(total + embed_batch_size - 1) // embed_batch_size}")
            
            # Generate embeddings
            embeddings = embed_bulk_text(batch_texts)
            logger.info(f"  Generated {len(embeddings)} embeddings")
            
            # Prepare comprehensive documents with vectors for AI Search
            documents = []
            for text, metadata, embedding in zip(batch_texts, batch_metas, embeddings):
                # Create comprehensive document with all field mappings
                doc = {
                    "id": str(uuid.uuid4()),
                    "content": text,
                    "content_vector": embedding,
                    "batch_id": batch_id,
                    
                    # Comprehensive field mapping for search compatibility
                    "TransactionID": str(metadata.get("transaction_id", metadata.get("TransactionID", ""))),
                    "FacilityID": str(metadata.get("facility_id", metadata.get("FacilityID", ""))),
                    "FacilityType": str(metadata.get("facility_type", metadata.get("FacilityType", "Unknown"))),
                    "Region": str(metadata.get("region", metadata.get("Region", "Unknown"))),
                    "ItemDesc": str(metadata.get("item_desc", metadata.get("ItemDesc", ""))),
                    "Vendor": str(metadata.get("vendor", metadata.get("Vendor", "Unknown"))),
                    "Manufacturer": str(metadata.get("manufacturer", metadata.get("Manufacturer", "Unknown"))),
                    "Department": str(metadata.get("department", metadata.get("Department", "Unknown"))),
                    "Category": str(metadata.get("category", metadata.get("Category", "Unknown"))),
                    
                    # Numeric fields with proper type conversion
                    "TotalSpend": float(metadata.get("total_spend", metadata.get("TotalSpend", 0))),
                    "PricePaid": float(metadata.get("price_paid", metadata.get("PricePaid", 0))),
                    "Quantity": int(metadata.get("quantity", metadata.get("Quantity", 0))),
                    "Month": int(metadata.get("month", metadata.get("Month", 0))) if metadata.get("month", metadata.get("Month")) else 0,
                    "Year": int(metadata.get("year", metadata.get("Year", 0))) if metadata.get("year", metadata.get("Year")) else 0,
                    
                    # Additional searchable fields
                    "VendorID": str(metadata.get("vendor_id", metadata.get("VendorID", ""))),
                    "ManufacturerID": str(metadata.get("manufacturer_id", metadata.get("ManufacturerID", ""))),
                    "LoadDate": metadata.get("load_date", metadata.get("LoadDate")),
                    
                    # Store rich metadata as JSON for reference
                    "metadata": json.dumps(metadata, default=str)
                }
                documents.append(doc)

            # Upload to AI Search with vectors
            logger.info(f"  Uploading {len(documents)} documents with vectors...")
            upload_result = ai_search.upload_documents(documents)
            
            if upload_result.get('uploaded', 0) > 0:
                successful_batches += 1
                total_uploaded += upload_result['uploaded']
                logger.info(f"  ✅ Batch {batch_no} completed: {upload_result['uploaded']} documents with vectors uploaded")
            else:
                error_msg = upload_result.get('error', 'Unknown error')
                logger.error(f"  ✖️ Batch {batch_no} failed: {error_msg}")

        except Exception as e:
            logger.error(f"  ✖️ Embedding batch {batch_no} failed for {filename}: {e}")
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
            continue

    # Final summary
    success_rate = (successful_batches / ((total + embed_batch_size - 1) // embed_batch_size)) * 100 if total > 0 else 0
    logger.info(f"Embedding processing completed for {filename}:")
    logger.info(f"  - Total chunks: {total}")
    logger.info(f"  - Successful batches: {successful_batches}")
    logger.info(f"  - Total uploaded: {total_uploaded}")
    logger.info(f"  - Success rate: {success_rate:.1f}%")
    
    return {
        "total_chunks": total,
        "successful_batches": successful_batches,
        "total_uploaded": total_uploaded,
        "success_rate": success_rate
    }

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
    Delete a specific batch from SQL, and AI Search documents
    """
    try:
        sql_service = get_sql_service()
        ai_search = get_ai_search_service()
        
        # Delete from supply_records
        delete_supply_query = "DELETE FROM supply_records WHERE batch_id = ?"
        sql_service.query_items(delete_supply_query, [{"name": "?", "value": batch_id}])
        
        # Find and delete AI Search documents with this batch_id
        try:
            # Search for documents with this batch_id
            ai_docs = ai_search.search("*", filters=f"batch_id eq '{batch_id}'", top=1000)
            if ai_docs:
                doc_ids = [doc["id"] for doc in ai_docs]
                delete_result = ai_search.delete_documents(doc_ids)
                logger.info(f"Deleted {delete_result['deleted']} documents from AI Search")
        except Exception as ai_error:
            logger.warning(f"Failed to delete AI Search documents: {ai_error}")
        
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
        
        ai_search = get_ai_search_service()
        ai_search_test = ai_search.test_connection()
        
        return {
            "status": "healthy",
            "sql_connection": sql_connection_test,
            "ai_search_connection": ai_search_test,
            "active_batches": len(status_store)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "active_batches": len(status_store)
        }