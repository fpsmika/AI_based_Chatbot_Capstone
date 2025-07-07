import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from app.utils.db import get_engine
from sqlalchemy import text

def test_connection():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Proper way to execute raw SQL with SQLAlchemy 2.0+
            version = conn.execute(text("SELECT @@VERSION")).scalar()
            print(f"\n✅ Successful connection to Azure SQL!")
            print(f"Server version: {version}")
            
            # Additional verification
            tables = conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'dbo'
            """)).scalar()
            print(f"Found {tables} tables in dbo schema")
            return True
            
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    test_connection()