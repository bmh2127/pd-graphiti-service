"""Status response models."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from .. import IngestionStatus


class CurrentOperation(BaseModel):
    """Information about the current operation being performed."""
    
    operation_type: str = Field(..., description="Type of operation (e.g., 'directory_ingestion')")
    operation_id: str = Field(..., description="Unique identifier for this operation")
    started_at: datetime = Field(..., description="When the operation started")
    progress_percentage: float = Field(..., description="Progress as percentage (0-100)")
    current_step: str = Field(..., description="Description of current processing step")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


class StatusResponse(BaseModel):
    """Response model for service status endpoints."""
    
    service_status: str = Field(..., description="Overall service status (idle/processing/error)")
    timestamp: datetime = Field(default_factory=datetime.now, description="Status timestamp")
    
    # Current operation information
    current_operation: Optional[CurrentOperation] = Field(None, description="Currently running operation")
    
    # Last ingestion information
    last_ingestion_status: Optional[IngestionStatus] = Field(None, description="Status of last ingestion")
    last_ingestion_time: Optional[datetime] = Field(None, description="When last ingestion occurred")
    last_ingestion_episodes: Optional[int] = Field(None, description="Episodes processed in last ingestion")
    
    # Queue information
    queued_operations: int = Field(default=0, description="Number of operations in queue")
    
    # Knowledge graph statistics
    total_episodes_ingested: int = Field(default=0, description="Total episodes ever ingested")
    knowledge_graph_nodes: Optional[int] = Field(None, description="Total nodes in knowledge graph")
    knowledge_graph_edges: Optional[int] = Field(None, description="Total edges in knowledge graph")
    
    # System information
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    memory_usage_mb: Optional[float] = Field(None, description="Current memory usage in MB")
    
    # Additional details
    details: Optional[Dict[str, Any]] = Field(None, description="Additional status details")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }
