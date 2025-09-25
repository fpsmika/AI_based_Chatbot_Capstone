# app/api/routes/search.py
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from app.services.text_to_sql_service import get_text_to_sql_service
import logging

router = APIRouter(prefix="/api/v1/search", tags=["search"])
logger = logging.getLogger(__name__)

@router.get("/business-search")
async def business_search(q: str, limit: int = Query(20, ge=1, le=100)):
    """Business-focused search that delegates to text-to-SQL service"""
    try:
        text_to_sql = get_text_to_sql_service()
        
        # Use your existing business analysis method
        analysis = text_to_sql.analyze_supply_chain_query(q)
        
        return {
            "query": q,
            "success": analysis["success"],
            "insights": analysis.get("insights", ""),
            "data_summary": analysis.get("data_summary", {}),
            "recommendations": analysis.get("recommendations", []),
            "result_count": analysis.get("result_count", 0)
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@router.get("/health")
async def search_health():
    """Health check for search services"""
    try:
        text_to_sql = get_text_to_sql_service()
        # Simple test - this doesn't execute SQL, just checks service availability
        return {
            "status": "healthy",
            "text_to_sql_service": "available"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }