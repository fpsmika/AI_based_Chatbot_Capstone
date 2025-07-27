# app/services/embedding_service.py
import os
import uuid
import logging
import pandas as pd
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

        # Get AI Search service
        ai_search = get_ai_search_service()

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
                
                # Prepare documents for AI Search
                documents = []
                for i, (text, metadata, embedding) in enumerate(zip(batch_texts, batch_metas, embeddings)):
                    doc = metadata.copy()  # Start with metadata
                    doc["id"] = str(uuid.uuid4())
                    doc["content"] = text
                    doc["content_vector"] = embedding
                    documents.append(doc)

                # Store in AI Search
                logger.info(f"  Storing embeddings in AI Search...")
                upload_result = ai_search.upload_documents(documents)
                
                successful_batches += 1
                total_processed += upload_result["uploaded"]
                logger.info(f"  ✅ Batch {batch_num} completed successfully ({upload_result['uploaded']} uploaded)")

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
        # Convert records to chunks using the same parser logic
        chunks = []
        for record in records:
            # Create a text representation and metadata for each record
            text_parts = []
            metadata = {}
            
            # Build text description
            for key, value in record.items():
                if value and str(value).strip():
                    if key in ['ItemDesc', 'Vendor', 'Manufacturer', 'Category', 'Department']:
                        text_parts.append(f"{key}: {value}")
                    metadata[key] = value
            
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

        # Get AI Search service
        ai_search = get_ai_search_service()

        for batch_i in range(0, len(chunks), batch_size):
            batch_end = min(batch_i + batch_size, len(chunks))
            batch_texts = texts[batch_i:batch_end]
            batch_metas = metadatas[batch_i:batch_end]

            batch_num = batch_i // batch_size + 1
            logger.info(f"Processing batch {batch_num} ({len(batch_texts)} items)")

            try:
                # Generate embeddings
                embeddings = embed_bulk_text(batch_texts)
                
                # Prepare documents for AI Search
                documents = []
                for text, metadata, embedding in zip(batch_texts, batch_metas, embeddings):
                    doc = metadata.copy()
                    doc["id"] = str(uuid.uuid4())
                    doc["content"] = text
                    doc["content_vector"] = embedding
                    documents.append(doc)

                # Store in AI Search
                upload_result = ai_search.upload_documents(documents)
                
                successful_batches += 1
                total_processed += upload_result["uploaded"]
                logger.info(f"  ✅ Batch {batch_num} completed ({upload_result['uploaded']} uploaded)")

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

def query_similar_embeddings(query_text: str, top_k: int = 15, min_score: float = 0.5) -> List[Dict[str, Any]]:
    """
    Find similar embeddings using Azure AI Search vector search
    Replaces the old SQL-based vector search
    """
    try:
        logger.info(f"Querying similar embeddings for: '{query_text}', top_k: {top_k}")
        
        # Generate embedding for query
        query_vector = embed_text(query_text)
        
        # Use AI Search for vector similarity
        ai_search = get_ai_search_service()
        results = ai_search.vector_search(query_vector, top=top_k)
        
        # Filter by minimum score and format results
        filtered_results = []
        for result in results:
            similarity = result.get("similarity", 0.0)
            if similarity >= min_score:
                filtered_results.append({
                    "id": result.get("id"),
                    "similarity": similarity,
                    "metadata": {
                        "TransactionID": result.get("TransactionID"),
                        "ItemDesc": result.get("ItemDesc"),
                        "Vendor": result.get("Vendor"),
                        "Manufacturer": result.get("Manufacturer"),
                        "TotalSpend": result.get("TotalSpend"),
                        "FacilityType": result.get("FacilityType"),
                        "Region": result.get("Region"),
                        "Department": result.get("Department"),
                        "Category": result.get("Category")
                    }
                })
        
        logger.info(f"Found {len(filtered_results)} similar embeddings")
        return filtered_results
        
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []

def test_embedding_service():
    """
    Test the embedding service functionality with AI Search
    """
    try:
        # Test single text embedding
        test_text = "Surgical gloves size large from MedSupply Corp"
        embedding = embed_text(test_text)
        logger.info(f"Single embedding test: {len(embedding)} dimensions")
        
        # Test bulk embedding
        test_texts = [
            "IV fluid bags 500ml",
            "Heart monitor leads",
            "Disposable syringes 10ml"
        ]
        bulk_embeddings = embed_bulk_text(test_texts)
        logger.info(f"Bulk embedding test: {len(bulk_embeddings)} embeddings")
        
        # Test AI Search connection
        ai_search = get_ai_search_service()
        connection_test = ai_search.test_connection()
        logger.info(f"AI Search connection test: {connection_test}")
        
        return True
    except Exception as e:
        logger.error(f"Embedding service test failed: {e}")
        return False

if __name__ == "__main__":
    # Run test
    success = test_embedding_service()
    print("Embedding service test:", "PASSED" if success else "FAILED")