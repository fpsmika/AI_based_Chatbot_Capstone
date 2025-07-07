# app/utils/db.py
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / '.env')

def get_engine():
    """Create SQLAlchemy engine with URL-encoded credentials"""
    username = os.getenv("DATABASE_USERNAME")
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))  # Critical for special chars
    server = os.getenv("DATABASE_SERVER")
    database = os.getenv("DATABASE_NAME")
    
    connection_url = (
    "mssql+pyodbc://azureadmin:Password%21123@supply-chatbot-server.database.windows.net:1433/supply-chatbot-db"
    "?driver=ODBC+Driver+18+for+SQL+Server"
    "&Encrypt=yes"
    "&TrustServerCertificate=no"
)
    
    return create_engine(connection_url, echo=True)  # echo=True for debug

if __name__ == "__main__":
    engine = get_engine()
    with engine.connect() as conn:
        print("✅ Connection successful!")
        print("Server version:", conn.scalar("SELECT @@VERSION"))