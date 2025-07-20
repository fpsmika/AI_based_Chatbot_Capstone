from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
from app.core.logging import setup_logging
from app.core.config import settings
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.services.cosmos_service import get_cosmos_service  # Add this import
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
import logging
from fastapi.middleware.cors import CORSMiddleware
from app.models.transaction import Transaction  
from app.api.routes.chat import router as chat_router
from app.api.routes.cosmos import router as cosmos_router from app.api.routes import process
app.include_router(process.router, prefix="/api/v1", tags=["Process"])


# Logging Setup
setup_logging()

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    suggestions: list[str]
    context: str = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle management"""
    logger.info("AI Chatbot Ready...")
    
    # Test Llama connection on startup
    try:
        test_response = LlamaService.query("Hello", max_tokens=10)
        logger.info(f"✅ Llama API connection verified: {test_response[:50]}...")
    except Exception as e:
        logger.error(f"❌ Llama API connection failed: {str(e)}")
    
    
    # Test Cosmos DB connection on startup
    try:
        cosmos_container = get_cosmos_service()
        list(cosmos_container.read_all_items(max_item_count=1))
        logger.info("✅ Cosmos DB connection verified")
    except Exception as e:
        logger.error(f"❌ Cosmos DB connection error: {str(e)}")

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
    cosmos_router,
    prefix="/api/v1/cosmos",
    tags=["Cosmos DB"]
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
    
        # Check Cosmos DB
    try:
        cosmos_container = get_cosmos_service()
        list(cosmos_container.read_all_items(max_item_count=1))
        health_status["services"]["cosmos_db"] = "healthy"
    except Exception as e:
        health_status["services"]["cosmos_db"] = f"unhealthy: {str(e)}"

    
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

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """AI-powered chatbot endpoint with context"""
    logger.info(f"Received chat message: {request.message}")
    
    try:
        # Get relevant transaction data for context
        relevant_transactions = Transaction.search_relevant(db, request.message, limit=3)
        
        # Build context for AI
        context = ""
        if relevant_transactions:
            context = "Recent transaction data:\n"
            for tx in relevant_transactions:
                context += f"- {tx.Vendor} ({tx.FacilityType}, {tx.Region})\n"
        
        # Create enhanced prompt with context
        system_prompt = """You are an AI assistant specializing in supply chain management. 
        Help users with transaction data, vendor information, and supply chain queries.
        Be concise but helpful. If asked about specific data, reference the context provided."""
        
        enhanced_prompt = f"{system_prompt}\n\nContext: {context}\n\nUser Question: {request.message}"
        
        # Get AI response
        ai_response = LlamaService.query(enhanced_prompt, max_tokens=300)
        
        # Generate contextual suggestions
        suggestions = []
        if "vendor" in request.message.lower():
            suggestions.extend(["Show vendor analytics", "Compare vendor performance"])
        if "transaction" in request.message.lower():
            suggestions.extend(["View recent transactions", "Transaction by date range"])
        if not suggestions:
            suggestions = ["Order status", "Inventory check", "Supplier contact"]
        
        return ChatResponse(
            response=ai_response,
            suggestions=suggestions[:3],  # Limit to 3 suggestions
            context=context if context else None
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        # Fallback response
        return ChatResponse(
            response=f"I encountered an issue processing your request: {str(e)}. Please try again.",
            suggestions=["Try rephrasing", "Check system status", "Contact support"]
        )

# Add a simple chat test endpoint
@app.post("/chat/test")
async def chat_test(request: ChatRequest):
    """Simple chat test without database dependency"""
    try:
        response = LlamaService.query(request.message, max_tokens=100)
        return {"response": response, "status": "success"}
    except Exception as e:
        return {"response": f"Error: {str(e)}", "status": "error"}