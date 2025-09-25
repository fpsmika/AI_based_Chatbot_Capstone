# app/services/chat_service.py
from app.services.embedding_service import embed_bulk_text
from app.services.embedding_service import query_similar_embeddings
from app.services.ai_service import generate_response
from app.services.text_to_sql_service import get_text_to_sql_service
from typing import Dict, Any, List
import datetime
import logging

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, top_k: int = 15):
        self.top_k = top_k
        self.text_to_sql_service = get_text_to_sql_service()
        
        # Simplified, consistent system prompt
        self.system_prompt = (
            "You are Earl, an AI assistant specializing in supply chain management and procurement data analysis.\n\n"
            
            "RESPONSE FORMAT - CRITICAL:\n"
            "- Use ONLY bullet points (-, *, or numbers)\n"
            "- One key insight per line - be concise and direct\n" 
            "- No paragraphs, explanations, or connecting phrases\n"
            "- No phrases like 'based on the data' or 'according to the CSV'\n"
            "- Start each bullet with the core insight immediately\n"
            "- Maximum 4-5 bullet points per response\n"
            "- Format currency as $X,XXX.XX\n"
            "- No bold, italics, or markdown formatting\n\n"
            
            "DATA ANALYSIS FOCUS:\n"
            "- Key metrics, totals, and spending patterns\n"
            "- Vendor performance and rankings\n" 
            "- Regional and facility comparisons\n"
            "- Cost optimization opportunities\n\n"
            
            "If insufficient data is available, state: '- Insufficient data for this analysis'\n\n"
        )

    def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Enhanced query processing with intelligent routing
        """
        try:
            logger.info(f"Processing query: '{user_query}'")
            
            # First, try vector search for contextual data
            vector_results = self._try_vector_search(user_query)
            
            # Determine if this looks like a SQL-based analytics query
            if self._is_analytics_query(user_query):
                logger.info("Routing to TextToSQL service for analytics")
                return self._route_to_sql_service(user_query, vector_results)
            
            # Handle as vector-based query if we have results
            if vector_results:
                logger.info("Processing as vector-based query")
                return self._process_vector_query(user_query, vector_results)
            
            # Fallback: try SQL service anyway
            logger.info("No vector results, falling back to SQL service")
            return self._route_to_sql_service(user_query, [])
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return self._error_response(str(e))

    def _try_vector_search(self, user_query: str) -> List[Dict[str, Any]]:
        """Try vector search and return results or empty list"""
        try:
            return query_similar_embeddings(user_query, top_k=self.top_k)
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    def _is_analytics_query(self, query: str) -> bool:
        """Determine if query should be routed to SQL analytics"""
        q = query.lower()
        
        # Keywords that suggest SQL analytics
        sql_keywords = [
            'total', 'sum', 'average', 'count', 'top', 'bottom', 'most', 'least',
            'vendor', 'facility', 'region', 'spend', 'cost', 'compare', 'trend',
            'how many', 'which', 'what are', 'show me', 'list', 'breakdown'
        ]
        
        return any(keyword in q for keyword in sql_keywords)

    def _route_to_sql_service(self, user_query: str, vector_context: List[Dict]) -> Dict[str, Any]:
        """Route query to TextToSQL service and format response"""
        try:
            # Get SQL service response
            sql_response = self.text_to_sql_service.analyze_supply_chain_query(user_query)
            
            # Convert to ChatService format for consistency
            return {
                "answer": sql_response.get("insights", "- No insights available"),
                "sources": self._format_sql_sources(sql_response),
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "context_used": True,
                "query_type": "sql_analytics",
                "sql_query": sql_response.get("sql_query"),
                "recommendations": sql_response.get("recommendations", [])
            }
            
        except Exception as e:
            logger.error(f"SQL service routing failed: {e}")
            return self._error_response(f"Analytics service error: {str(e)}")

    def _process_vector_query(self, user_query: str, vector_results: List[Dict]) -> Dict[str, Any]:
        """Process query using vector search results"""
        try:
            # Build context string from vector results
            context = self._build_context_string(vector_results)
            
            # Create prompt using improved system prompt
            prompt = (
                f"{self.system_prompt}"
                f"Context:\n{context}\n\n"
                f"Question: {user_query}\n"
                f"Answer:"
            )

            # Generate AI response
            answer = generate_response(prompt)

            return {
                "answer": answer.strip(),
                "sources": [chunk['metadata'] for chunk in vector_results],
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "context_used": True,
                "query_type": "vector_search"
            }
            
        except Exception as e:
            logger.error(f"Vector query processing failed: {e}")
            return self._error_response(str(e))

    def _build_context_string(self, chunks: List[Dict[str, Any]]) -> str:
        """Build a concise context string from search results"""
        if not chunks:
            return "No relevant context found."
            
        context_list = []
        
        for i, chunk in enumerate(chunks[:10], 1):  # Limit to top 10
            metadata = chunk.get('metadata', {})
            
            # Extract key fields from metadata
            item_desc = metadata.get('item_desc', 'N/A')
            vendor = metadata.get('vendor', 'N/A')
            total_spend = metadata.get('total_spend', 0)
            facility_type = metadata.get('facility_type', 'N/A')
            
            # Create concise context entry
            context_entry = f"{i}. {item_desc} | {vendor} | ${total_spend:,.2f} | {facility_type}"
            context_list.append(context_entry)

        return "\n".join(context_list)

    def _format_sql_sources(self, sql_response: Dict) -> List[Dict]:
        """Format SQL response sources for consistency"""
        sources = []
        
        if sql_response.get("sql_query"):
            sources.append({
                "source": "sql_database",
                "query": sql_response["sql_query"],
                "result_count": sql_response.get("result_count", 0)
            })
            
        return sources

    def process_csv_query(self, user_query: str, csv_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a query with uploaded CSV data using improved formatting
        """
        try:
            logger.info(f"Processing CSV query: '{user_query}'")
            
            # Get vector search results for additional context
            vector_results = self._try_vector_search(user_query)
            
            # Build combined context
            context_parts = []
            
            # Add vector context if available
            if vector_results:
                vector_context = self._build_context_string(vector_results)
                context_parts.append(f"Database Context:\n{vector_context}")
            
            # Add CSV analysis using improved format
            csv_context = self._analyze_csv_data_bullets(csv_data, user_query)
            if csv_context:
                context_parts.append(f"Uploaded Data Analysis:\n{csv_context}")
            
            if not context_parts:
                return {
                    "answer": "- No relevant data found to answer your question",
                    "sources": [],
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "query_type": "csv_analysis"
                }
            
            # Combine contexts
            full_context = "\n\n".join(context_parts)
            
            # Use improved system prompt
            prompt = (
                f"{self.system_prompt}"
                f"Context:\n{full_context}\n\n"
                f"Question: {user_query}\n"
                f"Answer:"
            )

            answer = generate_response(prompt)
            
            # Prepare sources
            sources = []
            if vector_results:
                sources.extend([{"source": "database", **chunk['metadata']} for chunk in vector_results])
            if csv_data:
                sources.append({
                    "source": "uploaded_csv",
                    "filename": csv_data.get('filename', 'unknown'),
                    "rows": csv_data.get('row_count', 0)
                })

            return {
                "answer": answer.strip(),
                "sources": sources,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "context_used": True,
                "query_type": "csv_analysis"
            }
            
        except Exception as e:
            logger.error(f"Error processing CSV query: {e}")
            return self._error_response(f"CSV analysis error: {str(e)}")

    def _analyze_csv_data_bullets(self, csv_data: Dict[str, Any], query: str) -> str:
        """
        Analyze uploaded CSV data and return bullet-point format
        """
        if not csv_data or not csv_data.get('data'):
            return ""
            
        bullets = []
        
        # Basic stats
        filename = csv_data.get('filename', 'unknown')
        row_count = csv_data.get('row_count', 0)
        headers = csv_data.get('headers', [])
        data = csv_data.get('data', [])
        
        bullets.append(f"- CSV file: {filename} ({row_count} rows, {len(headers)} columns)")
        
        # Dynamic analysis based on query
        query_lower = query.lower()
        
        try:
            # Spending analysis
            if any(word in query_lower for word in ['total', 'sum', 'spend', 'cost']):
                spend_columns = [col for col in headers if any(term in col.lower() for term in ['spend', 'cost', 'price', 'amount'])]
                for col in spend_columns[:2]:  # Limit to first 2 spend columns
                    values = [float(row.get(col, 0) or 0) for row in data if row.get(col)]
                    if values:
                        total_spend = sum(values)
                        avg_spend = total_spend / len(values)
                        bullets.append(f"- {col} total: ${total_spend:,.2f} (avg: ${avg_spend:,.2f})")
            
            # Vendor analysis
            if 'vendor' in query_lower:
                vendor_cols = [col for col in headers if 'vendor' in col.lower() or 'supplier' in col.lower()]
                for col in vendor_cols[:1]:  # Just first vendor column
                    vendors = [row.get(col, '') for row in data if row.get(col)]
                    unique_vendors = len(set(vendors))
                    if unique_vendors > 0:
                        bullets.append(f"- {unique_vendors} unique vendors in {col}")
            
            # Category/Department analysis
            if any(term in query_lower for term in ['department', 'category', 'type']):
                cat_cols = [col for col in headers if any(term in col.lower() for term in ['department', 'category', 'type'])]
                for col in cat_cols[:1]:  # Just first category column
                    categories = [row.get(col, '') for row in data if row.get(col)]
                    unique_cats = len(set(categories))
                    if unique_cats > 0:
                        bullets.append(f"- {unique_cats} unique {col.lower()}s identified")
                        
        except Exception as e:
            logger.warning(f"Error analyzing CSV data: {e}")
            bullets.append("- CSV analysis partially completed due to data format issues")
        
        return "\n".join(bullets) if bullets else ""

    def _error_response(self, error: str) -> Dict[str, Any]:
        """Return standardized error response"""
        return {
            "answer": "- Unable to process your request at this time\n- Please try rephrasing your question or check your data",
            "sources": [],
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "error": error,
            "query_type": "error"
        }

    def get_query_suggestions(self) -> List[str]:
        """Provide helpful query suggestions for users"""
        return [
            "Show me the top 5 vendors by total spend",
            "Which regions have the highest procurement costs?",
            "Compare spending across different facility types",
            "What are the most expensive items purchased?",
            "Analyze monthly spending trends",
            "List all vendors with spend over $10,000"
        ]

    def get_system_status(self) -> Dict[str, Any]:
        """Return system status for debugging"""
        try:
            # Check if SQL service is available
            sql_available = self.text_to_sql_service._has_data()
            
            # Check if vector service is available
            vector_test = self._try_vector_search("test")
            vector_available = len(vector_test) > 0
            
            return {
                "sql_service_available": sql_available,
                "vector_service_available": vector_available,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.datetime.utcnow().isoformat()
            }