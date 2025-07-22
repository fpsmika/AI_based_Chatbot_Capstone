from fastapi import APIRouter, HTTPException
from typing import Any, List, Dict
from app.services.cosmos_service import get_cosmos_service
import logging

router = APIRouter()


@router.get("/", response_model=List[Dict[str, Any]], summary="Search Items")
async def search_items(query: str):
    """
    Search Cosmos DB supply_records collection for items matching the query.
    """
    container = get_cosmos_service()

    sql = f"""
    SELECT *
      FROM c
     WHERE CONTAINS(LOWER(c.item_desc), "{query.lower()}")
        OR CONTAINS(LOWER(c.vendor),      "{query.lower()}")
        OR CONTAINS(LOWER(c.manufacturer),"{query.lower()}")
    """

    try:
        items = list(
            container.query_items(
                sql,
                enable_cross_partition_query=True
            )
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Cosmos query_items failed: {e}"
        )

    return items
