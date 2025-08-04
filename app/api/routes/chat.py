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
from app.services.chat_context_service import get_chat_context_service
from app.core.config import settings
import logging
from uuid import uuid4
from datetime import datetime
import re

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
    """Format search results for LLM context - ENHANCED to handle count queries"""
    if not results:
        return "No matching records found."
    
    # Special handling for count/summary queries
    if len(results) == 1 and results[0].get('source') == 'sql_count':
        result = results[0]
        summary_data = result.get('summary_data', {})
        
        return (
            f"Database Summary:\n"
            f"- Total Records: {summary_data.get('total_records', 0):,}\n"
            f"- Unique Batches: {summary_data.get('unique_batches', 0):,}\n"
            f"- Date Range: {summary_data.get('earliest_date', 'Unknown')} to {summary_data.get('latest_date', 'Unknown')}\n"
            f"- Total Spending: ${summary_data.get('total_spend', 0):,.2f}"
        )
    
    # FIXED: Deduplicate results by TransactionID before formatting
    unique_results = {}
    for res in results:
        transaction_id = res.get('TransactionID', res.get('transaction_id'))
        if transaction_id and transaction_id not in unique_results:
            unique_results[transaction_id] = res
        elif not transaction_id:
            # If no transaction ID, use a hash of the content to deduplicate
            content_hash = hash(str(res.get('ItemDesc', '')) + str(res.get('Vendor', '')))
            if content_hash not in unique_results:
                unique_results[content_hash] = res
    
    deduped_results = list(unique_results.values())
    
    formatted_results = []
    for i, res in enumerate(deduped_results[:10], 1):  # Show up to 10 unique results
        # Build comprehensive result string
        result_parts = []
        
        # Core item info
        item_desc = res.get('ItemDesc', res.get('item_desc', 'Unknown Item'))
        result_parts.append(f"Item: {item_desc}")
        
        # Vendor info
        vendor = res.get('Vendor', res.get('vendor', 'Unknown Vendor'))
        result_parts.append(f"Vendor: {vendor}")
        
        # Manufacturer info - CRITICAL for manufacturer queries
        manufacturer = res.get('Manufacturer', res.get('manufacturer', ''))
        if manufacturer and manufacturer != 'Unknown':
            result_parts.append(f"Manufacturer: {manufacturer}")
        
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
        
        # Transaction ID for tracking
        transaction_id = res.get('TransactionID', res.get('transaction_id', ''))
        if transaction_id:
            result_parts.append(f"TxnID: {transaction_id}")
        
        # Join all parts
        formatted_results.append(f"{i}. {' | '.join(result_parts)}")
    
    # Add summary information about the results
    total_unique = len(deduped_results)
    summary_line = f"Found {total_unique} unique transactions"
    if total_unique != len(results):
        summary_line += f" (deduplicated from {len(results)} search results)"
    
    return f"{summary_line}\n\nRelevant Data Found:\n" + "\n".join(formatted_results)

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
    """Get hybrid search results with improved deduplication for manufacturer queries"""
    try:
        logger.info(f"Getting search results for query: '{query}'")
        
        # ADDED: Check if query is asking for record count
        if _is_count_query(query):
            return await _get_transaction_count()
        
        # ADDED: Check if query is a specific transaction ID
        if _is_transaction_id_query(query):
            return await _get_transaction_by_id(query)
        
        # ADDED: Special handling for manufacturer queries
        if _is_manufacturer_query(query):
            return await _get_manufacturer_transactions(query)
        
        # For region queries, use broader search terms
        if 'region' in query.lower():
            search_terms = ['region', 'facility', 'location', 'area']
            all_results = []
            
            for term in search_terms:
                vector_results = query_similar_embeddings(term, top_k=15, min_score=0.2)
                all_results.extend(vector_results)
        else:
            # Regular search
            vector_results = query_similar_embeddings(query, top_k=20, min_score=0.3)
            all_results = vector_results
        
        # Get AI Search full-text results
        ai_search = get_ai_search_service()
        ai_results = ai_search.search(query, top=20)
        
        # ADDED: Cross-verify critical results with SQL database
        if ai_results:
            ai_results = await _verify_results_with_sql(ai_results)
        
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
                    "Manufacturer": metadata.get("Manufacturer", metadata.get("manufacturer", "")),  # CRITICAL
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
        
        logger.info(f"Combined search returned {len(combined)} unique results")
        
        return combined
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return []

def _is_count_query(query: str) -> bool:
    """Check if query is asking for record count"""
    count_patterns = [
        r'how many.*record',
        r'how many.*transaction',
        r'total.*record',
        r'total.*transaction',
        r'count.*record',
        r'count.*transaction',
        r'number.*record',
        r'number.*transaction'
    ]
    
    query_lower = query.lower()
    for pattern in count_patterns:
        if re.search(pattern, query_lower):
            return True
    return False

def _is_transaction_id_query(query: str) -> bool:
    """Check if query contains a specific transaction ID"""
    # Look for numeric transaction IDs
    transaction_patterns = [
        r'\b\d{10,}\b',  # 10+ digit numbers
        r'transaction[:\s]+(\d+)',  # "transaction: 123456"
        r'id[:\s]+(\d+)',  # "id: 123456"
    ]
    
    for pattern in transaction_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return True
    return False

async def _get_transaction_count() -> List[Dict]:
    """Get transaction count directly from SQL database"""
    try:
        logger.info("Getting transaction count from SQL database")
        
        sql_service = get_sql_service()
        count_query = """
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT batch_id) as unique_batches,
                MIN(LoadDate) as earliest_date,
                MAX(LoadDate) as latest_date,
                SUM(TotalSpend) as total_spend
            FROM supply_records
        """
        
        results = sql_service.query_items(count_query)
        
        if not results:
            logger.warning("No count results returned from SQL database")
            return []
        
        count_data = results[0]
        
        # Format as a search result for consistent processing
        formatted_result = {
            "TransactionID": "COUNT_SUMMARY",
            "ItemDesc": f"Database contains {count_data.get('total_records', 0):,} transaction records",
            "Vendor": "System Summary",
            "Region": "All Regions",
            "FacilityType": "All Facilities",
            "Department": "All Departments",
            "Category": "Database Statistics",
            "TotalSpend": float(count_data.get('total_spend', 0)),
            "PricePaid": 0.0,
            "Quantity": int(count_data.get('total_records', 0)),
            "Month": 0,
            "Year": 0,
            "LoadDate": str(count_data.get('latest_date', '')),
            "Manufacturer": "Database",
            "similarity": 1.0,
            "source": "sql_count",
            "verified": True,
            "summary_data": {
                "total_records": count_data.get('total_records', 0),
                "unique_batches": count_data.get('unique_batches', 0),
                "earliest_date": str(count_data.get('earliest_date', '')),
                "latest_date": str(count_data.get('latest_date', '')),
                "total_spend": float(count_data.get('total_spend', 0))
            }
        }
        
        logger.info(f"Found {count_data.get('total_records', 0)} total records in database")
        return [formatted_result]
        
    except Exception as e:
        logger.error(f"SQL count query failed: {e}")
        return []

async def _get_transaction_by_id(query: str) -> List[Dict]:
    """Get transaction directly from SQL database for accuracy"""
    try:
        import re
        
        # Extract transaction ID from query
        transaction_id = None
        patterns = [r'\b(\d{10,})\b', r'transaction[:\s]+(\d+)', r'id[:\s]+(\d+)']
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                transaction_id = match.group(1)
                break
        
        if not transaction_id:
            return []
        
        logger.info(f"Looking up transaction ID: {transaction_id}")
        
        # Query SQL database directly
        sql_service = get_sql_service()
        sql_query = """
            SELECT TransactionID, FacilityID, FacilityType, Region, BedSize,
                   Month, Year, LoadDate, Vendor, VendorID, Manufacturer, 
                   ManufacturerID, ManufacturercatalogNum, ItemDesc, Quantity,
                   PricePaid, TotalSpend, Department, Category, batch_id
            FROM supply_records 
            WHERE TransactionID = ?
        """
        
        results = sql_service.query_items(sql_query, [{"name": "?", "value": transaction_id}])
        
        if not results:
            logger.warning(f"Transaction {transaction_id} not found in SQL database")
            return []
        
        # Convert SQL result to search result format
        formatted_results = []
        for result in results:
            formatted_result = {
                "TransactionID": str(result.get("TransactionID", "")),
                "ItemDesc": str(result.get("ItemDesc", "")),
                "Vendor": str(result.get("Vendor", "")),
                "Region": str(result.get("Region", "")),
                "FacilityType": str(result.get("FacilityType", "")),
                "Department": str(result.get("Department", "")),
                "Category": str(result.get("Category", "")),
                "TotalSpend": float(result.get("TotalSpend", 0)),
                "PricePaid": float(result.get("PricePaid", 0)),
                "Quantity": int(result.get("Quantity", 0)),
                "Month": result.get("Month"),
                "Year": result.get("Year"),
                "LoadDate": str(result.get("LoadDate", "")),
                "Manufacturer": str(result.get("Manufacturer", "")),
                "similarity": 1.0,  # Exact match
                "source": "sql_direct",
                "verified": True
            }
            formatted_results.append(formatted_result)
        
        logger.info(f"Found {len(formatted_results)} SQL records for transaction {transaction_id}")
        return formatted_results
        
    except Exception as e:
        logger.error(f"SQL transaction lookup failed: {e}")
        return []

async def _verify_results_with_sql(ai_results: List[Dict]) -> List[Dict]:
    """Cross-verify AI Search results with SQL database for accuracy"""
    try:
        if not ai_results:
            return ai_results
        
        sql_service = get_sql_service()
        verified_results = []
        
        for result in ai_results:
            transaction_id = result.get("TransactionID")
            if not transaction_id:
                # If no transaction ID, include as-is
                verified_results.append(result)
                continue
            
            # Check SQL for this transaction
            sql_query = """
                SELECT TransactionID, ItemDesc, Vendor, Region, FacilityType, 
                       TotalSpend, Quantity, Department, Category
                FROM supply_records 
                WHERE TransactionID = ?
            """
            
            sql_records = sql_service.query_items(sql_query, [{"name": "?", "value": transaction_id}])
            
            if sql_records:
                # Use SQL data as the authoritative source
                sql_record = sql_records[0]
                verified_result = result.copy()
                
                # Update with correct SQL data
                verified_result.update({
                    "ItemDesc": str(sql_record.get("ItemDesc", "")),
                    "Vendor": str(sql_record.get("Vendor", "")),
                    "Region": str(sql_record.get("Region", "")),
                    "FacilityType": str(sql_record.get("FacilityType", "")),
                    "TotalSpend": float(sql_record.get("TotalSpend", 0)),
                    "Quantity": int(sql_record.get("Quantity", 0)),
                    "Department": str(sql_record.get("Department", "")),
                    "Category": str(sql_record.get("Category", "")),
                    "source": "sql_verified",
                    "verified": True
                })
                
                verified_results.append(verified_result)
            else:
                # Keep AI Search result but mark as unverified
                result["verified"] = False
                result["source"] = "ai_search_only"
                verified_results.append(result)
        
        logger.info(f"Verified {len([r for r in verified_results if r.get('verified')])} out of {len(ai_results)} results with SQL")
        return verified_results
        
    except Exception as e:
        logger.error(f"Result verification failed: {e}")
        # Return original results if verification fails
        for result in ai_results:
            result["verified"] = False
        return ai_results

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Handle chat queries with data analysis and conversation context",
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
    # 3. Get Conversation Context (ENHANCED)
    # =================================================================
    conversation_context = {}
    current_chat_id = None
    
    if request.session_id:
        try:
            chat_context_service = get_chat_context_service()
            
            # Create a temporary chat_id for context search if not provided
            # In production, you should pass the actual chat_id from the frontend
            current_chat_id = f"chat-{request.session_id}"
            
            conversation_context = await chat_context_service.get_conversation_context(
                current_message=request.message,
                chat_id=current_chat_id,
                session_id=request.session_id,
                context_limit=5
            )
        except Exception as context_error:
            logger.warning(f"Failed to get conversation context: {context_error}")
            conversation_context = {"has_context": False}

    # =================================================================
    # 4. Data-Aware Processing with Context
    # =================================================================
    context_parts = []
    sources = []
    
    try:
        # 4A. Add conversation context if available (ENHANCED)
        if conversation_context.get("has_context"):
            context_summary = conversation_context.get("context_summary", "")
            recent_history = conversation_context.get("recent_history", [])
            similar_conversations = conversation_context.get("similar_conversations", [])
            
            if context_summary:
                context_parts.append(f"Conversation Context: {context_summary}")
                
            # Add specific recent context
            if recent_history:
                recent_context = []
                for msg in recent_history[-3:]:  # Last 3 messages
                    if msg.get("message_type") == "user":
                        recent_context.append(f"Previous question: {msg.get('content', '')}")
                    elif msg.get("message_type") == "assistant":
                        recent_context.append(f"Previous answer: {msg.get('content', '')[:100]}...")
                
                if recent_context:
                    context_parts.append("Recent conversation:\n" + "\n".join(recent_context))
            
            # Add similar conversations context
            if similar_conversations:
                similar_context = []
                for conv in similar_conversations[:2]:  # Top 2 similar
                    similar_context.append(f"Related topic ({conv.get('similarity', 0):.2f}): {conv.get('content', '')[:100]}...")
                
                if similar_context:
                    context_parts.append("Related discussions:\n" + "\n".join(similar_context))
                
            sources.append({
                "source": "conversation_history", 
                "summary": context_summary,
                "recent_messages": len(recent_history),
                "similar_conversations": len(similar_conversations)
            })

        # 4B. Get search results (if available)
        search_results = await _get_search_results(request.message)
        if search_results:
            context_parts.append(_format_search_results(search_results))
            sources.extend([{"source": r.get("source", "database"), **r} for r in search_results])

        # 4C. Process CSV data (if provided)
        if request.csv_data and request.csv_data.row_count > 0:
            csv_context = _analyze_csv_data(request.csv_data)
            context_parts.append(csv_context)
            sources.append({
                "source": "uploaded_csv",
                "filename": request.csv_data.filename,
                "rows": request.csv_data.row_count
            })

        # =================================================================
        # 5. Enhanced Response Generation with Context
        # =================================================================
        if not context_parts:  # Data exists but no matches found
            response = ChatResponse(
                response=_generate_no_matches_response(request.message),
                suggestions=_generate_suggestions(request.message),
                session_id=request.session_id,
                sources=None
            )
        else:
            # Build enhanced LLM prompt with conversation context
            system_prompt = (
                "You are Earl, an AI assistant specializing in supply chain management and procurement data analysis.\n\n"
                "You have access to:\n"
                "1. Current transaction and supply chain data\n"
                "2. Previous conversation history for context\n"
                "3. Similar past discussions for reference\n"
                "4. Uploaded CSV data when provided\n\n"
                "Use conversation history to:\n"
                "- Reference previous questions and answers naturally\n"
                "- Build upon prior analysis and insights\n"
                "- Clarify follow-up questions based on context\n"
                "- Maintain conversation continuity and flow\n"
                "- Avoid repeating information already discussed\n\n"
                "Always provide actionable insights and maintain a professional yet friendly tone.\n"
                "Do not use formatting like bold, italics, or markdown symbols.\n"
                "Keep responses concise but comprehensive (4-6 sentences).\n"
            )
            
            context_joined = '\n\n'.join(context_parts)
            prompt = f"{system_prompt}\n\nContext:\n{context_joined}\n\nCurrent Question: {request.message}\n\nResponse:"

            ai_response = LlamaService.query(prompt, max_tokens=settings.DEFAULT_MAX_TOKENS)

            response = ChatResponse(
                response=ai_response,
                suggestions=_generate_context_aware_suggestions(request.message, conversation_context),
                context=context_joined if len(context_parts) > 1 else None,
                session_id=request.session_id,
                sources=sources if sources else None
            )

        # =================================================================
        # 6. Index the current conversation for future context (IMPROVED)
        # =================================================================
        if request.session_id and current_chat_id:
            try:
                chat_context_service = get_chat_context_service()
                
                # Index user message
                user_index_success = await chat_context_service.index_chat_message({
                    "message_id": str(uuid4()),
                    "chat_id": current_chat_id,
                    "session_id": request.session_id,
                    "message_type": "user",
                    "content": request.message,
                    "timestamp": datetime.utcnow().isoformat(),
                    "context": "",
                    "suggestions": [],
                    "sources": []
                })
                
                # Index assistant response
                assistant_index_success = await chat_context_service.index_chat_message({
                    "message_id": str(uuid4()),
                    "chat_id": current_chat_id,
                    "session_id": request.session_id,
                    "message_type": "assistant",
                    "content": response.response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "context": response.context or "",
                    "suggestions": response.suggestions,
                    "sources": response.sources or []
                })
                
                if user_index_success and assistant_index_success:
                    logger.info("Successfully indexed conversation messages for future context")
                else:
                    logger.warning("Partial success in indexing conversation messages")
                
            except Exception as index_error:
                logger.warning(f"Failed to index conversation for future context: {index_error}")
                # Don't fail the response if indexing fails - this is non-critical

        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Chat error: {str(exc)}", exc_info=True)
        return ChatResponse(
            response="I'm having trouble processing your request. Please try again later.",
            suggestions=["Try rephrasing your question", "Check your data format"],
            session_id=request.session_id
        )

def _generate_context_aware_suggestions(message: str, conversation_context: Dict[str, Any]) -> List[str]:
    """Generate suggestions based on current message and conversation context"""
    suggestions = []
    
    # Base suggestions from current message
    base_suggestions = _generate_suggestions(message)
    
    # Add context-aware suggestions if we have conversation history
    if conversation_context.get("has_context"):
        recent_history = conversation_context.get("recent_history", [])
        
        # Look for patterns in recent questions
        recent_topics = set()
        for msg in recent_history:
            if msg.get("message_type") == "user":
                content = msg.get("content", "").lower()
                if "vendor" in content:
                    recent_topics.add("vendor")
                elif "spend" in content or "cost" in content:
                    recent_topics.add("spending")
                elif "department" in content:
                    recent_topics.add("department")
        
        # Generate contextual suggestions
        if "vendor" in recent_topics:
            suggestions.extend(["Compare this vendor to others", "Show vendor trends over time"])
        if "spending" in recent_topics:
            suggestions.extend(["Break down spending by category", "Show cost-saving opportunities"])
        if "department" in recent_topics:
            suggestions.extend(["Compare department efficiency", "Show department budget utilization"])
    
    # Combine and deduplicate
    all_suggestions = base_suggestions + suggestions
    unique_suggestions = []
    seen = set()
    for s in all_suggestions:
        if s not in seen:
            unique_suggestions.append(s)
            seen.add(s)
    
    return unique_suggestions[:4]  # Limit to 4 suggestions

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


