import sys
import os
import pyodbc
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Azure SQL Database Configuration from environment variables
SERVER = os.getenv('SQL_SERVER')
DATABASE = os.getenv('SQL_DATABASE')
USERNAME = os.getenv('SQL_USERNAME')
PASSWORD = os.getenv('SQL_PASSWORD')
DRIVER = os.getenv('SQL_DRIVER', 'ODBC Driver 18 for SQL Server')

# Validate that all required environment variables are present
if not all([SERVER, DATABASE, USERNAME, PASSWORD]):
    logger.error("Missing required environment variables. Please check your .env file.")
    logger.error("Required: SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD")
    sys.exit(1)

def get_connection():
    """Create a connection to Azure SQL Database"""
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
    return pyodbc.connect(connection_string)

# SQL Commands for Transaction Table Only
SCHEMA_COMMANDS = [
    # Drop existing table if it exists
    "IF OBJECT_ID('transactions', 'U') IS NOT NULL DROP TABLE transactions;",
    
    # Create transactions table with your exact schema
    """
    CREATE TABLE transactions (
        TransactionID NVARCHAR(50) PRIMARY KEY,
        FacilityID NVARCHAR(50) NOT NULL,
        FacilityType NVARCHAR(100) NOT NULL,
        Region NVARCHAR(100) NOT NULL,
        BedSize NVARCHAR(50) NOT NULL,
        Month INT NOT NULL CHECK (Month BETWEEN 1 AND 12),
        Year INT NOT NULL CHECK (Year >= 2000),
        LoadDate DATE NOT NULL,
        Vendor NVARCHAR(200) NOT NULL
    );
    """,
    
    # Create performance indexes
    "CREATE INDEX idx_transactions_vendor ON transactions(Vendor);",
    "CREATE INDEX idx_transactions_date ON transactions(LoadDate);",
    
    # Insert sample data matching your format
    """
    INSERT INTO transactions (
        TransactionID, FacilityID, FacilityType, Region, BedSize,
        Month, Year, LoadDate, Vendor
    ) VALUES 
        ('TRANS001', 'FAC001', 'Hospital', 'West', '200-300', 6, 2023, '2023-06-15', 'VendorA'),
        ('TRANS002', 'FAC002', 'Clinic', 'East', '0-0', 6, 2023, '2023-06-16', 'VendorB'),
        ('TRANS003', 'FAC003', 'Hospital', 'Central', '100-200', 7, 2023, '2023-07-01', 'VendorC'),
        ('TRANS004', 'FAC004', 'Clinic', 'North', '50-100', 7, 2023, '2023-07-02', 'VendorA'),
        ('TRANS005', 'FAC005', 'Hospital', 'South', '300+', 8, 2023, '2023-08-15', 'VendorD');
    """
]

def execute_commands():
    """Execute all database setup commands"""
    conn = None
    try:
        logger.info(f"Connecting to Azure SQL Database: {SERVER}/{DATABASE}")
        conn = get_connection()
        cursor = conn.cursor()
        
        logger.info("Starting Azure SQL Database setup...")
        
        for cmd in SCHEMA_COMMANDS:
            try:
                logger.info(f"Executing: {cmd[:80]}...")
                cursor.execute(cmd)
                conn.commit()
                logger.info("✅ Success")
            except pyodbc.Error as e:
                logger.warning(f"⚠️ Skipped (likely exists): {str(e)}")
                conn.rollback()
        
        # Verify setup
        logger.info("\n🔍 Verification:")
        cursor.execute("""
            SELECT 
                t.name AS table_name, 
                COUNT(c.name) AS columns
            FROM sys.tables t
            JOIN sys.columns c ON t.object_id = c.object_id
            WHERE t.name = 'transactions'
            GROUP BY t.name
        """)
        result = cursor.fetchone()
        if result:
            logger.info(f"Found table: {result.table_name} with {result.columns} columns")
        
        logger.info("\nSample transaction data:")
        cursor.execute("SELECT TOP 3 * FROM transactions")
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        for row in rows:
            logger.info(dict(zip(columns, row)))
        
        logger.info("\n🚀 Database setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    success = execute_commands()
    sys.exit(0 if success else 1)