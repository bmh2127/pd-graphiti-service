"""FastAPI application for PD Graphiti Service."""

import asyncio
import logging
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

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
    """FastAPI lifespan management."""
    # Startup
    logger.info("Starting PD Graphiti Service...")
    
    try:
        # Load settings
        settings = get_settings()
        logger.info(f"Loaded settings: Neo4j={settings.neo4j_uri}, Group={settings.graphiti_group_id}")
        
        # Initialize services
        graphiti_client = create_graphiti_client(settings)
        ingestion_service = create_ingestion_service(settings, graphiti_client)
        file_monitor = create_file_monitor(settings, ingestion_service)
        
        # Store services globally
        _services["settings"] = settings
        _services["graphiti_client"] = graphiti_client
        _services["ingestion_service"] = ingestion_service
        _services["file_monitor"] = file_monitor
        _services["task_manager"] = task_manager
        
        # Initialize database
        try:
            init_result = await graphiti_client.initialize_database()
            logger.info(f"Database initialization: {init_result['status']}")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")
        
        # Test connections
        try:
            conn_result = await graphiti_client.test_connection()
            if conn_result["graphiti_ready"]:
                logger.info("✅ All services ready")
            else:
                logger.warning(f"⚠️ Service partially ready: {conn_result}")
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
        
        # Start file monitoring if enabled
        if settings.enable_monitoring:
            try:
                monitor_result = await file_monitor.start_monitoring()
                logger.info(f"File monitoring: {monitor_result['status']}")
            except Exception as e:
                logger.warning(f"File monitoring failed to start: {e}")
        
        logger.info("🚀 PD Graphiti Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise
    
    finally:
        # Shutdown
        logger.info("Shutting down PD Graphiti Service...")
        
        # Stop file monitoring
        if "file_monitor" in _services:
            try:
                await _services["file_monitor"].stop_monitoring()
                logger.info("File monitoring stopped")
            except Exception as e:
                logger.warning(f"Error stopping file monitor: {e}")
        
        # Close GraphitiClient
        if "graphiti_client" in _services:
            try:
                await _services["graphiti_client"].close()
                logger.info("GraphitiClient closed")
            except Exception as e:
                logger.warning(f"Error closing GraphitiClient: {e}")
        
        # Clean up background tasks
        try:
            await task_manager.cleanup_completed_tasks(0)  # Remove all tasks
            logger.info("Background tasks cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up tasks: {e}")
        
        logger.info("👋 PD Graphiti Service shutdown complete")

def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="PD Graphiti Service",
        description="Parkinson's Disease Target Discovery Knowledge Graph Service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Log request
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} "
            f"[{response.status_code}] {process_time:.3f}s"
        )
        
        # Add custom headers
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Service"] = "pd-graphiti-service"
        
        return response
    
    # Exception handlers
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors."""
        logger.warning(f"Validation error on {request.url.path}: {exc}")
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
        logger.warning(f"HTTP error {exc.status_code} on {request.url.path}: {exc.detail}")
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
        """Handle general exceptions."""
        logger.error(f"Unhandled error on {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred",
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