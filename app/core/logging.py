import logging
import logging.config
import sys
from typing import Dict, Any
from app.core.config import settings

def setup_logging() -> None:
    """
    Configure logging for the application
    """
    # Determine log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Determine which formatter to use based on LOG_FORMAT setting
    if settings.LOG_FORMAT.lower() == "json":
        default_formatter = "json"
    else:
        default_formatter = "default"
    
    # Logging configuration
    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "[%(asctime)s] %(levelname)-8s %(name)-20s %(funcName)-15s:%(lineno)-4d %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": default_formatter,  # Use the determined formatter
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "detailed",
                "filename": "logs/app.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": logging.ERROR,
                "formatter": "detailed",
                "filename": "logs/error.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "encoding": "utf8",
            }
        },
        "loggers": {
            # Application loggers
            "app": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "app.services": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "app.api": {
                "level": log_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            
            # Third-party loggers
            "azure": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "azure.core.pipeline.policies.http_logging_policy": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": logging.WARNING if not settings.DEBUG else logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            },
            "sentence_transformers": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "transformers": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "httpx": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn": {
                "level": logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": logging.WARNING,
                "handlers": ["console"],
                "propagate": False,
            },
            "fastapi": {
                "level": logging.INFO,
                "handlers": ["console"],
                "propagate": False,
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console", "error_file"],
        }
    }
    
    # Apply configuration
    logging.config.dictConfig(logging_config)
    
    # Create logs directory if it doesn't exist
    import os
    os.makedirs("logs", exist_ok=True)
    
    # Log startup message
    logger = logging.getLogger("app")
    logger.info(f"Logging configured - Level: {settings.LOG_LEVEL}")
    logger.info(f"Environment: {settings.DEBUG and 'DEBUG' or 'PRODUCTION'}")

class StructuredLogger:
    """
    Structured logging utility for consistent log formatting
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def info(self, message: str, **kwargs):
        """Log info with structured data"""
        extra_data = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message}{' | ' + extra_data if extra_data else ''}"
        self.logger.info(full_message)
    
    def error(self, message: str, **kwargs):
        """Log error with structured data"""
        extra_data = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message}{' | ' + extra_data if extra_data else ''}"
        self.logger.error(full_message)
    
    def warning(self, message: str, **kwargs):
        """Log warning with structured data"""
        extra_data = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message}{' | ' + extra_data if extra_data else ''}"
        self.logger.warning(full_message)
    
    def debug(self, message: str, **kwargs):
        """Log debug with structured data"""
        extra_data = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
        full_message = f"{message}{' | ' + extra_data if extra_data else ''}"
        self.logger.debug(full_message)

def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(name)

# Performance logging decorator
import functools
import time

def log_performance(logger_name: str = None):
    """Decorator to log function performance"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(logger_name or f"app.performance.{func.__module__}")
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(f"{func.__name__} completed in {execution_time:.3f}s")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {str(e)}")
                raise
        
        return wrapper
    return decorator

# Request logging middleware helper
def log_request(request_id: str, method: str, path: str, status_code: int = None, duration: float = None):
    """Log HTTP request details"""
    logger = logging.getLogger("app.api.requests")
    
    if status_code and duration:
        logger.info(f"Request completed | id={request_id} | {method} {path} | status={status_code} | duration={duration:.3f}s")
    else:
        logger.info(f"Request started | id={request_id} | {method} {path}")

# Database operation logging
def log_db_operation(operation: str, table: str, count: int = None, duration: float = None):
    """Log database operations"""
    logger = logging.getLogger("app.database")
    
    extra_info = []
    if count is not None:
        extra_info.append(f"count={count}")
    if duration is not None:
        extra_info.append(f"duration={duration:.3f}s")
    
    extra_str = " | ".join(extra_info)
    message = f"{operation} on {table}" + (f" | {extra_str}" if extra_str else "")
    logger.info(message)

# AI operation logging
def log_ai_operation(operation: str, query: str = None, tokens: int = None, duration: float = None):
    """Log AI/LLM operations"""
    logger = logging.getLogger("app.ai")
    
    extra_info = []
    if query:
        # Truncate long queries
        query_preview = query[:50] + "..." if len(query) > 50 else query
        extra_info.append(f"query='{query_preview}'")
    if tokens:
        extra_info.append(f"tokens={tokens}")
    if duration:
        extra_info.append(f"duration={duration:.3f}s")
    
    extra_str = " | ".join(extra_info)
    message = f"{operation}" + (f" | {extra_str}" if extra_str else "")
    logger.info(message)