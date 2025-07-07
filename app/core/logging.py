import logging
import sys
from datetime import datetime
from typing import Any, Dict
import json
from pathlib import Path

from .config import settings

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if they exist
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        
        if hasattr(record, 'execution_time'):
            log_entry["execution_time"] = record.execution_time
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry, ensure_ascii=False)

class RequestLogger:
    """Logger for HTTP requests"""
    
    def __init__(self):
        self.logger = logging.getLogger("requests")
    
    def log_request(self, method: str, url: str, status_code: int, 
                   execution_time: float, request_id: str = None, 
                   user_id: str = None):
        """Log HTTP request details"""
        extra = {
            "request_id": request_id,
            "user_id": user_id,
            "execution_time": execution_time
        }
        
        message = f"{method} {url} - {status_code} - {execution_time:.3f}s"
        
        if status_code >= 400:
            self.logger.error(message, extra=extra)
        else:
            self.logger.info(message, extra=extra)

class DatabaseLogger:
    """Logger for database operations"""
    
    def __init__(self):
        self.logger = logging.getLogger("database")
    
    def log_query(self, query: str, execution_time: float, 
                 affected_rows: int = None, request_id: str = None):
        """Log database query execution"""
        extra = {
            "request_id": request_id,
            "execution_time": execution_time,
            "affected_rows": affected_rows
        }
        
        # Truncate long queries for logging
        query_preview = query[:200] + "..." if len(query) > 200 else query
        message = f"Query executed: {query_preview} - {execution_time:.3f}s"
        
        if affected_rows is not None:
            message += f" - {affected_rows} rows affected"
        
        self.logger.info(message, extra=extra)
    
    def log_connection_error(self, error: Exception, request_id: str = None):
        """Log database connection errors"""
        extra = {"request_id": request_id}
        self.logger.error(f"Database connection error: {str(error)}", 
                         extra=extra, exc_info=True)

def setup_logging():
    """Configure application logging"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Get log level from settings
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)
    
    # File handler for general logs
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    
    # Error file handler
    error_handler = logging.FileHandler(log_dir / "error.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(error_handler)
    
    # Configure specific loggers
    
    # Suppress uvicorn access logs in production
    if not settings.DEBUG:
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.setLevel(logging.WARNING)
    
    # Database logger
    db_logger = logging.getLogger("database")
    db_file_handler = logging.FileHandler(log_dir / "database.log", encoding="utf-8")
    db_file_handler.setFormatter(JSONFormatter())
    db_logger.addHandler(db_file_handler)
    
    # Request logger
    request_logger = logging.getLogger("requests")
    request_file_handler = logging.FileHandler(log_dir / "requests.log", encoding="utf-8")
    request_file_handler.setFormatter(JSONFormatter())
    request_logger.addHandler(request_file_handler)
    
    # AI service logger
    ai_logger = logging.getLogger("ai_service")
    ai_file_handler = logging.FileHandler(log_dir / "ai_service.log", encoding="utf-8")
    ai_file_handler.setFormatter(JSONFormatter())
    ai_logger.addHandler(ai_file_handler)
    
    logging.info(f"Logging configured - Level: {settings.log_level}")

def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)

# Initialize specialized loggers
request_logger = RequestLogger()
db_logger = DatabaseLogger()