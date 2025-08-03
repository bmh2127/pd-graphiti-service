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

"""File monitoring service for automatic export directory processing."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, Set, Optional, Callable, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, DirCreatedEvent

from .config import Settings
from .ingestion_service import IngestionService
from .models import IngestionStatus

logger = logging.getLogger(__name__)


class MonitoringStatus(str, Enum):
    """Status of file monitoring service."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class ProcessingResult:
    """Result of processing an export directory."""
    
    def __init__(self, export_path: Path, status: IngestionStatus, result: Dict[str, Any]):
        self.export_path = export_path
        self.status = status
        self.result = result
        self.timestamp = datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "export_path": str(self.export_path),
            "status": self.status,
            "result": self.result,
            "timestamp": self.timestamp.isoformat()
        }


class ExportDirectoryHandler(FileSystemEventHandler):
    """Handles file system events for export directory monitoring."""
    
    def __init__(self, file_monitor: 'FileMonitor'):
        """Initialize handler with reference to FileMonitor."""
        self.file_monitor = file_monitor
        
    def on_created(self, event):
        """Handle file/directory creation events."""
        if isinstance(event, DirCreatedEvent):
            # New directory created - check if it's an export
            export_path = Path(event.src_path)
            logger.info(f"New directory detected: {export_path}")
            
            # Schedule export processing
            asyncio.create_task(
                self.file_monitor._process_new_export_async(export_path)
            )
            
        elif isinstance(event, FileCreatedEvent):
            # Check if manifest.json was created in existing directory
            if event.src_path.endswith("manifest.json"):
                export_path = Path(event.src_path).parent
                logger.info(f"Manifest file detected: {export_path}")
                
                # Schedule export processing
                asyncio.create_task(
                    self.file_monitor._process_new_export_async(export_path)
                )


class FileMonitor:
    """Service for monitoring export directories and triggering automatic processing."""
    
    def __init__(
        self, 
        settings: Settings, 
        ingestion_service: IngestionService,
        export_directory: Optional[Path] = None
    ):
        """Initialize FileMonitor.
        
        Args:
            settings: Application settings
            ingestion_service: IngestionService for processing exports
            export_directory: Directory to monitor (defaults to settings.export_directory)
        """
        self.settings = settings
        self.ingestion_service = ingestion_service
        self.export_directory = export_directory or settings.export_directory
        
        # Monitoring state
        self._status = MonitoringStatus.STOPPED
        self._observer: Optional[Observer] = None
        self._handler: Optional[ExportDirectoryHandler] = None
        
        # Processing state
        self._processing_queue: asyncio.Queue = asyncio.Queue()
        self._processed_exports: Set[str] = set()
        self._processing_results: List[ProcessingResult] = []
        self._concurrent_processors = 2  # Max concurrent export processing
        self._processor_tasks: List[asyncio.Task] = []
        
        # Event callbacks
        self._on_export_started: Optional[Callable[[Path], None]] = None
        self._on_export_completed: Optional[Callable[[ProcessingResult], None]] = None
        self._on_export_failed: Optional[Callable[[Path, str], None]] = None
        
        logger.info(f"FileMonitor initialized for directory: {self.export_directory}")

    @property
    def status(self) -> MonitoringStatus:
        """Get current monitoring status."""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if monitoring is currently running."""
        return self._status == MonitoringStatus.RUNNING

    @property
    def processed_exports_count(self) -> int:
        """Get count of processed exports."""
        return len(self._processed_exports)

    @property
    def processing_results(self) -> List[Dict[str, Any]]:
        """Get list of processing results."""
        return [result.to_dict() for result in self._processing_results]

    def set_callbacks(
        self,
        on_export_started: Optional[Callable[[Path], None]] = None,
        on_export_completed: Optional[Callable[[ProcessingResult], None]] = None,
        on_export_failed: Optional[Callable[[Path, str], None]] = None
    ):
        """Set event callbacks for monitoring events.
        
        Args:
            on_export_started: Called when export processing starts
            on_export_completed: Called when export processing completes successfully
            on_export_failed: Called when export processing fails
        """
        self._on_export_started = on_export_started
        self._on_export_completed = on_export_completed
        self._on_export_failed = on_export_failed

    def _is_valid_export_directory(self, path: Path) -> bool:
        """Check if path appears to be a valid export directory.
        
        Args:
            path: Path to check
            
        Returns:
            True if appears to be valid export directory
        """
        if not path.is_dir():
            return False
            
        # Check for manifest.json
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            # Maybe manifest hasn't been created yet - wait a bit
            time.sleep(0.5)
            if not manifest_path.exists():
                return False
        
        # Check for episodes directory or episode files
        episodes_dir = path / "episodes"
        if episodes_dir.exists() and episodes_dir.is_dir():
            return True
            
        # Check for JSON files directly in directory
        json_files = list(path.glob("*.json"))
        return len(json_files) > 1  # More than just manifest.json
        
    def _get_export_id(self, path: Path) -> str:
        """Generate unique export ID for tracking.
        
        Args:
            path: Export directory path
            
        Returns:
            Unique export identifier
        """
        return f"{path.name}_{int(path.stat().st_mtime)}"

    async def _process_new_export_async(self, export_path: Path):
        """Process new export directory asynchronously.
        
        Args:
            export_path: Path to export directory
        """
        try:
            # Wait a bit for files to be fully written
            await asyncio.sleep(1.0)
            
            # Validate export directory
            if not self._is_valid_export_directory(export_path):
                logger.debug(f"Skipping invalid export directory: {export_path}")
                return
            
            # Generate export ID and check if already processed
            export_id = self._get_export_id(export_path)
            if export_id in self._processed_exports:
                logger.debug(f"Export already processed: {export_id}")
                return
            
            logger.info(f"Queuing new export for processing: {export_path}")
            await self._processing_queue.put((export_path, export_id))
            
        except Exception as e:
            logger.error(f"Error handling new export {export_path}: {e}")

    async def _export_processor_worker(self, worker_id: int):
        """Worker task for processing exports from the queue.
        
        Args:
            worker_id: Unique identifier for this worker
        """
        logger.info(f"Export processor worker {worker_id} started")
        
        while self._status == MonitoringStatus.RUNNING:
            try:
                # Wait for new export to process
                export_path, export_id = await asyncio.wait_for(
                    self._processing_queue.get(), timeout=1.0
                )
                
                # Mark as processed to avoid duplicates
                self._processed_exports.add(export_id)
                
                logger.info(f"Worker {worker_id} processing export: {export_path}")
                
                # Trigger callback
                if self._on_export_started:
                    self._on_export_started(export_path)
                
                # Process the export directory
                start_time = time.time()
                result = await self.ingestion_service.process_export_directory(
                    export_path,
                    validate_files=True,
                    force_reingest=False
                )
                
                processing_time = time.time() - start_time
                result["worker_id"] = worker_id
                result["total_processing_time"] = processing_time
                
                # Create processing result
                processing_result = ProcessingResult(
                    export_path=export_path,
                    status=result.get("status", IngestionStatus.FAILED),
                    result=result
                )
                
                # Store result
                self._processing_results.append(processing_result)
                
                # Keep only last 100 results to prevent memory growth
                if len(self._processing_results) > 100:
                    self._processing_results = self._processing_results[-100:]
                
                # Trigger completion callback
                if processing_result.status == IngestionStatus.SUCCESS:
                    logger.info(f"Worker {worker_id} successfully processed: {export_path}")
                    if self._on_export_completed:
                        self._on_export_completed(processing_result)
                else:
                    logger.error(f"Worker {worker_id} failed to process: {export_path}")
                    if self._on_export_failed:
                        error_msg = result.get("error", "Unknown processing error")
                        self._on_export_failed(export_path, error_msg)
                
                # Mark task as done
                self._processing_queue.task_done()
                
            except asyncio.TimeoutError:
                # No new exports to process - continue waiting
                continue
            except Exception as e:
                logger.error(f"Error in export processor worker {worker_id}: {e}")
                
                # Mark task as done if we got one
                try:
                    self._processing_queue.task_done()
                except ValueError:
                    pass
        
        logger.info(f"Export processor worker {worker_id} stopped")

    async def start_monitoring(self) -> Dict[str, Any]:
        """Start file monitoring and processing.
        
        Returns:
            Dict containing start result
        """
        if self._status == MonitoringStatus.RUNNING:
            return {
                "status": "already_running",
                "message": "File monitoring is already running",
                "export_directory": str(self.export_directory)
            }
        
        try:
            self._status = MonitoringStatus.STARTING
            
            # Ensure export directory exists
            self.export_directory.mkdir(parents=True, exist_ok=True)
            
            # Setup watchdog observer
            self._handler = ExportDirectoryHandler(self)
            self._observer = Observer()
            self._observer.schedule(
                self._handler, 
                str(self.export_directory), 
                recursive=True
            )
            
            # Start processing workers
            self._processor_tasks = []
            for i in range(self._concurrent_processors):
                task = asyncio.create_task(self._export_processor_worker(i))
                self._processor_tasks.append(task)
            
            # Start observer
            self._observer.start()
            self._status = MonitoringStatus.RUNNING
            
            result = {
                "status": "started",
                "message": "File monitoring started successfully",
                "export_directory": str(self.export_directory),
                "concurrent_processors": self._concurrent_processors,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"File monitoring started: {self.export_directory}")
            return result
            
        except Exception as e:
            self._status = MonitoringStatus.ERROR
            error_msg = f"Failed to start file monitoring: {e}"
            logger.error(error_msg)
            
            return {
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop file monitoring and processing.
        
        Returns:
            Dict containing stop result
        """
        if self._status == MonitoringStatus.STOPPED:
            return {
                "status": "already_stopped",
                "message": "File monitoring is already stopped"
            }
        
        try:
            logger.info("Stopping file monitoring...")
            self._status = MonitoringStatus.STOPPED
            
            # Stop observer
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5.0)
                self._observer = None
            
            # Cancel processor tasks
            for task in self._processor_tasks:
                task.cancel()
            
            # Wait for tasks to complete
            if self._processor_tasks:
                await asyncio.gather(*self._processor_tasks, return_exceptions=True)
            
            self._processor_tasks = []
            self._handler = None
            
            result = {
                "status": "stopped",
                "message": "File monitoring stopped successfully",
                "processed_exports": len(self._processed_exports),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("File monitoring stopped")
            return result
            
        except Exception as e:
            error_msg = f"Error stopping file monitoring: {e}"
            logger.error(error_msg)
            
            return {
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    async def pause_monitoring(self) -> Dict[str, Any]:
        """Pause file monitoring (stop watching but keep processing queue).
        
        Returns:
            Dict containing pause result
        """
        if self._status != MonitoringStatus.RUNNING:
            return {
                "status": "not_running",
                "message": "Cannot pause - monitoring is not running"
            }
        
        try:
            # Stop observer but keep processors running
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5.0)
                self._observer = None
            
            self._status = MonitoringStatus.PAUSED
            
            result = {
                "status": "paused",
                "message": "File monitoring paused (processing continues)",
                "queue_size": self._processing_queue.qsize(),
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("File monitoring paused")
            return result
            
        except Exception as e:
            error_msg = f"Error pausing file monitoring: {e}"
            logger.error(error_msg)
            
            return {
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    async def resume_monitoring(self) -> Dict[str, Any]:
        """Resume file monitoring from paused state.
        
        Returns:
            Dict containing resume result
        """
        if self._status != MonitoringStatus.PAUSED:
            return {
                "status": "not_paused",
                "message": "Cannot resume - monitoring is not paused"
            }
        
        try:
            # Restart observer
            self._handler = ExportDirectoryHandler(self)
            self._observer = Observer()
            self._observer.schedule(
                self._handler, 
                str(self.export_directory), 
                recursive=True
            )
            self._observer.start()
            
            self._status = MonitoringStatus.RUNNING
            
            result = {
                "status": "resumed",
                "message": "File monitoring resumed",
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info("File monitoring resumed")
            return result
            
        except Exception as e:
            error_msg = f"Error resuming file monitoring: {e}"
            logger.error(error_msg)
            
            return {
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    async def trigger_directory_scan(self) -> Dict[str, Any]:
        """Manually trigger a scan of the export directory for existing exports.
        
        Returns:
            Dict containing scan results
        """
        try:
            logger.info(f"Starting manual directory scan: {self.export_directory}")
            
            if not self.export_directory.exists():
                return {
                    "status": "error",
                    "error": f"Export directory does not exist: {self.export_directory}",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Find potential export directories
            discovered_exports = []
            for item in self.export_directory.iterdir():
                if item.is_dir() and self._is_valid_export_directory(item):
                    export_id = self._get_export_id(item)
                    if export_id not in self._processed_exports:
                        discovered_exports.append(item)
                        await self._processing_queue.put((item, export_id))
            
            result = {
                "status": "completed",
                "message": f"Directory scan completed",
                "discovered_exports": len(discovered_exports),
                "export_paths": [str(p) for p in discovered_exports],
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Manual directory scan found {len(discovered_exports)} new exports")
            return result
            
        except Exception as e:
            error_msg = f"Error during directory scan: {e}"
            logger.error(error_msg)
            
            return {
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status and statistics.
        
        Returns:
            Dict containing monitoring status
        """
        return {
            "status": self._status,
            "is_running": self.is_running,
            "export_directory": str(self.export_directory),
            "processed_exports_count": len(self._processed_exports),
            "queue_size": self._processing_queue.qsize(),
            "active_processors": len([t for t in self._processor_tasks if not t.done()]),
            "total_results": len(self._processing_results),
            "successful_results": len([r for r in self._processing_results if r.status == IngestionStatus.SUCCESS]),
            "failed_results": len([r for r in self._processing_results if r.status == IngestionStatus.FAILED]),
            "timestamp": datetime.now().isoformat()
        }

    def clear_processing_history(self) -> None:
        """Clear processing history and results."""
        self._processed_exports.clear()
        self._processing_results.clear()
        logger.info("Processing history cleared")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_monitoring()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_monitoring()


# Convenience function for creating FileMonitor
def create_file_monitor(
    settings: Settings, 
    ingestion_service: IngestionService,
    export_directory: Optional[Path] = None
) -> FileMonitor:
    """Create and return a FileMonitor instance.
    
    Args:
        settings: Application settings
        ingestion_service: IngestionService for processing exports
        export_directory: Optional custom export directory
        
    Returns:
        Configured FileMonitor instance
    """
    return FileMonitor(settings, ingestion_service, export_directory)
