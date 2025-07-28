# app/services/embedding_service.py
import os
import uuid
import logging
import pandas as pd
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.ai_search_service import get_ai_search_service

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s] %(message)s"))
logger.addHandler(handler)

_model = None

def _load_model():
    """Load the sentence transformer model"""
    from sentence_transformers import SentenceTransformer
    model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    logger.info(f"Loading embedding model: {model_name}")
    return SentenceTransformer(model_name)

def embed_text(text: str) -> List[float]:
    """
    Embed a single text string
    """
    global _model
    if _model is None:
        _model = _load_model()
    
    embedding = _model.encode([text], convert_to_numpy=True, show_progress_bar=False)
    return embedding[0].tolist()

def embed_bulk_text(texts: List[str]) -> List[List[float]]:
    """
    Embed multiple text strings
    """
    global _model
    if _model is None:
        _model = _load_model()
    
    # Returns numpy array; convert to lists
    embeddings = _model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()

def process_and_embed_csv(file_path: str, batch_size: int = 500) -> Dict[str, Any]:
    """
    Process a CSV file and embed all chunks, storing them in Azure AI Search
    """
    logger.info(f"Starting embedding pipeline for file: {file_path}")
    
    try:
        # Check if AI Search is available
        ai_search = get_ai_search_service()
        if not ai_search.is_configured:
            logger.warning("Azure AI Search is not configured. Skipping embedding process.")
            return {
                "success": False,
                "message": "Azure AI Search is not configured. Please check your environment variables.",
                "chunks_processed": 0
            }

        # 1) Read CSV file (without lowercasing headers)
        df = pd.read_csv(file_path)
        logger.info(f"Loaded CSV with {len(df)} rows and columns: {list(df.columns)}")

        # 2) Convert to text+metadata chunks
        chunks = csv_to_purchase_chunks(df)
        total_chunks = len(chunks)
        logger.info(f"Parsed {total_chunks} chunks from data.")

        if total_chunks == 0:
            return {
                "success": False,
                "message": "No chunks were generated from the CSV file. Please check the data format.",
                "chunks_processed": 0
            }

        # 3) Prepare texts and metadata
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]

        successful_batches = 0
        total_processed = 0

        # 4) Process in batches
        for batch_i in range(0, total_chunks, batch_size):
            batch_end = min(batch_i + batch_size, total_chunks)
            batch_texts = texts[batch_i:batch_end]
            batch_metas = metadatas[batch_i:batch_end]

            batch_num = batch_i // batch_size + 1
            logger.info(f"Processing batch {batch_num} ({len(batch_texts)} items)")

            try:
                # Generate embeddings for this batch
                logger.info(f"  Generating embeddings...")
                embeddings = embed_bulk_text(batch_texts)
                
                # Prepare documents for AI Search with comprehensive field mapping
                documents = []
                for i, (text, metadata, embedding) in enumerate(zip(batch_texts, batch_metas, embeddings)):
                    # Create comprehensive document with proper field mapping
                    doc = {
                        "id": str(uuid.uuid4()),
                        "content": text,
                        "content_vector": embedding,
                        
                        # Map all possible field variants for maximum compatibility
                        "TransactionID": str(metadata.get("transaction_id", metadata.get("TransactionID", ""))),
                        "FacilityID": str(metadata.get("facility_id", metadata.get("FacilityID", ""))),
                        "FacilityType": str(metadata.get("facility_type", metadata.get("FacilityType", "Unknown"))),
                        "Region": str(metadata.get("region", metadata.get("Region", "Unknown"))),
                        "ItemDesc": str(metadata.get("item_desc", metadata.get("ItemDesc", ""))),
                        "Vendor": str(metadata.get("vendor", metadata.get("Vendor", "Unknown"))),
                        "Manufacturer": str(metadata.get("manufacturer", metadata.get("Manufacturer", "Unknown"))),
                        "Department": str(metadata.get("department", metadata.get("Department", "Unknown"))),
                        "Category": str(metadata.get("category", metadata.get("Category", "Unknown"))),
                        
                        # Additional fields to match your index
                        "VendorID": str(metadata.get("vendor_id", metadata.get("VendorID", ""))),
                        "ManufacturerID": str(metadata.get("manufacturer_id", metadata.get("ManufacturerID", ""))),
                        "ManufacturercatalogNum": str(metadata.get("manufacturercatalognum", metadata.get("catalog_num", ""))),
                        "BedSize": str(metadata.get("bed_size", metadata.get("BedSize", ""))),
                        
                        # Numeric fields with fallbacks
                        "TotalSpend": float(metadata.get("total_spend", metadata.get("TotalSpend", 0))),
                        "PricePaid": float(metadata.get("price_paid", metadata.get("PricePaid", 0))),
                        "UnitCost": float(metadata.get("unit_cost", metadata.get("UnitCost", 0))),
                        "Quantity": int(metadata.get("quantity", metadata.get("Quantity", 0))),
                        "Month": int(metadata.get("month", metadata.get("Month", 0))),
                        "Year": int(metadata.get("year", metadata.get("Year", 0))),
                        
                        # FIXED: Use batch_id (lowercase) to match your index schema
                        "batch_id": str(metadata.get("batch_id", "")),
                        
                        # Store original metadata for reference
                        "metadata": json.dumps(metadata, default=str)
                    }
                    documents.append(doc)

                # Store in AI Search
                logger.info(f"  Storing embeddings in AI Search...")
                upload_result = ai_search.upload_documents(documents)
                
                if upload_result.get("uploaded", 0) > 0:
                    successful_batches += 1
                    total_processed += upload_result["uploaded"]
                    logger.info(f"  ✅ Batch {batch_num} completed successfully ({upload_result['uploaded']} uploaded)")
                else:
                    logger.error(f"  ✖️ Batch {batch_num} failed: {upload_result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"  ✖️ Batch {batch_num} failed: {e}")
                continue

        logger.info(f"Embedding pipeline completed: {total_processed}/{total_chunks} chunks processed successfully")
        
        return {
            "success": True,
            "message": f"Successfully processed {total_processed} out of {total_chunks} chunks",
            "chunks_processed": total_processed,
            "batches_successful": successful_batches,
            "batches_total": (total_chunks + batch_size - 1) // batch_size
        }

    except Exception as e:
        logger.error(f"Embedding pipeline failed: {e}")
        return {
            "success": False,
            "message": f"Failed to process CSV file: {str(e)}",
            "chunks_processed": 0
        }

def process_and_embed_records(records: List[Dict], batch_size: int = 500) -> Dict[str, Any]:
    """
    Process a list of records, embed them, and store in AI Search
    """
    logger.info(f"Starting embedding pipeline for {len(records)} records")
    
    try:
        # Check if AI Search is available
        ai_search = get_ai_search_service()
        if not ai_search.is_configured:
            logger.warning("Azure AI Search is not configured. Skipping embedding process.")
            return {
                "success": False,
                "message": "Azure AI Search is not configured. Please check your environment variables.",
                "chunks_processed": 0
            }

        # Convert records to chunks using enhanced logic
        chunks = []
        for record in records:
            # Create comprehensive text representation
            text_parts = []
            metadata = record.copy()  # Start with full record as metadata
            
            # Build rich text description with all available information
            searchable_fields = [
                ('Item Description', ['ItemDesc', 'item_desc']),
                ('Vendor', ['Vendor', 'vendor']),
                ('Manufacturer', ['Manufacturer', 'manufacturer']),
                ('Facility Type', ['FacilityType', 'facility_type']),
                ('Region', ['Region', 'region']),
                ('Department', ['Department', 'department']),
                ('Category', ['Category', 'category']),
            ]
            
            for display_name, field_variants in searchable_fields:
                for field in field_variants:
                    value = record.get(field)
                    if value and str(value).strip() and str(value).strip().lower() not in ['unknown', 'null', 'none']:
                        text_parts.append(f"{display_name}: {value}")
                        break
            
            # Add numeric information if available
            quantity = record.get('Quantity', record.get('quantity'))
            if quantity:
                text_parts.append(f"Quantity: {quantity}")
                
            total_spend = record.get('TotalSpend', record.get('total_spend'))
            if total_spend:
                text_parts.append(f"Total Spend: ${total_spend}")
            
            # Add temporal information
            month = record.get('Month', record.get('month'))
            year = record.get('Year', record.get('year'))
            if month and year:
                month_names = {
                    1: "January", 2: "February", 3: "March", 4: "April",
                    5: "May", 6: "June", 7: "July", 8: "August",
                    9: "September", 10: "October", 11: "November", 12: "December"
                }
                month_name = month_names.get(int(month), f"Month-{month}")
                text_parts.append(f"Date: {month_name} {year}")
            
            if text_parts:
                chunk_text = " | ".join(text_parts)
                chunks.append({
                    "text": chunk_text,
                    "metadata": metadata
                })

        if not chunks:
            return {
                "success": False,
                "message": "No valid chunks generated from records",
                "chunks_processed": 0
            }

        # Process chunks in batches
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]

        total_processed = 0
        successful_batches = 0

        for batch_i in range(0, len(chunks), batch_size):
            batch_end = min(batch_i + batch_size, len(chunks))
            batch_texts = texts[batch_i:batch_end]
            batch_metas = metadatas[batch_i:batch_end]

            batch_num = batch_i // batch_size + 1
            logger.info(f"Processing batch {batch_num} ({len(batch_texts)} items)")

            try:
                # Generate embeddings
                embeddings = embed_bulk_text(batch_texts)
                
                # Prepare documents for AI Search with comprehensive mapping
                documents = []
                for text, metadata, embedding in zip(batch_texts, batch_metas, embeddings):
                    doc = {
                        "id": str(uuid.uuid4()),
                        "content": text,
                        "content_vector": embedding,
                        
                        # Comprehensive field mapping
                        "TransactionID": str(metadata.get("transaction_id", metadata.get("TransactionID", ""))),
                        "FacilityID": str(metadata.get("facility_id", metadata.get("FacilityID", ""))),
                        "FacilityType": str(metadata.get("facility_type", metadata.get("FacilityType", "Unknown"))),
                        "Region": str(metadata.get("region", metadata.get("Region", "Unknown"))),
                        "ItemDesc": str(metadata.get("item_desc", metadata.get("ItemDesc", ""))),
                        "Vendor": str(metadata.get("vendor", metadata.get("Vendor", "Unknown"))),
                        "Manufacturer": str(metadata.get("manufacturer", metadata.get("Manufacturer", "Unknown"))),
                        "Department": str(metadata.get("department", metadata.get("Department", "Unknown"))),
                        "Category": str(metadata.get("category", metadata.get("Category", "Unknown"))),
                        
                        # Additional fields
                        "VendorID": str(metadata.get("vendor_id", metadata.get("VendorID", ""))),
                        "ManufacturerID": str(metadata.get("manufacturer_id", metadata.get("ManufacturerID", ""))),
                        "ManufacturercatalogNum": str(metadata.get("manufacturercatalognum", metadata.get("catalog_num", ""))),
                        "BedSize": str(metadata.get("bed_size", metadata.get("BedSize", ""))),
                        
                        # Numeric fields
                        "TotalSpend": float(metadata.get("total_spend", metadata.get("TotalSpend", 0))),
                        "PricePaid": float(metadata.get("price_paid", metadata.get("PricePaid", 0))),
                        "UnitCost": float(metadata.get("unit_cost", metadata.get("UnitCost", 0))),
                        "Quantity": int(metadata.get("quantity", metadata.get("Quantity", 0))),
                        "Month": int(metadata.get("month", metadata.get("Month", 0))),
                        "Year": int(metadata.get("year", metadata.get("Year", 0))),
                        
                        # FIXED: Use batch_id (lowercase) to match your index schema
                        "batch_id": str(metadata.get("batch_id", "")),
                        
                        # Full metadata
                        "metadata": json.dumps(metadata, default=str)
                    }
                    documents.append(doc)

                # Store in AI Search
                upload_result = ai_search.upload_documents(documents)
                
                if upload_result.get("uploaded", 0) > 0:
                    successful_batches += 1
                    total_processed += upload_result["uploaded"]
                    logger.info(f"  ✅ Batch {batch_num} completed ({upload_result['uploaded']} uploaded)")
                else:
                    logger.error(f"  ✖️ Batch {batch_num} failed: {upload_result.get('error', 'Unknown error')}")

            except Exception as e:
                logger.error(f"  ✖️ Batch {batch_num} failed: {e}")
                continue

        return {
            "success": True,
            "message": f"Successfully processed {total_processed} out of {len(chunks)} records",
            "chunks_processed": total_processed,
            "batches_successful": successful_batches
        }

    except Exception as e:
        logger.error(f"Record embedding pipeline failed: {e}")
        return {
            "success": False,
            "message": f"Failed to process records: {str(e)}",
            "chunks_processed": 0
        }

def _parse_stored_metadata(metadata_str: str) -> Dict[str, Any]:
    """Parse stored JSON metadata safely"""
    try:
        if metadata_str:
            import json
            parsed = json.loads(metadata_str)
            if isinstance(parsed, dict):
                return parsed
    except Exception as e:
        logger.debug(f"Failed to parse metadata: {e}")
    return {}

def query_similar_embeddings(query_text: str, top_k: int = 15, min_score: float = 0.3) -> List[Dict[str, Any]]:
    """
    Find similar embeddings using Azure AI Search vector search with improved result mapping
    """
    try:
        logger.info(f"Querying similar embeddings for: '{query_text}', top_k: {top_k}, min_score: {min_score}")
        
        # Check if AI Search is available
        ai_search = get_ai_search_service()
        if not ai_search.is_configured:
            logger.warning("Azure AI Search is not configured. Returning empty results.")
            return []
        
        # Generate embedding for query
        query_vector = embed_text(query_text)
        logger.info(f"Generated query vector with {len(query_vector)} dimensions")
        
        # Use AI Search for vector similarity
        results = ai_search.vector_search(query_vector, top=top_k * 2)  # Get more results to filter
        logger.info(f"AI Search returned {len(results)} raw results")
        
        # Filter by minimum score and format results properly
        filtered_results = []
        for result in results:
            similarity = result.get("similarity", 0.5)
            
            if similarity >= min_score:
                # Create comprehensive metadata from the result
                metadata = {
                    "TransactionID": result.get("TransactionID", ""),
                    "FacilityID": result.get("FacilityID", ""),
                    "ItemDesc": result.get("ItemDesc", ""),
                    "Vendor": result.get("Vendor", "Unknown"),
                    "Manufacturer": result.get("Manufacturer", "Unknown"),
                    "FacilityType": result.get("FacilityType", "Unknown"),
                    "Region": result.get("Region", "Unknown"),
                    "Department": result.get("Department", "Unknown"),
                    "Category": result.get("Category", "Unknown"),
                    "TotalSpend": result.get("TotalSpend", 0),
                    "PricePaid": result.get("PricePaid", 0),
                    "Quantity": result.get("Quantity", 0),
                    "Month": result.get("Month", 0),
                    "Year": result.get("Year", 0),
                    "BatchId": result.get("BatchId", ""),
                    
                    # Include searchable content for display
                    "content": result.get("content", ""),
                    
                    # Try to parse stored metadata if available
                    **_parse_stored_metadata(result.get("metadata", "{}"))
                }
                
                filtered_results.append({
                    "id": result.get("id"),
                    "similarity": similarity,
                    "metadata": metadata,
                    "source": "vector_search"
                })
        
        # Sort by similarity score
        filtered_results.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Limit to requested number
        final_results = filtered_results[:top_k]
        
        logger.info(f"Returning {len(final_results)} filtered results (min_score: {min_score})")
        return final_results
        
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []

def test_embedding_service():
    """
    Test the embedding service functionality with AI Search
    """
    try:
        logger.info("Testing embedding service...")
        
        # Test single text embedding
        test_text = "Surgical gloves size large from MedSupply Corp in Emergency Department"
        embedding = embed_text(test_text)
        logger.info(f"✅ Single embedding test: {len(embedding)} dimensions")
        
        # Test bulk embedding
        test_texts = [
            "IV fluid bags 500ml from Cardinal Health",
            "Heart monitor leads from Philips Medical",
            "Disposable syringes 10ml from BD Medical"
        ]
        bulk_embeddings = embed_bulk_text(test_texts)
        logger.info(f"✅ Bulk embedding test: {len(bulk_embeddings)} embeddings")
        
        # Test AI Search connection
        ai_search = get_ai_search_service()
        connection_test = ai_search.test_connection()
        logger.info(f"✅ AI Search connection test: {connection_test}")
        
        # Test vector search if AI Search is available
        if ai_search.is_configured:
            logger.info("Testing vector search...")
            search_results = query_similar_embeddings("medical supplies", top_k=3, min_score=0.1)
            logger.info(f"✅ Vector search test: {len(search_results)} results found")
        else:
            logger.warning("⚠️ AI Search not configured, skipping vector search test")
        
        return connection_test.get("status") in ["connected", "disabled"]
        
    except Exception as e:
        logger.error(f"❌ Embedding service test failed: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    


def quick_region_test():
    """Quick test to see what regions are available"""
    print("🔍 Quick region test...")
    
    # Test the exact query from your logs
    query = "can you give me a list of regions listed in the doc? briefly"
    results = query_similar_embeddings(query, top_k=5, min_score=0.3)
    
    print(f"Query: '{query}'")
    print(f"Results found: {len(results)}")
    
    regions = set()
    for i, result in enumerate(results):
        metadata = result.get('metadata', {})
        region = metadata.get('Region', metadata.get('region', 'Unknown'))
        regions.add(region)
        
        print(f"\nResult {i+1}:")
        print(f"  Region: {region}")
        print(f"  Content: {result.get('content', 'NO_CONTENT')[:100]}...")
        print(f"  Similarity: {result.get('similarity', 0):.3f}")
    
    print(f"\nUnique regions found: {list(regions)}")
    
    # Also test with a simpler query
    simple_results = query_similar_embeddings("region", top_k=10, min_score=0.2)
    simple_regions = set()
    for result in simple_results:
        metadata = result.get('metadata', {})
        region = metadata.get('Region', metadata.get('region', 'Unknown'))
        if region != 'Unknown':
            simple_regions.add(region)
    
    print(f"Regions from simple 'region' query: {list(simple_regions)}")

if __name__ == "__main__":
    quick_region_test()

if __name__ == "__main__":
    # Run test
    success = test_embedding_service()
    print("Embedding service test:", "✅ PASSED" if success else "❌ FAILED")