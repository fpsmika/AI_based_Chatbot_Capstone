from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.models.transaction import Transaction
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class CSVData(BaseModel):
    filename: str = Field(..., description="Name of the uploaded file")
    headers: List[str] = Field(..., description="CSV column headers")
    data: List[Dict[str, Any]] = Field(..., description="CSV row data")
    row_count: int = Field(..., description="Total number of rows")

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Session identifier")
    csv_data: Optional[CSVData] = Field(None, description="Uploaded CSV data")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI generated response")
    suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")
    context: Optional[str] = Field(None, description="Contextual information used")
    session_id: Optional[str] = Field(None, description="Session identifier")

def _generate_suggestions(message: str, has_csv: bool = False) -> List[str]:
    """Generate contextual suggestions based on message content"""
    if has_csv:
        csv_suggestions = {
            'total': ["What's the total value?", "Show me a summary", "Which vendor has the highest total?"],
            'vendor': ["Compare vendors", "Top vendors by volume", "Vendor performance analysis"],
            'department': ["Department spending breakdown", "Which department spends most?", "Department comparison"],
            'date': ["Show monthly trends", "Spending over time", "Seasonal patterns"],
            'default': ["Summarize this data", "Show top 5 items", "Calculate totals by category"]
        }
        
        for keyword, suggestions in csv_suggestions.items():
            if keyword in message.lower():
                return suggestions
        return csv_suggestions['default']
    
    # Original suggestions for database queries
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
        if keyword in message.lower():
            return suggestions
    return suggestions_map['default']

def _format_csv_for_ai(csv_data: CSVData, sample_rows: int = 5) -> str:
    """Format CSV data for AI context with sample rows"""
    context = f"CSV File: {csv_data.filename}\n"
    context += f"Total Rows: {csv_data.row_count}\n"
    context += f"Columns: {', '.join(csv_data.headers)}\n\n"
    
    # Add sample data
    context += "Sample Data:\n"
    sample_data = csv_data.data[:sample_rows]
    
    for i, row in enumerate(sample_data, 1):
        context += f"Row {i}:\n"
        for header in csv_data.headers:
            value = row.get(header, 'N/A')
            context += f"  {header}: {value}\n"
        context += "\n"
    
    if csv_data.row_count > sample_rows:
        context += f"... and {csv_data.row_count - sample_rows} more rows\n"
    
    return context

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
    Main chat endpoint with CSV upload support and database context integration
    """
    logger.info(f"Received chat message: {request.message}")
    logger.info(f"CSV data included: {request.csv_data is not None}")
    
    context = ""
    
    try:
        # Priority 1: Use uploaded CSV data if available
        if request.csv_data:
            logger.info(f"Processing CSV data: {request.csv_data.filename} with {request.csv_data.row_count} rows")
            context = _format_csv_for_ai(request.csv_data)
            
        # Priority 2: Fall back to database transactions if no CSV
        else:
            try:
                relevant_transactions = Transaction.search_relevant(
                    db, request.message, limit=5
                )
                if relevant_transactions:
                    context = "Recent transaction data from database:\n" + "\n".join(
                        f"- {tx.Vendor} ({tx.FacilityType}, {tx.Region})" 
                        for tx in relevant_transactions
                    )
            except Exception as db_error:
                logger.warning(f"Database search failed: {str(db_error)}")
        
        # Create enhanced prompt with context
        system_prompt = """You are Earl, an AI assistant specializing in supply chain management and procurement data analysis. 
        You help users analyze transaction data, vendor information, and supply chain queries.
        
        When analyzing CSV data, provide specific insights about:
        - Key metrics and totals
        - Vendor/supplier analysis
        - Department or category breakdowns
        - Trends and patterns
        - Cost analysis
        
        Always reference specific data points from the provided context when possible.
        Be friendly but professional and provide actionable insights."""
        
        enhanced_prompt = f"{system_prompt}\n\n"
        if context:
            if request.csv_data:
                enhanced_prompt += f"Uploaded CSV Data to Analyze:\n{context}\n\n"
            else:
                enhanced_prompt += f"Database Context:\n{context}\n\n"
        enhanced_prompt += f"User Question: {request.message}"
        
        # Get AI response from LlamaService
        logger.info("Calling LlamaService...")
        ai_response = LlamaService.query(enhanced_prompt, max_tokens=400)
        logger.info(f"AI Response received: {ai_response[:100]}...")
        
        # Generate contextual suggestions
        suggestions = _generate_suggestions(request.message.lower(), has_csv=(request.csv_data is not None))
        
        return ChatResponse(
            response=ai_response,
            suggestions=suggestions[:3],
            context=context if context else None,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {str(e)}", exc_info=True)
        return _create_error_response(str(e), request.session_id)