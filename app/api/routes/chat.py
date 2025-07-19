from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.models.transaction import Transaction
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Session identifier")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI generated response")
    suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")
    context: Optional[str] = Field(None, description="Contextual information used")
    session_id: Optional[str] = Field(None, description="Session identifier")

def _generate_suggestions(message: str) -> List[str]:
    """Generate contextual suggestions based on message content"""
    suggestions_map = {
        'vendor': ["Show vendor analytics", "Compare vendor performance", "Top vendors by volume"],
        'supplier': ["Supplier performance metrics", "Contract expiration dates", "Supplier contact info"],
        'transaction': ["View recent transactions", "Transaction by date range", "Monthly spending trends"],
        'purchase': ["Purchase order status", "Pending approvals", "Requisition tracking"],
        'hospital': ["Filter by facility type", "Regional analysis", "Facility spending comparison"],
        'clinic': ["Clinic-specific reports", "Departmental spending", "Inventory levels"],
        'cost': ["Cost analysis by category", "Budget variance report", "Price trend analysis"],
        'default': ["Order status lookup", "Inventory insights", "Spending summary"]
    }
    
    for keyword, suggestions in suggestions_map.items():
        if keyword in message:
            return suggestions
    return suggestions_map['default']

def _create_error_response(error: str, session_id: Optional[str]) -> ChatResponse:
    """Create standardized error response"""
    return ChatResponse(
        response="I'm having trouble processing your request right now. Please try again later.",
        suggestions=["Try a simpler question", "Check system status", "Contact support"],
        context=None,
        session_id=session_id
    )

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Main chat endpoint with database context integration
    """
    logger.info(f"Received chat message: {request.message}")
    
    context = ""
    
    try:
        # Get relevant transaction data for context
        try:
            relevant_transactions = Transaction.search_relevant(
                db, request.message, limit=5
            )
            if relevant_transactions:
                context = "Recent transaction data:\n" + "\n".join(
                    f"- {tx.Vendor} ({tx.FacilityType}, {tx.Region})" 
                    for tx in relevant_transactions
                )
        except Exception as db_error:
            logger.warning(f"Database search failed: {str(db_error)}")
            # Context remains empty string
        
        # Create enhanced prompt with context
        system_prompt = """You are Earl, an AI assistant specializing in supply chain management and procurement data analysis. 
        You help users analyze transaction data, vendor information, and supply chain queries.
        Provide clear, concise, and helpful responses. If asked about specific data, reference the context provided.
        Be friendly but professional."""
        
        enhanced_prompt = f"{system_prompt}\n\n"
        if context:
            enhanced_prompt += f"Relevant Data Context:\n{context}\n\n"
        enhanced_prompt += f"User Question: {request.message}"
        
        # Get AI response from LlamaService
        logger.info("Calling LlamaService...")
        ai_response = LlamaService.query(enhanced_prompt, max_tokens=300)
        logger.info(f"AI Response received: {ai_response[:100]}...")
        
        # Generate contextual suggestions
        suggestions = _generate_suggestions(request.message.lower())
        
        return ChatResponse(
            response=ai_response,
            suggestions=suggestions[:3],  # Limit to 3 suggestions
            context=context if context else None,  # Can be None if empty
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}", exc_info=True)
        return _create_error_response(str(e), request.session_id)

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