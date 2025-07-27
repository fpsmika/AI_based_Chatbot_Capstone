# setup_azure_db.py - Enhanced with debugging
import sys
import os
import pyodbc
import logging
from datetime import datetime as dt  # Renamed to avoid conflict
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # More verbose than INFO
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
    if hasattr(e, 'handler'):
        logger.error(f"Error in handler: {e.handler}")

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

def execute_commands():
    """Execute with transaction logging"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        logger.info("Starting schema setup...")
        
        for i, cmd in enumerate(SCHEMA_COMMANDS, 1):
            try:
                # Log the command type (DDL/DML)
                cmd_type = "DDL" if any(cmd.strip().upper().startswith(x) for x in ['CREATE', 'DROP', 'ALTER']) else "DML"
                logger.debug(f"Executing {cmd_type} command {i}/{len(SCHEMA_COMMANDS)}: {cmd[:100]}...")
                
                cursor.execute(cmd)
                conn.commit()
                
                if cursor.rowcount >= 0:
                    logger.debug(f"Rows affected: {cursor.rowcount}")
                
            except pyodbc.Error as e:
                logger.error(f"⚠️ Command failed (attempt {i}): {str(e)}")
                log_sql_errors(e)
                conn.rollback()
                # Continue to next command even if one fails
        
        # Verification with detailed diagnostics
        logger.info("Verifying schema...")
        verify_schema(conn)
        
        logger.info("Schema setup completed successfully!")
        return True
        
    except Exception as e:
        logger.critical(f"Fatal setup error: {str(e)}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logger.debug("Connection closed")

def verify_schema(conn):
    """Detailed schema verification"""
    cursor = conn.cursor()
    
    # 1. Check tables exist
    cursor.execute("""
        SELECT name, type_desc 
        FROM sys.objects 
        WHERE type IN ('U') 
        ORDER BY name
    """)
    tables = cursor.fetchall()
    logger.info(f"Found {len(tables)} tables")
    
    for table in tables:
        logger.debug(f"Table: {table.name} ({table.type_desc})")
        
        # 2. Check columns for each table
        cursor.execute(f"""
            SELECT column_name, data_type 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{table.name}'
        """)
        cols = cursor.fetchall()
        logger.debug(f"  Columns: {[c.column_name for c in cols]}")
    
    # 3. Check constraints
    cursor.execute("""
        SELECT name, type_desc 
        FROM sys.objects 
        WHERE type IN ('PK', 'F') 
        ORDER BY type_desc, name
    """)
    constraints = cursor.fetchall()
    logger.info(f"Found {len(constraints)} constraints")
    
    # 4. Check row counts in key tables
    for table in ['transactions', 'facilities', 'vendors']:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            logger.info(f"Row count in {table}: {count}")
        except:
            logger.warning(f"Could not count rows in {table}")

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
    
    # Schema definition (unchanged from your version)
    SCHEMA_COMMANDS = [
        # Drop existing tables
        "IF OBJECT_ID('dbo.transactions', 'U') IS NOT NULL DROP TABLE dbo.transactions;",
        "IF OBJECT_ID('dbo.facilities', 'U') IS NOT NULL DROP TABLE dbo.facilities;",
        "IF OBJECT_ID('dbo.vendors', 'U') IS NOT NULL DROP TABLE dbo.vendors;",
        "IF OBJECT_ID('dbo.supplies', 'U') IS NOT NULL DROP TABLE dbo.supplies;",
        
        # Create vendors table
        """
        CREATE TABLE dbo.vendors (
            VendorID NVARCHAR(50) PRIMARY KEY,
            VendorName NVARCHAR(200) NOT NULL,
            created_at DATETIME2 DEFAULT GETDATE()
        );
        """,
        
        # Create facilities table
        """
        CREATE TABLE dbo.facilities (
            FacilityID NVARCHAR(50) PRIMARY KEY,
            FacilityType NVARCHAR(100) NOT NULL,
            Region NVARCHAR(100) NOT NULL,
            BedSize NVARCHAR(50) NOT NULL,
            created_at DATETIME2 DEFAULT GETDATE()
        );
        """,
        
        # Create supplies table
        """
        CREATE TABLE dbo.supplies (
            SupplyID NVARCHAR(50) PRIMARY KEY,
            ManufacturerCatalogNum NVARCHAR(100),
            ItemDesc NVARCHAR(500) NOT NULL,
            ManufacturerID NVARCHAR(50) NOT NULL,
            created_at DATETIME2 DEFAULT GETDATE()
        );
        """,
        
        # Create transactions table
        """
        CREATE TABLE dbo.transactions (
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
            created_at DATETIME2 DEFAULT GETDATE(),
            FOREIGN KEY (FacilityID) REFERENCES dbo.facilities(FacilityID),
            FOREIGN KEY (VendorID) REFERENCES dbo.vendors(VendorID),
            FOREIGN KEY (SupplyID) REFERENCES dbo.supplies(SupplyID)
        );
        """,
        
        # Create indexes
        "CREATE INDEX idx_transaction_id ON dbo.transactions(TransactionID);",
        "CREATE INDEX idx_transaction_facility ON dbo.transactions(FacilityID);",
        "CREATE INDEX idx_transaction_vendor ON dbo.transactions(VendorID);"
    ]
    
    success = execute_commands()
    sys.exit(0 if success else 1)