import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Add OpenRouter configuration
    OPENROUTER_API_KEY: str = "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"
    LLAMA_MODEL: str = "meta-llama/llama-4-scout:free"
    
    # Update Azure SQL settings to match your connector
    SQL_SERVER: str = "supply-chatbot-server.database.windows.net"
    SQL_DATABASE: str = "supply-chatbot-db"
    SQL_USERNAME: str = "azureadmin"
    SQL_PASSWORD: str = "Password!123"
    SQL_DRIVER: str = "ODBC Driver 18 for SQL Server"

    # App Configuration
    app_env: str = "development"
    app_name: str = "AI Chatbot"
    app_version: str = "0.1.0"
    PROJECT_NAME: str = "AI Chatbot"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "AI-powered supply chain chatbot"
    DEBUG: bool = False
    
    # Database Configuration
    database_url: Optional[str] = None
    database_host: str = "localhost"
    database_port: int = 1433
    database_name: str = "chatbot_db"
    database_user: Optional[str] = None
    database_password: Optional[str] = None
    database_server: str = "supply-chatbot-server.database.windows.net"
    database_username: str = "azureadmin"
    database_driver: str = "ODBC Driver 18 for SQL Server"
    sqlalchemy_database_uri: str = ""
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # JWT Configuration
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS Configuration - Fixed to match main.py expectation
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8080", "http://localhost:8000"]
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080", "http://localhost:8000"]  # Keep both for compatibility
    
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
        """Build complete database URL from components"""
        if self.database_url:
            return self.database_url
        
        if not self.database_user or not self.database_password:
            raise ValueError("Database credentials not provided")
        
        return (
            f"mssql+pyodbc://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
            f"?driver=ODBC+Driver+18+for+SQL+Server"
        )

settings = Settings()