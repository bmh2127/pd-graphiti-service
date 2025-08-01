# File: tests/api/test_api_endpoints.py
"""Tests for API endpoints."""

import asyncio
import json
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from httpx import AsyncClient

from pd_graphiti_service.main import app
from pd_graphiti_service.config import Settings
from pd_graphiti_service.models import IngestionStatus, GraphitiEpisode, EpisodeMetadata


# Test fixtures
@pytest.fixture
def mock_services():
    """Mock all service dependencies."""
    mock_graphiti = AsyncMock()
    mock_ingestion = AsyncMock()
    mock_monitor = AsyncMock()
    mock_task_manager = AsyncMock()
    
    # Configure mock responses
    mock_graphiti.test_connection.return_value = {
        "neo4j_connected": True,
        "openai_accessible": True,
        "graphiti_ready": True,
        "errors": []
    }
    
    mock_graphiti.get_graph_stats.return_value = {
        "total_nodes": 100,
        "total_relationships": 50,
        "group_nodes": 25,
        "group_id": "test_group",
        "timestamp": datetime.now().isoformat()
    }
    
    mock_ingestion.get_processing_stats.return_value = {
        "total_processed_episodes": 10,
        "processed_episode_names": ["test1", "test2"],
        "timestamp": datetime.now().isoformat()
    }
    
    mock_monitor.get_monitoring_status.return_value = {
        "status": "running",
        "is_running": True,
        "queue_size": 0,
        "uptime_seconds": 3600.0
    }
    
    mock_task_manager.get_task_status.return_value = None
    mock_task_manager.list_tasks.return_value = {}
    
    return {
        "graphiti_client": mock_graphiti,
        "ingestion_service": mock_ingestion,
        "file_monitor": mock_monitor,
        "task_manager": mock_task_manager
    }


@pytest.fixture
def sample_export_directory():
    """Create a sample export directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        export_dir = Path(tmp_dir) / "test_export"
        export_dir.mkdir()
        
        # Create manifest
        manifest = {
            "export_id": "test_export_123",
            "export_timestamp": "2025-07-01T12:00:00",
            "dagster_run_id": "run_123",
            "total_episodes": 1,
            "episode_types": {"gene_profile": 1},
            "genes": ["SNCA"],
            "checksum": "abc123"
        }
        
        with open(export_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)
        
        # Create episode file
        episodes_dir = export_dir / "episodes" / "gene_profile"
        episodes_dir.mkdir(parents=True)
        
        episode = {
            "episode_name": "Gene_Profile_SNCA",
            "episode_body": "SNCA encodes alpha-synuclein...",
            "source": "dagster_pipeline",
            "source_description": "Test episode"
        }
        
        with open(episodes_dir / "SNCA_gene_profile.json", "w") as f:
            json.dump(episode, f)
        
        yield export_dir


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.asyncio
    async def test_basic_health_check(self, mock_services):
        """Test basic health check endpoint."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                assert "knowledge_graph_statistics" in data
                assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_list_operations(self, mock_services):
        """Test list operations endpoint."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/operations")
                
                assert response.status_code == 200
                data = response.json()
                assert "background_tasks" in data
                assert "current_operations" in data

    @pytest.mark.asyncio
    async def test_cleanup_operations(self, mock_services):
        """Test operations cleanup endpoint."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.delete("/api/v1/operations/cleanup?max_age_hours=1")
                
                assert response.status_code == 200
                data = response.json()
                assert "message" in data
                assert "operations_removed" in data


class TestRootEndpoint:
    """Test root endpoint."""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, mock_services):
        """Test root endpoint returns service information."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/")
                
                assert response.status_code == 200
                data = response.json()
                assert data["service"] == "PD Graphiti Service"
                assert data["version"] == "0.1.0"
                assert data["status"] == "running"
                assert "uptime_seconds" in data


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_validation_error(self, mock_services):
        """Test request validation errors."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                # Send invalid request (missing required fields)
                response = await client.post(
                    "/api/v1/ingest/directory",
                    json={}  # Missing directory_path
                )
                
                assert response.status_code == 422
                data = response.json()
                assert data["error"] == "Validation Error"
                assert "detail" in data

    @pytest.mark.asyncio
    async def test_internal_server_error(self, mock_services):
        """Test internal server error handling."""
        # Configure mock to raise exception
        mock_services["graphiti_client"].get_graph_stats.side_effect = Exception("Database error")
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/stats")
                
                assert response.status_code == 500
                data = response.json()
                assert "Failed to get graph statistics" in data["detail"]

    @pytest.mark.asyncio
    async def test_service_unavailable(self, mock_services):
        """Test service unavailable errors."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: None,  # Service not available
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/stats")
                
                assert response.status_code == 503


class TestConcurrency:
    """Test concurrent API requests."""

    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, mock_services):
        """Test multiple concurrent health check requests."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                # Send multiple concurrent requests
                tasks = [
                    client.get("/health")
                    for _ in range(10)
                ]
                
                responses = await asyncio.gather(*tasks)
                
                # All should succeed
                for response in responses:
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_concurrent_status_requests(self, mock_services):
        """Test multiple concurrent status requests."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                # Send multiple concurrent requests
                tasks = [
                    client.get("/api/v1/status")
                    for _ in range(5)
                ]
                
                responses = await asyncio.gather(*tasks)
                
                # All should succeed
                for response in responses:
                    assert response.status_code == 200
                    data = response.json()
                    assert "service_status" in data


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_ingestion_workflow(self, mock_services, sample_export_directory):
        """Test complete ingestion workflow."""
        # Configure mocks for workflow
        mock_services["task_manager"].create_task.return_value = "test_op_123"
        mock_services["task_manager"].get_task_status.return_value = {
            "status": "completed",
            "result": {
                "status": IngestionStatus.SUCCESS,
                "total_episodes_loaded": 1
            }
        }
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                # 1. Check service health
                health_response = await client.get("/health/deep")
                assert health_response.status_code == 200
                
                # 2. Start directory ingestion
                ingest_response = await client.post(
                    "/api/v1/ingest/directory",
                    json={
                        "directory_path": str(sample_export_directory),
                        "validate_files": True,
                        "force_reingest": False
                    }
                )
                assert ingest_response.status_code == 200
                operation_id = ingest_response.json()["operation_id"]
                
                # 3. Check operation status
                status_response = await client.get(f"/api/v1/status/{operation_id}")
                assert status_response.status_code == 200
                
                # 4. Get graph statistics
                stats_response = await client.get("/api/v1/stats")
                assert stats_response.status_code == 200
                
                # 5. List all operations
                ops_response = await client.get("/api/v1/operations")
                assert ops_response.status_code == 200

    @pytest.mark.asyncio
    async def test_error_recovery_scenario(self, mock_services, sample_export_directory):
        """Test error recovery scenarios."""
        # Configure mock to fail first, then succeed
        call_count = 0
        
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary failure")
            return {
                "neo4j_connected": True,
                "openai_accessible": True,
                "graphiti_ready": True,
                "errors": []
            }
        
        mock_services["graphiti_client"].test_connection.side_effect = side_effect
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                # First call should show unhealthy
                response1 = await client.get("/health/deep")
                assert response1.status_code == 200
                data1 = response1.json()
                assert data1["status"] == "unhealthy"
                
                # Second call should succeed
                response2 = await client.get("/health/deep")
                assert response2.status_code == 200
                data2 = response2.json()
                assert data2["status"] == "healthy"
                data = response.json()
                assert data["status"] == "healthy"
                assert "timestamp" in data
                assert "version" in data

    @pytest.mark.asyncio
    async def test_basic_health_check_with_ping(self, mock_services):
        """Test basic health check with ping data."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health?ping_data=test123")
                
                assert response.status_code == 200
                data = response.json()
                assert data["ping_data"] == "test123"

    @pytest.mark.asyncio
    async def test_deep_health_check_healthy(self, mock_services):
        """Test deep health check when all services are healthy."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health/deep")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"
                assert data["neo4j_connected"] is True
                assert data["openai_api_accessible"] is True
                assert data["graphiti_ready"] is True

    @pytest.mark.asyncio
    async def test_deep_health_check_degraded(self, mock_services):
        """Test deep health check when services are degraded."""
        # Configure mock for degraded state
        mock_services["graphiti_client"].test_connection.return_value = {
            "neo4j_connected": True,
            "openai_accessible": False,  # OpenAI unavailable
            "graphiti_ready": False,
            "errors": ["OpenAI API connection failed"]
        }
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health/deep")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "degraded"
                assert data["neo4j_connected"] is True
                assert data["openai_api_accessible"] is False
                assert data["graphiti_ready"] is False

    @pytest.mark.asyncio
    async def test_readiness_probe_ready(self, mock_services):
        """Test readiness probe when service is ready."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health/ready")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_readiness_probe_not_ready(self, mock_services):
        """Test readiness probe when service is not ready."""
        # Configure mock for not ready state
        mock_services["graphiti_client"].test_connection.return_value = {
            "neo4j_connected": False,
            "openai_accessible": True,
            "graphiti_ready": False,
            "errors": ["Neo4j connection failed"]
        }
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health/ready")
                
                assert response.status_code == 503
                data = response.json()
                assert data["status"] == "not_ready"

    @pytest.mark.asyncio
    async def test_liveness_probe(self, mock_services):
        """Test liveness probe."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health/live")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "alive"


class TestIngestionEndpoints:
    """Test ingestion endpoints."""

    @pytest.mark.asyncio
    async def test_ingest_directory_success(self, mock_services, sample_export_directory):
        """Test successful directory ingestion."""
        # Configure mock ingestion service
        mock_services["ingestion_service"].process_export_directory.return_value = {
            "status": IngestionStatus.SUCCESS,
            "export_id": "test_export_123",
            "total_episodes_loaded": 1,
            "processing_time": 2.5
        }
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ingest/directory",
                    json={
                        "directory_path": str(sample_export_directory),
                        "validate_files": True,
                        "force_reingest": False
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "processing"
                assert "operation_id" in data

    @pytest.mark.asyncio
    async def test_ingest_directory_not_found(self, mock_services):
        """Test directory ingestion with non-existent directory."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ingest/directory",
                    json={
                        "directory_path": "/nonexistent/directory",
                        "validate_files": True,
                        "force_reingest": False
                    }
                )
                
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_ingest_episode_success(self, mock_services):
        """Test successful single episode ingestion."""
        # Configure mock ingestion service
        mock_services["ingestion_service"].process_single_episode.return_value = {
            "status": IngestionStatus.SUCCESS,
            "episode_name": "Test_Episode",
            "processing_time": 1.0,
            "graphiti_node_id": "node_123"
        }
        
        # Create sample episode
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime.now(),
            file_path=Path("/test/snca.json"),
            file_size=1024
        )
        
        episode = GraphitiEpisode(
            episode_name="Test_Episode_SNCA",
            episode_body="Test episode content",
            source="test",
            source_description="Test episode",
            metadata=metadata
        )
        
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ingest/episode",
                    json={
                        "episode": episode.model_dump(),
                        "validate_episode": True,
                        "force_reingest": False
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["episodes_processed"] == 1
                assert data["episodes_successful"] == 1

    @pytest.mark.asyncio
    async def test_get_service_status(self, mock_services):
        """Test service status endpoint."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/status")
                
                assert response.status_code == 200
                data = response.json()
                assert data["service_status"] in ["idle", "processing", "error"]
                assert "timestamp" in data
                assert "total_episodes_ingested" in data

    @pytest.mark.asyncio
    async def test_get_operation_status_not_found(self, mock_services):
        """Test operation status for non-existent operation."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/status/nonexistent_operation")
                
                assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_graph_stats(self, mock_services):
        """Test graph statistics endpoint."""
        with patch.multiple(
            "pd_graphiti_service.main",
            get_graphiti_client=lambda: mock_services["graphiti_client"],
            get_ingestion_service=lambda: mock_services["ingestion_service"],
            get_file_monitor=lambda: mock_services["file_monitor"],
            get_task_manager=lambda: mock_services["task_manager"]
        ):
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/api/v1/stats")
                
                assert response.status_code == 200  