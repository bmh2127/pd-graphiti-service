"""Base models for pd-graphiti-service."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field


class IngestionStatus(str, Enum):
    """Status of episode ingestion process."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class EpisodeMetadata(BaseModel):
    """Metadata for a Graphiti episode."""
    gene_symbol: str = Field(..., description="Gene symbol (e.g., SNCA, LRRK2)")
    episode_type: str = Field(..., description="Type of episode (gene_profile, gwas_evidence, etc.)")
    export_timestamp: datetime = Field(..., description="When the episode was exported from Dagster")
    file_path: Path = Field(..., description="Path to the episode JSON file")
    file_size: int = Field(..., ge=0, description="Size of the episode file in bytes")
    checksum: Optional[str] = Field(None, description="MD5 checksum of the episode file")
    validation_status: IngestionStatus = Field(
        default=IngestionStatus.PENDING, 
        description="Current validation/ingestion status"
    )
    error_message: Optional[str] = Field(None, description="Error message if validation/ingestion failed")


class GraphitiEpisode(BaseModel):
    """Complete episode data for Graphiti ingestion."""
    episode_name: str = Field(..., description="Unique name for the episode in Graphiti")
    episode_body: str = Field(..., description="Main content of the episode")
    source: str = Field(..., description="Source type (e.g., 'dagster_pipeline')")
    source_description: str = Field(..., description="Human-readable description of the source")
    group_id: str = Field(default="pd_target_discovery", description="Graphiti group ID for organization")
    metadata: EpisodeMetadata = Field(..., description="Additional metadata about the episode")

    model_config = {
        "json_encoders": {
            Path: str,
            datetime: lambda v: v.isoformat()
        }
    }


class ExportManifest(BaseModel):
    """Manifest file describing an export directory."""
    export_id: str = Field(..., description="Unique identifier for this export")
    export_timestamp: datetime = Field(..., description="When the export was created")
    dagster_run_id: str = Field(..., description="Dagster run ID that generated this export")
    total_episodes: int = Field(..., description="Total number of episodes in this export")
    episode_types: Dict[str, int] = Field(..., description="Count of each episode type")
    genes: list[str] = Field(..., description="List of gene symbols included in this export")
    checksum: str = Field(..., description="Overall checksum for the export")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }


# Export commonly used models
__all__ = [
    "IngestionStatus",
    "EpisodeMetadata", 
    "GraphitiEpisode",
    "ExportManifest"
]
