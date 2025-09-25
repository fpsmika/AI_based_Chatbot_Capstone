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
            prompt = system_prompt = (
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
    "Give straight answers only, no explanations until asked for one"
    "Each point must contain only one peice of information"
    "When asked for 'top' or 'most', look for numerical fields and sort descending. Always return concise ranked results using bullet points."
    "keep it consise and direct, avoid full paragraphs until specifically mentioned "
    "Do not mix multiple insight types in one sentence. Use bullet points or numbered lists where necessary for clarity.\n"
    "If data is incomplete or unclear, mention that explicitly and suggest what additional information would help improve the analysis.\n"
    "Do not repeat the user's question in your response. Focus only on the analysis.\n"
    "You may end with a short friendly suggestion or follow-up."
    "You will remain in this role across all interactions. If the user asks a follow-up question, treat it as a continuation of the previous context unless otherwise specified.\n"
    "If no CSV data has been uploaded or available context is missing, let the user know politely and ask them to upload a file to proceed with the analysis."
    "Do not list or cite your data sources explicitly. Avoid phrases like 'according to the data' or 'based on the uploaded CSV.'"
    "Do not list or cite your data sources explicitly."
    "Use newline-formatted bullet points (e.g., '-', '*', or numbered '1.', '2.', etc.) with one insight per line.\n"
    "Do not write multiple points in one sentence. Each insight must appear on a new line."
    "Use only the fields explicitly tagged for the relevant query type. "
    "For example, for vendor-related questions, use fields tagged as 'vendor_name'. "
    "If context does not contain enough tagged information, say so.\n\n"

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
            
            prompt = system_prompt = (
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
    "Give straight answers only, no explanations until asked for one"
    "Each point must contain only one peice of information"
    "When asked for 'top' or 'most', look for numerical fields and sort descending. Always return concise ranked results using bullet points."
    "keep it consise and direct, avoid full paragraphs until specifically mentioned "
    "Do not mix multiple insight types in one sentence. Use bullet points or numbered lists where necessary for clarity.\n"
    "If data is incomplete or unclear, mention that explicitly and suggest what additional information would help improve the analysis.\n"
    "Do not repeat the user's question in your response. Focus only on the analysis.\n"
    "You may end with a short friendly suggestion or follow-up."
    "You will remain in this role across all interactions. If the user asks a follow-up question, treat it as a continuation of the previous context unless otherwise specified.\n"
    "If no CSV data has been uploaded or available context is missing, let the user know politely and ask them to upload a file to proceed with the analysis."
    "Do not list or cite your data sources explicitly. Avoid phrases like 'according to the data' or 'based on the uploaded CSV.'"
    "Do not list or cite your data sources explicitly."
    "Use newline-formatted bullet points (e.g., '-', '*', or numbered '1.', '2.', etc.) with one insight per line.\n"
    "Do not write multiple points in one sentence. Each insight must appear on a new line."
    "Use only the fields explicitly tagged for the relevant query type. "
    "For example, for vendor-related questions, use fields tagged as 'vendor_name'. "
    "If context does not contain enough tagged information, say so.\n\n"
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