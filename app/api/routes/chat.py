# app/api/routes/chat.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
from app.services.embedding_service import query_similar_embeddings  # Updated import
from app.services.ai_search_service import get_ai_search_service  # Updated import
from app.core.config import settings
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
    sources: Optional[List[Dict[str, Any]]] = Field(None, description="Data sources used")

SUGGESTIONS_MAP = {
    'total': ["What's the total value?", "Show me a summary", "Which vendor has the highest total?"],
    'vendor': ["Compare vendors", "Top vendors by volume", "Vendor performance analysis"],
    'department': ["Department spending breakdown", "Which department spends most?", "Department comparison"],
    'date': ["Show monthly trends", "Spending over time", "Seasonal patterns"],
    'transaction': ["View recent transactions", "Transaction by date range"],
    'default': ["Summarize this data", "Show top 5 items", "Calculate totals by category"]
}

def _generate_suggestions(message: str) -> List[str]:
    """Generate contextual follow-up suggestions"""
    message_lower = message.lower()
    for keyword, suggestions in SUGGESTIONS_MAP.items():
        if keyword in message_lower:
            return suggestions
    return SUGGESTIONS_MAP['default']

def _format_search_results(results: List[Dict]) -> str:
    """Format search results for LLM context - FIXED to include all relevant fields"""
    if not results:
        return "No matching records found."
    
    formatted_results = []
    for i, res in enumerate(results[:10], 1):  # Show more results
        # Build comprehensive result string
        result_parts = []
        
        # Core item info
        item_desc = res.get('ItemDesc', res.get('item_desc', 'Unknown Item'))
        result_parts.append(f"Item: {item_desc}")
        
        # Vendor info
        vendor = res.get('Vendor', res.get('vendor', 'Unknown Vendor'))
        result_parts.append(f"Vendor: {vendor}")
        
        # CRITICAL FIX: Include Region information
        region = res.get('Region', res.get('region', ''))
        if region and region != 'Unknown':
            result_parts.append(f"Region: {region}")
        
        # Facility and location info
        facility_type = res.get('FacilityType', res.get('facility_type', ''))
        if facility_type and facility_type != 'Unknown':
            result_parts.append(f"Facility: {facility_type}")
        
        # Department info
        department = res.get('Department', res.get('department', ''))
        if department and department != 'Unknown':
            result_parts.append(f"Department: {department}")
        
        # Financial info
        total_spend = res.get('TotalSpend', res.get('total_spend', 0))
        if total_spend:
            result_parts.append(f"Spend: ${float(total_spend):,.2f}")
        
        # Quantity if available
        quantity = res.get('Quantity', res.get('quantity', ''))
        if quantity:
            result_parts.append(f"Qty: {quantity}")
        
        # Join all parts
        formatted_results.append(f"{i}. {' | '.join(result_parts)}")
    
    return "Relevant Data Found:\n" + "\n".join(formatted_results)

def _analyze_csv_data(csv_data: CSVData) -> str:
    """Analyze uploaded CSV data for LLM context"""
    analysis = []
    analysis.append(f"File: {csv_data.filename}")
    analysis.append(f"Rows: {csv_data.row_count}")
    analysis.append(f"Columns: {', '.join(csv_data.headers)}")
    
    # Calculate total spend if available
    spend_keys = [k for k in csv_data.headers if 'spend' in k.lower()]
    if spend_keys:
        total = sum(float(row.get(spend_keys[0], 0)) for row in csv_data.data)
        analysis.append(f"Total spend: ${total:,.2f}")
    
    # Get unique vendors if available
    vendor_keys = [k for k in csv_data.headers if 'vendor' in k.lower()]
    if vendor_keys:
        vendors = list(set(row.get(vendor_keys[0], '') for row in csv_data.data))
        analysis.append(f"Vendors: {', '.join(v for v in vendors if v)}")
    
    return "Uploaded Data Analysis:\n" + "\n".join(analysis)

async def _get_search_results(query: str) -> List[Dict]:
    """Get hybrid search results - ENHANCED to preserve all metadata"""
    try:
        logger.info(f"Getting search results for query: '{query}'")
        
        # For region queries, use broader search terms
        if 'region' in query.lower():
            search_terms = ['region', 'facility', 'location', 'area']
            all_results = []
            
            for term in search_terms:
                vector_results = query_similar_embeddings(term, top_k=15, min_score=0.2)
                all_results.extend(vector_results)
        else:
            # Regular search
            vector_results = query_similar_embeddings(query, top_k=10, min_score=0.3)
            all_results = vector_results
        
        # Get AI Search full-text results
        ai_search = get_ai_search_service()
        ai_results = ai_search.search(query, top=10)
        
        # Combine and deduplicate while preserving ALL metadata
        combined = []
        seen_ids = set()
        
        # Process vector results - PRESERVE ALL METADATA
        for r in all_results:
            metadata = r.get("metadata", {})
            doc_id = metadata.get("TransactionID", metadata.get("transaction_id"))
            
            if doc_id and doc_id not in seen_ids:
                # Create comprehensive result with ALL fields
                result_data = {
                    # Ensure all possible field variations are captured
                    "TransactionID": metadata.get("TransactionID", metadata.get("transaction_id", "")),
                    "ItemDesc": metadata.get("ItemDesc", metadata.get("item_desc", "")),
                    "Vendor": metadata.get("Vendor", metadata.get("vendor", "")),
                    "Region": metadata.get("Region", metadata.get("region", "")),  # CRITICAL
                    "FacilityType": metadata.get("FacilityType", metadata.get("facility_type", "")),
                    "Department": metadata.get("Department", metadata.get("department", "")),
                    "Category": metadata.get("Category", metadata.get("category", "")),
                    "TotalSpend": metadata.get("TotalSpend", metadata.get("total_spend", 0)),
                    "Quantity": metadata.get("Quantity", metadata.get("quantity", "")),
                    "Month": metadata.get("Month", metadata.get("month", "")),
                    "Year": metadata.get("Year", metadata.get("year", "")),
                    "similarity": r.get("similarity", 0),
                    "source": "vector",
                    # Include ALL original metadata
                    **metadata
                }
                combined.append(result_data)
                seen_ids.add(doc_id)
        
        # Process AI Search results
        for r in ai_results:
            doc_id = r.get("TransactionID")
            if doc_id and doc_id not in seen_ids:
                result_data = r.copy()
                result_data["source"] = "ai_search"
                result_data["similarity"] = 0.7
                combined.append(result_data)
                seen_ids.add(doc_id)
        
        logger.info(f"Combined search returned {len(combined)} results")
        
        # For region queries, also log what regions we found
        if 'region' in query.lower():
            found_regions = set()
            for r in combined:
                region = r.get('Region', r.get('region'))
                if region and region != 'Unknown':
                    found_regions.add(region)
            logger.info(f"Regions found in search results: {list(found_regions)}")
        
        return combined
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return []

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Handle chat queries with data analysis",
    tags=["chat"]
)
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db)
) -> ChatResponse:
    logger.info(f"Chat request from session {request.session_id}")
    
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # =================================================================
    # 1. System State Detection
    # =================================================================
    ai_search = get_ai_search_service()
    has_any_data = (
        ai_search.get_document_count() > 0 
        or (request.csv_data and request.csv_data.row_count > 0)
    )

    # =================================================================
    # 2. Empty State Handling
    # =================================================================
    if not has_any_data:
        return await _handle_empty_state(request)

    # =================================================================
    # 3. Data-Aware Processing
    # =================================================================
    context_parts = []
    sources = []
    
    try:
        # 3A. Get search results (if available)
        search_results = await _get_search_results(request.message)
        if search_results:
            context_parts.append(_format_search_results(search_results))
            sources.extend([{"source": r.get("source", "database"), **r} for r in search_results])

        # 3B. Process CSV data (if provided)
        if request.csv_data and request.csv_data.row_count > 0:
            csv_context = _analyze_csv_data(request.csv_data)
            context_parts.append(csv_context)
            sources.append({
                "source": "uploaded_csv",
                "filename": request.csv_data.filename,
                "rows": request.csv_data.row_count
            })

        # =================================================================
        # 4. Response Generation
        # =================================================================
        if not context_parts:  # Data exists but no matches found
            return ChatResponse(
                response=_generate_no_matches_response(request.message),
                suggestions=_generate_suggestions(request.message),
                session_id=request.session_id,
                sources=None
            )

        # Build the LLM prompt for data-aware responses
        system_prompt = (
    "You are Earl, an AI assistant specializing in supply chain management and procurement data analysis.\n\n"
    "Your role is to help users analyze transaction data, vendor performance, and supply chain queries, especially from uploaded CSV files.\n\n"
    "When CSV data is provided, you have access to the entire dataset, including:\n"
    "- Statistical summaries (e.g., totals, averages, min/max values)\n"
    "- Top values per category\n"
    "- Sample records (top and bottom rows)\n"
    "- Column breakdowns and data distributions\n\n"
    "Always reference real data points when possible. Focus on:\n"
    "1. Key Metrics & Totals — costs, units, frequencies\n"
    "2. Vendor Analysis — top vendors by spend, orders, frequency\n"
    "3. Department or Category Breakdowns — usage, spend, volume\n"
    "4. Trend Identification — monthly or quarterly shifts, anomalies\n"
    "5. Cost Analysis — savings opportunities, high-cost items\n"
    "6. Data Quality Observations — missing values, inconsistencies\n\n"
    "Always reference specific data points from the analysis when possible."
    "Respond in a friendly yet professional tone. Your insights should be actionable and easy to understand, "
    "tailored for supply chain managers or procurement officers.\n"
    "Avoid vague or generic analysis — always anchor your insights in the actual data provided."
    "Do not use formatting like bold, italics, or markdown symbols in your response."
    "Each response should be 4 to 5 sentences long, providing meaningful and well-rounded insights."
    "Structure your response in clear paragraphs, each covering one type of insight (e.g., vendor analysis, trends, cost breakdown). "
    "Do not mix multiple insight types in one sentence. Use bullet points or numbered lists where necessary for clarity.\n"
    "If data is incomplete or unclear, mention that explicitly and suggest what additional information would help improve the analysis.\n"
    "Do not repeat the user's question in your response. Focus only on the analysis.\n"
    "You may end with a short friendly suggestion or follow-up."
    "You will remain in this role across all interactions. If the user asks a follow-up question, treat it as a continuation of the previous context unless otherwise specified.\n"
    "If no CSV data has been uploaded or available context is missing, let the user know politely and ask them to upload a file to proceed with the analysis."
    "Do not list or cite your data sources explicitly. Avoid phrases like 'according to the data' or 'based on the uploaded CSV.'"
    "Do not list or cite your data sources explicitly."
)
        
        context_joined = '\n\n'.join(context_parts)
        prompt = f"{system_prompt}\n\nContext:\n{context_joined}\n\nQuestion: {request.message}"

        ai_response = LlamaService.query(prompt, max_tokens=settings.DEFAULT_MAX_TOKENS)

        return ChatResponse(
            response=ai_response,
            suggestions=_generate_suggestions(request.message),
            context=context_joined if len(context_parts) > 1 else None,
            session_id=request.session_id,
            sources=sources if sources else None
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Chat error: {str(exc)}", exc_info=True)
        return ChatResponse(
            response="I'm having trouble processing your request. Please try again later.",
            suggestions=["Try rephrasing your question", "Check your data format"],
            session_id=request.session_id
        )

# =================================================================
# Helper Functions
# =================================================================
async def _handle_empty_state(request: ChatRequest) -> ChatResponse:
    """Generate intelligent responses when no data exists"""
    # Craft a detailed prompt for the LLM
    prompt = f"""
    ROLE: You are Earl, a supply chain AI assistant.
    
    USER QUESTION: "{request.message}"
    
    CURRENT SYSTEM STATE:
    - No data available (SQL database empty, no files uploaded)
    - User may need guidance on data requirements
    
    RESPONSE REQUIREMENTS:
    1. If question is data-specific:
       - Explain what data would be needed
       - Provide example columns/format
    2. If general question:
       - Answer normally
    3. Always include:
       - Clear next steps
       - 3 relevant suggestions
    
    EXAMPLES:
    User: "Show top vendors"
    Response: "To analyze vendors, you'll need a file with Vendor and TotalSpend columns..."
    """
    
    llm_response = LlamaService.query(prompt)
    
    # Standardize suggestions
    suggestions = [
        "How to upload data",
        "Example file format",
        "What analyses are available"
    ]
    
    return ChatResponse(
        response=llm_response,
        suggestions=suggestions,
        session_id=request.session_id,
        sources=None
    )

def _generate_no_matches_response(query: str) -> str:
    """When data exists but doesn't match the query"""
    return (
        f"I couldn't find data matching '{query}'. Try:\n"
        "- Different search terms\n"
        "- Checking your file's column names\n"
        "- Asking about general trends"
    )

def _generate_suggestions(query: str) -> List[str]:
    """Context-aware follow-up questions"""
    query_lower = query.lower()
    
    # Data-specific suggestions
    if any(term in query_lower for term in ["vendor", "supplier"]):
        return [
            "Compare vendor performance",
            "Find alternative vendors",
            "Analyze vendor spend trends"
        ]
    elif any(term in query_lower for term in ["spend", "cost"]):
        return [
            "Show monthly spending",
            "Compare department budgets",
            "Identify cost savings"
        ]
    
    # Default suggestions
    return [
        "Upload a data file",
        "What analyses can you run?",
        "Show sample data format"
    ]


# ... (keep all your existing imports and setup code)

@router.get("/data/{batch_id}", response_model=List[Dict[str, Any]])
async def get_batch_data(
    batch_id: str,
    offset: int = 0,
    limit: int = 100
):
    """Endpoint to fetch batch data for frontend preview"""
    try:
        sql_service = get_sql_service()
        records = sql_service.get_records_by_batch(batch_id, offset, limit)
        return records
    except Exception as e:
        logger.error(f"Failed to fetch batch {batch_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat/health")
async def chat_health():
    """Health check for chat service and its dependencies"""
    try:
        # Test SQL connection
        sql_service = get_sql_service()
        sql_test = sql_service.test_connection()
        
        # Test AI Search connection
        ai_search = get_ai_search_service()
        ai_search_test = ai_search.test_connection()
        
        # Test embedding service
        from app.services.embedding_service import test_embedding_service
        embedding_test = test_embedding_service()
        
        return {
            "status": "healthy",
            "sql_connection": sql_test["status"] == "connected",
            "ai_search_connection": ai_search_test["status"] == "connected",
            "embedding_service": embedding_test,
            "llama_service": "available"  # Assume available if no errors
        }
        
    except Exception as e:
        logger.error(f"Chat health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@router.get("/search/vector-search")
async def vector_search(
    q: str, 
    top_k: int = 10,
    min_score: float = 0.5
):
    """Enhanced vector search with better error handling"""
    try:
        results = query_similar_embeddings(q, top_k, min_score)
        
        if not results:
            logger.warning(f"No vector results found for query: '{q}'")
            # Fall back to full-text search
            ai_search = get_ai_search_service()
            results = ai_search.search(q, top=top_k)
            for r in results:
                r['similarity'] = 0.7  # Add default similarity score
        
        return {
            "results": results,
            "count": len(results),
            "warning": "Used fallback search" if not results else None
        }
    except Exception as e:
        logger.error(f"Vector search failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Vector search failed",
                "message": str(e)
            }
        )


    