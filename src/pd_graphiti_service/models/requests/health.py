"""Health check request models."""

from typing import Optional
from pydantic import BaseModel, Field


class HealthCheckRequest(BaseModel):
    """Request model for health check endpoints."""
    
    ping_data: Optional[str] = Field(
        None, 
        description="Optional ping data to echo back in response"
    )
    check_dependencies: bool = Field(
        default=False,
        description="Whether to perform deep health checks on external dependencies"
    )
