import os
import json
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime, date
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
        self.index_name = self._get_config_value('AZURE_SEARCH_INDEX_NAME', 'chatbot-index-1')
        
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
        
        # SIMPLIFIED: No separate chat index - use main index for everything
        # Your chatbot-index-1 already has all necessary fields
        
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

    def _normalize_date_for_search(self, date_value: Any) -> Optional[str]:
        """Convert date to proper ISO format for AI Search or return None"""
        if not date_value or date_value == '' or pd.isna(date_value):
            return None
        
        try:
            if isinstance(date_value, str):
                parsed_date = pd.to_datetime(date_value)
            elif isinstance(date_value, (datetime, date, pd.Timestamp)):
                parsed_date = pd.to_datetime(date_value)
            else:
                parsed_date = pd.to_datetime(str(date_value))
            
            # FIXED: Return in proper DateTimeOffset format without microseconds
            return parsed_date.strftime('%Y-%m-%dT%H:%M:%SZ')
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_value}': {e}")
            return None

    def _normalize_document_for_search(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize document for AI Search with comprehensive field mapping"""
        try:
            # Create rich searchable content from all available fields
            normalized = {
                'id': str(doc.get('id', uuid4())),
                'content': self._create_comprehensive_searchable_content(doc),
                'TransactionID': str(doc.get('TransactionID', doc.get('transaction_id', ''))),
                'FacilityID': str(doc.get('FacilityID', doc.get('facility_id', ''))),
                'ItemDesc': str(doc.get('ItemDesc', doc.get('item_desc', ''))),
                'Manufacturer': str(doc.get('Manufacturer', doc.get('manufacturer', 'Unknown'))),
                'Vendor': str(doc.get('Vendor', doc.get('vendor', 'Unknown'))),
                'FacilityType': str(doc.get('FacilityType', doc.get('facility_type', 'Unknown'))),
                'Region': str(doc.get('Region', doc.get('region', 'Unknown'))),
                'Department': str(doc.get('Department', doc.get('department', 'Unknown'))),
                'Category': str(doc.get('Category', doc.get('category', 'Unknown'))),
                'VendorID': str(doc.get('VendorID', doc.get('vendor_id', ''))),
                'ManufacturerID': str(doc.get('ManufacturerID', doc.get('manufacturer_id', ''))),
                'ManufacturercatalogNum': str(doc.get('ManufacturercatalogNum', doc.get('manufacturercatalognum', doc.get('catalog_num', '')))),
                'BedSize': str(doc.get('BedSize', doc.get('bed_size', ''))),
                'PricePaid': self._safe_float(doc.get('PricePaid', doc.get('price_paid', 0.0))),
                'TotalSpend': self._safe_float(doc.get('TotalSpend', doc.get('total_spend', 0.0))),
                'UnitCost': self._safe_float(doc.get('UnitCost', doc.get('unit_cost', 0.0))),
                'Quantity': self._safe_int(doc.get('Quantity', doc.get('quantity', 0))),
                'LoadDate': self._normalize_date_for_search(doc.get('LoadDate', doc.get('load_date'))),
                'Month': self._safe_int(doc.get('Month', doc.get('month', 0))),
                'Year': self._safe_int(doc.get('Year', doc.get('year', 0))),
                'batch_id': str(doc.get('batch_id', doc.get('BatchId', ''))),
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
                elif key == 'batch_id':
                    # Only include batch_id if it has a valid value
                    if value and str(value).strip():
                        cleaned_doc[key] = str(value).strip()
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

    def search_with_comprehensive_results(self, query: str, top: int = 50, include_filters: bool = True) -> List[Dict]:
        """Enhanced search that works with your current index schema limitations"""
        if not self.is_configured:
            logger.warning("Search attempted but Azure AI Search is not configured")
            return []
        
        try:
            # Strategy 1: Search the main searchable fields (content, ItemDesc, Manufacturer, Vendor)
            results = []
            
            # Primary search on searchable fields
            search_params = {
                'search_text': query,
                'top': top,
                'include_total_count': True,
                'select': [
                    "id", "content", "TransactionID", "FacilityID", "ItemDesc", 
                    "Manufacturer", "Vendor", "VendorID", "ManufacturerID", 
                    "FacilityType", "Region", "BedSize", "Department", "Category",
                    "PricePaid", "TotalSpend", "UnitCost", "Quantity", 
                    "Month", "Year", "LoadDate", "batch_id", "metadata"
                ]
            }
            
            # For region queries, add filter-based search since Region is not searchable
            if 'region' in query.lower():
                # Extract potential region names from query
                potential_regions = ['Northeast', 'Southeast', 'Southwest', 'Northwest', 
                                   'Central', 'North', 'South', 'East', 'West', 'Mid-Atlantic', 
                                   'Pacific', 'Mountain', 'Plains']
                
                for region in potential_regions:
                    if region.lower() in query.lower():
                        search_params['filter'] = f"Region eq '{region}'"
                        break
            
            # Execute search
            search_results = self.search_client.search(**search_params)
            
            for result in search_results:
                doc = dict(result)
                doc["@search.score"] = result.get("@search.score", 1.0)
                doc["search_type"] = "comprehensive"
                results.append(doc)
            
            # Strategy 2: If no results and query mentions regions, try filter-only search
            if not results and 'region' in query.lower():
                filter_results = self.search_client.search(
                    search_text="*",
                    filter="Region ne null and Region ne 'Unknown'",
                    top=top,
                    select=search_params['select']
                )
                
                for result in filter_results:
                    doc = dict(result)
                    doc["@search.score"] = 0.7
                    doc["search_type"] = "filter_fallback"
                    results.append(doc)
            
            logger.info(f"Comprehensive search returned {len(results)} results for query: '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"Comprehensive search failed: {e}")
            return []

    def analyze_index_coverage(self) -> Dict[str, Any]:
        """Analyze what data is currently indexed"""
        if not self.is_configured:
            return {"error": "Not configured"}
        
        try:
            # Get sample documents
            results = self.search("*", top=100)
            
            # Analyze field coverage
            field_coverage = {}
            regions = set()
            vendors = set()
            departments = set()
            facility_types = set()
            
            for doc in results:
                for field, value in doc.items():
                    if field not in field_coverage:
                        field_coverage[field] = {"count": 0, "has_data": 0}
                    field_coverage[field]["count"] += 1
                    if value and str(value).strip() and str(value) != "Unknown":
                        field_coverage[field]["has_data"] += 1
                   
                    # Collect unique values for key fields
                    if field == "Region" and value and value != "Unknown":
                        regions.add(value)
                    elif field == "Vendor" and value and value != "Unknown":
                        vendors.add(value)
                    elif field == "Department" and value and value != "Unknown":
                        departments.add(value)
                    elif field == "FacilityType" and value and value != "Unknown":
                        facility_types.add(value)
           
            return {
                "total_documents": len(results),
                "field_coverage": field_coverage,
                "unique_regions": list(regions),
                "unique_vendors": list(vendors)[:10],  # First 10
                "unique_departments": list(departments),
                "unique_facility_types": list(facility_types),
                "regions_count": len(regions),
                "vendors_count": len(vendors),
                "departments_count": len(departments),
                "facility_types_count": len(facility_types)
            }
           
        except Exception as e:
            return {"error": str(e)}

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
                doc.pop('@search.score', None)
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

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
                    "TransactionID": doc.get("TransactionID", ""),
                    "FacilityID": doc.get("FacilityID", ""),
                    "ItemDesc": doc.get("ItemDesc", ""),
                    "Vendor": doc.get("Vendor", ""),
                    "Manufacturer": doc.get("Manufacturer", ""),
                    "FacilityType": doc.get("FacilityType", ""),
                    "Region": doc.get("Region", ""),
                    "Department": doc.get("Department", ""),
                    "Category": doc.get("Category", ""),
                    "TotalSpend": doc.get("TotalSpend", 0),
                    "PricePaid": doc.get("PricePaid", 0),
                    "Quantity": doc.get("Quantity", 0),
                    "Month": doc.get("Month", 0),
                    "Year": doc.get("Year", 0),
                    "content": doc.get("content", ""),
                    **{k: v for k, v in doc.items() if k not in ["@search.score", "content_vector"]}
                }
                documents.append(normalized_doc)
            
            logger.info(f"Vector search returned {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

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
            return results.get_count() or 0
        except Exception as e:
            logger.error(f"Failed to get document count: {e}")
            return 0

    def search(self, query: str, top: int = 50, filters: Optional[str] = None) -> List[Dict]:
        """Simplified search interface for compatibility"""
        return self.search_documents(query, top, filters)

    def upload_documents_to_index(self, documents: List[Dict[str, Any]], index_name: str) -> Dict[str, Any]:
        """Upload documents to a specific index by name"""
        try:
            if not self.is_configured:
                return {"uploaded": 0, "error": "AI Search not configured"}
            
            # SIMPLIFIED: No special handling needed since we use one index
            logger.info(f"Uploading {len(documents)} documents to index: {index_name}")
            
            # Create a client for the specified index
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(self.key)
            )
            
            # Upload documents
            result = search_client.upload_documents(documents=documents)
            
            uploaded_count = len([r for r in result if r.succeeded])
            failed_count = len([r for r in result if not r.succeeded])
            
            if failed_count > 0:
                logger.warning(f"Failed to upload {failed_count} documents to {index_name}")
                # Log first few failures for debugging
                failures = [r for r in result if not r.succeeded][:3]
                for failure in failures:
                    logger.warning(f"Upload failure: {failure}")
            
            return {
                "uploaded": uploaded_count,
                "failed": failed_count,
                "total": len(documents),
                "index": index_name
            }
            
        except Exception as e:
            logger.error(f"Failed to upload documents to index {index_name}: {e}")
            return {"uploaded": 0, "error": str(e), "index": index_name}

    def search_in_index(self, query: str, index_name: str, filters: str = None, top: int = 10) -> List[Dict[str, Any]]:
        """Search in a specific index by name"""
        try:
            if not self.is_configured:
                logger.warning("Search attempted but Azure AI Search is not configured")
                return []
            
            # Create search client for the specific index
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(self.key)
            )
            
            # Perform search
            search_results = search_client.search(
                search_text=query,
                filter=filters,
                top=top,
                include_total_count=True
            )
            
            # Process results
            results = []
            for result in search_results:
                doc = dict(result)
                results.append(doc)
            
            logger.info(f"Found {len(results)} results in index {index_name}")
            return results
            
        except Exception as e:
            logger.error(f"Search failed in index {index_name}: {e}")
            return []

    def vector_search_in_index(self, query_vector: List[float], index_name: str, filters: str = None, top: int = 10) -> List[Dict[str, Any]]:
        """Perform vector search in a specific index"""
        try:
            if not self.is_configured:
                logger.warning("Vector search attempted but Azure AI Search is not configured")
                return []
            
            # Create search client for the specific index
            search_client = SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(self.key)
            )
            
            # Create VectorizedQuery
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="content_vector"
            )
            
            # Perform vector search
            search_results = search_client.search(
                search_text=None,
                vector_queries=[vector_query],
                filter=filters,
                top=top
            )
            
            # Process results
            results = []
            for result in search_results:
                doc = dict(result)
                search_score = doc.get("@search.score", 0)
                doc["similarity"] = min(search_score / 1.0, 1.0) if search_score > 0 else 0.5
                results.append(doc)
            
            logger.info(f"Found {len(results)} vector results in index {index_name}")
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed in index {index_name}: {e}")
            return []

    def hybrid_search(self, query: str, query_vector: List[float], top: int = 50, filters: str = None) -> List[Dict[str, Any]]:
        """Enhanced hybrid search combining vector and full-text search"""
        if not self.is_configured:
            logger.warning("AI Search not configured")
            return []
        
        try:
            # Create vectorized query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=top,
                fields="content_vector"
            )
            
            search_params = {
                'search_text': query,
                'vector_queries': [vector_query],
                'top': top,
                'select': [
                    "id", "content", "TransactionID", "FacilityID", "FacilityType", 
                    "Region", "ItemDesc", "Vendor", "Manufacturer", "Department", 
                    "Category", "TotalSpend", "PricePaid", "Quantity", "Month", 
                    "Year", "VendorID", "ManufacturerID", "batch_id", "metadata"
                ]
            }
            
            if filters:
                search_params['filter'] = filters
            
            results = self.search_client.search(**search_params)
            
            documents = []
            for result in results:
                doc = dict(result)
                search_score = doc.get("@search.score", 0)
                doc["similarity"] = min(search_score / 1.0, 1.0) if search_score > 0 else 0.5
                documents.append(doc)
            
            logger.info(f"Hybrid search returned {len(documents)} results for query: '{query}'")
            return documents
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to separate searches
            return self._fallback_hybrid_search(query, query_vector, top, filters)

    def check_data_consistency(self, transaction_id: str) -> Dict[str, Any]:
        """Check consistency between AI Search and SQL data for a specific transaction"""
        if not self.is_configured:
            return {"error": "AI Search not configured"}
        
        try:
            # Search AI Search for this transaction
            ai_results = self.search(f"TransactionID:{transaction_id}", top=1)
            
            # Get SQL data for comparison
            from app.services.sql_service import get_sql_service
            sql_service = get_sql_service()
            
            sql_query = """
                SELECT TransactionID, ItemDesc, Vendor, Region, FacilityType, 
                       TotalSpend, Quantity, Department, Category, batch_id
                FROM supply_records 
                WHERE TransactionID = ?
            """
            
            sql_results = sql_service.query_items(sql_query, [{"name": "?", "value": transaction_id}])
            
            consistency_report = {
                "transaction_id": transaction_id,
                "ai_search_found": len(ai_results) > 0,
                "sql_found": len(sql_results) > 0,
                "consistent": False,
                "differences": []
            }
            
            if ai_results and sql_results:
                ai_record = ai_results[0]
                sql_record = sql_results[0]
                
                # Compare key fields
                fields_to_compare = ["ItemDesc", "Vendor", "Region", "FacilityType", "TotalSpend", "Quantity"]
                differences = []
                
                for field in fields_to_compare:
                    ai_value = str(ai_record.get(field, "")).strip()
                    sql_value = str(sql_record.get(field, "")).strip()
                    
                    if ai_value != sql_value:
                        differences.append({
                            "field": field,
                            "ai_search_value": ai_value,
                            "sql_value": sql_value
                        })
                
                consistency_report["differences"] = differences
                consistency_report["consistent"] = len(differences) == 0
                
                if differences:
                    logger.warning(f"Data inconsistency found for transaction {transaction_id}: {len(differences)} fields differ")
            
            return consistency_report
            
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return {"error": str(e)}

    def sync_transaction_with_sql(self, transaction_id: str) -> Dict[str, Any]:
        """Sync a specific transaction from SQL to AI Search"""
        try:
            from app.services.sql_service import get_sql_service
            sql_service = get_sql_service()
            
            # Get authoritative data from SQL
            sql_query = """
                SELECT *
                FROM supply_records 
                WHERE TransactionID = ?
            """
            
            sql_results = sql_service.query_items(sql_query, [{"name": "?", "value": transaction_id}])
            
            if not sql_results:
                return {"error": f"Transaction {transaction_id} not found in SQL"}
            
            sql_record = sql_results[0]
            
            # Normalize for AI Search
            normalized_doc = self._normalize_document_for_search(sql_record)
            
            if normalized_doc:
                # Upload to AI Search (will overwrite existing)
                upload_result = self.upload_documents([normalized_doc])
                
                return {
                    "success": upload_result.get("uploaded", 0) > 0,
                    "transaction_id": transaction_id,
                    "upload_result": upload_result
                }
            else:
                return {"error": "Failed to normalize SQL record for AI Search"}
                
        except Exception as e:
            logger.error(f"Transaction sync failed: {e}")
            return {"error": str(e)}

    def _fallback_hybrid_search(self, query: str, query_vector: List[float], top: int, filters: str) -> List[Dict[str, Any]]:
        """Fallback hybrid search using separate vector and text searches"""
        try:
            # Get vector results
            vector_results = self.vector_search(query_vector, top=top//2)
            
            # Get text results  
            text_results = self.search(query, top=top//2)
            
            # Combine and deduplicate
            combined = []
            seen_ids = set()
            
            for result in vector_results:
                doc_id = result.get("id")
                if doc_id and doc_id not in seen_ids:
                    combined.append(result)
                    seen_ids.add(doc_id)
            
            for result in text_results:
                doc_id = result.get("id")
                if doc_id and doc_id not in seen_ids:
                    result['similarity'] = 0.7  # Default similarity for text results
                    combined.append(result)
                    seen_ids.add(doc_id)
            
            # Sort by similarity
            combined.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            return combined[:top]
            
        except Exception as e:
            logger.error(f"Fallback hybrid search failed: {e}")
            return []

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