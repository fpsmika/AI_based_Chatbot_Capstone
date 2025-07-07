from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.models.transaction import Transaction
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str = None

class ChatResponse(BaseModel):
    response: str
    suggestions: list[str] = []
    context: str = None
    session_id: str = None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Main chat endpoint with database context integration
    """
    logger.info(f"Received chat message: {request.message}")
    
    try:
        # Get relevant transaction data for context
        relevant_transactions = Transaction.search_relevant(
            db, request.message, limit=5
        )
        
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
        message_lower = request.message.lower()
        
        if "vendor" in message_lower:
            suggestions.extend(["Show vendor analytics", "Compare vendor performance"])
        if "transaction" in message_lower:
            suggestions.extend(["View recent transactions", "Transaction by date range"])
        if "hospital" in message_lower or "clinic" in message_lower:
            suggestions.extend(["Filter by facility type", "Regional analysis"])
        if not suggestions:
            suggestions = ["Order status", "Inventory check", "Supplier contact"]
        
        return ChatResponse(
            response=ai_response,
            suggestions=suggestions[:3],  # Limit to 3 suggestions
            context=context if context else None,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}")
        # Fallback response
        return ChatResponse(
            response=f"I encountered an issue processing your request: {str(e)}. Please try again.",
            suggestions=["Try rephrasing", "Check system status", "Contact support"],
            session_id=request.session_id
        )

@router.post("/chat/simple")
async def simple_chat(request: ChatRequest):
    """
    Simple chat endpoint without database dependency for testing
    """
    try:
        response = LlamaService.query(request.message, max_tokens=150)
        return {
            "response": response,
            "status": "success",
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Simple chat error: {str(e)}")
        return {
            "response": f"Error: {str(e)}",
            "status": "error",
            "session_id": request.session_id
        }

@router.get("/chat/health")
async def chat_health():
    """
    Health check for chat services
    """
    try:
        # Test AI service
        test_response = LlamaService.query("Hello", max_tokens=10)
        return {
            "status": "healthy",
            "ai_service": "connected",
            "test_response": test_response[:50] + "..." if len(test_response) > 50 else test_response
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Chat service unhealthy: {str(e)}"
        )