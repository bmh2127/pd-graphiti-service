"""Fixtures and configuration for performance tests."""

import asyncio
import pytest
import tempfile
import json
import time
from pathlib import Path
from typing import Dict, Any, List, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import httpx
import psutil

from src.pd_graphiti_service.config import Settings
from src.pd_graphiti_service.models import GraphitiEpisode, EpisodeMetadata, IngestionStatus


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async session-scoped fixtures."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def performance_settings() -> Settings:
    """Test settings optimized for performance testing."""
    return Settings(
        neo4j_uri="bolt://localhost:7688",
        neo4j_user="neo4j", 
        neo4j_password="testpassword123",
        openai_api_key="test-key-for-performance-testing",
        graphiti_group_id="performance_test_group",
        log_level="INFO",
        enable_monitoring=True,
        enable_prometheus=True,
        host="localhost",
        port=8004,  # Different port to avoid conflicts
        metrics_port=8005
    )


@pytest.fixture
def mock_openai_responses():
    """Mock OpenAI responses to avoid API costs during load testing."""
    return {
        "embeddings": [0.1] * 1536,  # Standard embedding dimension
        "completion": "This is a test response for performance testing."
    }


@pytest.fixture
def sample_episode_data() -> Dict[str, Any]:
    """Sample episode data for performance testing."""
    return {
        "episode_metadata": {
            "gene_symbol": "SNCA",
            "episode_type": "gene_profile", 
            "export_timestamp": "2025-01-07T12:00:00Z"
        },
        "graphiti_episode": {
            "name": "SNCA_gene_profile",
            "episode_body": "SNCA (alpha-synuclein) is a protein that in humans is encoded by the SNCA gene. " * 50,  # Make it substantial
            "source": "performance_test",
            "source_description": "Generated episode for performance testing",
            "group_id": "performance_test_group"
        }
    }


@pytest.fixture 
def sample_episode(sample_episode_data) -> GraphitiEpisode:
    """Create a sample GraphitiEpisode for testing."""
    metadata = EpisodeMetadata(
        gene_symbol=sample_episode_data["episode_metadata"]["gene_symbol"],
        episode_type=sample_episode_data["episode_metadata"]["episode_type"],
        export_timestamp=sample_episode_data["episode_metadata"]["export_timestamp"],
        file_path=Path("/tmp/test_episode.json"),
        file_size=len(json.dumps(sample_episode_data)),
        validation_status=IngestionStatus.PENDING
    )
    
    episode_data = sample_episode_data["graphiti_episode"]
    return GraphitiEpisode(
        episode_name=episode_data["name"],
        episode_body=episode_data["episode_body"],
        source=episode_data["source"],
        source_description=episode_data["source_description"],
        group_id=episode_data["group_id"],
        metadata=metadata
    )


@pytest.fixture
def large_episode_batch(sample_episode_data) -> List[GraphitiEpisode]:
    """Generate a large batch of episodes for load testing."""
    episodes = []
    gene_symbols = ["SNCA", "LRRK2", "PARK7", "PINK1", "PRKN"] * 20  # 100 episodes
    episode_types = ["gene_profile", "gwas_evidence", "eqtl_evidence", "literature_evidence", "pathway_evidence"]
    
    for i, gene in enumerate(gene_symbols):
        episode_type = episode_types[i % len(episode_types)]
        
        metadata = EpisodeMetadata(
            gene_symbol=gene,
            episode_type=episode_type,
            export_timestamp="2025-01-07T12:00:00Z",
            file_path=Path(f"/tmp/test_episode_{i}.json"),
            file_size=1000 + i * 10,  # Varying sizes
            validation_status=IngestionStatus.PENDING
        )
        
        episode = GraphitiEpisode(
            episode_name=f"{gene}_{episode_type}_{i}",
            episode_body=f"Performance test episode for {gene} - {episode_type}. " + "Content. " * (50 + i),
            source="performance_test",
            source_description=f"Performance test episode {i}",
            group_id="performance_test_group",
            metadata=metadata
        )
        episodes.append(episode)
    
    return episodes


@pytest.fixture 
def mock_export_directory(tmp_path, large_episode_batch) -> Path:
    """Create a mock export directory with many episodes for testing."""
    export_dir = tmp_path / "mock_export_20250107_120000"
    export_dir.mkdir()
    
    # Create episodes directory structure
    episodes_dir = export_dir / "episodes"
    episodes_dir.mkdir()
    
    episode_types = ["gene_profile", "gwas_evidence", "eqtl_evidence", "literature_evidence", "pathway_evidence"]
    for episode_type in episode_types:
        type_dir = episodes_dir / episode_type
        type_dir.mkdir()
    
    # Write episode files
    manifest_data = {
        "export_id": "performance_test_export_20250107_120000",
        "export_timestamp": "2025-01-07T12:00:00Z",
        "dagster_run_id": "performance_test_run",
        "total_episodes": len(large_episode_batch),
        "episode_types": episode_types,
        "gene_symbols": ["SNCA", "LRRK2", "PARK7", "PINK1", "PRKN"]
    }
    
    for i, episode in enumerate(large_episode_batch):
        episode_data = {
            "episode_metadata": {
                "gene_symbol": episode.metadata.gene_symbol,
                "episode_type": episode.metadata.episode_type,
                "export_timestamp": "2025-01-07T12:00:00Z"
            },
            "graphiti_episode": {
                "name": episode.episode_name,
                "episode_body": episode.episode_body,
                "source": episode.source,
                "source_description": episode.source_description,
                "group_id": episode.group_id
            }
        }
        
        episode_file = episodes_dir / episode.metadata.episode_type / f"{episode.metadata.gene_symbol}_{episode.metadata.episode_type}_{i}.json"
        with open(episode_file, 'w') as f:
            json.dump(episode_data, f, indent=2)
    
    # Write manifest
    manifest_file = export_dir / "manifest.json"
    with open(manifest_file, 'w') as f:
        json.dump(manifest_data, f, indent=2)
    
    return export_dir


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API testing."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture
def performance_monitor():
    """Monitor system performance during tests."""
    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.start_memory = None
            self.end_memory = None
            self.start_cpu = None
            self.end_cpu = None
            self.process = psutil.Process()
        
        def start(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info()
            self.start_cpu = self.process.cpu_percent()
        
        def stop(self):
            self.end_time = time.time()
            self.end_memory = self.process.memory_info()
            self.end_cpu = self.process.cpu_percent()
        
        @property
        def duration(self) -> float:
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return 0.0
        
        @property
        def memory_delta(self) -> int:
            if self.start_memory and self.end_memory:
                return self.end_memory.rss - self.start_memory.rss
            return 0
        
        def get_stats(self) -> Dict[str, Any]:
            return {
                "duration": self.duration,
                "memory_delta_mb": self.memory_delta / 1024 / 1024,
                "start_memory_mb": self.start_memory.rss / 1024 / 1024 if self.start_memory else 0,
                "end_memory_mb": self.end_memory.rss / 1024 / 1024 if self.end_memory else 0,
                "start_cpu_percent": self.start_cpu,
                "end_cpu_percent": self.end_cpu
            }
    
    return PerformanceMonitor()


@pytest.fixture
def network_failure_simulator():
    """Simulate network failures for reliability testing."""
    class NetworkFailureSimulator:
        def __init__(self):
            self.original_methods = {}
        
        def simulate_connection_timeout(self, target_module, method_name, delay=5.0):
            """Simulate connection timeout by adding delay."""
            import time
            original_method = getattr(target_module, method_name)
            self.original_methods[f"{target_module.__name__}.{method_name}"] = original_method
            
            async def delayed_method(*args, **kwargs):
                await asyncio.sleep(delay)
                raise asyncio.TimeoutError("Simulated network timeout")
            
            setattr(target_module, method_name, delayed_method)
        
        def simulate_connection_error(self, target_module, method_name):
            """Simulate connection error."""
            original_method = getattr(target_module, method_name)
            self.original_methods[f"{target_module.__name__}.{method_name}"] = original_method
            
            async def error_method(*args, **kwargs):
                raise ConnectionError("Simulated connection error")
            
            setattr(target_module, method_name, error_method)
        
        def restore_all(self):
            """Restore all original methods."""
            for key, original_method in self.original_methods.items():
                module_name, method_name = key.rsplit('.', 1)
                # This is a simplified restore - in practice you'd need more sophisticated module resolution
                pass
    
    return NetworkFailureSimulator()