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

# File: src/pd_graphiti_service/api/health.py
"""Health check API endpoints."""

import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..models.requests.health import HealthCheckRequest
from ..models.responses.health import HealthResponse
from ..graphiti_client import GraphitiClient
from ..file_monitor import FileMonitor

router = APIRouter()

# Import dependencies from main module
def get_graphiti_client() -> GraphitiClient:
    """Get GraphitiClient dependency - will be replaced by main.py import."""
    from ..main import get_graphiti_client as _get_client
    return _get_client()

def get_file_monitor() -> FileMonitor:
    """Get FileMonitor dependency - will be replaced by main.py import."""
    from ..main import get_file_monitor as _get_monitor
    return _get_monitor()

@router.get(
    "",
    response_model=HealthResponse,
    summary="Basic Health Check",
    description="Quick health check that returns within 100ms"
)
async def health_check(
    ping_data: str = Query(None, description="Optional ping data to echo back")
) -> HealthResponse:
    """
    Basic health check endpoint.
    
    Returns service status and basic information quickly.
    Suitable for load balancer health checks.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        ping_data=ping_data
    )

@router.get(
    "/deep",
    response_model=HealthResponse,
    summary="Deep Health Check",
    description="Comprehensive health check testing all external dependencies"
)
async def deep_health_check(
    request: HealthCheckRequest = Depends(),
    graphiti_client: GraphitiClient = Depends(get_graphiti_client)
) -> HealthResponse:
    """
    Deep health check that tests all external dependencies.
    
    This endpoint:
    - Tests Neo4j connectivity
    - Tests OpenAI API accessibility
    - Verifies Graphiti readiness
    - May take several seconds to complete
    """
    start_time = time.time()
    
    try:
        # Test all connections
        connection_result = await graphiti_client.test_connection()
        
        # Determine overall status
        overall_status = "healthy" if connection_result["graphiti_ready"] else "degraded"
        
        # Get additional details if requested
        details = None
        if request.check_dependencies:
            details = {
                "connection_test_duration": time.time() - start_time,
                **connection_result
            }
        
        return HealthResponse(
            status=overall_status,
            timestamp=datetime.now(),
            neo4j_connected=connection_result["neo4j_connected"],
            openai_api_accessible=connection_result["openai_accessible"],
            graphiti_ready=connection_result["graphiti_ready"],
            ping_data=request.ping_data,
            details=details
        )
        
    except Exception as e:
        # Return unhealthy status with error information
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.now(),
            neo4j_connected=False,
            openai_api_accessible=False,
            graphiti_ready=False,
            ping_data=request.ping_data,
            details={
                "error": str(e),
                "test_duration": time.time() - start_time
            }
        )

@router.get(
    "/ready",
    summary="Readiness Probe",
    description="Kubernetes-style readiness probe"
)
async def readiness_probe(
    graphiti_client: GraphitiClient = Depends(get_graphiti_client),
    file_monitor: FileMonitor = Depends(get_file_monitor)
) -> JSONResponse:
    """
    Readiness probe for Kubernetes.
    
    Returns:
    - 200 if service is ready to handle requests
    - 503 if service is not ready (dependencies unavailable)
    """
    try:
        # Quick connection test
        connection_result = await graphiti_client.test_connection()
        
        # Check if essential services are ready
        services_ready = (
            connection_result["neo4j_connected"] and
            connection_result["openai_accessible"]
        )
        
        if services_ready:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "ready",
                    "timestamp": datetime.now().isoformat(),
                    "services": {
                        "neo4j": connection_result["neo4j_connected"],
                        "openai": connection_result["openai_accessible"],
                        "graphiti": connection_result["graphiti_ready"],
                        "file_monitor": file_monitor.status
                    }
                }
            )
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now().isoformat(),
                    "services": {
                        "neo4j": connection_result["neo4j_connected"],
                        "openai": connection_result["openai_accessible"],
                        "graphiti": connection_result["graphiti_ready"],
                        "file_monitor": file_monitor.status
                    },
                    "errors": connection_result.get("errors", [])
                }
            )
            
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
        )

@router.get(
    "/live",
    summary="Liveness Probe",
    description="Kubernetes-style liveness probe"
)
async def liveness_probe() -> JSONResponse:
    """
    Liveness probe for Kubernetes.
    
    Returns:
    - 200 if service is alive (always, unless process is dead)
    - Used by Kubernetes to determine if pod should be restarted
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
            "service": "pd-graphiti-service"
        }
    )
