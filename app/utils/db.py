from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging
from typing import Generator
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create SQLAlchemy engine with Azure SQL configuration
engine = create_engine(
    settings.database_url_complete,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.DEBUG,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    } if "sqlite" in settings.database_url_complete else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base for models
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database sessions.
    Creates a new database session for each request.
    """
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