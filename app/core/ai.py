# app/services/ai.py
import logging
from typing import List, Dict, Any, Optional
from app.services.llama_service import LlamaService
from app.services.embedding_service import query_similar_embeddings
from app.services.ai_search_service import get_ai_search_service
from app.services.sql_service import get_sql_service
import json

logger = logging.getLogger(__name__)

class AIAnalysisService:
    """
    Enhanced AI service that combines LLM responses with vector search and SQL analytics
    """
    
    def __init__(self):
        self.llama_service = LlamaService
        self.ai_search = get_ai_search_service()
        self.sql_service = get_sql_service()
    
    async def analyze_query(self, user_query: str, context_limit: int = 5) -> Dict[str, Any]:
        """
        Main analysis method that determines query type and provides comprehensive response
        """
        try:
            logger.info(f"Analyzing query: '{user_query}'")
            
            # Step 1: Classify the query type
            query_type = self._classify_query(user_query)
            logger.info(f"Classified query as: {query_type}")
            
            # Step 2: Get relevant context based on query type
            context_data = await self._get_context(user_query, query_type, context_limit)
            
            # Step 3: Generate AI response with context
            ai_response = await self._generate_response(user_query, context_data, query_type)
            
            # Step 4: Generate suggestions
            suggestions = self._generate_suggestions(query_type, context_data)
            
            return {
                "response": ai_response,
                "context_data": context_data,
                "query_type": query_type,
                "suggestions": suggestions,
                "data_sources": self._get_data_sources(context_data)
            }
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {
                "response": f"I encountered an issue analyzing your request: {str(e)}. Please try rephrasing your question.",
                "context_data": {},
                "query_type": "error",
                "suggestions": ["Try rephrasing your question", "Check specific vendor or item names", "Ask about spending trends"],
                "data_sources": []
            }
    
    def _classify_query(self, query: str) -> str:
        """
        Classify the user query to determine the best approach
        """
        query_lower = query.lower()
        
        # Vendor-related queries
        if any(word in query_lower for word in ['vendor', 'supplier', 'who sells', 'purchased from']):
            return 'vendor_analysis'
        
        # Spending/cost queries
        elif any(word in query_lower for word in ['spend', 'cost', 'price', 'expensive', 'budget', 'total']):
            return 'spending_analysis'
        
        # Item/product queries
        elif any(word in query_lower for word in ['item', 'product', 'equipment', 'supplies', 'what', 'find']):
            return 'item_search'
        
        # Facility/department queries
        elif any(word in query_lower for word in ['facility', 'hospital', 'department', 'region', 'location']):
            return 'facility_analysis'
        
        # Trend/comparison queries
        elif any(word in query_lower for word in ['trend', 'compare', 'increase', 'decrease', 'over time', 'monthly', 'yearly']):
            return 'trend_analysis'
        
        # Default to general search
        else:
            return 'general_search'
    
    async def _get_context(self, query: str, query_type: str, limit: int) -> Dict[str, Any]:
        """
        Get relevant context data based on query type
        """
        context = {
            "vector_results": [],
            "sql_analytics": {},
            "search_results": []
        }
        
        try:
            # Always get vector search results for semantic understanding
            vector_results = query_similar_embeddings(query, top_k=limit, min_score=0.4)
            context["vector_results"] = vector_results
            
            # Get additional context based on query type
            if query_type == 'vendor_analysis':
                context["sql_analytics"] = await self._get_vendor_analytics(query)
            
            elif query_type == 'spending_analysis':
                context["sql_analytics"] = await self._get_spending_analytics(query)
            
            elif query_type == 'facility_analysis':
                context["sql_analytics"] = await self._get_facility_analytics(query)
            
            # Get AI Search results for broader context
            ai_results = self.ai_search.search(query, top=limit)
            context["search_results"] = ai_results
            
        except Exception as e:
            logger.error(f"Error getting context: {e}")
        
        return context
    
    async def _get_vendor_analytics(self, query: str) -> Dict[str, Any]:
        """
        Get vendor-specific analytics from SQL
        """
        try:
            # Extract potential vendor names from query
            vendor_keywords = self._extract_entities(query, entity_type='vendor')
            
            analytics = {}
            for vendor in vendor_keywords:
                # Get vendor spending data
                vendor_query = """
                SELECT 
                    Vendor,
                    COUNT(*) as transaction_count,
                    SUM(TotalSpend) as total_spend,
                    AVG(TotalSpend) as avg_spend,
                    MIN(LoadDate) as first_purchase,
                    MAX(LoadDate) as last_purchase
                FROM supply_records 
                WHERE Vendor LIKE ?
                GROUP BY Vendor
                """
                results = self.sql_service.query_items(vendor_query, [{"name": "?", "value": f"%{vendor}%"}])
                if results:
                    analytics[vendor] = results[0]
            
            return analytics
        except Exception as e:
            logger.error(f"Vendor analytics error: {e}")
            return {}
    
    async def _get_spending_analytics(self, query: str) -> Dict[str, Any]:
        """
        Get spending analytics from SQL
        """
        try:
            # General spending summary
            spending_query = """
            SELECT 
                SUM(TotalSpend) as total_spend,
                COUNT(*) as total_transactions,
                AVG(TotalSpend) as avg_transaction,
                COUNT(DISTINCT Vendor) as unique_vendors,
                COUNT(DISTINCT FacilityID) as unique_facilities
            FROM supply_records
            """
            results = self.sql_service.query_items(spending_query)
            
            # Top spending categories
            category_query = """
            SELECT TOP 5
                Category,
                SUM(TotalSpend) as category_spend,
                COUNT(*) as item_count
            FROM supply_records
            WHERE Category IS NOT NULL AND Category != ''
            GROUP BY Category
            ORDER BY SUM(TotalSpend) DESC
            """
            category_results = self.sql_service.query_items(category_query)
            
            return {
                "summary": results[0] if results else {},
                "top_categories": category_results
            }
        except Exception as e:
            logger.error(f"Spending analytics error: {e}")
            return {}
    
    async def _get_facility_analytics(self, query: str) -> Dict[str, Any]:
        """
        Get facility-specific analytics from SQL
        """
        try:
            facility_query = """
            SELECT 
                FacilityType,
                Region,
                COUNT(*) as transaction_count,
                SUM(TotalSpend) as total_spend,
                AVG(TotalSpend) as avg_spend
            FROM supply_records
            GROUP BY FacilityType, Region
            ORDER BY SUM(TotalSpend) DESC
            """
            results = self.sql_service.query_items(facility_query)
            return {"facility_breakdown": results}
        except Exception as e:
            logger.error(f"Facility analytics error: {e}")
            return {}
    
    async def _generate_response(self, query: str, context_data: Dict[str, Any], query_type: str) -> str:
        """
        Generate AI response using LLM with context
        """
        try:
            # Build context string
            context_parts = []
            
            # Add vector search context
            if context_data.get("vector_results"):
                context_parts.append("Recent relevant transactions:")
                for result in context_data["vector_results"][:3]:
                    metadata = result.get("metadata", {})
                    context_parts.append(
                        f"- {metadata.get('ItemDesc', 'N/A')} from {metadata.get('Vendor', 'N/A')} "
                        f"(${metadata.get('TotalSpend', 0):,.2f})"
                    )
            
            # Add SQL analytics context
            if context_data.get("sql_analytics"):
                analytics = context_data["sql_analytics"]
                if query_type == 'spending_analysis' and analytics.get("summary"):
                    summary = analytics["summary"]
                    context_parts.append(
                        f"Spending Overview: Total spend ${summary.get('total_spend', 0):,.2f} "
                        f"across {summary.get('total_transactions', 0):,} transactions"
                    )
            
            context_str = "\n".join(context_parts)
            
            # Create enhanced prompt
            system_prompt = f"""You are an AI assistant specializing in healthcare supply chain analysis. 
            You help users understand purchasing data, vendor relationships, and spending patterns.
            
            Query type: {query_type}
            
            Available context:
            {context_str}
            
            Provide a helpful, concise response based on the context. If the context doesn't contain 
            enough information, acknowledge this and suggest specific alternatives."""
            
            # Generate response using LLM
            full_prompt = f"{system_prompt}\n\nUser Question: {query}"
            response = self.llama_service.query(full_prompt, max_tokens=400)
            
            return response
            
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return f"I found some relevant information but had trouble generating a complete response. {str(e)}"
    
    def _generate_suggestions(self, query_type: str, context_data: Dict[str, Any]) -> List[str]:
        """
        Generate contextual suggestions based on query type and results
        """
        suggestions = []
        
        if query_type == 'vendor_analysis':
            suggestions.extend([
                "Compare vendor pricing",
                "Show vendor performance metrics",
                "Find alternative vendors"
            ])
        elif query_type == 'spending_analysis':
            suggestions.extend([
                "Show spending trends over time",
                "Compare departmental spending",
                "Identify cost-saving opportunities"
            ])
        elif query_type == 'item_search':
            suggestions.extend([
                "Find similar products",
                "Compare item prices across vendors",
                "Show usage patterns"
            ])
        elif query_type == 'facility_analysis':
            suggestions.extend([
                "Compare facility spending",
                "Show regional differences",
                "Analyze facility efficiency"
            ])
        else:
            suggestions.extend([
                "Search for specific items",
                "Analyze vendor performance",
                "Review spending patterns"
            ])
        
        # Add context-specific suggestions
        if context_data.get("vector_results"):
            # If we found good matches, suggest drilling down
            suggestions.append("Get more details on these items")
        
        return suggestions[:4]  # Limit to 4 suggestions
    
    def _get_data_sources(self, context_data: Dict[str, Any]) -> List[str]:
        """
        Identify which data sources were used
        """
        sources = []
        if context_data.get("vector_results"):
            sources.append("Vector Search")
        if context_data.get("sql_analytics"):
            sources.append("SQL Analytics")
        if context_data.get("search_results"):
            sources.append("AI Search")
        return sources
    
    def _extract_entities(self, query: str, entity_type: str = 'vendor') -> List[str]:
        """
        Simple entity extraction for vendor names, items, etc.
        This is a basic implementation - could be enhanced with NER
        """
        # For now, return common keywords that might be entities
        words = query.split()
        
        # Filter out common stop words and short words
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an'}
        entities = [word.strip('.,!?') for word in words 
                   if len(word) > 2 and word.lower() not in stop_words]
        
        return entities[:3]  # Return up to 3 potential entities

# Singleton instance
ai_analysis_service = AIAnalysisService()

def get_ai_analysis_service() -> AIAnalysisService:
    """Get the shared AI analysis service instance"""
    return ai_analysis_service