import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd
import numpy as np
from uuid import uuid4
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
)
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError, ServiceRequestError
from azure.search.documents.models import VectorizedQuery

logger = logging.getLogger(__name__)

class AISearchService:
    """Azure AI Search Service with improved error handling and configuration management"""
    
    def __init__(self):
        # Safe configuration loading with fallbacks
        self.endpoint = self._get_config_value('AZURE_SEARCH_ENDPOINT')
        self.key = self._get_config_value('AZURE_SEARCH_API_KEY')
        self.index_name = self._get_config_value('AZURE_SEARCH_INDEX_NAME', 'supply-records-index')
        
        # If endpoint is empty, try to construct it from service name
        if not self.endpoint:
            service_name = self._get_config_value('AZURE_SEARCH_SERVICE_NAME')
            if service_name:
                self.endpoint = f"https://{service_name}.search.windows.net"
                logger.info(f"Constructed Azure Search endpoint from service name: {self.endpoint}")
        
        # Track if service is properly configured
        self.is_configured = bool(self.endpoint and self.key)
        
        if not self.is_configured:
            logger.warning("Azure AI Search not properly configured. Service will operate in mock mode.")
            self.search_client = None
            self.index_client = None
            return
        
        try:
            self.credential = AzureKeyCredential(self.key)
            self.search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=self.index_name,
                credential=self.credential
            )
            self.index_client = SearchIndexClient(
                endpoint=self.endpoint,
                credential=self.credential
            )
            logger.info(f"Azure AI Search service initialized for index: {self.index_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Azure AI Search: {e}")
            self.is_configured = False
            self.search_client = None
            self.index_client = None
    
    def _get_config_value(self, key: str, default: str = None) -> Optional[str]:
        """Safely get configuration value from settings or environment"""
        try:
            # Try to import settings
            from app.core.config import settings
            
            # Handle special case for AZURE_SEARCH_ENDPOINT
            if key == 'AZURE_SEARCH_ENDPOINT':
                # Try direct access first
                value = getattr(settings, key, None)
                if value:
                    return value
                # Fall back to using the property method
                return settings.get_azure_search_endpoint
            else:
                value = getattr(settings, key, None)
                if value:
                    return value
        except (ImportError, AttributeError) as e:
            logger.debug(f"Settings not available or {key} not found in settings: {e}")
        
        # Fallback to environment variable
        env_value = os.getenv(key, default)
        if env_value:
            logger.debug(f"Using environment variable for {key}")
            return env_value
        
        logger.warning(f"Configuration value {key} not found")
        return default
    
    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to Azure AI Search"""
        if not self.is_configured:
            return {
                "status": "disabled",
                "message": "Azure AI Search not configured",
                "configured": False
            }
        
        try:
            # Try to get document count as a connection test
            count = self.get_document_count()
            return {
                "status": "connected",
                "message": f"Successfully connected to Azure AI Search. Index has {count} documents.",
                "configured": True,
                "document_count": count
            }
        except Exception as e:
            logger.error(f"Azure AI Search connection test failed: {e}")
            return {
                "status": "error",
                "message": f"Connection failed: {str(e)}",
                "configured": True
            }
    
    def upload_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Upload documents to AI Search with proper error handling"""
        if not self.is_configured:
            logger.warning("Attempted to upload documents but Azure AI Search is not configured")
            return {"uploaded": 0, "failed": len(documents), "error": "Service not configured"}
        
        if not documents:
            return {"uploaded": 0, "failed": 0}
        
        try:
            logger.info(f"Uploading {len(documents)} documents to AI Search")
            
            # Normalize documents for AI Search
            normalized_docs = []
            for doc in documents:
                normalized_doc = self._normalize_document_for_search(doc)
                if normalized_doc:  # Only add if normalization succeeded
                    normalized_docs.append(normalized_doc)
            
            if not normalized_docs:
                logger.warning("No valid documents to upload after normalization")
                return {"uploaded": 0, "failed": len(documents), "error": "No valid documents after normalization"}
            
            # Upload in batches to avoid timeout
            batch_size = 100
            total_uploaded = 0
            total_failed = 0
            
            for i in range(0, len(normalized_docs), batch_size):
                batch = normalized_docs[i:i + batch_size]
                try:
                    result = self.search_client.upload_documents(documents=batch)
                    successful_uploads = sum(1 for r in result if r.succeeded)
                    failed_uploads = len(batch) - successful_uploads
                    
                    total_uploaded += successful_uploads
                    total_failed += failed_uploads
                    
                    if failed_uploads > 0:
                        logger.warning(f"Batch {i//batch_size + 1}: {successful_uploads} succeeded, {failed_uploads} failed")
                        
                        # Log failed document details
                        for r in result:
                            if not r.succeeded:
                                logger.error(f"Failed to upload document {r.key}: {r.error_message}")
                
                except Exception as batch_error:
                    logger.error(f"Batch upload failed: {batch_error}")
                    total_failed += len(batch)
                    continue
            
            logger.info(f"Upload completed: {total_uploaded} succeeded, {total_failed} failed")
            return {"uploaded": total_uploaded, "failed": total_failed}
            
        except Exception as e:
            logger.error(f"AI Search upload failed: {e}")
            return {"uploaded": 0, "failed": len(documents), "error": str(e)}
    
    def _normalize_document_for_search(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize document for AI Search with comprehensive field mapping"""
        try:
            # Create rich searchable content from all available fields
            normalized = {
                # Required fields
                'id': str(doc.get('id', uuid4())),
                'content': self._create_comprehensive_searchable_content(doc),
                
                # Map both underscore and PascalCase variants for compatibility
                'TransactionID': str(doc.get('TransactionID', doc.get('transaction_id', ''))),
                'FacilityID': str(doc.get('FacilityID', doc.get('facility_id', ''))),
                'ItemDesc': str(doc.get('ItemDesc', doc.get('item_desc', ''))),
                'Manufacturer': str(doc.get('Manufacturer', doc.get('manufacturer', 'Unknown'))),
                'Vendor': str(doc.get('Vendor', doc.get('vendor', 'Unknown'))),
                'FacilityType': str(doc.get('FacilityType', doc.get('facility_type', 'Unknown'))),
                'Region': str(doc.get('Region', doc.get('region', 'Unknown'))),
                'Department': str(doc.get('Department', doc.get('department', 'Unknown'))),
                'Category': str(doc.get('Category', doc.get('category', 'Unknown'))),
                
                # Numeric fields
                'PricePaid': self._safe_float(doc.get('PricePaid', doc.get('price_paid', 0.0))),
                'TotalSpend': self._safe_float(doc.get('TotalSpend', doc.get('total_spend', 0.0))),
                'Quantity': self._safe_int(doc.get('Quantity', doc.get('quantity', 0))),
                
                # Date field
                'LoadDate': self._normalize_date_for_search(doc.get('LoadDate', doc.get('load_date'))),
                
                # Additional metadata for better search
                'Month': self._safe_int(doc.get('Month', doc.get('month', 0))),
                'Year': self._safe_int(doc.get('Year', doc.get('year', 0))),
                'BatchId': str(doc.get('batch_id', doc.get('BatchId', ''))),
                
                # Store full metadata as JSON for reference
                'metadata': json.dumps(doc, default=str)
            }
            
            # Include vector if present
            if 'content_vector' in doc:
                normalized['content_vector'] = doc['content_vector']
            
            # Clean up - remove None values for optional fields
            cleaned_doc = {}
            for key, value in normalized.items():
                if key == 'LoadDate':
                    # Only include LoadDate if we have a valid date
                    if value and value != '':
                        cleaned_doc[key] = value
                else:
                    # For all other fields, include even if empty
                    cleaned_doc[key] = value if value is not None else ''
            
            return cleaned_doc
            
        except Exception as e:
            logger.error(f"Failed to normalize document for search: {e}")
            logger.debug(f"Problematic document: {doc}")
            return None
    
    def _create_comprehensive_searchable_content(self, doc: Dict[str, Any]) -> str:
        """Create comprehensive searchable content from ALL available fields"""
        content_parts = []
        
        # Primary searchable fields with both naming conventions
        searchable_mappings = [
            # Format: (display_name, [possible_field_names])
            ('Item', ['ItemDesc', 'item_desc']),
            ('Vendor', ['Vendor', 'vendor']),
            ('Manufacturer', ['Manufacturer', 'manufacturer']),
            ('Facility Type', ['FacilityType', 'facility_type']),
            ('Region', ['Region', 'region']),
            ('Department', ['Department', 'department']),
            ('Category', ['Category', 'category']),
            ('Transaction', ['TransactionID', 'transaction_id']),
            ('Facility', ['FacilityID', 'facility_id']),
        ]
        
        for display_name, field_variants in searchable_mappings:
            for field in field_variants:
                value = doc.get(field)
                if value and str(value).strip() and str(value).strip().lower() != 'unknown':
                    content_parts.append(f"{display_name}: {str(value).strip()}")
                    break  # Use first non-empty variant
        
        # Add numeric information
        quantity = doc.get('Quantity', doc.get('quantity'))
        if quantity:
            content_parts.append(f"Quantity: {quantity}")
            
        total_spend = doc.get('TotalSpend', doc.get('total_spend'))
        if total_spend:
            content_parts.append(f"Total Spend: ${total_spend}")
        
        # Add temporal information
        month = doc.get('Month', doc.get('month'))
        year = doc.get('Year', doc.get('year'))
        if month and year:
            month_names = {
                1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December"
            }
            month_name = month_names.get(int(month), f"Month-{month}")
            content_parts.append(f"Date: {month_name} {year}")
        
        return ' | '.join(content_parts) if content_parts else f"Record {doc.get('id', 'unknown')}"
    
    def _normalize_date_for_search(self, date_value: Any) -> Optional[str]:
        """Convert date to proper ISO format for AI Search or return None"""
        if not date_value or date_value == '' or pd.isna(date_value):
            return None
        
        try:
            if isinstance(date_value, str):
                if date_value.strip() == '':
                    return None
                # Try to parse the string date
                parsed_date = pd.to_datetime(date_value)
            elif isinstance(date_value, (datetime, date, pd.Timestamp)):
                parsed_date = pd.to_datetime(date_value)
            else:
                return None
            
            # Return in ISO format with timezone info
            return parsed_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_value}': {e}")
            return None
    
    def _safe_int(self, value: Any) -> int:
        """Safely convert to int"""
        if value is None or pd.isna(value):
            return 0
        try:
            if isinstance(value, str) and value.strip() == '':
                return 0
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    
    def _safe_float(self, value: Any) -> float:
        """Safely convert to float"""
        if value is None or pd.isna(value):
            return 0.0
        try:
            if isinstance(value, str) and value.strip() == '':
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def search_documents(self, query: str, top: int = 50, filters: Optional[str] = None) -> List[Dict]:
        """Search documents in the index"""
        if not self.is_configured:
            logger.warning("Search attempted but Azure AI Search is not configured")
            return []
        
        try:
            search_params = {
                'search_text': query,
                'top': top,
                'include_total_count': True
            }
            
            if filters:
                search_params['filter'] = filters
            
            results = self.search_client.search(**search_params)
            
            documents = []
            for result in results:
                doc = dict(result)
                # Remove the @search.score if present
                doc.pop('@search.score', None)
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def search(self, query: str, top: int = 50) -> List[Dict]:
        """Simplified search interface for compatibility"""
        return self.search_documents(query, top)
    
    def vector_search(self, query_vector: List[float], top: int = 50) -> List[Dict]:
        """Perform vector search with improved result mapping"""
        if not self.is_configured:
            logger.warning("Vector search attempted but Azure AI Search is not configured")
            return []
        
        try:
            # Create proper VectorizedQuery
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="content_vector",
                kind="vector"
            )
            
            results = self.search_client.search(
                search_text=None,
                vector_queries=[vector_query],
                top=top
            )
            
            documents = []
            for result in results:
                doc = dict(result)
                
                # Calculate similarity score from search score
                search_score = doc.get("@search.score", 0)
                # Convert Azure Search score to similarity (0-1 range)
                similarity = min(search_score / 1.0, 1.0) if search_score > 0 else 0.5
                
                # Create normalized document with consistent field mapping
                normalized_doc = {
                    "id": doc.get("id"),
                    "similarity": similarity,
                    
                    # Core fields with fallbacks
                    "TransactionID": doc.get("TransactionID", ""),
                    "FacilityID": doc.get("FacilityID", ""),
                    "ItemDesc": doc.get("ItemDesc", ""),
                    "Vendor": doc.get("Vendor", ""),
                    "Manufacturer": doc.get("Manufacturer", ""),
                    "FacilityType": doc.get("FacilityType", ""),
                    "Region": doc.get("Region", ""),
                    "Department": doc.get("Department", ""),
                    "Category": doc.get("Category", ""),
                    
                    # Numeric fields
                    "TotalSpend": doc.get("TotalSpend", 0),
                    "PricePaid": doc.get("PricePaid", 0),
                    "Quantity": doc.get("Quantity", 0),
                    "Month": doc.get("Month", 0),
                    "Year": doc.get("Year", 0),
                    
                    # Content for display
                    "content": doc.get("content", ""),
                    
                    # Include all original fields for completeness
                    **{k: v for k, v in doc.items() if k not in ["@search.score", "content_vector"]}
                }
                documents.append(normalized_doc)
            
            logger.info(f"Vector search returned {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def delete_documents(self, document_ids: List[str]) -> int:
        """Delete documents by their IDs"""
        if not self.is_configured:
            logger.warning("Delete attempted but Azure AI Search is not configured")
            return 0
        
        try:
            documents_to_delete = [{'id': doc_id} for doc_id in document_ids]
            result = self.search_client.delete_documents(documents=documents_to_delete)
            
            successful_deletes = sum(1 for r in result if r.succeeded)
            logger.info(f"Successfully deleted {successful_deletes}/{len(document_ids)} documents")
            return successful_deletes
            
        except Exception as e:
            logger.error(f"Delete documents failed: {e}")
            return 0
    
    def get_document_count(self) -> int:
        """Get total number of documents in the index"""
        if not self.is_configured:
            return 0
        
        try:
            results = self.search_client.search(
                search_text="*",
                include_total_count=True,
                top=0
            )
            return results.get_count()
        except Exception as e:
            logger.error(f"Failed to get document count: {e}")
            return 0
    
    def create_or_update_index(self):
        """Create or update the search index with comprehensive schema"""
        if not self.is_configured:
            logger.warning("Index creation attempted but Azure AI Search is not configured")
            return False
        
        try:
            # Define comprehensive search index schema
            fields = [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True),
                SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                
                # Core searchable fields
                SearchableField(name="TransactionID", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="FacilityID", type=SearchFieldDataType.String, filterable=True),
                SearchableField(name="ItemDesc", type=SearchFieldDataType.String, analyzer_name="standard.lucene"),
                SearchableField(name="Vendor", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="Manufacturer", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="FacilityType", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="Region", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="Department", type=SearchFieldDataType.String, filterable=True, facetable=True),
                SearchableField(name="Category", type=SearchFieldDataType.String, filterable=True, facetable=True),
                
                # Numeric fields
                SimpleField(name="TotalSpend", type=SearchFieldDataType.Double, filterable=True, sortable=True),
                SimpleField(name="PricePaid", type=SearchFieldDataType.Double, filterable=True, sortable=True),
                SimpleField(name="Quantity", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
                SimpleField(name="Month", type=SearchFieldDataType.Int32, filterable=True, facetable=True),
                SimpleField(name="Year", type=SearchFieldDataType.Int32, filterable=True, facetable=True),
                
                # Date field
                SimpleField(name="LoadDate", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
                
                # Batch tracking
                SimpleField(name="BatchId", type=SearchFieldDataType.String, filterable=True),
                
                # Metadata storage
                SimpleField(name="metadata", type=SearchFieldDataType.String),
                
                # Vector field
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=384,
                    vector_search_profile_name="my-vector-profile"
                ),
            ]
            
            # Configure vector search
            vector_search = VectorSearch(
                profiles=[
                    VectorSearchProfile(
                        name="my-vector-profile",
                        algorithm_configuration_name="my-algorithm-config",
                        kind="hnsw"
                    )
                ],
                algorithms=[
                    HnswAlgorithmConfiguration(
                        name="my-algorithm-config",
                        kind="hnsw",
                        parameters={
                            "m": 4,
                            "efConstruction": 400,
                            "efSearch": 500,
                            "metric": "cosine"
                        }
                    )
                ]
            )
            
            # Create the index
            index = SearchIndex(
                name=self.index_name,
                fields=fields,
                vector_search=vector_search
            )
            
            result = self.index_client.create_or_update_index(index)
            logger.info(f"Created/updated search index: {result.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create/update index: {e}")
            return False

# Safe singleton instance creation
try:
    ai_search_service = AISearchService()
except Exception as e:
    logger.error(f"Failed to create AI Search service instance: {e}")
    # Create a mock service that won't break the application
    ai_search_service = type('MockAISearchService', (), {
        'is_configured': False,
        'upload_documents': lambda self, docs: {"uploaded": 0, "failed": len(docs), "error": "Service not configured"},
        'search': lambda self, query, top=50: [],
        'vector_search': lambda self, vector, top=50: [],
        'get_document_count': lambda self: 0,
        'test_connection': lambda self: {"status": "disabled", "message": "Service initialization failed", "configured": False}
    })()

def get_ai_search_service():
    """Get the shared AI Search service instance"""
    return ai_search_service