from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.services.cosmos_service import get_cosmos_service
from app.models.transaction import Transaction
import logging

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
    context += "Sample Data:\n"
    for i, row in enumerate(csv_data.data[:sample_rows], 1):
        context += f"Row {i}:\n"
        for header in csv_data.headers:
            context += f"  {header}: {row.get(header, 'N/A')}\n"
        context += "\n"
    if csv_data.row_count > sample_rows:
        context += f"... and {csv_data.row_count - sample_rows} more rows\n"
    return context

def _create_error_response(error: str, session_id: Optional[str]) -> ChatResponse:
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
    Main chat endpoint with CSV upload and fallback to Cosmos or SQL DB.
    """
    logger.info(f"Received chat message: {request.message!r}")
    context: str = ""
    try:
        # Priority 1: CSV path
        if request.csv_data and request.csv_data.row_count > 0:
            logger.info(f"Processing CSV: {request.csv_data.filename} ({request.csv_data.row_count} rows)")
            context = _format_csv_for_ai(request.csv_data)
        else:
            # Priority 2: Try Cosmos
            try:
                container = get_cosmos_service()
                sql = f"""
                SELECT * FROM c
                WHERE CONTAINS(LOWER(c.item_desc), "{request.message.lower()}")
                   OR CONTAINS(LOWER(c.vendor),      "{request.message.lower()}")
                   OR CONTAINS(LOWER(c.manufacturer),"{request.message.lower()}")
                """
                items = list(container.query_items(sql, enable_cross_partition_query=True))
                if items:
                    lines = [
                        f"- {i.get('vendor','N/A')} | {i.get('item_desc','N/A')} | {i.get('load_date','N/A')} | ${i.get('unit_cost','N/A')}"
                        for i in items[:5]
                    ]
                    context = "Recent Cosmos DB items:\n" + "\n".join(lines)
                else:
                    raise ValueError("No Cosmos matches")
            except Exception as cosmos_err:
                logger.warning(f"Cosmos error or no data: {cosmos_err}")
                # SQL fallback with its own guard
                try:
                    relevant = Transaction.search_relevant(db, request.message, limit=5)
                    if relevant:
                        context = (
                            "Recent transaction data from database:\n" +
                            "\n".join(
                                f"- {tx.Vendor} ({tx.FacilityType}, {tx.Region})" for tx in relevant
                            )
                        )
                except Exception as sql_err:
                    logger.warning(f"SQL fallback error: {sql_err}")
                    # both failed, context stays empty
        # Build AI prompt
        system_prompt = (
            "You are Earl, an AI assistant specializing in supply chain management and procurement data analysis.\n"
            "Reference specific data from context when possible. Be friendly yet professional."
        )
        prompt = f"{system_prompt}\n\nContext:\n{context}\n\nUser Question: {request.message}"
        ai_response = LlamaService.query(prompt, max_tokens=400)
        raw_sugs = _generate_suggestions(request.message.lower(), has_csv=bool(request.csv_data))
        suggestions = raw_sugs or []
        return ChatResponse(
            response=ai_response,
            suggestions=suggestions[:3],
            context=context or None,
            session_id=request.session_id
        )
    except Exception as exc:
        logger.error(f"Chat endpoint error: {exc}", exc_info=True)
        return _create_error_response(str(exc), request.session_id)
