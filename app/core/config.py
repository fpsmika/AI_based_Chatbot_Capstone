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
    
    # Azure AI Search (matching your .env)
    AZURE_SEARCH_SERVICE_NAME: str = ""
    AZURE_SEARCH_API_KEY: str = ""
    AZURE_SEARCH_INDEX_NAME: str = "chatbot-index-1"
    
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
    
    # Embedding Model (matching your .env)
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Logging (matching your .env)
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Processing Configuration
    MAX_INGEST_ROWS: Optional[int] = None  # None = no limit
    DEFAULT_BATCH_SIZE: int = 500
    EMBEDDING_BATCH_SIZE: int = 100
    
    # AI Chat Configuration
    DEFAULT_MAX_TOKENS: int = 800
    DEFAULT_TEMPERATURE: float = 0.7
    DEFAULT_CONTEXT_LIMIT: int = 5
    
    # Rate Limiting
    REQUESTS_PER_MINUTE: int = 60
    
    # Health Check
    HEALTH_CHECK_INTERVAL: int = 30  # seconds
    
    # Search Configuration
    VECTOR_SEARCH_MIN_SCORE: float = 0.5
    FULLTEXT_SEARCH_TOP_K: int = 15
    HYBRID_SEARCH_ENABLED: bool = True
    
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
    
    # Check Azure AI Search
    if not all([settings.AZURE_SEARCH_SERVICE_NAME, settings.AZURE_SEARCH_API_KEY]):
        errors.append("Azure AI Search configuration incomplete. Check AZURE_SEARCH_* environment variables.")
    
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

# Database table configurations
DATABASE_TABLES = {
    "supply_records": {
        "primary_key": "TransactionID",
        "required_fields": ["TransactionID", "FacilityID", "Vendor", "ItemDesc", "TotalSpend"],
        "index_fields": ["Vendor", "FacilityType", "Category", "Department", "LoadDate"]
    }
}

# AI Search index schema
AI_SEARCH_SCHEMA = {
    "name": settings.AZURE_SEARCH_INDEX_NAME,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "searchable": False},
        {"name": "content", "type": "Edm.String", "searchable": True, "analyzer": "standard.lucene"},
        {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": True, "vector": True, "dimensions": 384},
        {"name": "TransactionID", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "FacilityID", "type": "Edm.String", "filterable": True},
        {"name": "FacilityType", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "Region", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "Vendor", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "Manufacturer", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "ItemDesc", "type": "Edm.String", "searchable": True, "analyzer": "standard.lucene"},
        {"name": "TotalSpend", "type": "Edm.Double", "filterable": True, "sortable": True},
        {"name": "Department", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "Category", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "batch_id", "type": "Edm.String", "filterable": True},
        {"name": "metadata", "type": "Edm.String", "searchable": False}
    ]
}