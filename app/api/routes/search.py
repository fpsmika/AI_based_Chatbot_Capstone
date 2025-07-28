# app/api/routes/search.py
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.services.sql_service import get_sql_service
from app.services.embedding_service import embed_text, query_similar_embeddings  # Updated imports
from app.services.ai_search_service import get_ai_search_service  # Updated import
import logging
from datetime import datetime

router = APIRouter(prefix="/api/v1/search", tags=["search"])
logger = logging.getLogger(__name__)

class SimilarResult(BaseModel):
    metadata: Dict[str, Any]
    similarity: float
    source: Optional[str] = None

class VendorSpendResult(BaseModel):
    vendor: str
    total_spend: float
    matching_items: int
    items: List[Dict[str, Any]]

class ItemSpendResult(BaseModel):
    item_query: str
    total_spend: float
    matching_items: int
    items: List[Dict[str, Any]]

class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]
    total_count: int
    query_time_ms: float

from fastapi import APIRouter, HTTPException
from app.services.embedding_service import query_similar_embeddings

router = APIRouter()

@router.get("/vector-search")
async def vector_search(q: str, top_k: int = 10):
    try:
        results = query_similar_embeddings(q, top_k)
        return {
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    
    
@router.get("/ai-search", response_model=SearchResponse, summary="Full-text AI Search")
async def ai_search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(15, ge=1, le=100),
    filters: str = Query(None, description="OData filter expression"),
    offset: int = Query(0, ge=0)
):
    """Search using Azure AI Search full-text search"""
    start_time = datetime.now()
    try:
        ai_search_service = get_ai_search_service()
        results = ai_search_service.search(q, filters=filters, top=top_k + offset)
        
        # Apply pagination
        paginated_results = results[offset:offset + top_k]
        
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        return SearchResponse(
            results=paginated_results,
            total_count=len(results),
            query_time_ms=query_time
        )
    except Exception as e:
        logger.error(f"AI Search failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI Search failed: {e}")

@router.get("/hybrid-search", response_model=SearchResponse, summary="Hybrid vector + full-text search")
async def hybrid_search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(15, ge=1, le=50),
    min_score: float = Query(0.5, ge=0, le=1),
    filters: str = Query(None, description="OData filter expression"),
    offset: int = Query(0, ge=0)
):
    """Combine vector and full-text search results using AI Search"""
    start_time = datetime.now()
    try:
        logger.info(f"Hybrid search query: '{q}', top_k: {top_k}, min_score: {min_score}")
        
        ai_search_service = get_ai_search_service()
        
        # Option 1: Use AI Search's native hybrid search if available
        try:
            # Generate query vector for hybrid search
            query_vector = embed_text(q)
            
            # Use AI Search hybrid search capability
            results = ai_search_service.hybrid_search(
                query=q, 
                query_vector=query_vector, 
                top=top_k + offset,
                filters=filters
            )
            
            # Filter by minimum score and apply pagination
            filtered_results = [
                {"metadata": r, "similarity": r.get("similarity", 0.0), "source": "hybrid_ai_search"}
                for r in results 
                if r.get("similarity", 0.0) >= min_score
            ]
            
        except Exception as hybrid_error:
            logger.warning(f"Native hybrid search failed, falling back to separate searches: {hybrid_error}")
            
            # Option 2: Fallback - combine separate vector and full-text searches
            vector_results = query_similar_embeddings(q, top_k=top_k + offset, min_score=min_score)
            ai_results = ai_search_service.search(q, filters=filters, top=top_k + offset)
            
            # Combine and deduplicate
            combined = []
            seen_ids = set()
            
            # Add vector results
            for r in vector_results:
                doc_id = r["metadata"].get("TransactionID") or str(hash(frozenset(r["metadata"].items())))
                if doc_id not in seen_ids:
                    combined.append({
                        "metadata": r["metadata"], 
                        "similarity": r["similarity"], 
                        "source": "vector"
                    })
                    seen_ids.add(doc_id)
            
            # Add AI Search results
            for r in ai_results:
                doc_id = r.get("TransactionID") or str(hash(frozenset(r.items())))
                if doc_id not in seen_ids:
                    combined.append({
                        "metadata": r, 
                        "similarity": 0.7,  # Default similarity for full-text
                        "source": "ai_search"
                    })
                    seen_ids.add(doc_id)
            
            # Sort by similarity
            combined.sort(key=lambda x: x["similarity"], reverse=True)
            filtered_results = combined
        
        # Apply pagination
        paginated_results = filtered_results[offset:offset + top_k]
        
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        return SearchResponse(
            results=paginated_results,
            total_count=len(filtered_results),
            query_time_ms=query_time
        )
        
    except Exception as e:
        logger.error(f"Hybrid search failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Hybrid search failed: {e}")

@router.get("/analytics/vendor-spend", response_model=VendorSpendResult)
async def vendor_total_spend(
    vendor: str = Query(..., description="Vendor name (case insensitive)"),
    min_score: float = Query(0.3, ge=0, le=1),
    include_items: bool = Query(False, description="Include individual items in response")
):
    """Calculate total spend for a vendor using AI Search"""
    try:
        logger.info(f"Vendor spend analysis for: '{vendor}'")
        
        # Use AI Search to find vendor-related items
        ai_search_service = get_ai_search_service()
        results = ai_search_service.search(
            query=vendor,
            filters=f"search.ismatch('{vendor}', 'Vendor')",
            top=1000
        )
        
        if not results:
            return VendorSpendResult(
                vendor=vendor,
                total_spend=0.0,
                matching_items=0,
                items=[]
            )
        
        # Calculate total spend
        total_spend = 0.0
        items = []
        
        for r in results:
            spend = float(r.get("TotalSpend", 0))
            total_spend += spend
            
            if include_items:
                items.append({
                    "item_desc": r.get("ItemDesc", ""),
                    "vendor": r.get("Vendor", ""),
                    "total_spend": spend,
                    "facility_type": r.get("FacilityType", ""),
                    "department": r.get("Department", "")
                })
        
        logger.info(f"Found {len(results)} items for vendor '{vendor}' with total spend: ${total_spend:,.2f}")
        
        return VendorSpendResult(
            vendor=vendor,
            total_spend=total_spend,
            matching_items=len(results),
            items=items
        )
        
    except Exception as e:
        logger.error(f"Vendor analytics failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Vendor analytics failed: {e}")

@router.get("/analytics/item-spend", response_model=ItemSpendResult)
async def item_total_spend(
    item: str = Query(..., description="Item description fragment"),
    min_score: float = Query(0.4, ge=0, le=1),
    include_items: bool = Query(False, description="Include individual items in response")
):
    """Calculate total spend for items matching description using AI Search"""
    try:
        logger.info(f"Item spend analysis for: '{item}'")
        
        # Use AI Search
        ai_search_service = get_ai_search_service()
        results = ai_search_service.search(
            query=item,
            filters=f"search.ismatch('{item}', 'ItemDesc')",
            top=1000
        )
        
        if not results:
            return ItemSpendResult(
                item_query=item,
                total_spend=0.0,
                matching_items=0,
                items=[]
            )
        
        # Calculate total spend
        total_spend = 0.0
        items = []
        
        for r in results:
            spend = float(r.get("TotalSpend", 0))
            total_spend += spend
            
            if include_items:
                items.append({
                    "item_desc": r.get("ItemDesc", ""),
                    "vendor": r.get("Vendor", ""),
                    "total_spend": spend,
                    "facility_type": r.get("FacilityType", ""),
                    "department": r.get("Department", ""),
                    "category": r.get("Category", "")
                })
        
        logger.info(f"Found {len(results)} matching items for '{item}' with total spend: ${total_spend:,.2f}")
        
        return ItemSpendResult(
            item_query=item,
            total_spend=total_spend,
            matching_items=len(results),
            items=items
        )
        
    except Exception as e:
        logger.error(f"Item analytics failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Item analytics failed: {e}")

@router.get("/analytics/facility-spend", summary="Spend analysis by facility type")
async def facility_spend_analysis(
    facility_type: str = Query(None, description="Filter by facility type"),
    region: str = Query(None, description="Filter by region")
):
    """Analyze spending by facility type and region using AI Search"""
    try:
        # Build search query
        ai_search_service = get_ai_search_service()
        filters = []
        if facility_type:
            filters.append(f"FacilityType eq '{facility_type}'")
        if region:
            filters.append(f"Region eq '{region}'")
        
        filter_str = " and ".join(filters) if filters else None
        results = ai_search_service.search("*", filters=filter_str, top=1000)
        
        # Group by facility type and region
        facility_stats = {}
        
        for r in results:
            ftype = r.get("FacilityType", "Unknown")
            fregion = r.get("Region", "Unknown")
            spend = float(r.get("TotalSpend", 0))
            
            key = f"{ftype}|{fregion}"
            if key not in facility_stats:
                facility_stats[key] = {
                    "facility_type": ftype,
                    "region": fregion,
                    "total_spend": 0.0,
                    "item_count": 0
                }
            
            facility_stats[key]["total_spend"] += spend
            facility_stats[key]["item_count"] += 1
        
        # Convert to list and sort by spend
        results_list = list(facility_stats.values())
        results_list.sort(key=lambda x: x["total_spend"], reverse=True)
        
        return {
            "facility_analysis": results_list,
            "total_facilities": len(results_list),
            "query_used": filter_str or "All facilities"
        }
        
    except Exception as e:
        logger.error(f"Facility analytics failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Facility analytics failed: {e}")

@router.get("/health")
async def search_health():
    """Health check for all search services"""
    try:
        # Test SQL connection
        sql_service = get_sql_service()
        sql_test = sql_service.test_connection()
        
        # Test AI Search connection
        ai_search_service = get_ai_search_service()
        ai_search_test = ai_search_service.test_connection()
        
        # Test embedding service
        from app.services.embedding_service import test_embedding_service
        embedding_test = test_embedding_service()
        
        return {
            "status": "healthy",
            "sql_connection": sql_test,
            "ai_search_connection": ai_search_test,
            "embedding_service": embedding_test
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }