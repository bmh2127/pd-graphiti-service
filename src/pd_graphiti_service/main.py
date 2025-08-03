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

"""FastAPI application for PD Graphiti Service."""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .graphiti_client import GraphitiClient, create_graphiti_client
from .ingestion_service import IngestionService, create_ingestion_service
from .file_monitor import FileMonitor, create_file_monitor
from .api.health import router as health_router
from .api.endpoints import router as api_router

# Import new modules
from .logging_config import configure_structured_logging, get_logger, RequestLoggingMiddleware, error_tracker
from .monitoring import setup_monitoring, get_metrics_collector, timer
from .config_validation import validate_configuration, raise_for_validation_errors, get_connection_monitor

# Configure structured logging
logger = get_logger(__name__)

# Global service instances
_services: Dict[str, Any] = {}
_background_tasks: Dict[str, Dict[str, Any]] = {}
_app_start_time = time.time()

class BackgroundTaskManager:
    """Manages background tasks and their status."""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock()
    
    async def create_task(self, task_id: str, coro, description: str = "") -> str:
        """Create and track a background task."""
        async with self.lock:
            if task_id in self.tasks:
                raise ValueError(f"Task {task_id} already exists")
            
            task = asyncio.create_task(coro)
            self.tasks[task_id] = {
                "task": task,
                "description": description,
                "status": "running",
                "created_at": datetime.now(),
                "result": None,
                "error": None
            }
            
            # Add completion callback
            task.add_done_callback(
                lambda t: asyncio.create_task(self._task_completed(task_id, t))
            )
            
            return task_id
    
    async def _task_completed(self, task_id: str, task: asyncio.Task):
        """Handle task completion."""
        async with self.lock:
            if task_id not in self.tasks:
                return
            
            if task.exception():
                self.tasks[task_id].update({
                    "status": "failed",
                    "error": str(task.exception()),
                    "completed_at": datetime.now()
                })
            else:
                self.tasks[task_id].update({
                    "status": "completed",
                    "result": task.result(),
                    "completed_at": datetime.now()
                })
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a background task."""
        async with self.lock:
            if task_id not in self.tasks:
                return None
            
            task_info = self.tasks[task_id].copy()
            # Remove the actual task object from response
            task_info.pop("task", None)
            return task_info
    
    async def list_tasks(self) -> Dict[str, Dict[str, Any]]:
        """List all background tasks."""
        async with self.lock:
            result = {}
            for task_id, task_info in self.tasks.items():
                info = task_info.copy()
                info.pop("task", None)  # Remove task object
                result[task_id] = info
            return result
    
    async def cleanup_completed_tasks(self, max_age_hours: int = 24):
        """Clean up old completed tasks."""
        async with self.lock:
            cutoff_time = datetime.now()
            cutoff_time = cutoff_time.replace(hour=cutoff_time.hour - max_age_hours)
            
            to_remove = []
            for task_id, task_info in self.tasks.items():
                if (task_info["status"] in ["completed", "failed"] and 
                    task_info.get("completed_at", datetime.now()) < cutoff_time):
                    to_remove.append(task_id)
            
            for task_id in to_remove:
                del self.tasks[task_id]

# Global task manager
task_manager = BackgroundTaskManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan management with comprehensive validation and monitoring."""
    # Startup
    logger.info("Starting PD Graphiti Service...")
    
    try:
        with timer("application_startup"):
            # Load settings first
            settings = Settings.from_env()  # Use direct instantiation to avoid circular dependency
            
            # Configure logging based on settings
            configure_structured_logging(
                log_level=settings.log_level,
                enable_json=(settings.log_format == "json"),
                service_name="pd-graphiti-service",
                service_version="0.1.0"
            )
            
            # Re-get logger after configuration
            startup_logger = get_logger(__name__)
            startup_logger.info(
                "Configuration loaded",
                neo4j_uri=settings.neo4j_uri,
                graphiti_group_id=settings.graphiti_group_id,
                log_level=settings.log_level,
                monitoring_enabled=settings.enable_monitoring
            )
            
            # Validate configuration and test connections
            startup_logger.info("Validating configuration and testing connections...")
            validation_results = await validate_configuration(settings)
            
            if not validation_results["valid"]:
                startup_logger.error(
                    "Configuration validation failed",
                    errors=validation_results["errors"],
                    warnings=validation_results["warnings"]
                )
                raise_for_validation_errors(validation_results, fail_fast=True)
            else:
                startup_logger.info(
                    "Configuration validation passed",
                    warnings_count=len(validation_results["warnings"]),
                    validation_time=validation_results["validation_time"]
                )
                if validation_results["warnings"]:
                    for warning in validation_results["warnings"]:
                        startup_logger.warning("Configuration warning", message=warning)
            
            # Initialize services
            startup_logger.info("Initializing core services...")
            graphiti_client = create_graphiti_client(settings)
            ingestion_service = create_ingestion_service(settings, graphiti_client)
            file_monitor = create_file_monitor(settings, ingestion_service)
            connection_monitor = get_connection_monitor(settings)
            
            # Store services globally
            _services["settings"] = settings
            _services["graphiti_client"] = graphiti_client
            _services["ingestion_service"] = ingestion_service
            _services["file_monitor"] = file_monitor
            _services["task_manager"] = task_manager
            _services["connection_monitor"] = connection_monitor
            
            # Initialize database
            startup_logger.info("Initializing database...")
            try:
                with timer("database_initialization", source_type="database"):
                    init_result = await graphiti_client.initialize_database()
                    startup_logger.info("Database initialization completed", status=init_result['status'])
                    get_metrics_collector().record_ingestion_request("success", "database_init")
            except Exception as e:
                startup_logger.warning("Database initialization failed", error=str(e))
                get_metrics_collector().record_ingestion_failure("database_init_error", "database")
            
            # Test connections and record metrics
            startup_logger.info("Testing service connections...")
            try:
                with timer("connection_test", source_type="connection"):
                    conn_result = await graphiti_client.test_connection()
                    
                    # Record health metrics
                    metrics = get_metrics_collector()
                    metrics.record_health_check("neo4j", 0.1, conn_result.get("neo4j_connected", False))
                    metrics.record_health_check("openai", 0.1, conn_result.get("openai_accessible", False))
                    metrics.record_health_check("graphiti", 0.1, conn_result.get("graphiti_ready", False))
                    
                    if conn_result["graphiti_ready"]:
                        startup_logger.info("✅ All services ready", connection_status=conn_result)
                    else:
                        startup_logger.warning("⚠️ Service partially ready", connection_status=conn_result)
            except Exception as e:
                error_id = error_tracker.track_error(e, {"operation": "startup_connection_test"})
                startup_logger.error("❌ Connection test failed", error_id=error_id, error=str(e))
            
            # Start file monitoring if enabled
            if settings.enable_monitoring:
                startup_logger.info("Starting file monitoring...")
                try:
                    with timer("file_monitor_start", source_type="file_monitor"):
                        monitor_result = await file_monitor.start_monitoring()
                        startup_logger.info("File monitoring started", status=monitor_result['status'])
                        get_metrics_collector().record_file_event("monitor_start", "success")
                except Exception as e:
                    startup_logger.warning("File monitoring failed to start", error=str(e))
                    get_metrics_collector().record_file_event("monitor_start", "failure")
            
            startup_logger.info("🚀 PD Graphiti Service started successfully")
        
        yield
        
    except Exception as e:
        error_id = error_tracker.track_error(e, {"operation": "application_startup"})
        logger.error("Failed to start service", error_id=error_id, error=str(e))
        raise
    
    finally:
        # Shutdown
        shutdown_logger = get_logger(__name__)
        shutdown_logger.info("Shutting down PD Graphiti Service...")
        
        # Stop file monitoring
        if "file_monitor" in _services:
            try:
                await _services["file_monitor"].stop_monitoring()
                shutdown_logger.info("File monitoring stopped")
                get_metrics_collector().record_file_event("monitor_stop", "success")
            except Exception as e:
                shutdown_logger.warning("Error stopping file monitor", error=str(e))
                get_metrics_collector().record_file_event("monitor_stop", "failure")
        
        # Close GraphitiClient
        if "graphiti_client" in _services:
            try:
                await _services["graphiti_client"].close()
                shutdown_logger.info("GraphitiClient closed")
            except Exception as e:
                shutdown_logger.warning("Error closing GraphitiClient", error=str(e))
        
        # Clean up background tasks
        try:
            await task_manager.cleanup_completed_tasks(0)  # Remove all tasks
            shutdown_logger.info("Background tasks cleaned up")
        except Exception as e:
            shutdown_logger.warning("Error cleaning up tasks", error=str(e))
        
        shutdown_logger.info("👋 PD Graphiti Service shutdown complete")

def create_app() -> FastAPI:
    """Create and configure FastAPI application with monitoring and logging."""
    
    app = FastAPI(
        title="PD Graphiti Service",
        description="Parkinson's Disease Target Discovery Knowledge Graph Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Set up monitoring and metrics
    setup_monitoring(app)
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add request logging middleware if enabled
    # Note: We'll check settings during startup, but middleware is added here
    app.add_middleware(RequestLoggingMiddleware)
    
    # Custom request metrics middleware
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Record metrics
        process_time = time.time() - start_time
        
        # Add custom headers
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Service"] = "pd-graphiti-service"
        response.headers["X-Version"] = "0.1.0"
        
        return response
    
    # Exception handlers with structured logging and error tracking
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        error_logger = get_logger(__name__)
        error_logger.warning(
            "Validation error",
            path=str(request.url.path),
            method=request.method,
            errors=exc.errors()
        )
        
        # Record metrics
        get_metrics_collector().record_ingestion_failure("validation_error", "request")
        
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation Error",
                "detail": exc.errors(),
                "path": str(request.url.path),
                "timestamp": datetime.now().isoformat()
            }
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions."""
        error_logger = get_logger(__name__)
        error_logger.warning(
            "HTTP exception",
            status_code=exc.status_code,
            path=str(request.url.path),
            method=request.method,
            detail=exc.detail
        )
        
        # Record metrics
        get_metrics_collector().record_ingestion_failure("http_error", "request")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": f"HTTP {exc.status_code}",
                "detail": exc.detail,
                "path": str(request.url.path),
                "timestamp": datetime.now().isoformat()
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions with error tracking."""
        error_id = error_tracker.track_error(
            exc,
            context={
                "path": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("user-agent"),
            },
            user_message="An unexpected error occurred while processing your request"
        )
        
        # Record metrics
        get_metrics_collector().record_ingestion_failure("internal_error", "request")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred",
                "error_id": error_id,
                "path": str(request.url.path),
                "timestamp": datetime.now().isoformat()
            }
        )
    
    # Include routers
    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(api_router, prefix="/api/v1", tags=["Ingestion"])
    
    # Root endpoint
    @app.get("/", summary="Service Information")
    async def root():
        """Get basic service information."""
        uptime = time.time() - _app_start_time
        
        return {
            "service": "PD Graphiti Service",
            "version": "0.1.0",
            "description": "Parkinson's Disease Target Discovery Knowledge Graph Service",
            "uptime_seconds": round(uptime, 2),
            "status": "running",
            "docs": "/docs",
            "health": "/health",
            "timestamp": datetime.now().isoformat()
        }
    
    return app

# Dependency injection functions
def get_settings() -> Settings:
    """Get settings dependency."""
    if "settings" not in _services:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _services["settings"]

def get_graphiti_client() -> GraphitiClient:
    """Get GraphitiClient dependency."""
    if "graphiti_client" not in _services:
        raise HTTPException(status_code=503, detail="GraphitiClient not available")
    return _services["graphiti_client"]

def get_ingestion_service() -> IngestionService:
    """Get IngestionService dependency."""
    if "ingestion_service" not in _services:
        raise HTTPException(status_code=503, detail="IngestionService not available")
    return _services["ingestion_service"]

def get_file_monitor() -> FileMonitor:
    """Get FileMonitor dependency."""
    if "file_monitor" not in _services:
        raise HTTPException(status_code=503, detail="FileMonitor not available")
    return _services["file_monitor"]

def get_task_manager() -> BackgroundTaskManager:
    """Get TaskManager dependency."""
    if "task_manager" not in _services:
        raise HTTPException(status_code=503, detail="TaskManager not available")
    return _services["task_manager"]

# Create app instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "pd_graphiti_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )
