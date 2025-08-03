"""Configuration validation and connection testing for the PD Graphiti Service."""

import asyncio
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import httpx
from neo4j import GraphDatabase
import structlog

from .config import Settings
from .logging_config import get_logger, error_tracker


class ConfigurationValidator:
    """Validates configuration and tests external connections."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self.validation_errors: List[str] = []
        self.warnings: List[str] = []
    
    async def validate_all(self) -> Dict[str, Any]:
        """
        Validate all configuration and test external connections.
        
        Returns:
            Dictionary with validation results
        """
        self.logger.info("Starting comprehensive configuration validation")
        start_time = time.time()
        
        validation_results = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "connection_tests": {},
            "validation_time": 0,
            "timestamp": time.time()
        }
        
        try:
            # Validate environment variables
            env_validation = await self._validate_environment_variables()
            validation_results["environment_validation"] = env_validation
            
            # Validate paths and directories
            path_validation = await self._validate_paths()
            validation_results["path_validation"] = path_validation
            
            # Test external connections
            connection_tests = await self._test_external_connections()
            validation_results["connection_tests"] = connection_tests
            
            # Validate application configuration
            app_validation = await self._validate_application_config()
            validation_results["application_validation"] = app_validation
            
            # Compile final results
            all_errors = (
                env_validation.get("errors", []) +
                path_validation.get("errors", []) +
                connection_tests.get("errors", []) +
                app_validation.get("errors", [])
            )
            
            all_warnings = (
                env_validation.get("warnings", []) +
                path_validation.get("warnings", []) +
                connection_tests.get("warnings", []) +
                app_validation.get("warnings", [])
            )
            
            validation_results["errors"] = all_errors
            validation_results["warnings"] = all_warnings
            validation_results["valid"] = len(all_errors) == 0
            validation_results["validation_time"] = time.time() - start_time
            
            if validation_results["valid"]:
                self.logger.info(
                    "Configuration validation completed successfully",
                    duration=validation_results["validation_time"],
                    warnings_count=len(all_warnings)
                )
            else:
                self.logger.error(
                    "Configuration validation failed",
                    errors=all_errors,
                    warnings=all_warnings,
                    duration=validation_results["validation_time"]
                )
            
            return validation_results
            
        except Exception as e:
            error_id = error_tracker.track_error(
                e, 
                context={"operation": "configuration_validation"},
                user_message="Failed to validate configuration"
            )
            
            validation_results.update({
                "valid": False,
                "errors": [f"Validation failed with error {error_id}: {str(e)}"],
                "validation_time": time.time() - start_time
            })
            
            return validation_results
    
    async def _validate_environment_variables(self) -> Dict[str, Any]:
        """Validate required environment variables."""
        self.logger.debug("Validating environment variables")
        
        errors = []
        warnings = []
        
        # Required variables
        required_vars = [
            ("openai_api_key", "OpenAI API key is required for AI operations"),
            ("neo4j_password", "Neo4j password is required for database access"),
        ]
        
        for var_name, error_message in required_vars:
            value = getattr(self.settings, var_name, None)
            if not value or (isinstance(value, str) and value.strip() == ""):
                errors.append(f"{error_message} (missing: {var_name})")
        
        # Validate API key format
        if hasattr(self.settings, 'openai_api_key') and self.settings.openai_api_key:
            if not self.settings.openai_api_key.startswith(('sk-', 'test-key-')):
                warnings.append("OpenAI API key format appears invalid (should start with 'sk-')")
        
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.settings.log_level.upper() not in valid_log_levels:
            errors.append(f"Invalid log level: {self.settings.log_level}. Must be one of {valid_log_levels}")
        
        # Validate ports
        if not (1024 <= self.settings.port <= 65535):
            errors.append(f"Invalid port number: {self.settings.port}. Must be between 1024 and 65535")
        
        if not (1024 <= self.settings.metrics_port <= 65535):
            errors.append(f"Invalid metrics port: {self.settings.metrics_port}. Must be between 1024 and 65535")
        
        if self.settings.port == self.settings.metrics_port:
            errors.append("Application port and metrics port cannot be the same")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checked_variables": len(required_vars) + 3  # +3 for log_level, ports
        }
    
    async def _validate_paths(self) -> Dict[str, Any]:
        """Validate file paths and directories."""
        self.logger.debug("Validating paths and directories")
        
        errors = []
        warnings = []
        
        # Check export directory
        export_dir = Path(self.settings.export_directory)
        if not export_dir.exists():
            warnings.append(f"Export directory does not exist: {export_dir}")
        elif not export_dir.is_dir():
            errors.append(f"Export directory path is not a directory: {export_dir}")
        else:
            # Check if directory is readable
            try:
                list(export_dir.iterdir())
            except PermissionError:
                errors.append(f"No read permission for export directory: {export_dir}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checked_paths": 1
        }
    
    async def _test_external_connections(self) -> Dict[str, Any]:
        """Test connections to external services."""
        self.logger.debug("Testing external connections")
        
        connection_results = {}
        errors = []
        warnings = []
        
        # Test Neo4j connection
        neo4j_result = await self._test_neo4j_connection()
        connection_results["neo4j"] = neo4j_result
        if not neo4j_result["connected"]:
            errors.append(f"Neo4j connection failed: {neo4j_result['error']}")
        
        # Test OpenAI API connection
        openai_result = await self._test_openai_connection()
        connection_results["openai"] = openai_result
        if not openai_result["connected"]:
            # OpenAI failures are warnings if using test key, errors otherwise
            if self.settings.openai_api_key.startswith('test-'):
                warnings.append(f"OpenAI API test failed (test key): {openai_result['error']}")
            else:
                errors.append(f"OpenAI API connection failed: {openai_result['error']}")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "connection_results": connection_results
        }
    
    async def _test_neo4j_connection(self) -> Dict[str, Any]:
        """Test Neo4j database connection."""
        try:
            start_time = time.time()
            
            driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password)
            )
            
            # Test connection with a simple query
            with driver.session() as session:
                result = session.run("RETURN 1 as test")
                test_value = result.single()["test"]
                assert test_value == 1
            
            driver.close()
            
            return {
                "connected": True,
                "response_time": time.time() - start_time,
                "database_version": None,  # Could be extracted from connection
                "error": None
            }
            
        except Exception as e:
            return {
                "connected": False,
                "response_time": time.time() - start_time,
                "database_version": None,
                "error": str(e)
            }
    
    async def _test_openai_connection(self) -> Dict[str, Any]:
        """Test OpenAI API connection."""
        try:
            start_time = time.time()
            
            # Skip actual API test for test keys
            if self.settings.openai_api_key.startswith('test-'):
                return {
                    "connected": False,
                    "response_time": 0,
                    "model_available": False,
                    "error": "Test key - API not tested"
                }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                        "User-Agent": "pd-graphiti-service/0.1.0"
                    },
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    model_ids = [model["id"] for model in models_data.get("data", [])]
                    model_available = self.settings.openai_model in model_ids
                    
                    return {
                        "connected": True,
                        "response_time": time.time() - start_time,
                        "model_available": model_available,
                        "available_models": len(model_ids),
                        "error": None
                    }
                else:
                    return {
                        "connected": False,
                        "response_time": time.time() - start_time,
                        "model_available": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
        except Exception as e:
            return {
                "connected": False,
                "response_time": time.time() - start_time,
                "model_available": False,
                "error": str(e)
            }
    
    async def _validate_application_config(self) -> Dict[str, Any]:
        """Validate application-specific configuration."""
        self.logger.debug("Validating application configuration")
        
        errors = []
        warnings = []
        
        # Validate Graphiti group ID format
        group_id = self.settings.graphiti_group_id
        if not group_id or not isinstance(group_id, str):
            errors.append("Graphiti group ID must be a non-empty string")
        elif len(group_id) < 3:
            warnings.append("Graphiti group ID is very short, consider using a more descriptive name")
        elif not group_id.replace('_', '').replace('-', '').isalnum():
            warnings.append("Graphiti group ID contains special characters, this may cause issues")
        
        # Validate model configuration
        if not self.settings.openai_model:
            errors.append("OpenAI model must be specified")
        
        if not self.settings.openai_small_model:
            warnings.append("OpenAI small model not specified, will use default model for all operations")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "checked_settings": 3
        }


async def validate_configuration(settings: Settings) -> Dict[str, Any]:
    """
    Validate configuration and return results.
    
    Args:
        settings: Application settings to validate
    
    Returns:
        Validation results dictionary
    """
    validator = ConfigurationValidator(settings)
    return await validator.validate_all()


def raise_for_validation_errors(validation_results: Dict[str, Any], fail_fast: bool = True):
    """
    Raise an exception if validation failed and fail_fast is True.
    
    Args:
        validation_results: Results from validate_configuration()
        fail_fast: Whether to raise exception on validation failure
    
    Raises:
        RuntimeError: If validation failed and fail_fast is True
    """
    if not validation_results["valid"] and fail_fast:
        errors = validation_results["errors"]
        error_message = f"Configuration validation failed with {len(errors)} error(s):\n"
        error_message += "\n".join(f"- {error}" for error in errors)
        
        if validation_results["warnings"]:
            warnings = validation_results["warnings"]
            error_message += f"\n\nAdditional warnings ({len(warnings)}):\n"
            error_message += "\n".join(f"- {warning}" for warning in warnings)
        
        raise RuntimeError(error_message)


class ConnectionMonitor:
    """Monitor external connections health."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self._connection_status = {
            "neo4j": False,
            "openai": False,
            "last_check": None
        }
    
    async def check_connections(self) -> Dict[str, Any]:
        """Check all external connections."""
        validator = ConfigurationValidator(self.settings)
        
        # Test connections
        neo4j_result = await validator._test_neo4j_connection()
        openai_result = await validator._test_openai_connection()
        
        # Update status
        self._connection_status.update({
            "neo4j": neo4j_result["connected"],
            "openai": openai_result["connected"],
            "last_check": time.time()
        })
        
        return {
            "neo4j": neo4j_result,
            "openai": openai_result,
            "all_healthy": neo4j_result["connected"] and openai_result["connected"]
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        return self._connection_status.copy()


# Global connection monitor
_connection_monitor: Optional[ConnectionMonitor] = None


def get_connection_monitor(settings: Settings) -> ConnectionMonitor:
    """Get or create the global connection monitor."""
    global _connection_monitor
    if _connection_monitor is None:
        _connection_monitor = ConnectionMonitor(settings)
    return _connection_monitor