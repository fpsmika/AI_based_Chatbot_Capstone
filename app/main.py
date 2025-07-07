from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from app.core.logging import setup_logging
from app.core.config import settings
from app.db.session import get_db
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
import logging
from fastapi.middleware.cors import CORSMiddleware
from app.models.transaction import Transaction  


# Logging Setup
setup_logging()
logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle management"""
    logger.info("AI Chatbot Ready...")
    yield
    logger.info("Shutting down AI Chatbot...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None
)

# CORS Middleware 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
def get_analytics(
    start_date: date = None,
    end_date: date = None,
    db: Session = Depends(get_db)
):
    """Vendor transaction analytics"""
    query = db.query(
        Transaction.Vendor,
        func.count(Transaction.TransactionID).label("count"),
    )
    
    if start_date and end_date:
        query = query.filter(Transaction.LoadDate.between(start_date, end_date))
    
    return query.group_by(Transaction.Vendor).all()

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

@app.post("/chat")
async def chat(request: ChatRequest):
    """Chatbot endpoint"""
    logger.info(f"Received chat message: {request.message}")
    return {
        "response": f"Received: {request.message}",
        "suggestions": ["Order status", "Inventory check", "Supplier contact"]
    }