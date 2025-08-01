"""Configuration management."""

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    
    # OpenAI Configuration
    openai_api_key: str
    
    # Neo4j Configuration
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str
    
    # Graphiti Configuration
    graphiti_group_id: str = "pd_target_discovery"
    
    # Export Directory Configuration
    export_directory: Path = Path("../pd-target-identification/exports")
    
    # Logging Configuration
    log_level: str = "INFO"
    
    # FastAPI Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Monitoring Configuration
    enable_monitoring: bool = True
    metrics_port: int = 8001

    @field_validator("export_directory", mode="before")
    @classmethod
    def convert_export_directory_to_path(cls, v):
        """Convert export directory string to Path object."""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level is one of the standard Python logging levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    @field_validator("neo4j_uri")
    @classmethod
    def validate_neo4j_uri(cls, v):
        """Basic validation for Neo4j URI format."""
        if not v.startswith(("bolt://", "neo4j://", "bolt+s://", "neo4j+s://")):
            raise ValueError("neo4j_uri must start with bolt://, neo4j://, bolt+s://, or neo4j+s://")
        return v

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        return cls(
            openai_api_key=cls._get_env_var("OPENAI_API_KEY"),
            neo4j_uri=cls._get_env_var("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=cls._get_env_var("NEO4J_USER", "neo4j"),
            neo4j_password=cls._get_env_var("NEO4J_PASSWORD"),
            graphiti_group_id=cls._get_env_var("GRAPHITI_GROUP_ID", "pd_target_discovery"),
            export_directory=Path(cls._get_env_var("EXPORT_DIRECTORY", "../pd-target-identification/exports")),
            log_level=cls._get_env_var("LOG_LEVEL", "INFO"),
            host=cls._get_env_var("HOST", "0.0.0.0"),
            port=int(cls._get_env_var("PORT", "8000")),
            enable_monitoring=cls._get_env_var("ENABLE_MONITORING", "true").lower() == "true",
            metrics_port=int(cls._get_env_var("METRICS_PORT", "8001")),
        )

    @staticmethod
    def _get_env_var(name: str, default: Optional[str] = None) -> str:
        """Get environment variable with optional default."""
        value = os.getenv(name, default)
        if value is None:
            raise ValueError(f"Required environment variable {name} is not set")
        return value


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings.from_env()


# Global settings instance - lazy loaded
_settings: Optional[Settings] = None


def settings() -> Settings:
    """Get cached settings instance."""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
