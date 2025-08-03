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
