# app/services/ai.py
import logging
from typing import List, Dict, Any, Optional
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
from app.services.text_to_sql_service import get_text_to_sql_service
import json

logger = logging.getLogger(__name__)

class AIAnalysisService:
    """
    AI service for text-to-SQL analysis only
    """
    
    def __init__(self):
        self.llama_service = LlamaService
        self.sql_service = get_sql_service()
        self.text_to_sql = get_text_to_sql_service()
    
    async def analyze_query(self, user_query: str, context_limit: int = 5) -> Dict[str, Any]:
        """
        Main analysis method using text-to-SQL approach
        """
        try:
            logger.info(f"Analyzing query: '{user_query}'")
            
            # Use text-to-SQL service for analysis
            analysis = self.text_to_sql.analyze_supply_chain_query(user_query)
            
            return {
                "response": analysis["insights"],
                "query_type": "sql_analysis",
                "suggestions": analysis["recommendations"],
                "data_sources": ["SQL Database"]
            }
            
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return {
                "response": f"I encountered an issue analyzing your request: {str(e)}. Please try rephrasing your question.",
                "query_type": "error",
                "suggestions": ["Try rephrasing your question", "Check specific vendor or item names", "Ask about spending trends"],
                "data_sources": []
            }

# Singleton instance
ai_analysis_service = AIAnalysisService()

def get_ai_analysis_service() -> AIAnalysisService:
    """Get the shared AI analysis service instance"""
    return ai_analysis_service