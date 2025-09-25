# app/core/config.py
import os
from typing import List, Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Application (matching your .env)
    APP_ENV: str = "development"
    APP_NAME: str = "AI Chatbot"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # Legacy fields for backward compatibility
    PROJECT_NAME: str = "Supply Chain AI Chatbot"
    DESCRIPTION: str = "AI-powered chatbot for healthcare supply chain analysis"
    VERSION: str = "1.0.0"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    
    # Database - Azure SQL Database (matching your .env)
    SQL_SERVER: str = ""
    SQL_DATABASE: str = ""
    SQL_USERNAME: str = ""
    SQL_PASSWORD: str = ""
    SQL_DRIVER: str = "ODBC Driver 18 for SQL Server"
    
    # Legacy Database Configuration (from your .env)
    DATABASE_URL: str = ""
    DATABASE_SERVER: str = ""
    DATABASE_NAME: str = ""
    DATABASE_USERNAME: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_DRIVER: str = "ODBC Driver 18 for SQL Server"
    
    # Azure Storage (matching your .env)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    BLOB_CONTAINER_NAME: str = "raw-upload"
    
    # AI/LLM Configuration (matching your .env)
    OPENROUTER_API_KEY: str = ""
    LLAMA_MODEL: str = "google/gemma-3-27b-it:free"
    OPENROUTER_MODEL: str = "anthropic/claude-3-haiku"  # Keep for backward compatibility
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    
    # Cosmos DB (keeping for compatibility even though not used)
    COSMOS_DB_ENDPOINT: str = ""
    COSMOS_DB_KEY: str = ""
    COSMOS_DB_DATABASE: str = ""
    COSMOS_DB_CONTAINER: str = ""
    COSMOS_DB_VECTOR_CONTAINER: str = ""
    
    # Logging (matching your .env)
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Processing Configuration
    MAX_INGEST_ROWS: Optional[int] = None  # None = no limit
    DEFAULT_BATCH_SIZE: int = 500
    
    # AI Chat Configuration
    DEFAULT_MAX_TOKENS: int = 800
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_CONTEXT_LIMIT: int = 5
    
    # Rate Limiting
    REQUESTS_PER_MINUTE: int = 60
    
    # Health Check
    HEALTH_CHECK_INTERVAL: int = 30  # seconds
    
    @property
    def get_database_url(self) -> str:
        """Construct SQL Server connection string from SQL_* fields"""
        if not all([self.SQL_SERVER, self.SQL_DATABASE, self.SQL_USERNAME, self.SQL_PASSWORD]):
            # Fallback to DATABASE_URL if SQL_* fields are not set
            return self.DATABASE_URL
        
        return (
            f"mssql+pyodbc://{self.SQL_USERNAME}:{self.SQL_PASSWORD}"
            f"@{self.SQL_SERVER}/{self.SQL_DATABASE}"
            f"?driver={self.SQL_DRIVER.replace(' ', '+')}"
            f"&TrustServerCertificate=yes"
            f"&Encrypt=yes"
        )
    
    @property
    def database_url_complete(self) -> str:
        """Alias for get_database_url to maintain backward compatibility"""
        return self.get_database_url
    
    # ADDED: Property to construct Azure Search endpoint from service name if not provided
    @property
    def get_azure_search_endpoint(self) -> str:
        """Get Azure Search endpoint, constructing from service name if needed"""
        if self.AZURE_SEARCH_ENDPOINT:
            return self.AZURE_SEARCH_ENDPOINT
        elif self.AZURE_SEARCH_SERVICE_NAME:
            return f"https://{self.AZURE_SEARCH_SERVICE_NAME}.search.windows.net"
        return ""
    

    def get_raw_connection_string(self) -> str:
        """Generate a raw ODBC connection string"""
        return (
            f"Driver={{{self.SQL_DRIVER}}};"
            f"Server={self.SQL_SERVER};"
            f"Database={self.SQL_DATABASE};"
            f"Uid={self.SQL_USERNAME};"
            f"Pwd={self.SQL_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )

    def get_database_config_status(self) -> dict:
        """Return a dictionary showing the status of database configuration"""
        return {
            "SQL_SERVER configured": bool(self.SQL_SERVER),
            "SQL_DATABASE configured": bool(self.SQL_DATABASE),
            "SQL_USERNAME configured": bool(self.SQL_USERNAME),
            "SQL_PASSWORD configured": bool(self.SQL_PASSWORD),
            "SQL_DRIVER configured": bool(self.SQL_DRIVER),
            "Can generate connection string": bool(self.get_raw_connection_string()),
            "Can generate SQLAlchemy URL": bool(self.get_database_url)
        }
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra environment variables
        
        @classmethod
        def parse_env_var(cls, field_name: str, raw_val: str) -> any:
            if field_name == 'ALLOWED_ORIGINS':
                return [x.strip() for x in raw_val.split(',')]
            return cls.json_loads(raw_val)

# Create global settings instance
settings = Settings()

def validate_settings():
    """Validate critical configuration settings"""
    errors = []
    
    # Check database configuration - use the property method
    if not settings.database_url_complete:
        errors.append("Database configuration incomplete. Check SQL_* or DATABASE_URL environment variables.")
    
    # Check LLM configuration
    if not settings.OPENROUTER_API_KEY:
        errors.append("LLM configuration incomplete. Check OPENROUTER_API_KEY environment variable.")
    
    if errors:
        error_msg = "\n".join(f"  - {error}" for error in errors)
        raise ValueError(f"Configuration validation failed:\n{error_msg}")
    
    return True

# Environment-specific settings
def get_environment() -> str:
    """Determine the current environment"""
    return os.getenv("ENVIRONMENT", "development").lower()

def is_production() -> bool:
    """Check if running in production"""
    return get_environment() == "production"

def is_development() -> bool:
    """Check if running in development"""
    return get_environment() == "development"



def test_database_connection():
    """Test the database connection and return diagnostic information"""
    from app.core.config import settings
    import pyodbc
    from datetime import datetime
    
    result = {
        "success": False,
        "error": None,
        "error_type": None,
        "server_version": None,
        "timestamp": datetime.now().isoformat(),
        "guidance": None
    }
    
    if not hasattr(settings, 'get_raw_connection_string'):
        result["error"] = "get_raw_connection_string() method not available"
        result["error_type"] = "ConfigurationError"
        result["guidance"] = "Add get_raw_connection_string() method to settings"
        return result
    
    try:
        conn_str = settings.get_raw_connection_string()
        with pyodbc.connect(conn_str, timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            
            result["success"] = True
            result["server_version"] = version.split('\n')[0]
            return result
            
    except pyodbc.Error as e:
        result["error"] = str(e)
        result["error_type"] = "DatabaseError"
        
        if "Cannot open database" in str(e):
            result["guidance"] = "Database might not exist or credentials are incorrect"
        elif "login failed" in str(e):
            result["guidance"] = "Authentication failed - check username and password"
        elif "server not found" in str(e):
            result["guidance"] = "Server name might be incorrect or network issues"
        elif "timeout" in str(e):
            result["guidance"] = "Connection timed out - check firewall rules and network"
        elif "driver" in str(e).lower():
            result["guidance"] = "ODBC driver might not be installed"
        elif "40613" in str(e):
            result["guidance"] = "Database might be paused - check Azure portal"
        
        return result
    except Exception as e:
        result["error"] = str(e)
        result["error_type"] = "UnknownError"
        result["guidance"] = "Unexpected error occurred - check logs for details"
        return result

# Database table configurations
DATABASE_TABLES = {
    "supply_records": {
        "primary_key": "TransactionID",
        "required_fields": ["TransactionID", "FacilityID", "Vendor", "ItemDesc", "TotalSpend"],
        "index_fields": ["Vendor", "FacilityType", "Category", "Department", "LoadDate"]
    }
}