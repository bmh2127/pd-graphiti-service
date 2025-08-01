"""Tests for FileMonitor."""

import asyncio
import json
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from pd_graphiti_service.config import Settings
from pd_graphiti_service.ingestion_service import IngestionService
from pd_graphiti_service.file_monitor import (
    FileMonitor,
    MonitoringStatus,
    ProcessingResult,
    ExportDirectoryHandler,
    create_file_monitor
)
from pd_graphiti_service.models import IngestionStatus


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        openai_api_key="test-key",
        neo4j_password="test-password",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        graphiti_group_id="test_group",
        export_directory=Path("/tmp/test_exports")
    )


@pytest.fixture
def mock_ingestion_service():
    """Create mock IngestionService."""
    service = AsyncMock(spec=IngestionService)
    
    # Mock successful export directory processing
    service.process_export_directory.return_value = {
        "status": IngestionStatus.SUCCESS,
        "export_id": "test_export_123",
        "total_episodes_loaded": 5,
        "processing_time": 2.5
    }
    
    return service


@pytest.fixture
def temp_export_directory():
    """Create temporary export directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        export_dir = Path(temp_dir) / "exports"
        export_dir.mkdir()
        yield export_dir


@pytest.fixture
def sample_export_data():
    """Create sample export directory with manifest and episodes."""
    return {
        "manifest": {
            "export_id": "test_export_20250701_123456",
            "export_timestamp": "2025-07-01T12:34:56",
            "dagster_run_id": "dagster_run_123",
            "total_episodes": 2,
            "episode_types": {"gene_profile": 1, "gwas_evidence": 1},
            "genes": ["SNCA"],
            "checksum": "abc123def456"
        },
        "episode": {
            "episode_name": "Gene_Profile_SNCA",
            "episode_body": "SNCA encodes α-synuclein...",
            "source": "dagster_pipeline",
            "source_description": "Test episode",
            "group_id": "test_group"
        }
    }


def create_sample_export(export_dir: Path, export_name: str, sample_data: dict):
    """Create a sample export directory with manifest and episodes."""
    export_path = export_dir / export_name
    export_path.mkdir()
    
    # Create manifest.json
    manifest_path = export_path / "manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(sample_data["manifest"], f)
    
    # Create episodes directory
    episodes_dir = export_path / "episodes"
    episodes_dir.mkdir()
    
    gene_profile_dir = episodes_dir / "gene_profile"
    gene_profile_dir.mkdir()
    
    # Create episode file
    episode_path = gene_profile_dir / "SNCA_gene_profile.json"
    with open(episode_path, 'w') as f:
        json.dump(sample_data["episode"], f)
    
    return export_path


class TestMonitoringStatus:
    """Test MonitoringStatus enum."""
    
    def test_monitoring_status_values(self):
        """Test MonitoringStatus enum values."""
        assert MonitoringStatus.STOPPED == "stopped"
        assert MonitoringStatus.STARTING == "starting"
        assert MonitoringStatus.RUNNING == "running"
        assert MonitoringStatus.PAUSED == "paused"
        assert MonitoringStatus.ERROR == "error"


class TestProcessingResult:
    """Test ProcessingResult class."""
    
    def test_processing_result_creation(self):
        """Test ProcessingResult creation and conversion."""
        export_path = Path("/test/export")
        status = IngestionStatus.SUCCESS
        result_data = {
            "export_id": "test_123",
            "total_episodes": 5,
            "processing_time": 2.5
        }
        
        result = ProcessingResult(export_path, status, result_data)
        
        assert result.export_path == export_path
        assert result.status == status
        assert result.result == result_data
        assert isinstance(result.timestamp, datetime)
        
        # Test dictionary conversion
        result_dict = result.to_dict()
        assert result_dict["export_path"] == str(export_path)
        assert result_dict["status"] == status
        assert result_dict["result"] == result_data
        assert "timestamp" in result_dict


class TestExportDirectoryHandler:
    """Test ExportDirectoryHandler class."""
    
    def test_handler_initialization(self, mock_settings, mock_ingestion_service):
        """Test ExportDirectoryHandler initialization."""
        file_monitor = FileMonitor(mock_settings, mock_ingestion_service)
        handler = ExportDirectoryHandler(file_monitor)
        
        assert handler.file_monitor == file_monitor

    @patch('asyncio.create_task')
    def test_on_created_directory_event(self, mock_create_task, mock_settings, mock_ingestion_service):
        """Test handling directory creation events."""
        file_monitor = FileMonitor(mock_settings, mock_ingestion_service)
        handler = ExportDirectoryHandler(file_monitor)
        
        # Mock directory creation event
        event = Mock()
        event.src_path = "/test/new_export"
        
        # Patch isinstance to return True for DirCreatedEvent
        with patch('pd_graphiti_service.file_monitor.isinstance') as mock_isinstance:
            mock_isinstance.return_value = True
            
            handler.on_created(event)
            
            mock_create_task.assert_called_once()

    @patch('asyncio.create_task')
    def test_on_created_manifest_file_event(self, mock_create_task, mock_settings, mock_ingestion_service):
        """Test handling manifest.json creation events."""
        file_monitor = FileMonitor(mock_settings, mock_ingestion_service)
        handler = ExportDirectoryHandler(file_monitor)
        
        # Mock file creation event for manifest.json
        event = Mock()
        event.src_path = "/test/export/manifest.json"
        
        # Patch isinstance to return False for DirCreatedEvent and True for FileCreatedEvent
        with patch('pd_graphiti_service.file_monitor.isinstance') as mock_isinstance:
            mock_isinstance.side_effect = lambda obj, cls: cls.__name__ == 'FileCreatedEvent'
            
            handler.on_created(event)
            
            mock_create_task.assert_called_once()


class TestFileMonitor:
    """Test FileMonitor class."""

    def test_monitor_initialization(self, mock_settings, mock_ingestion_service):
        """Test FileMonitor initialization."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        assert monitor.settings == mock_settings
        assert monitor.ingestion_service == mock_ingestion_service
        assert monitor.export_directory == mock_settings.export_directory
        assert monitor.status == MonitoringStatus.STOPPED
        assert not monitor.is_running
        assert monitor.processed_exports_count == 0

    def test_monitor_initialization_custom_directory(self, mock_settings, mock_ingestion_service):
        """Test FileMonitor initialization with custom directory."""
        custom_dir = Path("/custom/export/dir")
        monitor = FileMonitor(mock_settings, mock_ingestion_service, custom_dir)
        
        assert monitor.export_directory == custom_dir

    def test_properties(self, mock_settings, mock_ingestion_service):
        """Test FileMonitor properties."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Test initial state
        assert monitor.status == MonitoringStatus.STOPPED
        assert not monitor.is_running
        assert monitor.processed_exports_count == 0
        assert monitor.processing_results == []

    def test_set_callbacks(self, mock_settings, mock_ingestion_service):
        """Test setting event callbacks."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        on_started = Mock()
        on_completed = Mock()
        on_failed = Mock()
        
        monitor.set_callbacks(
            on_export_started=on_started,
            on_export_completed=on_completed,
            on_export_failed=on_failed
        )
        
        assert monitor._on_export_started == on_started
        assert monitor._on_export_completed == on_completed
        assert monitor._on_export_failed == on_failed

    def test_is_valid_export_directory(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test export directory validation."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Test non-existent directory
        non_existent = temp_export_directory / "nonexistent"
        assert not monitor._is_valid_export_directory(non_existent)
        
        # Test directory without manifest
        empty_dir = temp_export_directory / "empty"
        empty_dir.mkdir()
        assert not monitor._is_valid_export_directory(empty_dir)
        
        # Test valid export directory
        export_path = create_sample_export(temp_export_directory, "valid_export", sample_export_data)
        assert monitor._is_valid_export_directory(export_path)

    def test_get_export_id(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test export ID generation."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        test_dir = temp_export_directory / "test_export"
        test_dir.mkdir()
        
        export_id = monitor._get_export_id(test_dir)
        
        assert "test_export" in export_id
        assert "_" in export_id  # Contains timestamp
        
        # Test consistency
        export_id2 = monitor._get_export_id(test_dir)
        assert export_id == export_id2

    @pytest.mark.asyncio
    async def test_process_new_export_async_valid(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test processing new export directory."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Create valid export
        export_path = create_sample_export(temp_export_directory, "new_export", sample_export_data)
        
        # Mock queue operations
        monitor._processing_queue = AsyncMock()
        
        await monitor._process_new_export_async(export_path)
        
        # Verify export was queued
        monitor._processing_queue.put.assert_called_once()
        call_args = monitor._processing_queue.put.call_args[0][0]
        assert call_args[0] == export_path

    @pytest.mark.asyncio
    async def test_process_new_export_async_invalid(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test processing invalid export directory."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Create invalid export (no manifest)
        invalid_export = temp_export_directory / "invalid_export"
        invalid_export.mkdir()
        
        # Mock queue operations
        monitor._processing_queue = AsyncMock()
        
        await monitor._process_new_export_async(invalid_export)
        
        # Verify export was not queued
        monitor._processing_queue.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_new_export_async_already_processed(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test processing already processed export."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Create valid export
        export_path = create_sample_export(temp_export_directory, "processed_export", sample_export_data)
        
        # Mark as already processed
        export_id = monitor._get_export_id(export_path)
        monitor._processed_exports.add(export_id)
        
        # Mock queue operations
        monitor._processing_queue = AsyncMock()
        
        await monitor._process_new_export_async(export_path)
        
        # Verify export was not queued
        monitor._processing_queue.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_monitoring_success(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test successful monitoring start."""
        # Use temp directory for testing
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        
        with patch('pd_graphiti_service.file_monitor.Observer') as mock_observer_class:
            mock_observer = Mock()
            mock_observer_class.return_value = mock_observer
            
            result = await monitor.start_monitoring()
            
            assert result["status"] == "started"
            assert "File monitoring started successfully" in result["message"]
            assert monitor.status == MonitoringStatus.RUNNING
            assert monitor.is_running
            
            # Verify observer was configured and started
            mock_observer.schedule.assert_called_once()
            mock_observer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self, mock_settings, mock_ingestion_service):
        """Test starting monitoring when already running."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        monitor._status = MonitoringStatus.RUNNING
        
        result = await monitor.start_monitoring()
        
        assert result["status"] == "already_running"
        assert "already running" in result["message"]

    @pytest.mark.asyncio
    async def test_start_monitoring_error(self, mock_settings, mock_ingestion_service):
        """Test monitoring start error."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        with patch('pd_graphiti_service.file_monitor.Observer') as mock_observer_class:
            mock_observer_class.side_effect = Exception("Observer error")
            
            result = await monitor.start_monitoring()
            
            assert result["status"] == "error"
            assert "Failed to start file monitoring" in result["error"]
            assert monitor.status == MonitoringStatus.ERROR

    @pytest.mark.asyncio
    async def test_stop_monitoring_success(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test successful monitoring stop."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        
        # Set running state with mocked observer
        monitor._status = MonitoringStatus.RUNNING
        mock_observer = Mock()
        monitor._observer = mock_observer
        
        # Add mock processor tasks
        mock_task1 = AsyncMock()
        mock_task2 = AsyncMock()
        monitor._processor_tasks = [mock_task1, mock_task2]
        
        result = await monitor.stop_monitoring()
        
        assert result["status"] == "stopped"
        assert "File monitoring stopped successfully" in result["message"]
        assert monitor.status == MonitoringStatus.STOPPED
        assert not monitor.is_running
        
        # Verify observer was stopped
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        
        # Verify tasks were cancelled
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_monitoring_already_stopped(self, mock_settings, mock_ingestion_service):
        """Test stopping monitoring when already stopped."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        result = await monitor.stop_monitoring()
        
        assert result["status"] == "already_stopped"
        assert "already stopped" in result["message"]

    @pytest.mark.asyncio
    async def test_pause_monitoring_success(self, mock_settings, mock_ingestion_service):
        """Test successful monitoring pause."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        monitor._status = MonitoringStatus.RUNNING
        
        mock_observer = Mock()
        monitor._observer = mock_observer
        
        result = await monitor.pause_monitoring()
        
        assert result["status"] == "paused"
        assert "paused" in result["message"]
        assert monitor.status == MonitoringStatus.PAUSED
        
        # Verify observer was stopped
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_monitoring_not_running(self, mock_settings, mock_ingestion_service):
        """Test pausing monitoring when not running."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        result = await monitor.pause_monitoring()
        
        assert result["status"] == "not_running"
        assert "Cannot pause" in result["message"]

    @pytest.mark.asyncio
    async def test_resume_monitoring_success(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test successful monitoring resume."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        monitor._status = MonitoringStatus.PAUSED
        
        with patch('pd_graphiti_service.file_monitor.Observer') as mock_observer_class:
            mock_observer = Mock()
            mock_observer_class.return_value = mock_observer
            
            result = await monitor.resume_monitoring()
            
            assert result["status"] == "resumed"
            assert "resumed" in result["message"]
            assert monitor.status == MonitoringStatus.RUNNING
            
            # Verify new observer was created and started
            mock_observer.schedule.assert_called_once()
            mock_observer.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_monitoring_not_paused(self, mock_settings, mock_ingestion_service):
        """Test resuming monitoring when not paused."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        result = await monitor.resume_monitoring()
        
        assert result["status"] == "not_paused"
        assert "Cannot resume" in result["message"]

    @pytest.mark.asyncio
    async def test_trigger_directory_scan_success(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test successful directory scan."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        
        # Create some export directories
        export1 = create_sample_export(temp_export_directory, "export1", sample_export_data)
        export2 = create_sample_export(temp_export_directory, "export2", sample_export_data)
        
        # Mock queue operations
        monitor._processing_queue = AsyncMock()
        
        result = await monitor.trigger_directory_scan()
        
        assert result["status"] == "completed"
        assert result["discovered_exports"] == 2
        assert len(result["export_paths"]) == 2
        
        # Verify exports were queued
        assert monitor._processing_queue.put.call_count == 2

    @pytest.mark.asyncio
    async def test_trigger_directory_scan_nonexistent_directory(self, mock_settings, mock_ingestion_service):
        """Test directory scan with nonexistent directory."""
        nonexistent_dir = Path("/nonexistent/directory")
        monitor = FileMonitor(mock_settings, mock_ingestion_service, nonexistent_dir)
        
        result = await monitor.trigger_directory_scan()
        
        assert result["status"] == "error"
        assert "does not exist" in result["error"]

    def test_get_monitoring_status(self, mock_settings, mock_ingestion_service):
        """Test getting monitoring status."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Add some processed exports and results
        monitor._processed_exports.add("export1")
        monitor._processed_exports.add("export2")
        
        result1 = ProcessingResult(Path("/test/export1"), IngestionStatus.SUCCESS, {})
        result2 = ProcessingResult(Path("/test/export2"), IngestionStatus.FAILED, {})
        monitor._processing_results.extend([result1, result2])
        
        status = monitor.get_monitoring_status()
        
        assert status["status"] == MonitoringStatus.STOPPED
        assert not status["is_running"]
        assert status["processed_exports_count"] == 2
        assert status["total_results"] == 2
        assert status["successful_results"] == 1
        assert status["failed_results"] == 1
        assert "timestamp" in status

    def test_clear_processing_history(self, mock_settings, mock_ingestion_service):
        """Test clearing processing history."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service)
        
        # Add some processed exports and results
        monitor._processed_exports.add("export1")
        monitor._processed_exports.add("export2")
        
        result1 = ProcessingResult(Path("/test/export1"), IngestionStatus.SUCCESS, {})
        monitor._processing_results.append(result1)
        
        assert len(monitor._processed_exports) == 2
        assert len(monitor._processing_results) == 1
        
        monitor.clear_processing_history()
        
        assert len(monitor._processed_exports) == 0
        assert len(monitor._processing_results) == 0

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_settings, mock_ingestion_service, temp_export_directory):
        """Test FileMonitor as async context manager."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        
        with patch('pd_graphiti_service.file_monitor.Observer'):
            async with monitor as m:
                assert m == monitor
                assert monitor.is_running
            
            assert not monitor.is_running


class TestFileMonitorCreation:
    """Test FileMonitor creation utilities."""

    def test_create_file_monitor(self, mock_settings, mock_ingestion_service):
        """Test create_file_monitor convenience function."""
        monitor = create_file_monitor(mock_settings, mock_ingestion_service)
        
        assert isinstance(monitor, FileMonitor)
        assert monitor.settings == mock_settings
        assert monitor.ingestion_service == mock_ingestion_service

    def test_create_file_monitor_custom_directory(self, mock_settings, mock_ingestion_service):
        """Test create_file_monitor with custom directory."""
        custom_dir = Path("/custom/directory")
        monitor = create_file_monitor(mock_settings, mock_ingestion_service, custom_dir)
        
        assert monitor.export_directory == custom_dir


class TestFileMonitorIntegration:
    """Integration-style tests for FileMonitor."""

    @pytest.mark.asyncio
    async def test_export_processor_worker_success(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test export processor worker with successful processing."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        monitor._status = MonitoringStatus.RUNNING
        
        # Create export and add to queue
        export_path = create_sample_export(temp_export_directory, "test_export", sample_export_data)
        export_id = monitor._get_export_id(export_path)
        
        await monitor._processing_queue.put((export_path, export_id))
        
        # Set up callbacks
        started_callback = Mock()
        completed_callback = Mock()
        monitor.set_callbacks(on_export_started=started_callback, on_export_completed=completed_callback)
        
        # Process one item and then stop
        async def limited_worker():
            await monitor._export_processor_worker(0)
        
        # Run worker briefly
        worker_task = asyncio.create_task(limited_worker())
        
        # Wait a bit for processing
        await asyncio.sleep(0.1)
        
        # Stop monitoring to exit worker loop
        monitor._status = MonitoringStatus.STOPPED
        
        # Wait for worker to complete
        await asyncio.wait_for(worker_task, timeout=2.0)
        
        # Verify callbacks were called
        started_callback.assert_called_once_with(export_path)
        
        # Verify export was processed
        assert export_id in monitor._processed_exports
        assert len(monitor._processing_results) > 0
        
        # Verify ingestion service was called
        mock_ingestion_service.process_export_directory.assert_called_once_with(
            export_path,
            validate_files=True,
            force_reingest=False
        )

    @pytest.mark.asyncio
    async def test_export_processor_worker_failure(self, mock_settings, mock_ingestion_service, temp_export_directory, sample_export_data):
        """Test export processor worker with processing failure."""
        monitor = FileMonitor(mock_settings, mock_ingestion_service, temp_export_directory)
        monitor._status = MonitoringStatus.RUNNING
        
        # Mock ingestion service to return failure
        mock_ingestion_service.process_export_directory.return_value = {
            "status": IngestionStatus.FAILED,
            "error": "Processing failed",
            "export_id": "test_export_123"
        }
        
        # Create export and add to queue
        export_path = create_sample_export(temp_export_directory, "test_export", sample_export_data)
        export_id = monitor._get_export_id(export_path)
        
        await monitor._processing_queue.put((export_path, export_id))
        
        # Set up callbacks
        failed_callback = Mock()
        monitor.set_callbacks(on_export_failed=failed_callback)
        
        # Process one item and then stop
        async def limited_worker():
            await monitor._export_processor_worker(0)
        
        # Run worker briefly
        worker_task = asyncio.create_task(limited_worker())
        
        # Wait a bit for processing
        await asyncio.sleep(0.1)
        
        # Stop monitoring to exit worker loop
        monitor._status = MonitoringStatus.STOPPED
        
        # Wait for worker to complete
        await asyncio.wait_for(worker_task, timeout=2.0)
        
        # Verify failure callback was called
        failed_callback.assert_called_once()
        
        # Verify export was processed but marked as failed
        assert export_id in monitor._processed_exports
        assert len(monitor._processing_results) > 0
        assert monitor._processing_results[0].status == IngestionStatus.FAILED