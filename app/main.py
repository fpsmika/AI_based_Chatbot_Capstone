from fastapi import FastAPI, Depends, HTTPException, Query
from contextlib import asynccontextmanager
from pydantic import BaseModel
from app.core.logging import setup_logging
from app.core.config import settings
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service  
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
import logging
from fastapi.middleware.cors import CORSMiddleware
from app.models.transaction import Transaction  
from app.api.routes.chat import router as chat_router
from app.api.routes.sql_data import router as sql_router
from app.api.routes.process import router as process_router
from app.api.routes.chat_history import router as chat_history_router
from fastapi import UploadFile, File
import os
from azure.storage.blob import BlobServiceClient






# Logging Setup
setup_logging()

azure_logger = logging.getLogger("azure")
azure_logger.setLevel(logging.WARNING)  # Only show WARNING and above for all Azure components

# Specifically silence the HTTP logger
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    suggestions: list[str]
    context: str = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI Chatbot Starting...")
    
    try:
        # Test OpenRouter connection
        test_response = LlamaService.query("Hello", max_tokens=10)
        logger.info(f"✅ Llama API connection verified: {test_response[:50]}...")
        
        # Test SQL Database connection
        try:
            sql_service = get_sql_service()
            sql_test = sql_service.test_connection()
            logger.info(f"✅ SQL Database connection verified: {sql_test}")
        except Exception as sql_error:
            logger.error(f"❌ SQL Database connection failed: {sql_error}")
        
        logger.info("✅ System startup completed")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
    
    yield
    logger.info("AI Chatbot Shutting Down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None
)


# CORS Middleware 
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.ALLOWED_ORIGINS,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )



logger.info(f"CORS origins at runtime: {settings.ALLOWED_ORIGINS}\n")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(
    chat_router,
    prefix="/api/v1",
    tags=["AI Chat"]
)

app.include_router(
    sql_router,  
    prefix="/api/v1/sql",  
    tags=["SQL Database"]  
)

app.include_router(
    process_router,
    prefix="/api/v1",
    tags=["Process"]
)

app.include_router(
    chat_history_router,
    prefix="/api/v1",
    tags=["Chat History"]
)


blob_service_client = BlobServiceClient.from_connection_string(
    settings.AZURE_STORAGE_CONNECTION_STRING
)
container_client = blob_service_client.get_container_client(
    settings.BLOB_CONTAINER_NAME
)

@app.get("/api/v1/ping-blob")
async def ping_blob():
    """
    Quick check that our blob container is reachable.
    """
    try:
        count = sum(1 for _ in container_client.list_blobs())
        return {
            "container": settings.BLOB_CONTAINER_NAME,
            "blob_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Blob ping failed: {str(e)}")

@app.post("/api/v1/upload")
async def upload_to_blob(file: UploadFile = File(...)):
    """
    Receive a CSV/XLS/XLSX from the frontend,
    upload it as a blob into your raw-upload container.
    """
    
    blob_name = file.filename

    try:
        data = await file.read()
        container_client.upload_blob(
            name=blob_name,
            data=data,
            overwrite=True
        )
        return {
            "status": "success",
            "message": f"Uploaded '{blob_name}' to container '{settings.BLOB_CONTAINER_NAME}'."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.get("/")
def root():
    return {"message": f"{settings.PROJECT_NAME} v{settings.VERSION}"}

@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    """Health check with DB verification"""
    try:
        db.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/health")
def health_check():
    """Simple health check without database dependency"""
    return {"status": "healthy", "timestamp": date.today().isoformat()}

@app.get("/health/full")
def full_health_check(db: Session = Depends(get_db)):
    """Comprehensive health check for all services"""
    health_status = {
        "timestamp": date.today().isoformat(),
        "services": {}
    }
    
    # Check SQL Database
    try:
        db.execute("SELECT 1")
        health_status["services"]["sql_database"] = "healthy"
    except Exception as e:
        health_status["services"]["sql_database"] = f"unhealthy: {str(e)}"
    
        # Check SQL DB
    try:
        service = get_sql_service()
        service.test_connection()
        health_status["services"]["sql_database"] = "healthy"
    except Exception as e:
        health_status["services"]["sql_database"] = f"unhealthy: {str(e)}"

    
    # Check Llama API
    try:
        response = LlamaService.query("Test", max_tokens=5)
        health_status["services"]["llama_api"] = "healthy"
    except Exception as e:
        health_status["services"]["llama_api"] = f"unhealthy: {str(e)}"
    
    # Determine overall status
    unhealthy_services = [k for k, v in health_status["services"].items() if "unhealthy" in v]
    health_status["overall_status"] = "healthy" if not unhealthy_services else "degraded"
    
    return health_status

@app.get("/api/v1/health/llama")
def llama_health_check():
    """Test Llama API connectivity"""
    try:
        response = LlamaService.query("Test", max_tokens=5)
        return {"status": "healthy", "llama_response": response}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Llama API unavailable: {str(e)}")

@app.get("/transactions")
def list_transactions(db: Session = Depends(get_db)):
    """Legacy endpoint - consider deprecating"""
    return db.query(Transaction).limit(100).all()

@app.get("/api/v1/transactions")
def get_transactions(
    skip: int = 0,
    limit: int = 100,
    year: int = None,
    vendor: str = None,
    db: Session = Depends(get_db)
):
    """Improved transaction endpoint with filtering"""
    query = db.query(Transaction)
    
    if year:
        query = query.filter(Transaction.Year == year)
    if vendor:
        query = query.filter(Transaction.Vendor.ilike(f"%{vendor}%"))
    
    return query.offset(skip).limit(limit).all()

@app.get("/api/v1/transactions/analytics")
async def get_analytics(
    question: str = Query("Show me vendor transaction summary", description="Natural language question"),
    db: Session = Depends(get_db)
):
    """Analytics using natural language to SQL conversion"""
    try:
        from app.services.text_to_sql_service import get_text_to_sql_service
        
        text_to_sql = get_text_to_sql_service()
        result = text_to_sql.analyze_supply_chain_query(question)
        
        if not result["success"]:
            return {"error": result.get("error"), "insights": result["insights"]}
        
        return {
            "question": question,
            "insights": result["insights"],
            "data_summary": result["data_summary"],
            "recommendations": result["recommendations"]
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/v1/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    """Get single transaction by ID"""
    transaction = db.query(Transaction).filter(Transaction.TransactionID == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


# Add a simple chat test endpoint
@app.post("/chat/test")
async def chat_test(request: ChatRequest):
    """Simple chat test without database dependency"""
    try:
        response = LlamaService.query(request.message, max_tokens=100)
        return {"response": response, "status": "success"}
    except Exception as e:
        return {"response": f"Error: {str(e)}", "status": "error"}