# File: src/pd_graphiti_service/models/responses/ingestion.py
"""Updated ingestion response models."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from .. import IngestionStatus


class EpisodeIngestionResult(BaseModel):
    """Result of ingesting a single episode."""
    
    episode_name: str = Field(..., description="Name of the episode that was processed")
    status: IngestionStatus = Field(..., description="Result status of the ingestion")
    processing_time_seconds: float = Field(..., description="Time taken to process this episode")
    error_message: Optional[str] = Field(None, description="Error message if ingestion failed")
    graphiti_node_id: Optional[str] = Field(None, description="Graphiti node ID if successfully ingested")


class IngestionResponse(BaseModel):
    """Response model for ingestion operations."""
    
    status: IngestionStatus = Field(..., description="Overall status of the ingestion operation")
    message: str = Field(..., description="Human-readable status message")
    
    # Episode processing results
    episodes_processed: int = Field(..., description="Total number of episodes processed")
    episodes_successful: int = Field(..., description="Number of episodes successfully ingested")
    episodes_failed: int = Field(..., description="Number of episodes that failed to ingest")
    
    # Timing information
    start_time: datetime = Field(..., description="When the ingestion started")
    end_time: Optional[datetime] = Field(None, description="When the ingestion completed")
    total_processing_time_seconds: Optional[float] = Field(None, description="Total time for ingestion")
    
    # Operation tracking
    operation_id: Optional[str] = Field(None, description="ID for tracking background operations")
    
    # Detailed results
    episode_results: List[EpisodeIngestionResult] = Field(
        default_factory=list, 
        description="Detailed results for each episode"
    )
    
    # Error information
    errors: List[str] = Field(default_factory=list, description="List of error messages")
    warnings: List[str] = Field(default_factory=list, description="List of warning messages")
    
    # Graph statistics
    knowledge_graph_stats: Optional[Dict[str, Any]] = Field(
        None, 
        description="Statistics about the knowledge graph after ingestion"
    )
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }