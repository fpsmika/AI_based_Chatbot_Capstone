
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.utils.db import get_db
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
from app.services.embedding_service import query_similar_embeddings
from app.services.ai_search_service import get_ai_search_service
from app.services.chat_context_service import get_chat_context_service
from app.core.config import settings
import logging
import json
import re
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    session_id: Optional[str] = Field(None, description="Session identifier")

class ChatResponse(BaseModel):
    response: str = Field(..., description="AI generated response")
    suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions")
    session_id: Optional[str] = Field(None, description="Session identifier")
    sql_query: Optional[str] = Field(None, description="Generated SQL query if applicable")
    data_preview: Optional[List[Dict]] = Field(None, description="Preview of query results")

class SQLGenerator:
    """Dynamic SQL generation using LLM"""
    
    @staticmethod
    def get_table_schema() -> str:
        """Return the table schema for the LLM"""
        return """
        Table: supply_records
        Columns:
        - TransactionID (varchar): Unique transaction identifier
        - FacilityID (varchar): Facility identifier
        - FacilityType (varchar): Type of facility
        - Region (varchar): Geographic region
        - BedSize (int): Bed size
        - Month (int): Month number (1-12)
        - Year (int): Year
        - LoadDate (datetime): Transaction date
        - Vendor (varchar): Vendor name
        - VendorID (varchar): Vendor identifier
        - Manufacturer (varchar): Manufacturer name
        - ManufacturerID (varchar): Manufacturer identifier
        - ManufacturercatalogNum (varchar): Catalog number
        - ItemDesc (varchar): Item description
        - Quantity (int): Quantity purchased
        - PricePaid (float): Price paid per unit
        - TotalSpend (float): Total amount spent (Quantity * PricePaid)
        - Department (varchar): Department name
        - Category (varchar): Item category
        - batch_id (varchar): Batch identifier
        """
    
    @staticmethod
    def generate_sql(user_question: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Generate SQL query from natural language question"""
        
        schema = SQLGenerator.get_table_schema()
        
        prompt = f"""You are a SQL expert. Generate a SQL query for Microsoft SQL Server based on the user's question.

DATABASE SCHEMA:
{schema}

IMPORTANT RULES:
1. Use Microsoft SQL Server syntax (use TOP instead of LIMIT)
2. Always include column aliases for aggregations
3. For monetary values, round to 2 decimal places
4. Include ORDER BY clauses for better results
5. Use appropriate JOINs if needed (though this is a single table)
6. Handle NULL values appropriately
7. Return ONLY valid SQL - no explanations or markdown

CONTEXT (if any): {context or 'None'}

USER QUESTION: {user_question}

Generate the SQL query:"""

        try:
            sql_response = LlamaService.query(prompt, max_tokens=500)
            
            # Clean the SQL query
            sql_query = SQLGenerator._clean_sql_query(sql_response)
            
            # Validate basic SQL structure
            if not SQLGenerator._validate_sql(sql_query):
                raise ValueError("Invalid SQL query generated")
            
            # Determine query type
            query_type = SQLGenerator._determine_query_type(sql_query)
            
            return {
                "success": True,
                "sql": sql_query,
                "query_type": query_type,
                "explanation": SQLGenerator._generate_explanation(user_question, query_type)
            }
            
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "fallback": True
            }
    
    @staticmethod
    def _clean_sql_query(sql_response: str) -> str:
        """Clean and extract SQL from LLM response"""
        # Remove markdown code blocks
        sql_response = re.sub(r'```sql\s*', '', sql_response)
        sql_response = re.sub(r'```\s*', '', sql_response)
        
        # Remove any leading/trailing whitespace
        sql_response = sql_response.strip()
        
        # Remove any explanatory text before SELECT
        if 'SELECT' in sql_response.upper():
            select_index = sql_response.upper().find('SELECT')
            sql_response = sql_response[select_index:]
        
        return sql_response
    
    @staticmethod
    def _validate_sql(sql_query: str) -> bool:
        """Basic SQL validation"""
        sql_upper = sql_query.upper()
        
        # Must start with SELECT
        if not sql_upper.startswith('SELECT'):
            return False
        
        # Must have FROM clause
        if 'FROM' not in sql_upper:
            return False
        
        # Check for dangerous operations
        dangerous_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE', 'ALTER', 'EXEC', 'EXECUTE']
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return False
        
        return True
    
    @staticmethod
    def _determine_query_type(sql_query: str) -> str:
        """Determine the type of query for better response formatting"""
        sql_upper = sql_query.upper()
        
        if 'COUNT(*)' in sql_upper:
            return 'count'
        elif 'SUM(' in sql_upper and 'GROUP BY' in sql_upper:
            return 'aggregation'
        elif 'AVG(' in sql_upper or 'MAX(' in sql_upper or 'MIN(' in sql_upper:
            return 'statistics'
        elif 'GROUP BY' in sql_upper:
            return 'grouping'
        elif 'ORDER BY' in sql_upper and 'TOP' in sql_upper:
            return 'ranking'
        else:
            return 'selection'
    
    @staticmethod
    def _generate_explanation(question: str, query_type: str) -> str:
        """Generate a human-readable explanation of what the query does"""
        explanations = {
            'count': "Counting records based on your criteria",
            'aggregation': "Calculating totals and summaries",
            'statistics': "Computing statistical measures",
            'grouping': "Grouping and analyzing data by categories",
            'ranking': "Finding top results",
            'selection': "Retrieving specific records"
        }
        return explanations.get(query_type, "Processing your query")

class DataFormatter:
    """Format SQL results for LLM consumption"""
    
    @staticmethod
    def format_results(results: List[Dict], query_type: str, limit: int = 20) -> str:
        """Format query results for the LLM"""
        if not results:
            return "No results found for this query."
        
        # Limit results for LLM context
        limited_results = results[:limit]
        
        if query_type == 'count':
            return DataFormatter._format_count_results(limited_results)
        elif query_type == 'aggregation':
            return DataFormatter._format_aggregation_results(limited_results)
        elif query_type == 'statistics':
            return DataFormatter._format_statistics_results(limited_results)
        elif query_type == 'ranking':
            return DataFormatter._format_ranking_results(limited_results)
        else:
            return DataFormatter._format_general_results(limited_results)
    
    @staticmethod
    def _format_count_results(results: List[Dict]) -> str:
        """Format count query results"""
        if not results:
            return "Count: 0"
        
        result = results[0]
        count_col = next((k for k in result.keys() if 'count' in k.lower()), None)
        if count_col:
            return f"Total count: {result[count_col]:,}"
        return str(result)
    
    @staticmethod
    def _format_aggregation_results(results: List[Dict]) -> str:
        """Format aggregation results"""
        lines = []
        for i, row in enumerate(results, 1):
            row_parts = []
            for key, value in row.items():
                if isinstance(value, (int, float)):
                    if 'spend' in key.lower() or 'cost' in key.lower() or 'price' in key.lower():
                        row_parts.append(f"{key}: ${value:,.2f}")
                    else:
                        row_parts.append(f"{key}: {value:,}")
                else:
                    row_parts.append(f"{key}: {value}")
            lines.append(f"{i}. {' | '.join(row_parts)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_statistics_results(results: List[Dict]) -> str:
        """Format statistical results"""
        if not results:
            return "No statistics available"
        
        result = results[0]
        lines = []
        for key, value in result.items():
            if isinstance(value, (int, float)):
                if 'spend' in key.lower() or 'cost' in key.lower():
                    lines.append(f"{key}: ${value:,.2f}")
                else:
                    lines.append(f"{key}: {value:,.2f}")
            else:
                lines.append(f"{key}: {value}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_ranking_results(results: List[Dict]) -> str:
        """Format ranking results"""
        lines = ["Top results:"]
        for i, row in enumerate(results, 1):
            main_field = DataFormatter._identify_main_field(row)
            value_field = DataFormatter._identify_value_field(row)
            
            if main_field and value_field:
                value = row[value_field]
                if isinstance(value, (int, float)) and ('spend' in value_field.lower() or 'cost' in value_field.lower()):
                    lines.append(f"{i}. {row[main_field]} — ${value:,.2f}")
                else:
                    lines.append(f"{i}. {row[main_field]} — {value}")
            else:
                # Fallback to showing all fields
                lines.append(f"{i}. {DataFormatter._format_row(row)}")
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_general_results(results: List[Dict]) -> str:
        """Format general query results"""
        lines = [f"Found {len(results)} results:"]
        for i, row in enumerate(results[:10], 1):  # Show first 10
            lines.append(f"{i}. {DataFormatter._format_row(row)}")
        
        if len(results) > 10:
            lines.append(f"... and {len(results) - 10} more results")
        
        return "\n".join(lines)
    
    @staticmethod
    def _identify_main_field(row: Dict) -> Optional[str]:
        """Identify the main descriptive field in a result row"""
        priority_fields = ['ItemDesc', 'Vendor', 'Manufacturer', 'Department', 'Category', 'Region']
        for field in priority_fields:
            if field in row and row[field]:
                return field
        return None
    
    @staticmethod
    def _identify_value_field(row: Dict) -> Optional[str]:
        """Identify the main value field in a result row"""
        value_fields = ['total_spend', 'TotalSpend', 'sum_spend', 'avg_spend', 'count', 'quantity']
        for field in value_fields:
            if field in row:
                return field
        
        # Look for any field with numeric value
        for key, value in row.items():
            if isinstance(value, (int, float)) and key not in ['Month', 'Year', 'TransactionID']:
                return key
        
        return None
    
    @staticmethod
    def _format_row(row: Dict) -> str:
        """Format a single row of data"""
        parts = []
        for key, value in row.items():
            if value is not None:
                if isinstance(value, float):
                    if 'spend' in key.lower() or 'cost' in key.lower():
                        parts.append(f"{key}: ${value:,.2f}")
                    else:
                        parts.append(f"{key}: {value:.2f}")
                elif isinstance(value, int):
                    parts.append(f"{key}: {value:,}")
                else:
                    parts.append(f"{key}: {value}")
        
        return " | ".join(parts)

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db)
) -> ChatResponse:
    """Enhanced chat endpoint with dynamic SQL generation"""
    
    logger.info(f"Chat request: {request.message}")
    
    try:
        # Check if system has data
        ai_search = get_ai_search_service()
        sql_service = get_sql_service()
        
        # Quick check for data availability
        has_data = False
        try:
            test_query = "SELECT TOP 1 TransactionID FROM supply_records"
            test_result = sql_service.query_items(test_query)
            has_data = bool(test_result)
        except:
            pass
        
        if not has_data:
            return ChatResponse(
                response="I don't see any data in the system yet. Please upload your supply chain data first, and then I can help you analyze it with any questions you have!",
                suggestions=[
                    "How do I upload data?",
                    "What data format do you accept?",
                    "What kind of analysis can you do?"
                ],
                session_id=request.session_id
            )
        
        # Get conversation context if available
        context = None
        if request.session_id:
            try:
                chat_context_service = get_chat_context_service()
                context_data = await chat_context_service.get_conversation_context(
                    current_message=request.message,
                    chat_id=f"chat-{request.session_id}",
                    session_id=request.session_id,
                    context_limit=3
                )
                if context_data.get("has_context"):
                    context = context_data.get("context_summary", "")
            except Exception as e:
                logger.warning(f"Failed to get context: {e}")
        
        # Generate SQL query using LLM
        sql_result = SQLGenerator.generate_sql(request.message, context)
        
        if not sql_result["success"]:
            # Fallback to vector search if SQL generation fails
            return await _handle_with_vector_search(request)
        
        # Execute the generated SQL
        sql_query = sql_result["sql"]
        query_type = sql_result["query_type"]
        
        logger.info(f"Generated SQL: {sql_query}")
        
        try:
            query_results = sql_service.query_items(sql_query)
            
            if not query_results:
                return ChatResponse(
                    response="I couldn't find any data matching your query. Try asking in a different way or with different criteria.",
                    suggestions=_generate_alternative_suggestions(request.message),
                    session_id=request.session_id,
                    sql_query=sql_query
                )
            
            # Format results for LLM
            formatted_results = DataFormatter.format_results(query_results, query_type)
            
            # Generate natural language response
            response_prompt = f"""You are Earl, a supply chain data analyst AI. 
Based on the user's question and the query results below, provide a clear, insightful response.

User Question: {request.message}
Query Type: {sql_result['explanation']}

Results:
{formatted_results}

Provide a natural, conversational response that:
1. Directly answers the user's question
2. Highlights key insights from the data
3. Suggests potential follow-up analyses
4. Uses proper formatting for numbers (currency, percentages, etc.)

Keep the response concise but comprehensive (4-6 sentences).
Do not mention SQL or technical details unless specifically asked."""

            ai_response = LlamaService.query(response_prompt, max_tokens=500)
            
            # Generate smart suggestions based on the query
            suggestions = _generate_contextual_suggestions(request.message, query_results, query_type)
            
            # Prepare data preview (first 10 rows)
            data_preview = query_results[:10] if len(query_results) > 10 else query_results
            
            return ChatResponse(
                response=ai_response,
                suggestions=suggestions,
                session_id=request.session_id,
                sql_query=sql_query,
                data_preview=data_preview
            )
            
        except Exception as sql_error:
            logger.error(f"SQL execution failed: {sql_error}")
            # Try to help the user with a better query
            return ChatResponse(
                response=f"I had trouble with that query. Let me search for relevant information instead...",
                suggestions=_generate_alternative_suggestions(request.message),
                session_id=request.session_id
            )
            
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        return ChatResponse(
            response="I encountered an error processing your request. Please try rephrasing your question.",
            suggestions=["Show me total spend", "List all vendors", "What's in the database?"],
            session_id=request.session_id
        )

async def _handle_with_vector_search(request: ChatRequest) -> ChatResponse:
    """Fallback to vector search when SQL generation fails"""
    try:
        # Use vector search for relevant context
        search_results = query_similar_embeddings(request.message, top_k=10, min_score=0.3)
        
        if not search_results:
            return ChatResponse(
                response="I couldn't understand your question well enough to search the database. Could you rephrase it? For example, you could ask about specific vendors, total spending, or product categories.",
                suggestions=[
                    "Show total spend by vendor",
                    "What are the top products?",
                    "List all regions"
                ],
                session_id=request.session_id
            )
        
        # Format vector search results
        context_lines = []
        for i, result in enumerate(search_results[:5], 1):
            metadata = result.get("metadata", {})
            context_lines.append(
                f"{i}. {metadata.get('ItemDesc', 'Unknown')} | "
                f"Vendor: {metadata.get('Vendor', 'Unknown')} | "
                f"Spend: ${metadata.get('TotalSpend', 0):,.2f}"
            )
        
        context = "\n".join(context_lines)
        
        # Generate response
        prompt = f"""Based on these search results, answer the user's question:

User Question: {request.message}

Relevant Data:
{context}

Provide a helpful response that acknowledges you found related information but might not have the exact answer they're looking for."""

        response = LlamaService.query(prompt, max_tokens=300)
        
        return ChatResponse(
            response=response,
            suggestions=_generate_alternative_suggestions(request.message),
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"Vector search fallback failed: {e}")
        return ChatResponse(
            response="I'm having trouble searching the database. Please try a simpler question.",
            suggestions=["Show all vendors", "Total spend summary", "Recent transactions"],
            session_id=request.session_id
        )

def _generate_contextual_suggestions(question: str, results: List[Dict], query_type: str) -> List[str]:
    """Generate smart follow-up suggestions based on the query results"""
    suggestions = []
    
    # Analyze the results to suggest deeper insights
    if query_type == 'aggregation' and results:
        # If showing spend by vendor, suggest drill-downs
        if any('vendor' in k.lower() for k in results[0].keys()):
            top_vendor = results[0].get('Vendor', '')
            if top_vendor:
                suggestions.append(f"What products does {top_vendor} supply?")
                suggestions.append(f"Compare {top_vendor} with other vendors")
        
    elif query_type == 'ranking':
        suggestions.append("Show trends over time")
        suggestions.append("Break down by department")
        
    elif query_type == 'count':
        suggestions.append("Show distribution by category")
        suggestions.append("What are the top items?")
    
    # Add general analytical suggestions
    suggestions.extend([
        "Analyze spending patterns",
        "Find cost-saving opportunities",
        "Show monthly trends"
    ])
    
    return suggestions[:4]  # Return top 4 suggestions

def _generate_alternative_suggestions(question: str) -> List[str]:
    """Generate alternative ways to ask the question"""
    return [
        "Show total spending by vendor",
        "What are the most expensive items?",
        "List all departments and their spending",
        "Show spending trends over time"
    ]

# Keep the health check endpoint
@router.get("/chat/health")
async def chat_health():
    """Health check endpoint"""
    try:
        sql_service = get_sql_service()
        sql_test = sql_service.test_connection()
        
        return {
            "status": "healthy",
            "sql_connection": sql_test["status"] == "connected",
            "llm_available": True
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }