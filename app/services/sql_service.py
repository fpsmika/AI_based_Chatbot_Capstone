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
    """Fixed Azure SQL Service aligned with existing supply_records schema"""
    
    def __init__(self):
        # Enhanced connection string with proper timeout settings
        self.conn_str = (
            f"Driver={{{settings.SQL_DRIVER}}};"
            f"Server=tcp:{settings.SQL_SERVER},1433;"
            f"Database={settings.SQL_DATABASE};"
            f"Uid={settings.SQL_USERNAME};"
            f"Pwd={settings.SQL_PASSWORD};"
            f"Encrypt=yes;TrustServerCertificate=no;"
            f"Connection Timeout=90;"
            f"Command Timeout=600;"
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
        try:
            for attempt in range(max_retries):
                try:
                    logger.info(f"Attempting SQL connection (attempt {attempt + 1}/{max_retries})")
                    connection = pyodbc.connect(
                        self.conn_str,
                        
                    )
                    connection.timeout = 300
                    connection.autocommit = False
                    logger.info("✅ SQL connection established successfully")
                    
                    # Initialize tables if needed
                    if not self._tables_initialized:
                        self._check_schema(connection)
                        self._tables_initialized = True
                    
                    yield connection
                    return  # Exit after successful yield
                    
                except Exception as e:
                    logger.error(f"SQL connection attempt {attempt + 1} failed: {e}")
                    if connection:
                        try:
                            connection.close()
                        except:
                            pass
                        connection = None
                        
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"Retrying connection in {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        raise e
        
        except Exception as e:
            logger.error(f"All connection attempts failed: {e}")
            raise
        finally:
            if connection:
                try:
                    connection.close()
                except:
                    pass
    
    def _check_schema(self, connection):
        """Check existing schema and log what we have"""
        cursor = connection.cursor()
        
        try:
            # Check what tables exist
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"Existing tables: {tables}")
            
            # Check supply_records columns specifically
            if 'supply_records' in tables:
                cursor.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'supply_records'
                    ORDER BY ORDINAL_POSITION
                """)
                columns = cursor.fetchall()
                logger.info("supply_records table columns:")
                for col in columns:
                    logger.info(f"  - {col[0]} ({col[1]}, nullable: {col[2]})")
            
        except Exception as e:
            logger.error(f"Failed to check schema: {e}")
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
        """Bulk upsert using ONLY the existing supply_records table schema"""
        if not records:
            return 0
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                successful_upserts = 0
                
                logger.info(f"Starting bulk upsert of {len(records)} records to supply_records table")
                
                # Debug: Check first few records to understand data structure
                if len(records) > 0:
                    sample_record = records[0]
                    logger.info(f"Sample record keys: {list(sample_record.keys())}")
                    logger.info(f"Sample Month value: {sample_record.get('Month')} (type: {type(sample_record.get('Month'))})")
                    logger.info(f"Sample LoadDate value: {sample_record.get('LoadDate')} (type: {type(sample_record.get('LoadDate'))})")
                
                for i, record in enumerate(records):
                    try:
                        # Normalize the record to match existing schema
                        normalized_record = self._normalize_record_for_supply_table(record, batch_id)
                        
                        # Debug: Log first few normalized records
                        if i < 3:
                            logger.info(f"Normalized record {i+1}: Month={normalized_record['Month']}, Year={normalized_record['Year']}, LoadDate={normalized_record['LoadDate']}")
                        
                        self._upsert_supply_record_safe(cursor, normalized_record)
                        successful_upserts += 1
                        
                        if successful_upserts % 1000 == 0:
                            logger.info(f"Processed {successful_upserts}/{len(records)} records")
                            
                    except Exception as record_error:
                        logger.warning(f"Failed to upsert record {i+1}: {record_error}")
                        # Log the problematic record for debugging
                        if i < 10:  # Only log first 10 failures to avoid spam
                            logger.debug(f"Problematic record data: {record}")
                        continue
                
                conn.commit()
                cursor.close()
                logger.info(f"Successfully upserted {successful_upserts}/{len(records)} records")
                return successful_upserts
                
        except Exception as e:
            logger.error(f"Bulk upsert failed: {e}")
            raise
    
    def _normalize_record_for_supply_table(self, record: Dict[str, Any], batch_id: str) -> Dict[str, Any]:
        """Normalize record to match the existing supply_records table schema exactly"""
        # Extract date components for Month/Year if missing
        load_date = self._safe_date(record.get('LoadDate'))
        current_date = datetime.now()
        
        # Try to extract month/year from LoadDate if not provided
        month_value = self._safe_int(record.get('Month'))
        year_value = self._safe_int(record.get('Year'))
        
        if not month_value or not year_value:
            try:
                if load_date:
                    date_obj = pd.to_datetime(load_date)
                    if not month_value:
                        month_value = date_obj.month
                    if not year_value:
                        year_value = date_obj.year
                else:
                    # Fallback to current date
                    if not month_value:
                        month_value = current_date.month
                    if not year_value:
                        year_value = current_date.year
            except:
                # Ultimate fallback
                if not month_value:
                    month_value = current_date.month
                if not year_value:
                    year_value = current_date.year

        # Based on your schema, these columns are NOT NULL and need default values
        normalized = {
            'id': record.get('id', str(uuid4())),
            'batch_id': batch_id,
            'TransactionID': record.get('TransactionID') or f"TXN-{str(uuid4())[:8]}",
            'FacilityID': record.get('FacilityID') or 'UNKNOWN',
            'FacilityType': record.get('FacilityType') or 'Unknown',
            'Region': record.get('Region') or 'Unknown',
            'BedSize': record.get('BedSize') or 'Unknown',
            'Month': month_value,
            'Year': year_value,
            'LoadDate': load_date or current_date.date().isoformat(),
            'Vendor': record.get('Vendor') or 'Unknown Vendor',
            'VendorID': record.get('VendorID') or self._generate_vendor_id(record.get('Vendor', 'Unknown')),
            'Manufacturer': record.get('Manufacturer') or 'Unknown Manufacturer',
            'ManufacturerID': record.get('ManufacturerID') or 'UNKNOWN',
            'ManufacturercatalogNum': record.get('ManufacturercatalogNum', record.get('ManufacturerCatalogNum', 'UNKNOWN')),
            'ItemDesc': record.get('ItemDesc') or 'Unknown Item',
            'Quantity': self._safe_int(record.get('Quantity')) or 0,
            'PricePaid': self._safe_decimal(record.get('PricePaid')) or 0.0,
            'TotalSpend': self._safe_decimal(record.get('TotalSpend')) or 0.0,
            'Department': record.get('Department'),  # NULL allowed
            'Category': record.get('Category')       # NULL allowed
        }
        
        return normalized
    
    def _safe_int(self, value) -> int:
        """Safely convert to int or return 0 for required fields"""
        if value is None or pd.isna(value):
            return 0
        try:
            if isinstance(value, str) and value.strip() == '':
                return 0
            return int(float(value))  # Handle float strings
        except (ValueError, TypeError):
            return 0
    
    def _safe_decimal(self, value) -> float:
        """Safely convert to decimal or return 0.0 for required fields"""
        if value is None or pd.isna(value):
            return 0.0
        try:
            if isinstance(value, str) and value.strip() == '':
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _safe_date(self, value) -> Optional[str]:
        """Safely convert to date string or return None"""
        if value is None or pd.isna(value):
            return None
        try:
            if isinstance(value, str) and value.strip() == '':
                return None
            if isinstance(value, (datetime, date, pd.Timestamp)):
                return pd.to_datetime(value).date().isoformat()
            elif isinstance(value, str):
                return pd.to_datetime(value).date().isoformat()
            return None
        except:
            return None
    
    def _generate_vendor_id(self, vendor_name: str) -> str:
        """Generate a vendor ID from vendor name"""
        if not vendor_name or vendor_name.strip() == '':
            return 'V-UNKNOWN'
        return f"V-{hashlib.md5(vendor_name.encode()).hexdigest()[:8].upper()}"
    
    def _upsert_supply_record_safe(self, cursor, record: Dict[str, Any]) -> bool:
        """Safe upsert for supply records using exact column names from your schema"""
        try:
            cursor.execute("""
                MERGE supply_records AS target
                USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)) AS source 
                    (id, batch_id, TransactionID, FacilityID, FacilityType, Region, BedSize,
                     Month, Year, LoadDate, Vendor, VendorID, Manufacturer, ManufacturerID,
                     ManufacturercatalogNum, ItemDesc, Quantity, PricePaid, TotalSpend, Department)
                ON target.id = source.id OR (target.TransactionID = source.TransactionID AND target.TransactionID != '')
                WHEN MATCHED THEN
                    UPDATE SET 
                        batch_id = source.batch_id,
                        TransactionID = source.TransactionID,
                        FacilityID = source.FacilityID,
                        FacilityType = source.FacilityType,
                        Region = source.Region,
                        BedSize = source.BedSize,
                        Month = source.Month,
                        Year = source.Year,
                        LoadDate = source.LoadDate,
                        Vendor = source.Vendor,
                        VendorID = source.VendorID,
                        Manufacturer = source.Manufacturer,
                        ManufacturerID = source.ManufacturerID,
                        ManufacturercatalogNum = source.ManufacturercatalogNum,
                        ItemDesc = source.ItemDesc,
                        Quantity = source.Quantity,
                        PricePaid = source.PricePaid,
                        TotalSpend = source.TotalSpend,
                        Department = source.Department,
                        updated_at = GETUTCDATE()
                WHEN NOT MATCHED THEN
                    INSERT (id, batch_id, TransactionID, FacilityID, FacilityType, Region, BedSize,
                            Month, Year, LoadDate, Vendor, VendorID, Manufacturer, ManufacturerID,
                            ManufacturercatalogNum, ItemDesc, Quantity, PricePaid, TotalSpend, Department,
                            created_at, updated_at)
                    VALUES (source.id, source.batch_id, source.TransactionID, source.FacilityID,
                           source.FacilityType, source.Region, source.BedSize, source.Month, source.Year,
                           source.LoadDate, source.Vendor, source.VendorID, source.Manufacturer,
                           source.ManufacturerID, source.ManufacturercatalogNum, source.ItemDesc,
                           source.Quantity, source.PricePaid, source.TotalSpend, source.Department,
                           GETUTCDATE(), GETUTCDATE());
            """, (
                record['id'],
                record['batch_id'],
                record['TransactionID'],
                record['FacilityID'],
                record['FacilityType'],
                record['Region'],
                record['BedSize'],
                record['Month'],
                record['Year'],
                record['LoadDate'],
                record['Vendor'],
                record['VendorID'],
                record['Manufacturer'],
                record['ManufacturerID'],
                record['ManufacturercatalogNum'],
                record['ItemDesc'],
                record['Quantity'],
                record['PricePaid'],
                record['TotalSpend'],
                record['Department']
            ))
            return True
        except Exception as e:
            logger.error(f"Failed to upsert supply record: {e}")
            raise
    
    def upsert_item(self, record: Dict[str, Any], table_name: str = "supply_records") -> bool:
        """Insert or update a single record"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if table_name == "supply_records":
                    # Generate batch_id for single records
                    batch_id = record.get('batch_id', str(uuid4()))
                    normalized_record = self._normalize_record_for_supply_table(record, batch_id)
                    success = self._upsert_supply_record_safe(cursor, normalized_record)
                else:
                    raise ValueError(f"Table {table_name} not supported in this simplified version")
                
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
                cursor = None
                try:
                    cursor = conn.cursor()
                    
                    if params:
                        # Handle parameterized queries
                        param_values = [p["value"] for p in params]
                        cursor.execute(query, param_values)
                    else:
                        cursor.execute(query)
                    
                    columns = [column[0] for column in cursor.description]
                    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    
                    logger.info(f"Query executed successfully: {len(results)} rows returned")
                    return results
                    
                except Exception as e:
                    logger.error(f"Query execution failed: {e}")
                    logger.error(f"Query was: {query}")
                    if params:
                        logger.error(f"Parameters: {params}")
                    raise
                finally:
                    if cursor:
                        try:
                            cursor.close()
                        except:
                            pass
                
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
    
    def get_records_by_batch(self, batch_id: str, offset: int = 0, limit: int = 100) -> List[Dict]:
        """Get paginated records by batch ID from supply_records table"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT * FROM supply_records
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
    
    def test_chat_tables(self) -> Dict[str, Any]:
        """Test chat history tables specifically"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if chat tables exist
                cursor.execute("""
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME IN ('chat_sessions', 'chat_messages')
                """)
                existing_tables = [row[0] for row in cursor.fetchall()]
                
                # Test basic operations if tables exist
                test_results = {
                    "chat_sessions_exists": "chat_sessions" in existing_tables,
                    "chat_messages_exists": "chat_messages" in existing_tables,
                    "can_read": False,
                    "can_write": False
                }
                
                if test_results["chat_sessions_exists"]:
                    # Test read
                    cursor.execute("SELECT COUNT(*) FROM chat_sessions")
                    count = cursor.fetchone()[0]
                    test_results["can_read"] = True
                    test_results["chat_sessions_count"] = count
                    
                    # Test write with a dummy record
                    test_chat_id = f"test-{uuid4()}"
                    try:
                        cursor.execute("""
                            INSERT INTO chat_sessions (chat_id, session_id, title)
                            VALUES (?, 'test-session', 'Test Chat')
                        """, (test_chat_id,))
                        
                        # Clean up test record
                        cursor.execute("DELETE FROM chat_sessions WHERE chat_id = ?", (test_chat_id,))
                        conn.commit()
                        test_results["can_write"] = True
                    except Exception as write_error:
                        test_results["write_error"] = str(write_error)
                        conn.rollback()
                
                cursor.close()
                return test_results
                
        except Exception as e:
            logger.error(f"Chat tables test failed: {e}")
            return {"error": str(e)}

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

# Singleton instance for dependency injection
sql_service = SQLService()

def get_sql_service():
    """Get the shared SQL service instance"""
    return sql_service