"""Tests for Pydantic models."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from pd_graphiti_service.models import (
    IngestionStatus, 
    EpisodeMetadata, 
    GraphitiEpisode, 
    ExportManifest
)
from pd_graphiti_service.models.requests import (
    HealthCheckRequest,
    IngestDirectoryRequest,
    IngestEpisodeRequest
)
from pd_graphiti_service.models.responses import (
    HealthResponse,
    IngestionResponse,
    StatusResponse
)


class TestBaseModels:
    """Test base models in models/__init__.py."""

    def test_ingestion_status_enum(self):
        """Test IngestionStatus enum values."""
        assert IngestionStatus.PENDING == "pending"
        assert IngestionStatus.PROCESSING == "processing"
        assert IngestionStatus.SUCCESS == "success"
        assert IngestionStatus.FAILED == "failed"

    def test_episode_metadata_creation(self):
        """Test EpisodeMetadata model creation."""
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile", 
            export_timestamp=datetime.now(),
            file_path=Path("/test/path.json"),
            file_size=1024
        )
        
        assert metadata.gene_symbol == "SNCA"
        assert metadata.episode_type == "gene_profile"
        assert metadata.file_size == 1024
        assert metadata.validation_status == IngestionStatus.PENDING  # default
        assert metadata.error_message is None  # default

    def test_graphiti_episode_creation(self):
        """Test GraphitiEpisode model creation."""
        metadata = EpisodeMetadata(
            gene_symbol="LRRK2",
            episode_type="gwas_evidence",
            export_timestamp=datetime.now(),
            file_path=Path("/test/lrrk2.json"),
            file_size=2048
        )
        
        episode = GraphitiEpisode(
            episode_name="Gene_Profile_LRRK2",
            episode_body="LRRK2 is a key protein kinase...",
            source="dagster_pipeline",
            source_description="Generated from PD target identification pipeline",
            metadata=metadata
        )
        
        assert episode.episode_name == "Gene_Profile_LRRK2"
        assert episode.group_id == "pd_target_discovery"  # default
        assert episode.metadata.gene_symbol == "LRRK2"

    def test_export_manifest_creation(self):
        """Test ExportManifest model creation."""
        manifest = ExportManifest(
            export_id="export_20250731_123456",
            export_timestamp=datetime.now(),
            dagster_run_id="run_abc123",
            total_episodes=81,
            episode_types={"gene_profile": 14, "gwas_evidence": 14},
            genes=["SNCA", "LRRK2", "HLA-DRA"],
            checksum="abc123def456"
        )
        
        assert manifest.total_episodes == 81
        assert len(manifest.genes) == 3
        assert manifest.episode_types["gene_profile"] == 14

    def test_model_serialization(self):
        """Test that models serialize to JSON correctly."""
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime(2025, 7, 31, 12, 0, 0),
            file_path=Path("/test/snca.json"),
            file_size=1024,
            checksum="test_checksum"
        )
        
        # Test JSON serialization
        json_data = metadata.model_dump_json()
        parsed_data = json.loads(json_data)
        
        assert parsed_data["gene_symbol"] == "SNCA"
        assert parsed_data["file_size"] == 1024
        assert "2025-07-31T12:00:00" in parsed_data["export_timestamp"]
        
        # Test deserialization
        new_metadata = EpisodeMetadata.model_validate(parsed_data)
        assert new_metadata.gene_symbol == metadata.gene_symbol
        assert new_metadata.file_size == metadata.file_size


class TestRequestModels:
    """Test request models."""

    def test_health_check_request(self):
        """Test HealthCheckRequest model."""
        # Test with minimal data
        request = HealthCheckRequest()
        assert request.ping_data is None
        assert request.check_dependencies is False
        
        # Test with full data
        request = HealthCheckRequest(
            ping_data="test_ping",
            check_dependencies=True
        )
        assert request.ping_data == "test_ping"
        assert request.check_dependencies is True

    def test_ingest_directory_request(self):
        """Test IngestDirectoryRequest model."""
        request = IngestDirectoryRequest(
            directory_path=Path("/test/exports"),
            validate_files=True,
            force_reingest=False,
            episode_types_filter=["gene_profile", "gwas_evidence"]
        )
        
        assert isinstance(request.directory_path, Path)
        assert request.validate_files is True
        assert len(request.episode_types_filter) == 2

    def test_ingest_episode_request(self):
        """Test IngestEpisodeRequest model."""
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime.now(),
            file_path=Path("/test/snca.json"),
            file_size=1024
        )
        
        episode = GraphitiEpisode(
            episode_name="Gene_Profile_SNCA",
            episode_body="SNCA content...",
            source="dagster_pipeline",
            source_description="Test episode",
            metadata=metadata
        )
        
        request = IngestEpisodeRequest(
            episode=episode,
            force_reingest=True,
            validate_episode=True
        )
        
        assert request.episode.episode_name == "Gene_Profile_SNCA"
        assert request.force_reingest is True


class TestResponseModels:
    """Test response models."""

    def test_health_response(self):
        """Test HealthResponse model."""
        response = HealthResponse(
            status="healthy",
            neo4j_connected=True,
            openai_api_accessible=True,
            graphiti_ready=True,
            ping_data="test_echo"
        )
        
        assert response.status == "healthy"
        assert response.version == "0.1.0"  # default
        assert response.neo4j_connected is True
        assert response.ping_data == "test_echo"

    def test_ingestion_response(self):
        """Test IngestionResponse model."""
        from pd_graphiti_service.models.responses.ingestion import EpisodeIngestionResult
        
        episode_result = EpisodeIngestionResult(
            episode_name="Gene_Profile_SNCA",
            status=IngestionStatus.SUCCESS,
            processing_time_seconds=1.5,
            graphiti_node_id="node_123"
        )
        
        response = IngestionResponse(
            status=IngestionStatus.SUCCESS,
            message="Ingestion completed successfully",
            episodes_processed=1,
            episodes_successful=1,
            episodes_failed=0,
            start_time=datetime.now(),
            episode_results=[episode_result]
        )
        
        assert response.episodes_processed == 1
        assert response.episodes_successful == 1
        assert len(response.episode_results) == 1
        assert response.episode_results[0].episode_name == "Gene_Profile_SNCA"

    def test_status_response(self):
        """Test StatusResponse model."""
        from pd_graphiti_service.models.responses.status import CurrentOperation
        
        current_op = CurrentOperation(
            operation_type="directory_ingestion",
            operation_id="op_123",
            started_at=datetime.now(),
            progress_percentage=50.0,
            current_step="Processing episode 5 of 10"
        )
        
        response = StatusResponse(
            service_status="processing",
            current_operation=current_op,
            last_ingestion_status=IngestionStatus.SUCCESS,
            total_episodes_ingested=75,
            uptime_seconds=3600.0
        )
        
        assert response.service_status == "processing"
        assert response.current_operation.progress_percentage == 50.0
        assert response.total_episodes_ingested == 75

    def test_response_serialization(self):
        """Test that response models serialize correctly."""
        response = HealthResponse(
            status="healthy",
            timestamp=datetime(2025, 7, 31, 12, 0, 0),
            neo4j_connected=True
        )
        
        json_data = response.model_dump_json()
        parsed_data = json.loads(json_data)
        
        assert parsed_data["status"] == "healthy"
        assert "2025-07-31T12:00:00" in parsed_data["timestamp"]
        assert parsed_data["neo4j_connected"] is True


class TestValidation:
    """Test model validation."""

    def test_episode_metadata_validation(self):
        """Test validation errors for EpisodeMetadata."""
        with pytest.raises(ValidationError):
            # Missing required fields
            EpisodeMetadata()
            
        with pytest.raises(ValidationError):
            # Invalid file_size (negative)
            EpisodeMetadata(
                gene_symbol="SNCA",
                episode_type="gene_profile",
                export_timestamp=datetime.now(),
                file_path=Path("/test/path.json"),
                file_size=-1  # Invalid
            )

    def test_path_validation(self):
        """Test Path field validation."""
        # Test that string paths are converted to Path objects
        request = IngestDirectoryRequest(directory_path="/test/exports")
        assert isinstance(request.directory_path, Path)
        
        # Test Path object input
        request = IngestDirectoryRequest(directory_path=Path("/test/exports"))
        assert isinstance(request.directory_path, Path)