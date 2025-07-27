from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging
from typing import Generator
from app.core.config import settings

logger = logging.getLogger(__name__)

def create_database_engine():
    """Create SQLAlchemy engine with proper configuration"""
    try:
        database_url = settings.database_url_complete
        
        if not database_url:
            raise ValueError("Database URL is not configured. Check your environment variables.")
        
        logger.info(f"Creating database engine for: {database_url.split('@')[0] if '@' in database_url else 'Local DB'}")
        
        # Configure connection arguments based on database type
        connect_args = {}
        
        if "sqlite" in database_url.lower():
            connect_args = {
                "check_same_thread": False,
                "timeout": 30,
            }
        elif "mssql" in database_url.lower() or "sqlserver" in database_url.lower():
            # Azure SQL Server specific configurations
            connect_args = {
                "timeout": 30,
                "pool_timeout": 20,
                "pool_recycle": -1,
            }
        
        # Create engine with appropriate settings
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=settings.DEBUG,
            connect_args=connect_args
        )
        
        return engine
        
    except Exception as e:
        logger.error(f"Failed to create database engine: {str(e)}")
        raise

# Create SQLAlchemy engine with Azure SQL configuration
try:
    engine = create_database_engine()
except Exception as e:
    logger.error(f"Database engine creation failed: {e}")
    # Create a dummy engine for development/testing
    engine = None

# Create session factory
if engine:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    SessionLocal = None

# Create declarative base for models
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.
    Creates a new database session for each request.
    """
    if not SessionLocal:
        raise RuntimeError("Database is not properly configured. Check your environment variables.")
    
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

def test_database_connection() -> bool:
    """
    Test database connectivity.
    Returns True if connection is successful.
    """
    if not engine:
        logger.error("Database engine is not available")
        return False
        
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1 as test"))
            test_value = result.scalar()
            logger.info(f"Database connection test successful: {test_value}")
            return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False

def create_tables():
    """
    Create all database tables.
    """
    if not engine:
        logger.error("Database engine is not available")
        return False
        
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create tables: {str(e)}")
        return False

def get_table_info():
    """
    Get information about existing tables.
    """
    if not engine:
        logger.error("Database engine is not available")
        return []
        
    try:
        with engine.connect() as conn:
            # For SQL Server
            result = conn.execute(text("""
                SELECT 
                    t.name AS table_name,
                    COUNT(c.name) AS column_count
                FROM sys.tables t
                JOIN sys.columns c ON t.object_id = c.object_id
                GROUP BY t.name
                ORDER BY t.name
            """))
            tables = result.fetchall()
            return [{"table": row[0], "columns": row[1]} for row in tables]
    except Exception as e:
        logger.error(f"Failed to get table info: {str(e)}")
        return []

def get_database_status():
    """
    Get comprehensive database status information
    """
    status = {
        "engine_created": engine is not None,
        "connection_string_configured": bool(settings.database_url_complete),
        "connection_test": False,
        "tables": []
    }
    
    if engine:
        status["connection_test"] = test_database_connection()
        if status["connection_test"]:
            status["tables"] = get_table_info()
    
    return status