"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from pd_graphiti_service.config import Settings, get_settings


class TestSettings:
    """Test Settings class."""

    def test_settings_with_minimal_env_vars(self, monkeypatch):
        """Test settings load with minimal required environment variables."""
        # Set minimal required environment variables
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
        
        # Clear test environment variables to test actual defaults
        monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
        
        settings = Settings.from_env()
        
        assert settings.openai_api_key == "test-key"
        assert settings.neo4j_password == "test-password"
        assert settings.neo4j_uri == "bolt://localhost:7687"  # default
        assert settings.neo4j_user == "neo4j"  # default
        assert settings.graphiti_group_id == "pd_target_discovery"  # default
        assert settings.log_level == "INFO"  # default
        assert settings.host == "0.0.0.0"  # default
        assert settings.port == 8000  # default

    def test_settings_missing_required_env_vars(self, monkeypatch):
        """Test settings fail when required environment variables are missing."""
        # Clear environment variables
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
        
        with pytest.raises(ValueError) as exc_info:
            Settings.from_env()
        
        # Should fail with error about missing required environment variable
        assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_settings_custom_values(self, monkeypatch):
        """Test settings with custom environment variables."""
        monkeypatch.setenv("OPENAI_API_KEY", "custom-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "custom-password")
        monkeypatch.setenv("NEO4J_URI", "bolt://custom:7687")
        monkeypatch.setenv("GRAPHITI_GROUP_ID", "custom_group")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("PORT", "9000")
        
        settings = Settings.from_env()
        
        assert settings.openai_api_key == "custom-key"
        assert settings.neo4j_password == "custom-password"
        assert settings.neo4j_uri == "bolt://custom:7687"
        assert settings.graphiti_group_id == "custom_group"
        assert settings.log_level == "DEBUG"
        assert settings.port == 9000

    def test_export_directory_conversion(self, monkeypatch):
        """Test export directory string is converted to Path."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
        monkeypatch.setenv("EXPORT_DIRECTORY", "/test/path")
        
        settings = Settings.from_env()
        
        assert isinstance(settings.export_directory, Path)
        assert str(settings.export_directory) == "/test/path"

    def test_log_level_validation(self, monkeypatch):
        """Test log level validation."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
        
        # Valid log levels should work
        for level in ["DEBUG", "info", "Warning", "ERROR", "critical"]:
            monkeypatch.setenv("LOG_LEVEL", level)
            settings = Settings.from_env()
            assert settings.log_level == level.upper()

        # Invalid log level should fail
        monkeypatch.setenv("LOG_LEVEL", "INVALID")
        with pytest.raises(ValidationError):
            Settings.from_env()

    def test_neo4j_uri_validation(self, monkeypatch):
        """Test Neo4j URI validation."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
        
        # Valid URIs should work
        valid_uris = [
            "bolt://localhost:7687",
            "neo4j://localhost:7687",
            "bolt+s://localhost:7687",
            "neo4j+s://localhost:7687",
        ]
        
        for uri in valid_uris:
            monkeypatch.setenv("NEO4J_URI", uri)
            settings = Settings.from_env()
            assert settings.neo4j_uri == uri

        # Invalid URI should fail
        monkeypatch.setenv("NEO4J_URI", "invalid://localhost:7687")
        with pytest.raises(ValidationError):
            Settings.from_env()

    def test_get_settings_function(self, monkeypatch):
        """Test get_settings function returns Settings instance."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
        
        settings = get_settings()
        
        assert isinstance(settings, Settings)
        assert settings.openai_api_key == "test-key"