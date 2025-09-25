# app/api/routes/chat.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from app.services.text_to_sql_service import get_text_to_sql_service

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    csv_data: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    response: str
    suggestions: List[str]
    context: Optional[str] = None
    data_summary: Optional[Dict[str, Any]] = None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    """
    Enhanced chat endpoint for healthcare supply chain managers
    """
    try:
        logger.info(f"Processing supply chain question: {request.message}")
        
        # Get text-to-SQL service
        text_to_sql = get_text_to_sql_service()
        
        # Analyze the supply chain query
        analysis = text_to_sql.analyze_supply_chain_query(request.message)
        
        return ChatResponse(
            response=analysis["insights"],
            suggestions=analysis["recommendations"],
            context=f"Found {analysis.get('result_count', 0)} matching records" if analysis.get('success') else None,
            data_summary=analysis.get("data_summary")
        )
        
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        return ChatResponse(
            response="I'm having trouble analyzing your supply chain data right now. Please try rephrasing your question.",
            suggestions=[
                "Ask about specific vendors or suppliers",
                "Inquire about spending by department",
                "Request cost analysis for specific items"
            ],
            context="Error occurred during analysis"
        )