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


class DagsterExportInfo(BaseModel):
    """Export metadata from Dagster pipeline."""
    timestamp: str = Field(..., description="Export timestamp string")
    directory: str = Field(..., description="Export directory path")
    dagster_asset: str = Field(..., description="Dagster asset that generated the export")
    pipeline_version: str = Field(..., description="Pipeline version")


class EpisodeSummary(BaseModel):
    """Summary of episodes in the export."""
    total_episodes: int = Field(..., description="Total number of episodes")
    episodes_by_type: Dict[str, int] = Field(..., description="Count of each episode type")
    genes_included: list[str] = Field(..., description="List of gene symbols included")
    total_genes: int = Field(..., description="Total number of unique genes")


class EpisodeStructure(BaseModel):
    """Description of episode file structure."""
    episode_metadata: str = Field(..., description="Description of episode metadata")
    graphiti_episode: str = Field(..., description="Description of graphiti episode data")


class IngestionInstructions(BaseModel):
    """Instructions for ingesting the episodes."""
    recommended_order: list[str] = Field(..., description="Recommended processing order")
    file_format: str = Field(..., description="File format (e.g., 'json')")
    encoding: str = Field(..., description="File encoding (e.g., 'utf-8')")
    episode_structure: EpisodeStructure = Field(..., description="Episode file structure description")


class ValidationInfo(BaseModel):
    """Validation information for the export."""
    total_files: int = Field(..., description="Total number of files")
    total_errors: int = Field(..., description="Total number of errors")
    success_rate: float = Field(..., description="Success rate percentage")
    checksums_available: bool = Field(..., description="Whether checksums are available")


class ExportManifest(BaseModel):
    """Manifest file describing a Dagster export directory (matches actual Dagster format)."""
    export_info: DagsterExportInfo = Field(..., description="Export metadata")
    episode_summary: EpisodeSummary = Field(..., description="Summary of episodes")
    ingestion_instructions: IngestionInstructions = Field(..., description="Ingestion instructions")
    validation: ValidationInfo = Field(..., description="Validation information")
    next_steps: list[str] = Field(..., description="Recommended next steps")
    
    # Convenience properties for backward compatibility
    @property
    def export_id(self) -> str:
        """Generate export ID from timestamp and asset."""
        return f"{self.export_info.dagster_asset}_{self.export_info.timestamp}"
    
    @property
    def export_timestamp(self) -> str:
        """Get export timestamp."""
        return self.export_info.timestamp
    
    @property
    def total_episodes(self) -> int:
        """Get total episodes count."""
        return self.episode_summary.total_episodes
    
    @property
    def episode_types(self) -> Dict[str, int]:
        """Get episode types dict."""
        return self.episode_summary.episodes_by_type
    
    @property
    def genes(self) -> list[str]:
        """Get genes list."""
        return self.episode_summary.genes_included
    
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
    "ExportManifest",
    "DagsterExportInfo",
    "EpisodeSummary",
    "IngestionInstructions",
    "ValidationInfo",
    "EpisodeStructure"
]
