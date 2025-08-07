import logging
from typing import Dict, Any, List, Optional
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
import re

logger = logging.getLogger(__name__)

class TextToSQLService:
    def __init__(self):
        self.llama_service = LlamaService
        self.sql_service = get_sql_service()
        # Enhanced schema definition with data types and descriptions
        self.schema = """
        Table: supply_records
        Columns:
        - TransactionID (varchar): Unique transaction identifier
        - FacilityID (varchar): Hospital/facility identifier  
        - FacilityType (varchar): Type of healthcare facility
        - Region (varchar): Geographic region
        - BedSize (int): Number of beds in facility
        - Month (int): Month of transaction (1-12)
        - Year (int): Year of transaction
        - LoadDate (datetime): Data load timestamp
        - Vendor (varchar): Supplier/vendor name
        - VendorID (varchar): Vendor identifier
        - Manufacturer (varchar): Product manufacturer
        - ManufacturerID (varchar): Manufacturer identifier
        - ManufacturerCatalogNum (varchar): Manufacturer catalog number
        - ItemDesc (varchar): Item description/name
        - Quantity (decimal): Quantity purchased
        - PricePaid (decimal): Unit price paid
        - TotalSpend (decimal): Total amount spent (Quantity * PricePaid)
        """
    
    def analyze_supply_chain_query(self, user_question: str) -> Dict[str, Any]:
        """Main method - generates SQL, executes it, and creates business response"""
        try:
            logger.info(f"Analyzing query: {user_question}")
            
            # Check if we have data
            if not self._has_data():
                return self._no_data_response()
            
            # Generate and execute SQL
            sql_query = self._generate_sql(user_question)
            if not sql_query:
                return self._error_response("Could not generate SQL query")
            
            logger.info(f"Generated SQL: {sql_query}")  # Add this for debugging
            
            # Execute SQL with proper error handling
            try:
                results = self.sql_service.query_items(sql_query)
                logger.info(f"SQL returned {len(results)} results")
                
                # Debug: Log first result to see what data we're getting
                if results:
                    logger.info(f"First result sample: {results[0]}")
                    
            except Exception as sql_error:
                logger.error(f"SQL execution failed: {sql_error}")
                return self._error_response(f"Database query failed: {str(sql_error)}")
            
            # Generate business response
            insights = self._create_business_response(user_question, results, sql_query)
            
            return {
                "success": True,
                "insights": insights,
                "data_summary": self._summarize_data(results),
                "recommendations": self._get_recommendations(user_question),
                "result_count": len(results),
                "sql_query": sql_query  # Include for debugging
            }
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return self._error_response(str(e))
    
    def _has_data(self) -> bool:
        """Quick check if database has data with better error handling"""
        try:
            result = self.sql_service.query_items("SELECT COUNT(*) as count FROM supply_records")
            return result[0]['count'] > 0 if result else False
        except Exception as e:
            logger.error(f"Data availability check failed: {e}")
            return False
    
    def _generate_sql(self, question: str) -> Optional[str]:
        """Generate SQL query - always includes core business columns"""
        
        prompt = f"""
        Generate a SQL Server query for supply_records table to answer this question.
        
        Schema: {self.schema}
        
        Question: {question}
        
        CRITICAL RULES:
        1. For individual transaction queries, ALWAYS SELECT: TransactionID, Vendor, VendorID, ItemDesc, Quantity, PricePaid, TotalSpend, FacilityID, Month, Year
        2. For summary/aggregate queries, include relevant grouping columns plus SUM(TotalSpend), COUNT(*), etc.
        3. Use TOP 100 for large result sets
        4. Use exact column names from schema
        5. Return ONLY the SQL query, no explanations
        
        Examples:
        - "transaction 123 vendor and item" → SELECT TransactionID, Vendor, VendorID, ItemDesc, Quantity, PricePaid, TotalSpend, FacilityID FROM supply_records WHERE TransactionID = '123'
        - "top vendors by spend" → SELECT TOP 100 Vendor, SUM(TotalSpend) as TotalSpend, COUNT(*) as TransactionCount FROM supply_records GROUP BY Vendor ORDER BY SUM(TotalSpend) DESC
        
        SQL:
        """
        
        try:
            sql = self.llama_service.query(prompt, max_tokens=200, temperature=0.1)
            cleaned_sql = self._clean_sql(sql)
            logger.info(f"Generated SQL: {cleaned_sql}")
            return cleaned_sql
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return None
    
    def _clean_sql(self, query: str) -> str:
        """Clean generated SQL with better error handling"""
        if not query:
            raise ValueError("Empty SQL query")
            
        # Remove markdown and formatting
        query = re.sub(r'```sql\n?|```\n?|```\n|```', '', query).strip()
        
        # Remove trailing semicolons
        query = query.rstrip(';').strip()
        
        # Fix TOP position if needed - this regex handles various TOP placements
        query = re.sub(r'SELECT\s+(.+?)\s+TOP\s+(\d+)', r'SELECT TOP \2 \1', query, flags=re.IGNORECASE)
        
        # Security check
        dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'INSERT', 'UPDATE']
        if any(word in query.upper() for word in dangerous):
            raise ValueError("Unsafe SQL operation detected")
        
        # Validate basic SQL structure
        if not query.upper().startswith('SELECT'):
            raise ValueError("Query must start with SELECT")
            
        return query
    
    def _create_business_response(self, question: str, results: List[Dict], sql_query: str) -> str:
        """Generate business-focused response using only retrieved data"""
        if not results:
            return "No relevant data found for your question. Try asking about specific vendors, items, or facilities in your uploaded data."
        
        # Create context summary with only available data
        context = self._format_results_safe(results, question)
        
        # Get list of available columns from first result
        available_columns = list(results[0].keys()) if results else []
        
        prompt = f"""
        You are EARL, a helpful supply chain AI assistant for hospital managers.
        
        User Question: {question}
        Retrieved Data: {context}
        Available Data Fields: {available_columns}
        
        CRITICAL: Only discuss data fields that are actually available in the Retrieved Data above. 
        Do not mention or speculate about fields like Quantity, PricePaid, or TotalSpend unless they appear in the Available Data Fields list.
        
        Provide a clear, conversational answer using only the retrieved information. If key information is missing, acknowledge what you found and suggest a more specific query.
        
        Keep response under 100 words and be specific with numbers and names.
        """
        
        try:
            return self.llama_service.query(prompt, max_tokens=200, temperature=0.1).strip()
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return f"I found the data but had trouble formatting the response. Here's what I found: {context}"
    
    def _format_results_safe(self, results: List[Dict], question: str) -> str:
        """Format results safely, handling None values and missing columns"""
        if not results:
            return "No data found"
            
        def safe_get(record: Dict, key: str, default: str = "Not available") -> str:
            """Safely get value from record, handling None and missing keys"""
            value = record.get(key)
            if value is None or value == '' or str(value).lower() == 'none':
                return default
            return str(value)
        
        def safe_float(record: Dict, key: str, default: float = 0.0) -> float:
            """Safely convert to float, handling None and invalid values"""
            value = record.get(key)
            if value is None or value == '' or str(value).lower() == 'none':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        if len(results) == 1 and 'transaction' in question.lower():
            # Single transaction details
            r = results[0]
            
            # Build response with only available data
            parts = []
            if 'TransactionID' in r:
                parts.append(f"Transaction {safe_get(r, 'TransactionID')}")
            if 'ItemDesc' in r:
                parts.append(f"Item: {safe_get(r, 'ItemDesc')}")
            if 'Vendor' in r:
                parts.append(f"Vendor: {safe_get(r, 'Vendor')}")
            if 'Quantity' in r:
                qty = safe_get(r, 'Quantity', 'Not available')
                parts.append(f"Quantity: {qty}")
            if 'PricePaid' in r:
                price = safe_float(r, 'PricePaid')
                if price > 0:
                    parts.append(f"Unit Price: ${price:,.2f}")
                else:
                    parts.append("Unit Price: Not available")
            if 'TotalSpend' in r:
                total = safe_float(r, 'TotalSpend')
                if total > 0:
                    parts.append(f"Total: ${total:,.2f}")
                else:
                    parts.append("Total: Not available")
                    
            return " | ".join(parts)
        
        # Multiple results summary
        total_spend = sum(safe_float(r, 'TotalSpend') for r in results)
        vendors = len(set(safe_get(r, 'Vendor', 'Unknown') for r in results))
        
        context = f"{len(results)} records found"
        if total_spend > 0:
            context += f", ${total_spend:,.2f} total spend"
        if vendors > 0:
            context += f", {vendors} vendors"
        
        # Add top vendor if available
        if 'Vendor' in results[0] and 'TotalSpend' in results[0]:
            vendor_totals = {}
            for r in results:
                vendor = safe_get(r, 'Vendor', 'Unknown')
                vendor_totals[vendor] = vendor_totals.get(vendor, 0) + safe_float(r, 'TotalSpend')
            
            if vendor_totals:
                top_vendor = max(vendor_totals.items(), key=lambda x: x[1])
                if top_vendor[1] > 0:
                    context += f" | Top vendor: {top_vendor[0]} (${top_vendor[1]:,.2f})"
        
        return context
    
    def _summarize_data(self, results: List[Dict]) -> Dict[str, Any]:
        """Create data summary for frontend"""
        if not results:
            return {"total_records": 0}
        
        def safe_float(record: Dict, key: str) -> float:
            """Safely convert to float"""
            value = record.get(key, 0)
            if value is None or value == '' or str(value).lower() == 'none':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        
        total_spend = sum(safe_float(r, 'TotalSpend') for r in results)
        
        return {
            "total_records": len(results),
            "total_spend": total_spend,
            "average_spend": total_spend / len(results) if len(results) > 0 else 0,
            "unique_vendors": len(set(r.get('Vendor', '') for r in results if r.get('Vendor'))),
            "unique_items": len(set(r.get('ItemDesc', '') for r in results if r.get('ItemDesc')))
        }
    
    def _get_recommendations(self, question: str) -> List[str]:
        """Simple context-based recommendations"""
        question_lower = question.lower()
        
        if 'vendor' in question_lower:
            return ["Compare vendor pricing", "Analyze vendor performance", "Find alternative suppliers"]
        elif 'cost' in question_lower or 'spend' in question_lower:
            return ["Identify cost savings", "Review spending trends", "Compare departmental costs"]
        elif 'transaction' in question_lower:
            return ["View transaction details", "Find similar purchases", "Check vendor history"]
        else:
            return ["Ask about specific vendors", "Review spending patterns", "Analyze top purchases"]
    
    def _no_data_response(self) -> Dict[str, Any]:
        """Response when no data is available"""
        return {
            "success": False,
            "insights": "No supply chain data uploaded yet. Please upload a CSV file to get started.",
            "data_summary": {"total_records": 0},
            "recommendations": ["Upload CSV file", "Check file format", "Try sample data"],
            "result_count": 0
        }
    
    def _error_response(self, error: str) -> Dict[str, Any]:
        """Response for errors"""
        return {
            "success": False,
            "insights": "I'm having trouble analyzing your request. Please try rephrasing your question.",
            "data_summary": {"total_records": 0},
            "recommendations": ["Try different keywords", "Ask about specific items", "Check data upload"],
            "result_count": 0,
            "error": error
        }

# Singleton instance
text_to_sql_service = TextToSQLService()

def get_text_to_sql_service() -> TextToSQLService:
    return text_to_sql_service