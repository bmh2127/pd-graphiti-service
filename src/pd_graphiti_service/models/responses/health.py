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

"""Health check response models."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for health check endpoints."""
    
    status: str = Field(..., description="Overall health status (healthy/unhealthy)")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp of health check")
    version: str = Field(default="0.1.0", description="Service version")
    
    # Dependency health checks
    neo4j_connected: Optional[bool] = Field(None, description="Neo4j database connectivity status")
    openai_api_accessible: Optional[bool] = Field(None, description="OpenAI API accessibility status")
    graphiti_ready: Optional[bool] = Field(None, description="Graphiti service readiness status")
    
    # Optional echo data
    ping_data: Optional[str] = Field(None, description="Echo of ping data from request")
    
    # Detailed information for deep health checks
    details: Optional[Dict[str, Any]] = Field(None, description="Detailed health check information")
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }
