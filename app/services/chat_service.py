# app/services/chat_service.py
from app.services.embedding_service import embed_bulk_text
from app.services.embedding_service import query_similar_embeddings
from app.services.ai_service import generate_response
from typing import Dict, Any, List
import datetime
import logging

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, top_k: int = 15):
        self.top_k = top_k

    def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Process a user query using vector search and AI generation
        """
        try:
            # Use the vector search service that works with SQL
            top_chunks = query_similar_embeddings(user_query, top_k=self.top_k)
            
            if not top_chunks:
                return {
                    "answer": "I couldn't find relevant information to answer your question. Please try rephrasing your query or check if the database has been populated with data.",
                    "sources": [],
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }

            # Build context string from returned metadata
            context = self.build_context_string(top_chunks)
            
            # Create prompt for AI
            prompt = (
                f"You are Earl, an AI assistant specializing in supply chain management. "
                f"Answer the following hospital supply chain question using only the provided data context. "
                f"If the context doesn't contain enough information to answer the question, say so.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {user_query}\n"
                f"Answer:"
            )

            # Generate AI response
            answer = generate_response(prompt)

            return {
                "answer": answer.strip(),
                "sources": [chunk['metadata'] for chunk in top_chunks],
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "context_used": len(top_chunks) > 0
            }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "I'm sorry, I encountered an error while processing your request. Please try again later.",
                "sources": [],
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "error": str(e)
            }

    def build_context_string(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Build a context string from search results
        """
        context_list = []
        
        for i, chunk in enumerate(chunks, 1):
            metadata = chunk.get('metadata', {})
            similarity = chunk.get('similarity', 0)
            
            # Extract key fields from metadata
            item_desc = metadata.get('item_desc', 'N/A')
            vendor = metadata.get('vendor', 'N/A')
            facility_type = metadata.get('facility_type', 'N/A')
            total_spend = metadata.get('total_spend', 0)
            department = metadata.get('department', 'N/A')
            category = metadata.get('category', 'N/A')
            
            # Format the context entry
            context_entry = (
                f"{i}. Item: {item_desc} | "
                f"Vendor: {vendor} | "
                f"Facility: {facility_type} | "
                f"Department: {department} | "
                f"Category: {category} | "
                f"Spend: ${total_spend:,.2f} | "
                f"Relevance: {similarity:.3f}"
            )
            
            context_list.append(context_entry)

        return "\n".join(context_list)

    def process_csv_query(self, user_query: str, csv_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a query that includes CSV data
        """
        try:
            # Get vector search results
            vector_results = query_similar_embeddings(user_query, top_k=self.top_k)
            
            # Build context from both vector search and CSV
            context_parts = []
            
            if vector_results:
                vector_context = self.build_context_string(vector_results)
                context_parts.append(f"Database Knowledge:\n{vector_context}")
            
            # Add CSV analysis
            csv_context = self._analyze_csv_data(csv_data, user_query)
            if csv_context:
                context_parts.append(f"Uploaded Data:\n{csv_context}")
            
            if not context_parts:
                return {
                    "answer": "I couldn't find relevant data to answer your question.",
                    "sources": [],
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
            
            # Combine contexts
            full_context = "\n\n".join(context_parts)
            
            prompt = (
                f"You are Earl, an AI assistant specializing in supply chain management. "
                f"Use the following context to answer the question. If unsure, say so.\n\n"
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
                "context_used": True
            }
            
        except Exception as e:
            logger.error(f"Error processing CSV query: {e}")
            return {
                "answer": "I'm sorry, I encountered an error while processing your request with the uploaded data.",
                "sources": [],
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "error": str(e)
            }

    def _analyze_csv_data(self, csv_data: Dict[str, Any], query: str) -> str:
        """
        Analyze uploaded CSV data for context
        """
        if not csv_data or not csv_data.get('data'):
            return ""
            
        analysis = []
        
        # Basic stats
        filename = csv_data.get('filename', 'unknown')
        row_count = csv_data.get('row_count', 0)
        headers = csv_data.get('headers', [])
        data = csv_data.get('data', [])
        
        analysis.append(f"File: {filename}")
        analysis.append(f"Rows: {row_count}")
        analysis.append(f"Columns: {', '.join(headers)}")
        
        # Dynamic analysis based on query and available data
        query_lower = query.lower()
        
        try:
            # Spending analysis
            if any(word in query_lower for word in ['total', 'sum', 'spend', 'cost']):
                spend_columns = [col for col in headers if 'spend' in col.lower() or 'cost' in col.lower() or 'price' in col.lower()]
                for col in spend_columns:
                    values = [float(row.get(col, 0) or 0) for row in data if row.get(col)]
                    if values:
                        analysis.append(f"Total {col}: ${sum(values):,.2f}")
                        analysis.append(f"Average {col}: ${sum(values)/len(values):,.2f}")
            
            # Vendor analysis
            if 'vendor' in query_lower and 'vendor' in headers:
                vendors = list(set(row.get('vendor', '') for row in data if row.get('vendor')))
                analysis.append(f"Unique vendors: {len(vendors)}")
                if len(vendors) <= 10:  # Show vendors if not too many
                    analysis.append(f"Vendors: {', '.join(vendors)}")
            
            # Department analysis
            if 'department' in query_lower and 'department' in headers:
                departments = list(set(row.get('department', '') for row in data if row.get('department')))
                analysis.append(f"Departments: {', '.join(departments)}")
                
        except Exception as e:
            logger.warning(f"Error analyzing CSV data: {e}")
        
        return "\n".join(analysis) if analysis else "No specific analysis available for uploaded data."