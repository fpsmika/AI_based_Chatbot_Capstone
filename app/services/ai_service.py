import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from app.services.ai_search_service import get_ai_search_service
from app.services.embedding_service import embed_text, query_similar_embeddings

load_dotenv()

LLAMA_API_URL = os.getenv("LLAMA_API_URL")        
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY", "")    

DEFAULT_MAX_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))
DEFAULT_MODEL_NAME = os.getenv("LLAMA_MODEL_NAME", "llama2")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LLAMA_API_KEY}" if LLAMA_API_KEY else ""
}


def generate_response(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, **kwargs: Dict[str, Any]) -> str:
    """
    Generate a completion using the external LLaMA API.
    Compatible with Ollama, Together AI, or other hosted endpoints.
    """
    payload = {
        "model": DEFAULT_MODEL_NAME,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        **kwargs
    }

    try:
        response = requests.post(LLAMA_API_URL, json=payload, headers=HEADERS)
        response.raise_for_status()

        data = response.json()

        # If using TogetherAI or Replicate, the structure may vary
        if "choices" in data:
            return data["choices"][0]["text"].strip()
        elif "response" in data:
            return data["response"].strip()
        else:
            return str(data).strip()

    except requests.RequestException as e:
        print(f" LLaMA API error: {e}")
        return " Error generating response from LLaMA API."

def get_comprehensive_context(query: str, top_k: int = 15) -> Dict[str, Any]:
    """
    Get comprehensive context for a query using multiple search methods
    """
    try:
        ai_search = get_ai_search_service()
        context_sources = []
        
        # 1. Vector search for semantic similarity
        vector_results = query_similar_embeddings(query, top_k=top_k, min_score=0.3)
        if vector_results:
            context_sources.append({
                "type": "vector_search",
                "results": vector_results,
                "count": len(vector_results)
            })
        
        # 2. Enhanced full-text search using comprehensive method
        if ai_search.is_configured:
            fulltext_results = ai_search.search_with_comprehensive_results(query, top=top_k)
            if fulltext_results:
                context_sources.append({
                    "type": "fulltext_search", 
                    "results": fulltext_results,
                    "count": len(fulltext_results)
                })
        
        # 3. Special handling for region queries
        if 'region' in query.lower() and ai_search.is_configured:
            try:
                # Get all unique regions first
                coverage_analysis = ai_search.analyze_index_coverage()
                available_regions = coverage_analysis.get("unique_regions", [])
                
                if available_regions:
                    # Search for documents in each region
                    region_results = []
                    for region in available_regions[:5]:  # Top 5 regions
                        region_docs = ai_search.search(
                            "*", 
                            filters=f"Region eq '{region}'",
                            top=3
                        )
                        region_results.extend(region_docs)
                    
                    if region_results:
                        context_sources.append({
                            "type": "region_specific_search",
                            "results": region_results,
                            "count": len(region_results),
                            "available_regions": available_regions
                        })
            except Exception as region_error:
                logger.warning(f"Region-specific search failed: {region_error}")
        
        # 4. Hybrid approach - combine results
        combined_results = _combine_search_results(context_sources)
        
        return {
            "query": query,
            "total_results": len(combined_results),
            "context_sources": context_sources,
            "combined_results": combined_results,
            "comprehensive_context": _build_comprehensive_context(combined_results)
        }
        
    except Exception as e:
        print(f"Error getting comprehensive context: {e}")
        return {
            "query": query,
            "total_results": 0,
            "context_sources": [],
            "combined_results": [],
            "comprehensive_context": ""
        }

def _combine_search_results(context_sources: List[Dict]) -> List[Dict]:
    """Combine and deduplicate results from multiple search sources"""
    combined = []
    seen_ids = set()
    
    for source in context_sources:
        for result in source["results"]:
            # Extract unique identifier
            if source["type"] == "vector_search":
                metadata = result.get("metadata", {})
                doc_id = metadata.get("TransactionID", metadata.get("transaction_id"))
                result_data = metadata.copy()
                result_data["similarity"] = result.get("similarity", 0)
                result_data["source_type"] = "vector"
            else:
                doc_id = result.get("TransactionID", result.get("id"))
                result_data = result.copy()
                result_data["similarity"] = result.get("@search.score", 0.7)
                result_data["source_type"] = "fulltext"
            
            if doc_id and doc_id not in seen_ids:
                combined.append(result_data)
                seen_ids.add(doc_id)
    
    # Sort by relevance score
    combined.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return combined

def _build_comprehensive_context(results: List[Dict]) -> str:
    """Build comprehensive context string from combined results"""
    if not results:
        return "No relevant data found in the database."
    
    context_parts = []
    
    # Group results by type for better organization
    facilities = set()
    vendors = set()
    regions = set()
    departments = set()
    categories = set()
    total_spend = 0
    
    context_entries = []
    
    for i, result in enumerate(results[:15], 1):  # Top 15 results
        # Extract comprehensive information with multiple field name variants
        item_desc = (result.get("ItemDesc") or result.get("item_desc") or "Unknown Item")
        vendor = (result.get("Vendor") or result.get("vendor") or "Unknown")
        facility_type = (result.get("FacilityType") or result.get("facility_type") or "Unknown")
        region = (result.get("Region") or result.get("region") or "Unknown")
        department = (result.get("Department") or result.get("department") or "Unknown")
        category = (result.get("Category") or result.get("category") or "Unknown")
        
        # Handle nested metadata
        if hasattr(result, 'get') and result.get("metadata"):
            try:
                import json
                metadata = json.loads(result["metadata"]) if isinstance(result["metadata"], str) else result["metadata"]
                if isinstance(metadata, dict):
                    item_desc = item_desc if item_desc != "Unknown Item" else metadata.get("item_desc", "Unknown Item")
                    vendor = vendor if vendor != "Unknown" else metadata.get("vendor", "Unknown")
                    region = region if region != "Unknown" else metadata.get("region", "Unknown")
                    department = department if department != "Unknown" else metadata.get("department", "Unknown")
            except:
                pass
        
        spend = float(result.get("TotalSpend") or result.get("total_spend") or 0)
        quantity = result.get("Quantity") or result.get("quantity") or ""
        
        # Collect for summary
        if facility_type != "Unknown":
            facilities.add(facility_type)
        if vendor != "Unknown":
            vendors.add(vendor)
        if region != "Unknown":
            regions.add(region)
        if department != "Unknown":
            departments.add(department)
        if category != "Unknown":
            categories.add(category)
        total_spend += spend
        
        # Build detailed entry
        entry_parts = [f"Item: {item_desc}"]
        if vendor != "Unknown":
            entry_parts.append(f"Vendor: {vendor}")
        if facility_type != "Unknown":
            entry_parts.append(f"Facility: {facility_type}")
        if region != "Unknown":
            entry_parts.append(f"Region: {region}")
        if department != "Unknown":
            entry_parts.append(f"Department: {department}")
        if category != "Unknown":
            entry_parts.append(f"Category: {category}")
        if spend > 0:
            entry_parts.append(f"Spend: ${spend:,.2f}")
        if quantity:
            entry_parts.append(f"Qty: {quantity}")
        
        similarity = result.get("similarity", result.get("@search.score", 0))
        source_type = result.get("source_type", result.get("search_type", "unknown"))
        entry_parts.append(f"Relevance: {similarity:.3f} ({source_type})")
        
        context_entries.append(f"{i}. {' | '.join(entry_parts)}")
    
    # Build comprehensive summary
    summary_parts = []
    if facilities:
        summary_parts.append(f"Facilities: {', '.join(sorted(facilities))}")
    if vendors:
        summary_parts.append(f"Vendors: {', '.join(sorted(vendors))}")
    if regions:
        summary_parts.append(f"Regions: {', '.join(sorted(regions))}")
    if departments:
        summary_parts.append(f"Departments: {', '.join(sorted(departments))}")
    if categories:
        summary_parts.append(f"Categories: {', '.join(sorted(categories))}")
    if total_spend > 0:
        summary_parts.append(f"Total Spend: ${total_spend:,.2f}")
    
    # Combine all context
    context_parts.append("=== DATA SUMMARY ===")
    context_parts.extend(summary_parts)
    context_parts.append(f"\n=== DETAILED RECORDS ({len(context_entries)} items) ===")
    context_parts.extend(context_entries)
    
    return "\n".join(context_parts)

def get_intelligent_response(query: str, context_data: Dict[str, Any] = None) -> str:
    """
    Generate intelligent response using comprehensive context
    """
    # Get comprehensive context if not provided
    if not context_data:
        context_data = get_comprehensive_context(query)
    
    comprehensive_context = context_data.get("comprehensive_context", "")
    total_results = context_data.get("total_results", 0)
    
    if total_results == 0:
        return "I don't have any data in the system that matches your query. Please ensure data has been uploaded and indexed properly."
    
    # Build enhanced prompt
    system_prompt = """You are Earl, an expert AI assistant for healthcare supply chain analysis. 
    
Use the provided data context to answer questions comprehensively. Include:
- Specific numbers, vendors, facilities, and departments when available
- Trends and patterns you can identify
- Actionable insights and recommendations
- Clear, professional responses without technical jargon

If the context doesn't fully answer the question, explain what information is available and what might be missing."""
    
    full_prompt = f"""{system_prompt}

CONTEXT DATA:
{comprehensive_context}

USER QUESTION: {query}

RESPONSE:"""
    
    return generate_response(full_prompt, max_tokens=600)
