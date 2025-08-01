# File: src/pd_graphiti_service/api/endpoints.py
"""Ingestion API endpoints."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Path as PathParam
from fastapi.responses import JSONResponse

from ..models.requests.ingestion import IngestDirectoryRequest, IngestEpisodeRequest
from ..models.responses.ingestion import IngestionResponse, EpisodeIngestionResult
from ..models.responses.status import StatusResponse, CurrentOperation
from ..models import IngestionStatus
from ..graphiti_client import GraphitiClient
from ..ingestion_service import IngestionService
from ..file_monitor import FileMonitor

router = APIRouter()

# Import dependencies from main module  
def get_graphiti_client() -> GraphitiClient:
    """Get GraphitiClient dependency."""
    from ..main import get_graphiti_client as _get_client
    return _get_client()

def get_ingestion_service() -> IngestionService:
    """Get IngestionService dependency."""
    from ..main import get_ingestion_service as _get_service
    return _get_service()

def get_file_monitor() -> FileMonitor:
    """Get FileMonitor dependency."""
    from ..main import get_file_monitor as _get_monitor
    return _get_monitor()

def get_task_manager():
    """Get TaskManager dependency."""
    from ..main import get_task_manager as _get_manager
    return _get_manager()

# In-memory storage for current operations (in production, use Redis/database)
_current_operations: Dict[str, CurrentOperation] = {}

async def background_directory_ingestion(
    operation_id: str,
    request: IngestDirectoryRequest,
    ingestion_service: IngestionService
):
    """Background task for directory ingestion."""
    try:
        # Update operation as started
        _current_operations[operation_id] = CurrentOperation(
            operation_type="directory_ingestion",
            operation_id=operation_id,
            started_at=datetime.now(),
            progress_percentage=0.0,
            current_step="Starting directory ingestion..."
        )
        
        # Process the export directory
        result = await ingestion_service.process_export_directory(
            export_dir=request.directory_path,
            validate_files=request.validate_files,
            force_reingest=request.force_reingest,
            episode_types_filter=request.episode_types_filter
        )
        
        # Update operation as completed
        _current_operations[operation_id].progress_percentage = 100.0
        _current_operations[operation_id].current_step = "Directory ingestion completed"
        
        return result
        
    except Exception as e:
        # Update operation as failed
        _current_operations[operation_id].current_step = f"Failed: {str(e)}"
        raise

@router.post(
    "/ingest/directory",
    response_model=IngestionResponse,
    summary="Ingest Export Directory",
    description="Trigger ingestion of a complete export directory with episodes"
)
async def ingest_directory(
    request: IngestDirectoryRequest,
    background_tasks: BackgroundTasks,
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    task_manager = Depends(get_task_manager)
) -> IngestionResponse:
    """
    Ingest all episodes from an export directory.
    
    This endpoint:
    - Validates the export directory structure
    - Processes episodes in the correct order
    - Runs as a background task for large exports
    - Returns immediately with a task ID for status tracking
    """
    
    # Validate directory exists
    if not request.directory_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Export directory not found: {request.directory_path}"
        )
    
    if not request.directory_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.directory_path}"
        )
    
    # Generate operation ID
    operation_id = f"ingest_{uuid.uuid4().hex[:8]}"
    
    try:
        # Create background task
        await task_manager.create_task(
            task_id=operation_id,
            coro=background_directory_ingestion(operation_id, request, ingestion_service),
            description=f"Directory ingestion: {request.directory_path.name}"
        )
        
        # Return response immediately
        return IngestionResponse(
            status=IngestionStatus.PROCESSING,
            message=f"Directory ingestion started. Use GET /status/{operation_id} to track progress.",
            episodes_processed=0,
            episodes_successful=0,
            episodes_failed=0,
            start_time=datetime.now(),
            episode_results=[],
            operation_id=operation_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start directory ingestion: {str(e)}"
        )

@router.post(
    "/ingest/episode",
    response_model=IngestionResponse,
    summary="Ingest Single Episode",
    description="Ingest a single episode for testing purposes"
)
async def ingest_episode(
    request: IngestEpisodeRequest,
    ingestion_service: IngestionService = Depends(get_ingestion_service)
) -> IngestionResponse:
    """
    Ingest a single episode.
    
    This endpoint is primarily used for testing and debugging.
    For production ingestion, use the directory endpoint.
    """
    
    start_time = datetime.now()
    
    try:
        # Process the episode
        result = await ingestion_service.process_single_episode(
            episode=request.episode,
            validate_episode=request.validate_episode,
            force_reingest=request.force_reingest
        )
        
        # Convert result to response format
        episode_result = EpisodeIngestionResult(
            episode_name=request.episode.episode_name,
            status=result["status"],
            processing_time_seconds=result.get("processing_time", 0.0),
            error_message=result.get("error"),
            graphiti_node_id=result.get("graphiti_node_id")
        )
        
        # Determine overall status
        overall_status = result["status"]
        episodes_successful = 1 if overall_status == IngestionStatus.SUCCESS else 0
        episodes_failed = 1 if overall_status == IngestionStatus.FAILED else 0
        
        return IngestionResponse(
            status=overall_status,
            message=f"Episode ingestion {overall_status}",
            episodes_processed=1,
            episodes_successful=episodes_successful,
            episodes_failed=episodes_failed,
            start_time=start_time,
            end_time=datetime.now(),
            total_processing_time_seconds=result.get("processing_time", 0.0),
            episode_results=[episode_result]
        )
        
    except Exception as e:
        return IngestionResponse(
            status=IngestionStatus.FAILED,
            message=f"Episode ingestion failed: {str(e)}",
            episodes_processed=1,
            episodes_successful=0,
            episodes_failed=1,
            start_time=start_time,
            end_time=datetime.now(),
            errors=[str(e)],
            episode_results=[
                EpisodeIngestionResult(
                    episode_name=request.episode.episode_name,
                    status=IngestionStatus.FAILED,
                    processing_time_seconds=0.0,
                    error_message=str(e)
                )
            ]
        )

@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Service Status",
    description="Get current service status and operation information"
)
async def get_service_status(
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    file_monitor: FileMonitor = Depends(get_file_monitor),
    graphiti_client: GraphitiClient = Depends(get_graphiti_client)
) -> StatusResponse:
    """
    Get comprehensive service status.
    
    Returns information about:
    - Current operations
    - Service health
    - Processing statistics
    - Knowledge graph status
    """
    
    try:
        # Get current operation (if any)
        current_operation = None
        if _current_operations:
            # Get the most recent operation
            latest_op_id = max(_current_operations.keys(), key=lambda k: _current_operations[k].started_at)
            current_operation = _current_operations[latest_op_id]
        
        # Get ingestion statistics
        ingestion_stats = ingestion_service.get_processing_stats()
        
        # Get file monitor status
        monitor_status = file_monitor.get_monitoring_status()
        
        # Get knowledge graph statistics (optional, may be slow)
        kg_stats = None
        try:
            kg_stats = await graphiti_client.get_graph_stats()
        except Exception as e:
            # Don't fail status request if graph stats unavailable
            pass
        
        # Determine service status
        if current_operation and current_operation.progress_percentage < 100:
            service_status = "processing"
        elif monitor_status["status"] == "error":
            service_status = "error"
        else:
            service_status = "idle"
        
        return StatusResponse(
            service_status=service_status,
            timestamp=datetime.now(),
            current_operation=current_operation,
            queued_operations=monitor_status.get("queue_size", 0),
            total_episodes_ingested=ingestion_stats["total_processed_episodes"],
            knowledge_graph_nodes=kg_stats.get("total_nodes") if kg_stats else None,
            knowledge_graph_edges=kg_stats.get("total_relationships") if kg_stats else None,
            uptime_seconds=monitor_status.get("uptime_seconds", 0.0),
            details={
                "ingestion_stats": ingestion_stats,
                "monitor_status": monitor_status,
                "graph_stats": kg_stats
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get service status: {str(e)}"
        )

@router.get(
    "/status/{operation_id}",
    summary="Operation Status",
    description="Get status of a specific background operation"
)
async def get_operation_status(
    operation_id: str = PathParam(..., description="Operation ID to check"),
    task_manager = Depends(get_task_manager)
) -> JSONResponse:
    """
    Get status of a specific background operation.
    
    Returns detailed information about the operation progress.
    """
    
    # Check background task status
    task_status = await task_manager.get_task_status(operation_id)
    
    if not task_status:
        # Check if it's in current operations
        if operation_id in _current_operations:
            operation = _current_operations[operation_id]
            return JSONResponse(
                status_code=200,
                content={
                    "operation_id": operation_id,
                    "status": "processing" if operation.progress_percentage < 100 else "completed",
                    "operation_type": operation.operation_type,
                    "started_at": operation.started_at.isoformat(),
                    "progress_percentage": operation.progress_percentage,
                    "current_step": operation.current_step,
                    "estimated_completion": operation.estimated_completion.isoformat() if operation.estimated_completion else None
                }
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Operation {operation_id} not found"
            )
    
    return JSONResponse(
        status_code=200,
        content={
            "operation_id": operation_id,
            "task_status": task_status,
            "timestamp": datetime.now().isoformat()
        }
    )

@router.get(
    "/stats",
    summary="Knowledge Graph Statistics",
    description="Get detailed knowledge graph statistics"
)
async def get_graph_stats(
    graphiti_client: GraphitiClient = Depends(get_graphiti_client)
) -> JSONResponse:
    """
    Get comprehensive knowledge graph statistics.
    
    Returns:
    - Node and relationship counts
    - Group-specific statistics
    - Node type distribution
    """
    
    try:
        stats = await graphiti_client.get_graph_stats()
        return JSONResponse(
            status_code=200,
            content={
                "knowledge_graph_statistics": stats,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get graph statistics: {str(e)}"
        )

@router.get(
    "/operations",
    summary="List Operations",
    description="List all background operations"
)
async def list_operations(
    task_manager = Depends(get_task_manager)
) -> JSONResponse:
    """
    List all background operations and their status.
    """
    
    try:
        tasks = await task_manager.list_tasks()
        
        # Also include current operations
        operations = {}
        for op_id, operation in _current_operations.items():
            operations[op_id] = {
                "operation_type": operation.operation_type,
                "started_at": operation.started_at.isoformat(),
                "progress_percentage": operation.progress_percentage,
                "current_step": operation.current_step,
                "status": "processing" if operation.progress_percentage < 100 else "completed"
            }
        
        return JSONResponse(
            status_code=200,
            content={
                "background_tasks": tasks,
                "current_operations": operations,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list operations: {str(e)}"
        )

@router.delete(
    "/operations/cleanup",
    summary="Cleanup Operations",
    description="Clean up completed operations and tasks"
)
async def cleanup_operations(
    max_age_hours: int = Query(24, description="Maximum age in hours for operations to keep"),
    task_manager = Depends(get_task_manager)
) -> JSONResponse:
    """
    Clean up old completed operations and background tasks.
    """
    
    try:
        # Clean up background tasks
        await task_manager.cleanup_completed_tasks(max_age_hours)
        
        # Clean up current operations
        cutoff_time = datetime.now()
        cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - max_age_hours)
        
        to_remove = []
        for op_id, operation in _current_operations.items():
            if operation.progress_percentage >= 100 and operation.started_at < cutoff_time:
                to_remove.append(op_id)
        
        for op_id in to_remove:
            del _current_operations[op_id]
        
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Cleaned up operations older than {max_age_hours} hours",
                "operations_removed": len(to_remove),
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup operations: {str(e)}"
        )