"""Tests for IngestionService."""

import asyncio
import json
import tempfile
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from pd_graphiti_service.config import Settings
from pd_graphiti_service.graphiti_client import GraphitiClient
from pd_graphiti_service.ingestion_service import (
    IngestionService,
    IngestionError,
    ManifestValidationError,
    FileIntegrityError,
    create_ingestion_service
)
from pd_graphiti_service.models import (
    GraphitiEpisode,
    EpisodeMetadata,
    IngestionStatus,
    ExportManifest
)


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    return Settings(
        openai_api_key="test-key",
        neo4j_password="test-password",
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        graphiti_group_id="test_group"
    )


@pytest.fixture
def mock_graphiti_client():
    """Create mock GraphitiClient."""
    client = AsyncMock(spec=GraphitiClient)
    
    # Mock successful episode ingestion
    client.add_episode.return_value = {
        "status": IngestionStatus.SUCCESS,
        "episode_name": "test_episode",
        "processing_time_seconds": 0.1,
        "graphiti_node_id": "node_123"
    }
    
    # Mock successful batch ingestion
    client.add_episodes_batch.return_value = {
        "status": IngestionStatus.SUCCESS,
        "total_episodes": 1,
        "successful": 1,
        "failed": 0,
        "episode_results": [{
            "status": IngestionStatus.SUCCESS,
            "episode_name": "test_episode"
        }]
    }
    
    return client


@pytest.fixture
def sample_manifest_data():
    """Create sample manifest data."""
    return {
        "export_id": "test_export_20250701_123456",
        "export_timestamp": "2025-07-01T12:34:56",
        "dagster_run_id": "dagster_run_123",
        "total_episodes": 2,
        "episode_types": {
            "gene_profile": 1,
            "gwas_evidence": 1
        },
        "genes": ["SNCA", "LRRK2"],
        "checksum": "abc123def456"
    }


@pytest.fixture
def sample_episode_data():
    """Create sample episode data."""
    return {
        "episode_name": "Gene_Profile_SNCA",
        "episode_body": "SNCA encodes α-synuclein, a protein central to Parkinson's disease pathology...",
        "source": "dagster_pipeline",
        "source_description": "Generated from PD target identification pipeline",
        "group_id": "test_group"
    }


@pytest.fixture
def temp_export_dir(sample_manifest_data, sample_episode_data):
    """Create temporary export directory with sample files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        export_dir = Path(temp_dir) / "test_export"
        export_dir.mkdir()
        
        # Create manifest.json
        manifest_path = export_dir / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(sample_manifest_data, f)
        
        # Create episodes directory structure
        episodes_dir = export_dir / "episodes"
        episodes_dir.mkdir()
        
        gene_profile_dir = episodes_dir / "gene_profile"
        gene_profile_dir.mkdir()
        
        gwas_dir = episodes_dir / "gwas_evidence"
        gwas_dir.mkdir()
        
        # Create episode files
        snca_episode_path = gene_profile_dir / "SNCA_gene_profile.json"
        with open(snca_episode_path, 'w') as f:
            json.dump(sample_episode_data, f)
        
        gwas_episode_data = sample_episode_data.copy()
        gwas_episode_data["episode_name"] = "GWAS_Evidence_SNCA"
        gwas_episode_data["episode_body"] = "GWAS evidence for SNCA..."
        
        gwas_episode_path = gwas_dir / "SNCA_gwas_evidence.json"
        with open(gwas_episode_path, 'w') as f:
            json.dump(gwas_episode_data, f)
        
        yield export_dir


class TestIngestionService:
    """Test IngestionService class."""

    def test_service_initialization(self, mock_settings, mock_graphiti_client):
        """Test IngestionService initialization."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        assert service.settings == mock_settings
        assert service.graphiti_client == mock_graphiti_client
        assert len(service._processed_episodes) == 0

    def test_calculate_file_checksum(self, mock_settings, mock_graphiti_client):
        """Test file checksum calculation."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("test content")
            temp_file.flush()
            temp_path = Path(temp_file.name)
        
        try:
            checksum = service._calculate_file_checksum(temp_path)
            
            # Verify checksum is MD5 hex string
            assert len(checksum) == 32
            assert all(c in '0123456789abcdef' for c in checksum)
            
            # Verify consistent checksums
            checksum2 = service._calculate_file_checksum(temp_path)
            assert checksum == checksum2
            
        finally:
            temp_path.unlink()

    def test_load_manifest_success(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test successful manifest loading."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        manifest = service._load_manifest(temp_export_dir)
        
        assert isinstance(manifest, ExportManifest)
        assert manifest.export_id == "test_export_20250701_123456"
        assert manifest.total_episodes == 2
        assert "SNCA" in manifest.genes

    def test_load_manifest_missing_file(self, mock_settings, mock_graphiti_client):
        """Test manifest loading with missing file."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "empty_export"
            export_dir.mkdir()
            
            with pytest.raises(ManifestValidationError) as exc_info:
                service._load_manifest(export_dir)
            
            assert "Manifest file not found" in str(exc_info.value)

    def test_load_manifest_invalid_json(self, mock_settings, mock_graphiti_client):
        """Test manifest loading with invalid JSON."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "invalid_export"
            export_dir.mkdir()
            
            manifest_path = export_dir / "manifest.json"
            with open(manifest_path, 'w') as f:
                f.write("invalid json {")
            
            with pytest.raises(ManifestValidationError) as exc_info:
                service._load_manifest(export_dir)
            
            assert "Invalid JSON in manifest" in str(exc_info.value)

    def test_discover_episode_files(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test episode file discovery."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        episode_files = service._discover_episode_files(temp_export_dir)
        
        assert len(episode_files) == 2
        assert all(f.suffix == ".json" for f in episode_files)
        assert any("SNCA_gene_profile.json" in str(f) for f in episode_files)
        assert any("SNCA_gwas_evidence.json" in str(f) for f in episode_files)

    def test_load_episode_from_file(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test loading episode from file."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        episode_files = service._discover_episode_files(temp_export_dir)
        gene_profile_file = next(f for f in episode_files if "gene_profile" in str(f))
        
        episode = service._load_episode_from_file(gene_profile_file, validate_checksum=False)
        
        assert isinstance(episode, GraphitiEpisode)
        assert episode.episode_name == "Gene_Profile_SNCA"
        assert "SNCA" in episode.episode_body
        assert episode.metadata.gene_symbol == "SNCA"
        assert episode.metadata.episode_type == "gene_profile"
        assert episode.metadata.file_size > 0

    def test_load_episode_with_checksum_validation(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test loading episode with checksum validation."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        episode_files = service._discover_episode_files(temp_export_dir)
        gene_profile_file = next(f for f in episode_files if "gene_profile" in str(f))
        
        episode = service._load_episode_from_file(gene_profile_file, validate_checksum=True)
        
        assert episode.metadata.checksum is not None
        assert len(episode.metadata.checksum) == 32

    def test_load_episode_invalid_json(self, mock_settings, mock_graphiti_client):
        """Test loading episode with invalid JSON."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            temp_file.write("invalid json {")
            temp_file.flush()
            temp_path = Path(temp_file.name)
        
        try:
            with pytest.raises(IngestionError) as exc_info:
                service._load_episode_from_file(temp_path, validate_checksum=False)
            
            assert "Invalid JSON in episode file" in str(exc_info.value)
            
        finally:
            temp_path.unlink()

    def test_validate_file_integrity_success(self, mock_settings, mock_graphiti_client):
        """Test successful file integrity validation."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("test content")
            temp_file.flush()
            temp_path = Path(temp_file.name)
        
        try:
            # Calculate expected checksum
            expected_checksum = service._calculate_file_checksum(temp_path)
            
            # Should succeed with correct checksum
            result = service._validate_file_integrity(temp_path, expected_checksum)
            assert result is True
            
        finally:
            temp_path.unlink()

    def test_validate_file_integrity_mismatch(self, mock_settings, mock_graphiti_client):
        """Test file integrity validation with checksum mismatch."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write("test content")
            temp_file.flush()
            temp_path = Path(temp_file.name)
        
        try:
            wrong_checksum = "wrong_checksum_value"
            
            with pytest.raises(FileIntegrityError) as exc_info:
                service._validate_file_integrity(temp_path, wrong_checksum)
            
            assert "Checksum mismatch" in str(exc_info.value)
            
        finally:
            temp_path.unlink()

    def test_get_episode_processing_order(self, mock_settings, mock_graphiti_client):
        """Test episode processing order sorting."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Create episodes with different types
        episodes = []
        episode_types = ["integration", "gene_profile", "pathway_evidence", "gwas_evidence"]
        
        for i, episode_type in enumerate(episode_types):
            metadata = EpisodeMetadata(
                gene_symbol=f"GENE{i}",
                episode_type=episode_type,
                export_timestamp=datetime.now(),
                file_path=Path(f"/test/{episode_type}.json"),
                file_size=1024
            )
            
            episode = GraphitiEpisode(
                episode_name=f"{episode_type}_GENE{i}",
                episode_body=f"Episode for {episode_type}",
                source="test",
                source_description="test",
                metadata=metadata
            )
            episodes.append(episode)
        
        # Sort by processing order
        sorted_episodes = service._get_episode_processing_order(episodes)
        
        # Verify correct order: gene_profile, gwas_evidence, pathway_evidence, integration
        expected_order = ["gene_profile", "gwas_evidence", "pathway_evidence", "integration"]
        actual_order = [ep.metadata.episode_type for ep in sorted_episodes]
        
        assert actual_order == expected_order

    @pytest.mark.asyncio
    async def test_process_export_directory_success(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test successful export directory processing."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        result = await service.process_export_directory(temp_export_dir, validate_files=False)
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert result["export_id"] == "test_export_20250701_123456"
        assert result["total_files_discovered"] == 2
        assert result["total_episodes_loaded"] == 2
        assert len(result["load_errors"]) == 0
        assert "processing_time" in result
        
        # Verify GraphitiClient was called
        mock_graphiti_client.add_episodes_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_export_directory_missing_manifest(self, mock_settings, mock_graphiti_client):
        """Test export directory processing with missing manifest."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "empty_export"
            export_dir.mkdir()
            
            result = await service.process_export_directory(export_dir)
            
            assert result["status"] == IngestionStatus.FAILED
            assert "Export validation failed" in result["error"]

    @pytest.mark.asyncio
    async def test_process_export_directory_no_files(self, mock_settings, mock_graphiti_client, sample_manifest_data):
        """Test export directory processing with no episode files."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "empty_export"
            export_dir.mkdir()
            
            # Create manifest but no episode files
            manifest_path = export_dir / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(sample_manifest_data, f)
            
            result = await service.process_export_directory(export_dir)
            
            assert result["status"] == IngestionStatus.FAILED
            assert "No episode files found" in result["error"]

    @pytest.mark.asyncio
    async def test_process_export_directory_with_filter(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test export directory processing with episode type filter."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        result = await service.process_export_directory(
            temp_export_dir, 
            validate_files=False,
            episode_types_filter=["gene_profile"]
        )
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert result["total_episodes_loaded"] == 1  # Only gene_profile episodes
        
        # Verify only gene_profile episode was processed
        call_args = mock_graphiti_client.add_episodes_batch.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].metadata.episode_type == "gene_profile"

    @pytest.mark.asyncio
    async def test_process_export_directory_already_processed(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test export directory processing with already processed episodes."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Pre-populate processed episodes
        service._processed_episodes.add("Gene_Profile_SNCA")
        service._processed_episodes.add("GWAS_Evidence_SNCA")
        
        result = await service.process_export_directory(temp_export_dir, validate_files=False)
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert "All episodes already processed" in result["message"]
        assert result["total_episodes_loaded"] == 0

    @pytest.mark.asyncio
    async def test_process_export_directory_force_reingest(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test export directory processing with force reingest."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Pre-populate processed episodes
        service._processed_episodes.add("Gene_Profile_SNCA")
        service._processed_episodes.add("GWAS_Evidence_SNCA")
        
        result = await service.process_export_directory(
            temp_export_dir, 
            validate_files=False,
            force_reingest=True
        )
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert result["total_episodes_loaded"] == 2  # Force reprocessed

    @pytest.mark.asyncio
    async def test_process_single_episode_success(self, mock_settings, mock_graphiti_client):
        """Test successful single episode processing."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime.now(),
            file_path=Path("/test/snca.json"),
            file_size=1024
        )
        
        episode = GraphitiEpisode(
            episode_name="Gene_Profile_SNCA",
            episode_body="SNCA episode content",
            source="test",
            source_description="test",
            metadata=metadata
        )
        
        result = await service.process_single_episode(episode)
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert "processing_time" in result
        assert episode.episode_name in service._processed_episodes
        
        mock_graphiti_client.add_episode.assert_called_once_with(episode)

    @pytest.mark.asyncio
    async def test_process_single_episode_already_processed(self, mock_settings, mock_graphiti_client):
        """Test single episode processing when already processed."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime.now(),
            file_path=Path("/test/snca.json"),
            file_size=1024
        )
        
        episode = GraphitiEpisode(
            episode_name="Gene_Profile_SNCA",
            episode_body="SNCA episode content",
            source="test",
            source_description="test",
            metadata=metadata
        )
        
        # Pre-mark as processed
        service._processed_episodes.add(episode.episode_name)
        
        result = await service.process_single_episode(episode)
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert "already processed" in result["message"]
        
        # Verify GraphitiClient was not called
        mock_graphiti_client.add_episode.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_single_episode_graphiti_error(self, mock_settings, mock_graphiti_client):
        """Test single episode processing with GraphitiClient error."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Mock GraphitiClient to raise exception
        mock_graphiti_client.add_episode.side_effect = Exception("Graphiti error")
        
        metadata = EpisodeMetadata(
            gene_symbol="SNCA",
            episode_type="gene_profile",
            export_timestamp=datetime.now(),
            file_path=Path("/test/snca.json"),
            file_size=1024
        )
        
        episode = GraphitiEpisode(
            episode_name="Gene_Profile_SNCA",
            episode_body="SNCA episode content",
            source="test",
            source_description="test",
            metadata=metadata
        )
        
        result = await service.process_single_episode(episode)
        
        assert result["status"] == IngestionStatus.FAILED
        assert "Graphiti error" in result["error"]
        assert episode.episode_name not in service._processed_episodes

    def test_get_processing_stats(self, mock_settings, mock_graphiti_client):
        """Test processing statistics retrieval."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Add some processed episodes
        service._processed_episodes.add("Gene_Profile_SNCA")
        service._processed_episodes.add("GWAS_Evidence_LRRK2")
        
        stats = service.get_processing_stats()
        
        assert stats["total_processed_episodes"] == 2
        assert "Gene_Profile_SNCA" in stats["processed_episode_names"]
        assert "GWAS_Evidence_LRRK2" in stats["processed_episode_names"]
        assert "timestamp" in stats

    def test_clear_processing_history(self, mock_settings, mock_graphiti_client):
        """Test clearing processing history."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # Add some processed episodes
        service._processed_episodes.add("Gene_Profile_SNCA")
        service._processed_episodes.add("GWAS_Evidence_LRRK2")
        
        assert len(service._processed_episodes) == 2
        
        service.clear_processing_history()
        
        assert len(service._processed_episodes) == 0


class TestIngestionServiceCreation:
    """Test IngestionService creation utilities."""

    def test_create_ingestion_service(self, mock_settings, mock_graphiti_client):
        """Test create_ingestion_service convenience function."""
        service = create_ingestion_service(mock_settings, mock_graphiti_client)
        
        assert isinstance(service, IngestionService)
        assert service.settings == mock_settings
        assert service.graphiti_client == mock_graphiti_client


class TestIngestionServiceIntegration:
    """Integration-style tests for IngestionService."""

    @pytest.mark.asyncio
    async def test_end_to_end_processing_workflow(self, mock_settings, mock_graphiti_client, temp_export_dir):
        """Test complete end-to-end processing workflow."""
        service = IngestionService(mock_settings, mock_graphiti_client)
        
        # 1. Process export directory
        result = await service.process_export_directory(temp_export_dir, validate_files=True)
        
        assert result["status"] == IngestionStatus.SUCCESS
        assert result["total_episodes_loaded"] == 2
        
        # 2. Verify processing stats
        stats = service.get_processing_stats()
        assert stats["total_processed_episodes"] == 2
        
        # 3. Try processing again (should skip already processed)
        result2 = await service.process_export_directory(temp_export_dir, validate_files=False)
        assert "already processed" in result2["message"]
        
        # 4. Force reprocess
        result3 = await service.process_export_directory(
            temp_export_dir, 
            validate_files=False,
            force_reingest=True
        )
        assert result3["status"] == IngestionStatus.SUCCESS
        assert result3["total_episodes_loaded"] == 2
        
        # 5. Clear history and verify
        service.clear_processing_history()
        stats_after_clear = service.get_processing_stats()
        assert stats_after_clear["total_processed_episodes"] == 0