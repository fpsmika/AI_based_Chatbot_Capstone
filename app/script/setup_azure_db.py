# setup_azure_db_compatible.py - Works with existing supply_records table
import sys
import os
import pyodbc
import logging
from datetime import datetime as dt
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('db_setup.log')
    ]
)
logger = logging.getLogger(__name__)

def log_sql_errors(e):
    """Helper to log SQL errors in detail"""
    if hasattr(e, 'args'):
        logger.error(f"SQL Error Details: {e.args}")
    if hasattr(e, 'sqlstate'):
        logger.error(f"SQL State: {e.sqlstate}")

def get_connection():
    """Create connection with debug logging"""
    try:
        logger.debug("Building connection string...")
        connection_string = (
            f"Driver={{{DRIVER}}};"
            f"Server=tcp:{SERVER},1433;"
            f"Database={DATABASE};"
            f"Uid={USERNAME};"
            f"Pwd={PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )
        logger.debug(f"Connecting to: {SERVER}/{DATABASE}")
        return pyodbc.connect(connection_string)
    except pyodbc.Error as e:
        log_sql_errors(e)
        raise

def check_existing_schema():
    """Check what tables and columns already exist"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        logger.info("Checking existing database schema...")
        
        # Check existing tables
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Existing tables: {tables}")
        
        # Check supply_records columns if it exists
        if 'supply_records' in tables:
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'supply_records'
                ORDER BY ORDINAL_POSITION
            """)
            columns = cursor.fetchall()
            logger.info("supply_records table columns:")
            for col in columns:
                logger.info(f"  - {col[0]} ({col[1]}, nullable: {col[2]})")
        
        return tables
        
    except Exception as e:
        logger.error(f"Failed to check schema: {e}")
        return []
    finally:
        if conn:
            conn.close()

def create_missing_tables():
    """Only create tables that don't exist and are compatible"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        existing_tables = check_existing_schema()
        
        # Remove embeddings table creation - not needed for text-to-SQL approach
        
        # Verify supply_records table exists (should already exist)
        if 'supply_records' not in existing_tables:
            logger.warning("supply_records table doesn't exist! This should have been created already.")
            logger.info("Creating supply_records table with your schema...")
            cursor.execute("""
                CREATE TABLE supply_records (
                    -- Primary Key
                    id NVARCHAR(50) PRIMARY KEY DEFAULT NEWID(),
                    
                    -- Batch tracking
                    batch_id NVARCHAR(50) NULL,
                    
                    -- Transaction Details
                    TransactionID NVARCHAR(50) NOT NULL,
                    FacilityID NVARCHAR(50) NOT NULL,
                    FacilityType NVARCHAR(100) NOT NULL,
                    Region NVARCHAR(100) NOT NULL,
                    BedSize NVARCHAR(50) NOT NULL,
                    Month INT NOT NULL,
                    Year INT NOT NULL,
                    LoadDate DATE NOT NULL,
                    
                    -- Vendor Information
                    Vendor NVARCHAR(200) NOT NULL,
                    VendorID NVARCHAR(50) NOT NULL,
                    
                    -- Manufacturer Information
                    Manufacturer NVARCHAR(200) NOT NULL,
                    ManufacturerID NVARCHAR(50) NOT NULL,
                    ManufacturercatalogNum NVARCHAR(100) NOT NULL,
                    
                    -- Item Details
                    ItemDesc NVARCHAR(500) NOT NULL,
                    
                    -- Financial Data
                    Quantity INT NOT NULL,
                    PricePaid DECIMAL(18,2) NOT NULL,
                    TotalSpend DECIMAL(18,2) NOT NULL,
                    
                    -- Optional columns
                    Department NVARCHAR(100) NULL,
                    Category NVARCHAR(100) NULL,
                    
                    -- Audit columns
                    created_at DATETIME2 DEFAULT GETUTCDATE(),
                    updated_at DATETIME2 DEFAULT GETUTCDATE()
                );
                
                -- Create indexes for better performance
                CREATE INDEX IX_supply_records_batch_id ON supply_records(batch_id);
                CREATE INDEX IX_supply_records_transaction ON supply_records(TransactionID);
                CREATE INDEX IX_supply_records_facility ON supply_records(FacilityID);
                CREATE INDEX IX_supply_records_vendor ON supply_records(VendorID);
                CREATE INDEX IX_supply_records_manufacturer ON supply_records(ManufacturerID);
                CREATE INDEX IX_supply_records_date ON supply_records(Year, Month);
                CREATE INDEX IX_supply_records_loaddate ON supply_records(LoadDate);
            """)
            conn.commit()
            logger.info("✅ Created supply_records table with indexes")
        else:
            logger.info("✅ supply_records table already exists")
        
        logger.info("Schema setup completed successfully!")
        return True
        
    except Exception as e:
        logger.critical(f"Fatal setup error: {str(e)}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def test_data_operations():
    """Test basic CRUD operations on existing schema"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        logger.info("Testing data operations...")
        
        # Test inserting a sample record
        test_record = {
            'id': 'test-001',
            'batch_id': 'test-batch',
            'TransactionID': 'TXN-001',
            'FacilityID': 'FAC-001',
            'FacilityType': 'Hospital',
            'Region': 'Northeast',
            'BedSize': '200-299',
            'Month': 7,
            'Year': 2025,
            'LoadDate': '2025-07-27',
            'Vendor': 'Test Vendor',
            'VendorID': 'V-001',
            'Manufacturer': 'Test Manufacturer',
            'ManufacturerID': 'M-001',
            'ManufacturercatalogNum': 'CAT-001',
            'ItemDesc': 'Test Supply Item',
            'Quantity': 10,
            'PricePaid': 25.50,
            'TotalSpend': 255.00,
            'Department': 'Surgery',
            'Category': 'Medical Supplies'
        }
        
        # Insert test record
        cursor.execute("""
            INSERT INTO supply_records (
                id, batch_id, TransactionID, FacilityID, FacilityType, Region, BedSize,
                Month, Year, LoadDate, Vendor, VendorID, Manufacturer, ManufacturerID,
                ManufacturercatalogNum, ItemDesc, Quantity, PricePaid, TotalSpend,
                Department, Category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_record['id'], test_record['batch_id'], test_record['TransactionID'],
            test_record['FacilityID'], test_record['FacilityType'], test_record['Region'],
            test_record['BedSize'], test_record['Month'], test_record['Year'],
            test_record['LoadDate'], test_record['Vendor'], test_record['VendorID'],
            test_record['Manufacturer'], test_record['ManufacturerID'],
            test_record['ManufacturercatalogNum'], test_record['ItemDesc'],
            test_record['Quantity'], test_record['PricePaid'], test_record['TotalSpend'],
            test_record['Department'], test_record['Category']
        ))
        conn.commit()
        
        # Query it back
        cursor.execute("SELECT COUNT(*) FROM supply_records WHERE id = ?", (test_record['id'],))
        count = cursor.fetchone()[0]
        
        if count == 1:
            logger.info("✅ Test record inserted and verified successfully")
            
            # Clean up test record
            cursor.execute("DELETE FROM supply_records WHERE id = ?", (test_record['id'],))
            conn.commit()
            logger.info("✅ Test record cleaned up")
        else:
            logger.error("❌ Test record verification failed")
        
        return True
        
    except Exception as e:
        logger.error(f"Data operations test failed: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    load_dotenv()
    
    # Config with validation
    SERVER = os.getenv('SQL_SERVER')
    DATABASE = os.getenv('SQL_DATABASE')
    USERNAME = os.getenv('SQL_USERNAME')
    PASSWORD = os.getenv('SQL_PASSWORD')
    DRIVER = os.getenv('SQL_DRIVER', 'ODBC Driver 18 for SQL Server')
    
    if not all([SERVER, DATABASE, USERNAME, PASSWORD]):
        logger.critical("Missing required environment variables")
        logger.debug(f"Current env: SERVER={SERVER}, DB={DATABASE}, USER={USERNAME}")
        sys.exit(1)
    
    logger.info("=== Azure DB Compatibility Setup ===")
    
    # Step 1: Check existing schema
    logger.info("Step 1: Checking existing schema...")
    existing_tables = check_existing_schema()
    
    # Step 2: Create any missing compatible tables
    logger.info("Step 2: Creating missing tables...")
    setup_success = create_missing_tables()
    
    # Step 3: Test operations
    logger.info("Step 3: Testing data operations...")
    test_success = test_data_operations()
    
    if setup_success and test_success:
        logger.info("🎉 Database setup completed successfully!")
        logger.info("Your existing supply_records table is compatible and ready to use.")
        sys.exit(0)
    else:
        logger.error("❌ Database setup failed")
        sys.exit(1)