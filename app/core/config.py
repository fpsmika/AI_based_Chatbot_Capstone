import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Configuration
    PROJECT_NAME: str = "AI Chatbot"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "AI-powered supply chain chatbot"
    DEBUG: bool = False
    
    # API Configuration
    api_v1_prefix: str = "/api/v1"
    
    # Database Configuration
    database_url: Optional[str] = None
    database_host: str = "localhost"
    database_port: int = 1433
    database_name: str = "chatbot_db"
    database_user: Optional[str] = None
    database_password: Optional[str] = None
    
    # Redis Configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # JWT Configuration
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS Configuration
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]
    
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
            f"?driver=ODBC+Driver+17+for+SQL+Server"
        )
    
    @property
    def redis_url(self) -> str:
        """Build Redis URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    DEBUG: bool = True  # Ensure this is True


settings = Settings()