"""Ingestion request models."""

from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator

from .. import GraphitiEpisode


class IngestDirectoryRequest(BaseModel):
    """Request to ingest an entire export directory."""
    
    directory_path: Path = Field(..., description="Path to the export directory containing episodes")
    validate_files: bool = Field(
        default=True, 
        description="Whether to validate file checksums before ingestion"
    )
    force_reingest: bool = Field(
        default=False,
        description="Whether to re-ingest episodes that were already processed successfully"
    )
    episode_types_filter: Optional[List[str]] = Field(
        None,
        description="Optional list of episode types to ingest (if None, ingest all)"
    )
    
    @field_validator("directory_path")
    @classmethod
    def validate_directory_path(cls, v):
        """Validate that the directory path exists."""
        path = Path(v)
        if not path.is_absolute():
            # Convert relative paths to absolute
            path = Path.cwd() / path
        return path


class IngestEpisodeRequest(BaseModel):
    """Request to ingest a single episode (for testing)."""
    
    episode: GraphitiEpisode = Field(..., description="Complete episode data to ingest")
    force_reingest: bool = Field(
        default=False,
        description="Whether to re-ingest if episode was already processed"
    )
    validate_episode: bool = Field(
        default=True,
        description="Whether to validate episode data before ingestion"
    )
