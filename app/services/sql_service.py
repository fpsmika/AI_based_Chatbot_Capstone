import os
import json
import pyodbc
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd
import numpy as np
from app.core.config import settings
from uuid import uuid4
import time
from contextlib import contextmanager
import hashlib

logger = logging.getLogger(__name__)

class SQLService:
    """Enhanced Azure SQL Service with normalized schema support and improved error handling"""
    
    def __init__(self):
        # Enhanced connection string with proper timeout settings
        self.conn_str = (
            f"Driver={{{settings.SQL_DRIVER}}};"
            f"Server=tcp:{settings.SQL_SERVER},1433;"
            f"Database={settings.SQL_DATABASE};"
            f"Uid={settings.SQL_USERNAME};"
            f"Pwd={settings.SQL_PASSWORD};"
            f"Encrypt=yes;TrustServerCertificate=no;"
            f"Connection Timeout=60;"
            f"Command Timeout=120;"
            f"Login Timeout=30;"
            f"ConnectRetryCount=3;"
            f"ConnectRetryInterval=10;"
        )
        
        # Initialize tables on first use
        self._tables_initialized = False
    
    @contextmanager
    def _get_connection(self, max_retries: int = 3):
        """Create a new database connection with retry logic"""
        connection = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting SQL connection (attempt {attempt + 1}/{max_retries})")
                connection = pyodbc.connect(
                    self.conn_str,
                    timeout=30
                )
                connection.timeout = 120
                connection.autocommit = False
                logger.info("✅ SQL connection established successfully")
                
                # Initialize tables if needed
                if not self._tables_initialized:
                    self._ensure_tables_exist(connection)
                    self._tables_initialized = True
                
                yield connection
                break
                
            except Exception as e:
                logger.error(f"SQL connection attempt {attempt + 1} failed: {e}")
                if connection:
                    try:
                        connection.close()
                    except:
                        pass
                        
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying connection in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    raise e
        else:
            if connection:
                try:
                    connection.close()
                except:
                    pass
    
    def _ensure_tables_exist(self, connection):
        """Create necessary tables if they don't exist - both normalized and denormalized"""
        cursor = connection.cursor()
        
        try:
            # Create normalized schema tables (for your setup_azure_db.py)
            normalized_schema = [
                # Vendors table
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'vendors')
                BEGIN
                    CREATE TABLE vendors (
                        VendorID NVARCHAR(50) PRIMARY KEY,
                        VendorName NVARCHAR(200) NOT NULL,
                        created_at DATETIME2 DEFAULT GETDATE()
                    );
                END
                """,
                
                # Facilities table
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'facilities')
                BEGIN
                    CREATE TABLE facilities (
                        FacilityID NVARCHAR(50) PRIMARY KEY,
                        FacilityType NVARCHAR(100) NOT NULL,
                        Region NVARCHAR(100) NOT NULL,
                        BedSize NVARCHAR(50) NOT NULL,
                        created_at DATETIME2 DEFAULT GETDATE()
                    );
                END
                """,
                
                # Supplies table
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'supplies')
                BEGIN
                    CREATE TABLE supplies (
                        SupplyID NVARCHAR(50) PRIMARY KEY,
                        ManufacturerCatalogNum NVARCHAR(100),
                        ItemDesc NVARCHAR(500) NOT NULL,
                        ManufacturerID NVARCHAR(50) NOT NULL,
                        created_at DATETIME2 DEFAULT GETDATE()
                    );
                END
                """,
                
                # Transactions table (normalized)
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'transactions')
                BEGIN
                    CREATE TABLE transactions (
                        TransactionID NVARCHAR(50) PRIMARY KEY,
                        FacilityID NVARCHAR(50) NOT NULL,
                        VendorID NVARCHAR(50) NOT NULL,
                        SupplyID NVARCHAR(50) NOT NULL,
                        Month INT NOT NULL CHECK (Month BETWEEN 1 AND 12),
                        Year INT NOT NULL CHECK (Year >= 2000),
                        LoadDate DATE NOT NULL,
                        Quantity INT NOT NULL,
                        PricePaid DECIMAL(18,2) NOT NULL,
                        TotalSpend DECIMAL(18,2) NOT NULL,
                        batch_id NVARCHAR(50),
                        created_at DATETIME2 DEFAULT GETDATE()
                    );
                    
                    -- Create indexes for better performance
                    CREATE INDEX idx_transaction_facility ON transactions(FacilityID);
                    CREATE INDEX idx_transaction_vendor ON transactions(VendorID);
                    CREATE INDEX idx_transaction_batch ON transactions(batch_id);
                END
                """,
                
                # Denormalized supply_records table (for compatibility)
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'supply_records')
                BEGIN
                    CREATE TABLE supply_records (
                        id NVARCHAR(50) PRIMARY KEY,
                        batch_id NVARCHAR(50) NULL,
                        TransactionID NVARCHAR(50) NULL,
                        FacilityID NVARCHAR(50) NULL,
                        FacilityType NVARCHAR(100) NULL,
                        Region NVARCHAR(100) NULL,
                        Department NVARCHAR(100) NULL,
                        Vendor NVARCHAR(200) NULL,
                        ItemDesc NVARCHAR(500) NULL,
                        Manufacturer NVARCHAR(200) NULL,
                        Category NVARCHAR(100) NULL,
                        TotalSpend DECIMAL(18,2) NULL,
                        PricePaid DECIMAL(18,2) NULL,
                        Quantity INT NULL,
                        LoadDate DATETIME2 NULL,
                        Month INT NULL,
                        Year INT NULL,
                        BedSize NVARCHAR(50) NULL,
                        ManufacturercatalogNum NVARCHAR(100) NULL,
                        VendorID NVARCHAR(50) NULL,
                        created_at DATETIME2 DEFAULT GETUTCDATE(),
                        updated_at DATETIME2 DEFAULT GETUTCDATE()
                    );
                    
                    CREATE INDEX IX_supply_records_batch_id ON supply_records(batch_id);
                    CREATE INDEX IX_supply_records_vendor ON supply_records(Vendor);
                    CREATE INDEX IX_supply_records_facility ON supply_records(FacilityID);
                    CREATE INDEX IX_supply_records_transaction ON supply_records(TransactionID);
                END
                """,
                
                # Embeddings table
                """
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'embeddings')
                BEGIN
                    CREATE TABLE embeddings (
                        id NVARCHAR(50) PRIMARY KEY,
                        vector NVARCHAR(MAX) NULL,
                        metadata NVARCHAR(MAX) NULL,
                        created_at DATETIME2 DEFAULT GETUTCDATE(),
                        updated_at DATETIME2 DEFAULT GETUTCDATE()
                    );
                END
                """
            ]
            
            # Execute schema creation
            for i, cmd in enumerate(normalized_schema, 1):
                try:
                    logger.debug(f"Executing schema command {i}/{len(normalized_schema)}")
                    cursor.execute(cmd)
                    connection.commit()
                except Exception as e:
                    logger.warning(f"Schema command {i} failed: {e}")
                    connection.rollback()
                    continue
            
            logger.info("✅ Database schema verified/created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create schema: {e}")
            connection.rollback()
            raise
        finally:
            cursor.close()
    
    def test_connection(self) -> Dict[str, Any]:
        """Test database connection and basic operations"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Test basic query
                cursor.execute("SELECT 1 AS test_value")
                test_result = cursor.fetchone()[0]
                
                # Check which tables exist
                cursor.execute("""
                    SELECT TABLE_NAME 
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """)
                tables = [row[0] for row in cursor.fetchall()]
                
                cursor.close()
                
                return {
                    "status": "connected",
                    "test_value": test_result,
                    "tables": tables,
                    "supply_records_table": "supply_records" in tables,
                    "normalized_schema": all(t in tables for t in ["vendors", "facilities", "supplies", "transactions"]),
                    "embeddings_table": "embeddings" in tables
                }
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def bulk_upsert_records(self, records: List[Dict[str, Any]], batch_id: str) -> int:
        """Enhanced bulk upsert supporting both normalized and denormalized approaches"""
        if not records:
            return 0
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                successful_upserts = 0
                
                # Check if we have normalized tables
                cursor.execute("""
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME IN ('vendors', 'facilities', 'supplies', 'transactions')
                """)
                normalized_tables_count = cursor.fetchone()[0]
                
                if normalized_tables_count == 4:
                    # Use normalized approach
                    logger.info("Using normalized schema for bulk upsert")
                    successful_upserts = self._bulk_upsert_normalized(cursor, records, batch_id)
                else:
                    # Use denormalized approach
                    logger.info("Using denormalized schema for bulk upsert")
                    successful_upserts = self._bulk_upsert_denormalized(cursor, records, batch_id)
                
                conn.commit()
                cursor.close()
                logger.info(f"Successfully upserted {successful_upserts}/{len(records)} records")
                return successful_upserts
                
        except Exception as e:
            logger.error(f"Bulk upsert failed: {e}")
            raise
    
    def _bulk_upsert_normalized(self, cursor, records: List[Dict[str, Any]], batch_id: str) -> int:
        """Bulk upsert for normalized schema"""
        successful_upserts = 0
        
        # Extract unique values for reference tables
        vendors = {}
        facilities = {}
        supplies = {}
        
        for record in records:
            # Generate VendorID if missing
            vendor_name = record.get('Vendor', '')
            if vendor_name:
                vendor_id = self._generate_id('V', vendor_name)
                vendors[vendor_id] = vendor_name
                record['VendorID'] = vendor_id
            
            # Generate FacilityID if missing in record
            facility_id = record.get('FacilityID', '')
            if facility_id:
                facilities[facility_id] = {
                    'FacilityType': record.get('FacilityType', ''),
                    'Region': record.get('Region', ''),
                    'BedSize': record.get('BedSize', '')
                }
            
            # Generate SupplyID from ManufacturerCatalogNum
            catalog_num = record.get('ManufacturercatalogNum', record.get('ManufacturerCatalogNum', ''))
            if catalog_num:
                supply_id = f"SUP-{catalog_num}"
                supplies[supply_id] = {
                    'ManufacturerCatalogNum': catalog_num,
                    'ItemDesc': record.get('ItemDesc', ''),
                    'ManufacturerID': record.get('Manufacturer', 'UNKNOWN')
                }
                record['SupplyID'] = supply_id
        
        try:
            # Upsert vendors
            for vendor_id, vendor_name in vendors.items():
                cursor.execute("""
                    MERGE vendors AS target
                    USING (VALUES (?, ?)) AS source (VendorID, VendorName)
                    ON target.VendorID = source.VendorID
                    WHEN NOT MATCHED THEN
                        INSERT (VendorID, VendorName) VALUES (source.VendorID, source.VendorName);
                """, (vendor_id, vendor_name))
            
            # Upsert facilities
            for facility_id, facility_data in facilities.items():
                cursor.execute("""
                    MERGE facilities AS target
                    USING (VALUES (?, ?, ?, ?)) AS source (FacilityID, FacilityType, Region, BedSize)
                    ON target.FacilityID = source.FacilityID
                    WHEN NOT MATCHED THEN
                        INSERT (FacilityID, FacilityType, Region, BedSize)
                        VALUES (source.FacilityID, source.FacilityType, source.Region, source.BedSize);
                """, (facility_id, facility_data['FacilityType'], facility_data['Region'], facility_data['BedSize']))
            
            # Upsert supplies
            for supply_id, supply_data in supplies.items():
                cursor.execute("""
                    MERGE supplies AS target
                    USING (VALUES (?, ?, ?, ?)) AS source (SupplyID, ManufacturerCatalogNum, ItemDesc, ManufacturerID)
                    ON target.SupplyID = source.SupplyID
                    WHEN NOT MATCHED THEN
                        INSERT (SupplyID, ManufacturerCatalogNum, ItemDesc, ManufacturerID)
                        VALUES (source.SupplyID, source.ManufacturerCatalogNum, source.ItemDesc, source.ManufacturerID);
                """, (supply_id, supply_data['ManufacturerCatalogNum'], supply_data['ItemDesc'], supply_data['ManufacturerID']))
            
            # Upsert transactions
            for record in records:
                try:
                    normalized_record = self._normalize_record(record)
                    cursor.execute("""
                        MERGE transactions AS target
                        USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) AS source 
                            (TransactionID, FacilityID, VendorID, SupplyID, Month, Year, LoadDate, Quantity, PricePaid, TotalSpend, batch_id)
                        ON target.TransactionID = source.TransactionID
                        WHEN MATCHED THEN
                            UPDATE SET 
                                FacilityID = source.FacilityID,
                                VendorID = source.VendorID,
                                SupplyID = source.SupplyID,
                                Month = source.Month,
                                Year = source.Year,
                                LoadDate = source.LoadDate,
                                Quantity = source.Quantity,
                                PricePaid = source.PricePaid,
                                TotalSpend = source.TotalSpend,
                                batch_id = source.batch_id
                        WHEN NOT MATCHED THEN
                            INSERT (TransactionID, FacilityID, VendorID, SupplyID, Month, Year, LoadDate, Quantity, PricePaid, TotalSpend, batch_id)
                            VALUES (source.TransactionID, source.FacilityID, source.VendorID, source.SupplyID, 
                                   source.Month, source.Year, source.LoadDate, source.Quantity, source.PricePaid, source.TotalSpend, source.batch_id);
                    """, (
                        normalized_record.get('TransactionID', ''),
                        normalized_record.get('FacilityID', ''),
                        normalized_record.get('VendorID', ''),
                        normalized_record.get('SupplyID', ''),
                        int(normalized_record.get('Month', 0)) if normalized_record.get('Month') else None,
                        int(normalized_record.get('Year', 0)) if normalized_record.get('Year') else None,
                        normalized_record.get('LoadDate'),
                        int(normalized_record.get('Quantity', 0)) if normalized_record.get('Quantity') else None,
                        float(normalized_record.get('PricePaid', 0)) if normalized_record.get('PricePaid') else None,
                        float(normalized_record.get('TotalSpend', 0)) if normalized_record.get('TotalSpend') else None,
                        batch_id
                    ))
                    successful_upserts += 1
                except Exception as record_error:
                    logger.warning(f"Failed to upsert transaction record: {record_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"Normalized upsert failed: {e}")
            raise
        
        return successful_upserts
    
    def _bulk_upsert_denormalized(self, cursor, records: List[Dict[str, Any]], batch_id: str) -> int:
        """Bulk upsert for denormalized supply_records table"""
        successful_upserts = 0
        
        for record in records:
            try:
                # Normalize the record
                normalized_record = self._normalize_record(record)
                normalized_record.setdefault('id', str(uuid4()))
                normalized_record['batch_id'] = batch_id
                
                # Generate VendorID if missing
                if 'VendorID' not in normalized_record and 'Vendor' in normalized_record:
                    normalized_record['VendorID'] = self._generate_id('V', normalized_record['Vendor'])
                
                self._upsert_supply_record(cursor, normalized_record)
                successful_upserts += 1
                
            except Exception as record_error:
                logger.warning(f"Failed to upsert supply record: {record_error}")
                continue
        
        return successful_upserts
    
    def _generate_id(self, prefix: str, value: str) -> str:
        """Generate a consistent ID based on a string value"""
        hash_value = hashlib.md5(str(value).encode()).hexdigest()[:8]
        return f"{prefix}-{hash_value.upper()}"
    
    def upsert_item(self, record: Dict[str, Any], table_name: str = "supply_records") -> bool:
        """Insert or update a single record"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Prepare record data
                record = self._normalize_record(record)
                record.setdefault('id', str(uuid4()))
                
                if table_name == "supply_records":
                    success = self._upsert_supply_record(cursor, record)
                elif table_name == "embeddings":
                    success = self._upsert_embedding(cursor, record)
                else:
                    raise ValueError(f"Unknown table: {table_name}")
                
                conn.commit()
                cursor.close()
                return success
        except Exception as e:
            logger.error(f"Upsert failed: {e}")
            raise
    
    def query_items(self, query: str, params: Optional[List[Dict]] = None) -> List[Dict]:
        """Execute a custom SQL query and return results"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    # Handle parameterized queries
                    param_values = [p["value"] for p in params]
                    cursor.execute(query, param_values)
                else:
                    cursor.execute(query)
                
                columns = [column[0] for column in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                cursor.close()
                return results
                
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
    
    def vector_search(self, query_vector: List[float], top_k: int = 5, min_score: float = 0.5) -> List[Dict]:
        """Simplified vector search (can be enhanced later with proper vector search)"""
        try:
            # For now, return empty results - this can be enhanced with proper vector search
            logger.info("Vector search requested but not fully implemented yet")
            return []
                
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def store_embeddings_bulk(self, embeddings: List[Dict[str, Any]]) -> int:
        """Bulk store embeddings with metadata"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                successful_stores = 0
                for emb in embeddings:
                    try:
                        cursor.execute("""
                            MERGE embeddings AS target
                            USING (VALUES (?, ?, ?, ?)) AS source (id, vector, metadata, created_at)
                            ON target.id = source.id
                            WHEN MATCHED THEN
                                UPDATE SET 
                                    vector = source.vector,
                                    metadata = source.metadata,
                                    updated_at = GETUTCDATE()
                            WHEN NOT MATCHED THEN
                                INSERT (id, vector, metadata, created_at, updated_at)
                                VALUES (source.id, source.vector, source.metadata, source.created_at, source.created_at);
                        """, (
                            emb["id"],
                            json.dumps(emb["vector"]),
                            json.dumps(emb["metadata"]),
                            datetime.utcnow().isoformat()
                        ))
                        successful_stores += 1
                    except Exception as emb_error:
                        logger.warning(f"Failed to store embedding: {emb_error}")
                        continue
                
                conn.commit()
                cursor.close()
                return successful_stores
                
        except Exception as e:
            logger.error(f"Failed to store embeddings: {e}")
            raise
    
    def get_records_by_batch(self, batch_id: str, offset: int = 0, limit: int = 100) -> List[Dict]:
        """Get paginated records by batch ID"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Try supply_records first, then transactions
                try:
                    cursor.execute("""
                        SELECT * FROM supply_records
                        WHERE batch_id = ?
                        ORDER BY created_at DESC
                        OFFSET ? ROWS
                        FETCH NEXT ? ROWS ONLY
                    """, (batch_id, offset, limit))
                except:
                    # Fallback to transactions table
                    cursor.execute("""
                        SELECT * FROM transactions
                        WHERE batch_id = ?
                        ORDER BY created_at DESC
                        OFFSET ? ROWS
                        FETCH NEXT ? ROWS ONLY
                    """, (batch_id, offset, limit))
                
                columns = [column[0] for column in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                cursor.close()
                return results
                
        except Exception as e:
            logger.error(f"Failed to get records by batch: {e}")
            raise
    
    # Helper methods
    def _normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert special types to SQL-compatible formats"""
        normalized = record.copy()
        for key, value in record.items():
            if isinstance(value, (datetime, date, pd.Timestamp, np.datetime64)):
                normalized[key] = pd.to_datetime(value).isoformat()
            elif isinstance(value, (dict, list)):
                normalized[key] = json.dumps(value)
            elif pd.isna(value) or value is None:
                normalized[key] = None
            elif isinstance(value, (np.int64, np.int32)):
                normalized[key] = int(value)
            elif isinstance(value, (np.float64, np.float32)):
                normalized[key] = float(value)
            elif isinstance(value, str) and len(value) > 500:
                # Truncate very long strings to fit database constraints
                normalized[key] = value[:500]
        return normalized
    
    def _upsert_supply_record(self, cursor, record: Dict[str, Any]) -> bool:
        """Specialized upsert for supply records with proper column names"""
        try:
            cursor.execute("""
                MERGE supply_records AS target
                USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) AS source 
                    (id, batch_id, TransactionID, FacilityID, FacilityType, Region, 
                     Department, Vendor, ItemDesc, Manufacturer, Category, 
                     TotalSpend, PricePaid, Quantity, LoadDate, Month, Year, BedSize, VendorID)
                ON target.TransactionID = source.TransactionID OR target.id = source.id
                WHEN MATCHED THEN
                    UPDATE SET 
                        batch_id = source.batch_id,
                        FacilityID = source.FacilityID,
                        FacilityType = source.FacilityType,
                        Region = source.Region,
                        Department = source.Department,
                        Vendor = source.Vendor,
                        ItemDesc = source.ItemDesc,
                        Manufacturer = source.Manufacturer,
                        Category = source.Category,
                        TotalSpend = source.TotalSpend,
                        PricePaid = source.PricePaid,
                        Quantity = source.Quantity,
                        LoadDate = source.LoadDate,
                        Month = source.Month,
                        Year = source.Year,
                        BedSize = source.BedSize,
                        VendorID = source.VendorID,
                        updated_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (id, batch_id, TransactionID, FacilityID, FacilityType, Region,
                            Department, Vendor, ItemDesc, Manufacturer, Category,
                            TotalSpend, PricePaid, Quantity, LoadDate, Month, Year, BedSize, VendorID,
                            created_at, updated_at)
                    VALUES (source.id, source.batch_id, source.TransactionID, source.FacilityID,
                           source.FacilityType, source.Region, source.Department, source.Vendor,
                           source.ItemDesc, source.Manufacturer, source.Category,
                           source.TotalSpend, source.PricePaid, source.Quantity,
                           source.LoadDate, source.Month, source.Year, source.BedSize, source.VendorID,
                           GETUTCDATE(), GETUTCDATE());
            """, (
                record.get('id', str(uuid4())),
                record.get('batch_id', ''),
                record.get('TransactionID', ''),
                record.get('FacilityID', ''),
                record.get('FacilityType', ''),
                record.get('Region', ''),
                record.get('Department', ''),
                record.get('Vendor', ''),
                record.get('ItemDesc', ''),
                record.get('Manufacturer', ''),
                record.get('Category', ''),
                float(record.get('TotalSpend', 0)) if record.get('TotalSpend') is not None else None,
                float(record.get('PricePaid', 0)) if record.get('PricePaid') is not None else None,
                int(record.get('Quantity', 0)) if record.get('Quantity') is not None else None,
                record.get('LoadDate'),
                int(record.get('Month', 0)) if record.get('Month') is not None else None,
                int(record.get('Year', 0)) if record.get('Year') is not None else None,
                record.get('BedSize', ''),
                record.get('VendorID', '')
            ))
            return True
        except Exception as e:
            logger.error(f"Failed to upsert supply record: {e}")
            raise
    
    def _upsert_embedding(self, cursor, embedding: Dict[str, Any]) -> bool:
        """Specialized upsert for embeddings"""
        cursor.execute("""
            MERGE embeddings AS target
            USING (VALUES (?, ?, ?, ?)) AS source (id, vector, metadata, created_at)
            ON target.id = source.id
            WHEN MATCHED THEN
                UPDATE SET 
                    vector = source.vector,
                    metadata = source.metadata,
                    updated_at = GETUTCDATE()
            WHEN NOT MATCHED THEN
                INSERT (id, vector, metadata, created_at, updated_at)
                VALUES (source.id, source.vector, source.metadata, source.created_at, source.created_at);
        """, (
            embedding['id'],
            json.dumps(embedding.get('vector', [])),
            json.dumps(embedding.get('metadata', {})),
            datetime.utcnow().isoformat()
        ))
        return True

# Singleton instance for dependency injection
sql_service = SQLService()

def get_sql_service():
    """Get the shared SQL service instance"""
    return sql_service