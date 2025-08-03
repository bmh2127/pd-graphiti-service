"""
PD Discovery Platform - Parkinson's Disease Target Discovery Knowledge Graph Service

Copyright (C) 2025 PD Discovery Platform Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

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
