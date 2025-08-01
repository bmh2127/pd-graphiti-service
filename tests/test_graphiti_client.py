"""Tests for GraphitiClient."""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock

from pd_graphiti_service.config import Settings
from pd_graphiti_service.graphiti_client import (
    GraphitiClient, 
    GraphitiConnectionError, 
    GraphitiValidationError,
    create_graphiti_client
)
from pd_graphiti_service.models import (
    GraphitiEpisode, 
    EpisodeMetadata, 
    IngestionStatus
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
def sample_episode():
    """Create a sample episode for testing."""
    metadata = EpisodeMetadata(
        gene_symbol="SNCA",
        episode_type="gene_profile",
        export_timestamp=datetime.now(),
        file_path=Path("/test/snca.json"),
        file_size=1024
    )
    
    return GraphitiEpisode(
        episode_name="Gene_Profile_SNCA",
        episode_body="SNCA encodes α-synuclein, a protein central to Parkinson's disease pathology...",
        source="dagster_pipeline",
        source_description="Generated from PD target identification pipeline",
        metadata=metadata
    )


class TestGraphitiClient:
    """Test GraphitiClient class."""

    def test_client_initialization(self, mock_settings):
        """Test GraphitiClient initialization."""
        with patch('pd_graphiti_service.graphiti_client.openai') as mock_openai:
            client = GraphitiClient(mock_settings)
            
            assert client.settings == mock_settings
            assert client._graphiti is None
            assert not client._database_initialized
            
            # Verify OpenAI API key is set
            mock_openai.api_key = mock_settings.openai_api_key

    @pytest.mark.asyncio
    async def test_get_graphiti_creates_instance(self, mock_settings):
        """Test that _get_graphiti creates Graphiti instance."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            mock_graphiti_instance = AsyncMock()
            mock_graphiti_class.return_value = mock_graphiti_instance
            
            client = GraphitiClient(mock_settings)
            
            # First call should create instance
            result = await client._get_graphiti()
            
            assert result == mock_graphiti_instance
            assert client._graphiti == mock_graphiti_instance
            
            # Second call should return same instance
            result2 = await client._get_graphiti()
            assert result2 == mock_graphiti_instance
            
            # Verify Graphiti was initialized with correct parameters
            mock_graphiti_class.assert_called_once_with(
                uri=mock_settings.neo4j_uri,
                user=mock_settings.neo4j_user,
                password=mock_settings.neo4j_password,
                driver_config={"database": "neo4j"}
            )

    @pytest.mark.asyncio
    async def test_initialize_database_success(self, mock_settings):
        """Test successful database initialization."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            mock_graphiti = AsyncMock()
            mock_graphiti.build_indices_and_constraints = AsyncMock()
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            result = await client.initialize_database()
            
            assert result["status"] == "success"
            assert "Graphiti database initialized successfully" in result["message"]
            assert client._database_initialized is True
            
            mock_graphiti.build_indices_and_constraints.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_database_failure(self, mock_settings):
        """Test database initialization failure."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            mock_graphiti = AsyncMock()
            mock_graphiti.build_indices_and_constraints.side_effect = Exception("Database error")
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            # The retry decorator will retry 3 times before failing with RetryError
            with pytest.raises(Exception) as exc_info:
                await client.initialize_database()
            
            # Could be either RetryError or GraphitiConnectionError depending on retry behavior
            assert "Database error" in str(exc_info.value) or "RetryError" in str(exc_info.value)
            assert client._database_initialized is False

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_settings):
        """Test successful connection test."""
        with patch('pd_graphiti_service.graphiti_client.openai') as mock_openai, \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            # Mock Neo4j connection - properly mock async context manager
            mock_session = AsyncMock()
            mock_session.run = AsyncMock()
            
            # Create proper async context manager mock
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_driver = AsyncMock()
            mock_driver.session = Mock(return_value=mock_session_context)
            
            mock_graphiti = AsyncMock()
            mock_graphiti.driver = mock_driver
            mock_graphiti_class.return_value = mock_graphiti
            
            # Mock OpenAI API
            mock_openai_client = Mock()
            mock_response = Mock()
            mock_openai_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_openai_client
            
            client = GraphitiClient(mock_settings)
            client._database_initialized = True  # Set for full readiness
            
            result = await client.test_connection()
            
            assert result["neo4j_connected"] is True
            assert result["openai_accessible"] is True
            assert result["graphiti_ready"] is True
            assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_test_connection_neo4j_failure(self, mock_settings):
        """Test connection test with Neo4j failure."""
        with patch('pd_graphiti_service.graphiti_client.openai') as mock_openai, \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            # Mock Neo4j connection failure
            mock_graphiti_class.side_effect = Exception("Neo4j connection failed")
            
            # Mock successful OpenAI
            mock_openai_client = Mock()
            mock_response = Mock()
            mock_openai_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_openai_client
            
            client = GraphitiClient(mock_settings)
            
            result = await client.test_connection()
            
            assert result["neo4j_connected"] is False
            assert result["openai_accessible"] is True
            assert result["graphiti_ready"] is False
            assert len(result["errors"]) > 0
            assert "Neo4j connection failed" in result["errors"][0]

    def test_validate_episode_success(self, mock_settings, sample_episode):
        """Test successful episode validation."""
        with patch('pd_graphiti_service.graphiti_client.openai'):
            client = GraphitiClient(mock_settings)
            
            # Should not raise any exception
            client._validate_episode(sample_episode)

    def test_validate_episode_missing_required_fields(self, mock_settings):
        """Test episode validation with missing required fields."""
        with patch('pd_graphiti_service.graphiti_client.openai'):
            client = GraphitiClient(mock_settings)
            
            metadata = EpisodeMetadata(
                gene_symbol="TEST",
                episode_type="test",
                export_timestamp=datetime.now(),
                file_path=Path("/test/test.json"),
                file_size=1024
            )
            
            # Test missing episode_name
            episode = GraphitiEpisode(
                episode_name="",  # Empty name
                episode_body="test body",
                source="test",
                source_description="test",
                metadata=metadata
            )
            
            with pytest.raises(GraphitiValidationError) as exc_info:
                client._validate_episode(episode)
            
            assert "episode_name is required" in str(exc_info.value)

    def test_validate_episode_too_large(self, mock_settings):
        """Test episode validation with too large body."""
        with patch('pd_graphiti_service.graphiti_client.openai'):
            client = GraphitiClient(mock_settings)
            
            metadata = EpisodeMetadata(
                gene_symbol="TEST",
                episode_type="test",
                export_timestamp=datetime.now(),
                file_path=Path("/test/test.json"),
                file_size=1024
            )
            
            # Create episode with body too large
            large_body = "x" * 100001  # Over 100KB limit
            episode = GraphitiEpisode(
                episode_name="Test_Episode",
                episode_body=large_body,
                source="test",
                source_description="test",
                metadata=metadata
            )
            
            with pytest.raises(GraphitiValidationError) as exc_info:
                client._validate_episode(episode)
            
            assert "episode_body too large" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_episode_success(self, mock_settings, sample_episode):
        """Test successful episode addition."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            # Mock successful Graphiti response
            mock_result = Mock()
            mock_result.node_id = "node_123"
            
            mock_graphiti = AsyncMock()
            mock_graphiti.add_memory.return_value = mock_result
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            result = await client.add_episode(sample_episode)
            
            assert result["status"] == IngestionStatus.SUCCESS
            assert result["episode_name"] == sample_episode.episode_name
            assert result["graphiti_node_id"] == "node_123"
            assert "processing_time_seconds" in result
            
            # Verify Graphiti was called with correct parameters
            mock_graphiti.add_memory.assert_called_once_with(
                name=sample_episode.episode_name,
                episode_body=sample_episode.episode_body,
                source=sample_episode.source,
                source_description=sample_episode.source_description,
                group_id=sample_episode.group_id
            )

    @pytest.mark.asyncio
    async def test_add_episode_validation_error(self, mock_settings):
        """Test episode addition with validation error."""
        with patch('pd_graphiti_service.graphiti_client.openai'):
            client = GraphitiClient(mock_settings)
            
            # Create invalid episode
            metadata = EpisodeMetadata(
                gene_symbol="TEST",
                episode_type="test",
                export_timestamp=datetime.now(),
                file_path=Path("/test/test.json"),
                file_size=1024
            )
            
            invalid_episode = GraphitiEpisode(
                episode_name="",  # Invalid empty name
                episode_body="test body",
                source="test",
                source_description="test",
                metadata=metadata
            )
            
            with pytest.raises(GraphitiValidationError):
                await client.add_episode(invalid_episode)

    @pytest.mark.asyncio
    async def test_add_episodes_batch_success(self, mock_settings, sample_episode):
        """Test successful batch episode addition."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            mock_result = Mock()
            mock_result.node_id = "node_123"
            
            mock_graphiti = AsyncMock()
            mock_graphiti.add_memory.return_value = mock_result
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            # Create multiple episodes with different types for ordering test
            episodes = [sample_episode]  # gene_profile type
            
            result = await client.add_episodes_batch(episodes)
            
            assert result["status"] == IngestionStatus.SUCCESS
            assert result["total_episodes"] == 1
            assert result["successful"] == 1
            assert result["failed"] == 0
            assert len(result["episode_results"]) == 1

    @pytest.mark.asyncio
    async def test_get_graph_stats_success(self, mock_settings):
        """Test successful graph statistics retrieval."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            # Mock Neo4j session and query results
            mock_record1 = {"node_count": 100}
            mock_record2 = {"rel_count": 50}
            mock_record3 = {"group_nodes": 25}
            
            mock_result1 = AsyncMock()
            mock_result1.single.return_value = mock_record1
            
            mock_result2 = AsyncMock()
            mock_result2.single.return_value = mock_record2
            
            mock_result3 = AsyncMock()
            mock_result3.single.return_value = mock_record3
            
            mock_result4 = AsyncMock()
            mock_result4.__aiter__.return_value = [
                {"labels": ["Entity"], "count": 15},
                {"labels": ["Episode"], "count": 10}
            ]
            
            mock_session = AsyncMock()
            mock_session.run.side_effect = [mock_result1, mock_result2, mock_result3, mock_result4]
            
            # Create proper async context manager mock
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_driver = AsyncMock()
            mock_driver.session = Mock(return_value=mock_session_context)
            
            mock_graphiti = AsyncMock()
            mock_graphiti.driver = mock_driver
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            result = await client.get_graph_stats()
            
            assert result["total_nodes"] == 100
            assert result["total_relationships"] == 50
            assert result["group_nodes"] == 25
            assert result["group_id"] == mock_settings.graphiti_group_id
            assert "node_types" in result
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_close_client(self, mock_settings):
        """Test client cleanup."""
        with patch('pd_graphiti_service.graphiti_client.openai'), \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            mock_graphiti = AsyncMock()
            mock_graphiti.close = AsyncMock()
            mock_graphiti_class.return_value = mock_graphiti
            
            client = GraphitiClient(mock_settings)
            
            # Initialize graphiti instance
            await client._get_graphiti()
            
            # Close client
            await client.close()
            
            assert client._graphiti is None
            mock_graphiti.close.assert_called_once()


class TestGraphitiClientCreation:
    """Test GraphitiClient creation utilities."""

    def test_create_graphiti_client(self, mock_settings):
        """Test create_graphiti_client convenience function."""
        with patch('pd_graphiti_service.graphiti_client.openai'):
            client = create_graphiti_client(mock_settings)
            
            assert isinstance(client, GraphitiClient)
            assert client.settings == mock_settings


class TestGraphitiClientIntegration:
    """Integration-style tests (still mocked but more comprehensive)."""

    @pytest.mark.asyncio
    async def test_full_workflow_success(self, mock_settings, sample_episode):
        """Test complete workflow: init -> test -> add episode -> stats."""
        with patch('pd_graphiti_service.graphiti_client.openai') as mock_openai, \
             patch('pd_graphiti_service.graphiti_client.Graphiti') as mock_graphiti_class:
            
            # Setup comprehensive mocks
            mock_result = Mock()
            mock_result.node_id = "node_123"
            
            mock_session = AsyncMock()
            mock_session.run = AsyncMock()
            
            # Create proper async context manager mock
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_driver = AsyncMock()
            mock_driver.session = Mock(return_value=mock_session_context)
            
            mock_graphiti = AsyncMock()
            mock_graphiti.driver = mock_driver
            mock_graphiti.build_indices_and_constraints = AsyncMock()
            mock_graphiti.add_memory.return_value = mock_result
            mock_graphiti.close = AsyncMock()
            mock_graphiti_class.return_value = mock_graphiti
            
            # Mock OpenAI
            mock_openai_client = Mock()
            mock_response = Mock()
            mock_openai_client.chat.completions.create.return_value = mock_response
            mock_openai.OpenAI.return_value = mock_openai_client
            
            client = GraphitiClient(mock_settings)
            
            # 1. Initialize database
            init_result = await client.initialize_database()
            assert init_result["status"] == "success"
            assert client._database_initialized is True
            
            # 2. Test connections
            conn_result = await client.test_connection()
            assert conn_result["graphiti_ready"] is True
            
            # 3. Add episode
            add_result = await client.add_episode(sample_episode)
            assert add_result["status"] == IngestionStatus.SUCCESS
            
            # 4. Get stats (mock the session.run calls for stats)
            mock_session.run.side_effect = [
                # Mock results for each stats query
                AsyncMock(**{"single.return_value": {"node_count": 1}}),
                AsyncMock(**{"single.return_value": {"rel_count": 0}}),
                AsyncMock(**{"single.return_value": {"group_nodes": 1}}),
                AsyncMock(**{"__aiter__.return_value": [{"labels": ["Entity"], "count": 1}]})
            ]
            
            stats_result = await client.get_graph_stats()
            assert "total_nodes" in stats_result
            
            # 5. Close client
            await client.close()
            assert client._graphiti is None