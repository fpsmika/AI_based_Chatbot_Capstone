# app/services/ai_search_service.py
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery
import os
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class AISearchService:
    def __init__(self):
        self.service_name = os.getenv("AZURE_SEARCH_SERVICE_NAME")
        self.index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "supply-records")
        self.api_key = os.getenv("AZURE_SEARCH_API_KEY")
        self.endpoint = f"https://{self.service_name}.search.windows.net"
        
        if not all([self.service_name, self.api_key]):
            raise ValueError("Missing required Azure Search configuration")
        
        self.search_client = SearchClient(
            endpoint=self.endpoint,
            index_name=self.index_name,
            credential=AzureKeyCredential(self.api_key)
        )
        
        self.index_client = SearchIndexClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key)
        )

    def search(self, query: str, filters: str = None, top: int = 5) -> List[Dict[str, Any]]:
        """
        Perform full-text search without vectors
        """
        try:
            logger.info(f"AI Search query: '{query}', top: {top}, filters: {filters}")
            
            search_params = {
                "search_text": query if query != "*" else None,
                "filter": filters,
                "top": top,
                "include_total_count": True
            }
            
            results = self.search_client.search(**search_params)
            
            documents = []
            for result in results:
                # Convert search result to dict and clean up
                doc = dict(result)
                # Remove search score and other internal fields if needed
                doc.pop("@search.score", None)
                doc.pop("@search.highlights", None)
                documents.append(doc)
            
            logger.info(f"AI Search returned {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"AI Search failed: {e}")
            raise

    def vector_search(self, query_vector: List[float], top: int = 5, filters: str = None) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search
        """
        try:
            logger.info(f"Vector search with {len(query_vector)}-dim vector, top: {top}")
            
            # Create vectorized query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="content_vector"  # Make sure this matches your index field name
            )
            
            search_params = {
                "search_text": None,
                "vector_queries": [vector_query],
                "filter": filters,
                "top": top
            }
            
            results = self.search_client.search(**search_params)
            
            documents = []
            for result in results:
                doc = dict(result)
                # Add similarity score from vector search
                doc["similarity"] = doc.pop("@search.score", 0.0)
                doc.pop("@search.highlights", None)
                documents.append(doc)
            
            logger.info(f"Vector search returned {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise

    def hybrid_search(self, query: str, query_vector: List[float] = None, top: int = 5, filters: str = None) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining full-text and vector search
        """
        try:
            logger.info(f"Hybrid search: '{query}', vector: {bool(query_vector)}, top: {top}")
            
            search_params = {
                "search_text": query if query and query != "*" else None,
                "filter": filters,
                "top": top
            }
            
            # Add vector query if provided
            if query_vector:
                vector_query = VectorizedQuery(
                    vector=query_vector,
                    k_nearest_neighbors=top,
                    fields="content_vector"
                )
                search_params["vector_queries"] = [vector_query]
            
            results = self.search_client.search(**search_params)
            
            documents = []
            for result in results:
                doc = dict(result)
                doc["similarity"] = doc.pop("@search.score", 0.0)
                doc.pop("@search.highlights", None)
                documents.append(doc)
            
            logger.info(f"Hybrid search returned {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            raise

    def upload_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Upload documents to Azure AI Search
        Enhanced to handle embeddings if provided
        """
        try:
            logger.info(f"Uploading {len(documents)} documents to AI Search")
            
            # Convert your SQL records to AI Search format
            search_docs = []
            for doc in documents:
                search_doc = {
                    "id": str(doc.get("TransactionID", doc.get("id", ""))),
                    "content": self._create_searchable_content(doc),
                    "TransactionID": str(doc.get("TransactionID", "")),
                    "FacilityID": str(doc.get("FacilityID", "")),
                    "FacilityType": str(doc.get("FacilityType", "")),
                    "Region": str(doc.get("Region", "")),
                    "BedSize": str(doc.get("BedSize", "")),
                    "Vendor": str(doc.get("Vendor", "")),
                    "VendorID": str(doc.get("VendorID", "")),
                    "Manufacturer": str(doc.get("Manufacturer", "")),
                    "ManufacturerID": str(doc.get("ManufacturerID", "")),
                    "ItemDesc": str(doc.get("ItemDesc", "")),
                    "ManufacturercatalogNum": str(doc.get("ManufacturercatalogNum", "")),
                    "Quantity": float(doc.get("Quantity", 0)),
                    "PricePaid": float(doc.get("PricePaid", 0)),
                    "TotalSpend": float(doc.get("TotalSpend", 0)),
                    "Month": int(doc.get("Month", 0)),
                    "Year": int(doc.get("Year", 0)),
                    "LoadDate": str(doc.get("LoadDate", "")),
                    "Department": str(doc.get("Department", "")),
                    "Category": str(doc.get("Category", "")),
                    "metadata": json.dumps(doc)
                }
                
                # Add embedding if provided
                if "content_vector" in doc:
                    search_doc["content_vector"] = doc["content_vector"]
                
                search_docs.append(search_doc)
            
            # Upload in batches to avoid size limits
            batch_size = 1000
            results = []
            for i in range(0, len(search_docs), 1000):  # Smaller batches
                batch = search_docs[i:i+1000]
                try:
                    batch_results = self.search_client.upload_documents(batch)
                    results.extend(batch_results)
                    logger.info(f"Uploaded batch {i//1000 + 1}")
                except Exception as e:
                    logger.error(f"Batch upload failed: {e}")
                    # Retry logic can be added here
            
            return {
                "uploaded": sum(1 for r in results if r.succeeded),
                "failed": len(documents) - sum(1 for r in results if r.succeeded)
            }
        except Exception as e:
            logger.error(f"Upload failed completely: {e}")
            raise

    def upload_documents_with_vectors(self, documents: List[Dict[str, Any]], vectors: List[List[float]]) -> Dict[str, Any]:
        """
        Upload documents along with their vector embeddings
        """
        try:
            if len(documents) != len(vectors):
                raise ValueError("Documents and vectors lists must have the same length")
            
            logger.info(f"Uploading {len(documents)} documents with vectors")
            
            # Add vectors to documents
            enriched_docs = []
            for doc, vector in zip(documents, vectors):
                enriched_doc = doc.copy()
                enriched_doc["content_vector"] = vector
                enriched_docs.append(enriched_doc)
            
            return self.upload_documents(enriched_docs)
            
        except Exception as e:
            logger.error(f"Document upload with vectors failed: {e}")
            raise

    def delete_documents(self, document_ids: List[str]) -> Dict[str, Any]:
        """
        Delete documents from the search index
        """
        try:
            logger.info(f"Deleting {len(document_ids)} documents")
            
            docs_to_delete = [{"id": doc_id} for doc_id in document_ids]
            results = self.search_client.delete_documents(documents=docs_to_delete)
            
            success_count = len([r for r in results if r.succeeded])
            logger.info(f"Successfully deleted {success_count}/{len(document_ids)} documents")
            
            return {
                "deleted": success_count,
                "failed": len(document_ids) - success_count,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Document deletion failed: {e}")
            raise

    def get_document_count(self) -> int:
        """
        Get total number of documents in the index
        """
        try:
            results = self.search_client.search("*", top=0, include_total_count=True)
            return results.get_count()
        except Exception as e:
            logger.error(f"Failed to get document count: {e}")
            return 0

    def _create_searchable_content(self, doc: Dict[str, Any]) -> str:
        """
        Create a searchable content string from document fields
        """
        content_parts = []
        
        # Key fields for search
        key_fields = [
            "ItemDesc", "Vendor", "Manufacturer", "FacilityType", 
            "Region", "Department", "Category", "ManufacturercatalogNum"
        ]
        
        for field in key_fields:
            value = doc.get(field)
            if value and str(value).strip():
                content_parts.append(str(value))
        
        return " | ".join(content_parts)

    def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection to Azure AI Search
        """
        try:
            # Try to get index statistics
            doc_count = self.get_document_count()
            return {
                "status": "connected",
                "service": self.service_name,
                "index": self.index_name,
                "document_count": doc_count
            }
        except Exception as e:
            logger.error(f"AI Search connection test failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

# Singleton instance
ai_search_service = AISearchService()

def get_ai_search_service():
    """Get the shared AI Search service instance"""
    return ai_search_service