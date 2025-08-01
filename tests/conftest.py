# File: tests/conftest.py
"""Test configuration for API endpoints."""

import pytest
from pathlib import Path
from unittest.mock import patch
import os
import tempfile

# Set test environment variables
os.environ.update({
    "OPENAI_API_KEY": "test-key-12345",
    "NEO4J_PASSWORD": "test-password",
    "NEO4J_URI": "bolt://localhost:7687",
    "NEO4J_USER": "neo4j",
    "GRAPHITI_GROUP_ID": "test_group",
    "LOG_LEVEL": "INFO",
    "EXPORT_DIRECTORY": str(Path(tempfile.gettempdir()) / "test_exports"),
    "ENABLE_MONITORING": "false"  # Disable monitoring for tests
})

# Global test configuration
@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment before running any tests."""
    
    # Create test export directory
    test_export_dir = Path(tempfile.gettempdir()) / "test_exports"
    test_export_dir.mkdir(exist_ok=True)
    
    yield
    
    # Cleanup after tests
    try:
        import shutil
        shutil.rmtree(test_export_dir, ignore_errors=True)
    except Exception:
        pass

@pytest.fixture(autouse=True)
def mock_app_services():
    """Mock all FastAPI app services for testing."""
    
    # Mock the service initialization to prevent actual startup
    with patch('pd_graphiti_service.main.lifespan'), \
         patch('pd_graphiti_service.main._services', {
             "settings": None,
             "graphiti_client": None,
             "ingestion_service": None,
             "file_monitor": None,
             "task_manager": None
         }):
        yield

# Test database configuration
pytest_plugins = ["pytest_asyncio"]

# Configure asyncio for tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )