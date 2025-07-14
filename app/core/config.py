import os
from typing import Optional
from pydantic_settings import BaseSettings
from typing import List
import json
from pydantic import validator

class Settings(BaseSettings):
    # OpenRouter/AI Configuration (from environment only)
    OPENROUTER_API_KEY: str
    LLAMA_MODEL: str = "meta-llama/llama-4-scout:free"

    # Cosmos DB Configuration
    COSMOS_DB_ENDPOINT: str
    COSMOS_DB_KEY: str
    COSMOS_DB_DATABASE: str = "supply_chain_db"
    
    # Azure SQL Configuration (from environment only)
    SQL_SERVER: str
    SQL_DATABASE: str
    SQL_USERNAME: str
    SQL_PASSWORD: str
    SQL_DRIVER: str = "ODBC Driver 18 for SQL Server"

    # App Configuration
    app_env: str = "development"
    app_name: str = "AI Chatbot"
    app_version: str = "0.1.0"
    PROJECT_NAME: str = "AI Chatbot"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "AI-powered supply chain chatbot"
    DEBUG: bool = False
    
    # Database Configuration (legacy fields for compatibility)
    database_url: Optional[str] = None
    database_host: str = "localhost"
    database_port: int = 1433
    database_name: str = "chatbot_db"
    database_user: Optional[str] = None
    database_password: Optional[str] = None
    sqlalchemy_database_uri: str = ""
    
    
    
    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173/", "http://localhost:3000", "http://localhost:8080", "http://localhost:8000"]
    
    @validator('ALLOWED_ORIGINS', pre=True)
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(',')]
        return v
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Performance Configuration
    max_connections: int = 100
    connection_timeout: int = 30
    query_timeout: int = 30
    
    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_per_minutes: int = 1
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
    
    @property
    def database_url_complete(self) -> str:
        """Build complete database URL from environment variables"""
        if self.database_url:
            return self.database_url
        
        # Use the Azure SQL settings from environment
        return (
            f"mssql+pyodbc://{self.SQL_USERNAME}:{self.SQL_PASSWORD}"
            f"@{self.SQL_SERVER}:1433/{self.SQL_DATABASE}"
            f"?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
        )

settings = Settings()