"""Episode ingestion service for processing Dagster exports."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

from .config import Settings
from .graphiti_client import GraphitiClient, GraphitiConnectionError, GraphitiValidationError
from .models import (
    GraphitiEpisode, 
    EpisodeMetadata, 
    IngestionStatus, 
    ExportManifest
)

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for ingestion-related errors."""
    pass


class ManifestValidationError(IngestionError):
    """Raised when export manifest validation fails."""
    pass


class FileIntegrityError(IngestionError):
    """Raised when file integrity checks fail."""
    pass


class IngestionService:
    """Service for processing Dagster episode exports into Graphiti knowledge graph."""
    
    def __init__(self, settings: Settings, graphiti_client: GraphitiClient):
        """Initialize IngestionService.
        
        Args:
            settings: Application settings
            graphiti_client: Initialized GraphitiClient instance
        """
        self.settings = settings
        self.graphiti_client = graphiti_client
        self._processed_episodes: Set[str] = set()
        
        logger.info("IngestionService initialized")

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            MD5 checksum as hex string
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _load_manifest(self, export_dir: Path) -> ExportManifest:
        """Load and validate export manifest.
        
        Args:
            export_dir: Path to export directory
            
        Returns:
            Validated ExportManifest
            
        Raises:
            ManifestValidationError: If manifest is missing or invalid
        """
        manifest_path = export_dir / "manifest.json"
        
        if not manifest_path.exists():
            raise ManifestValidationError(f"Manifest file not found: {manifest_path}")
        
        try:
            with open(manifest_path, 'r') as f:
                manifest_data = json.load(f)
            
            # Parse and validate manifest
            manifest = ExportManifest.model_validate(manifest_data)
            
            logger.info(f"Loaded manifest: {manifest.export_id} with {manifest.total_episodes} episodes")
            return manifest
            
        except json.JSONDecodeError as e:
            raise ManifestValidationError(f"Invalid JSON in manifest: {e}")
        except Exception as e:
            raise ManifestValidationError(f"Failed to parse manifest: {e}")

    def _discover_episode_files(self, export_dir: Path) -> List[Path]:
        """Discover all episode JSON files in export directory.
        
        Args:
            export_dir: Path to export directory
            
        Returns:
            List of episode file paths
        """
        episode_files = []
        
        # Look for episodes in subdirectories
        episodes_dir = export_dir / "episodes"
        if episodes_dir.exists():
            # Search for all JSON files in episode type subdirectories
            for episode_type_dir in episodes_dir.iterdir():
                if episode_type_dir.is_dir():
                    for json_file in episode_type_dir.glob("*.json"):
                        episode_files.append(json_file)
        
        # Also check for JSON files directly in export directory
        for json_file in export_dir.glob("*.json"):
            if json_file.name != "manifest.json":  # Skip manifest
                episode_files.append(json_file)
        
        logger.info(f"Discovered {len(episode_files)} episode files")
        return sorted(episode_files)

    def _load_episode_from_file(self, file_path: Path, validate_checksum: bool = True) -> GraphitiEpisode:
        """Load episode from JSON file and create GraphitiEpisode.
        
        Args:
            file_path: Path to episode JSON file
            validate_checksum: Whether to validate file checksum
            
        Returns:
            GraphitiEpisode instance
            
        Raises:
            FileIntegrityError: If file validation fails
            IngestionError: If episode loading fails
        """
        try:
            # Calculate file metadata
            file_size = file_path.stat().st_size
            checksum = self._calculate_file_checksum(file_path) if validate_checksum else None
            
            # Load episode data
            with open(file_path, 'r') as f:
                episode_data = json.load(f)
            
            # Extract episode metadata from file path and content
            # Assume file structure: episodes/{episode_type}/{gene_symbol}_{episode_type}.json
            parts = file_path.stem.split('_')
            if len(parts) >= 2:
                gene_symbol = parts[0]
                episode_type = '_'.join(parts[1:])
            else:
                # Fallback parsing
                gene_symbol = parts[0] if parts else "unknown"
                episode_type = file_path.parent.name if file_path.parent.name != "episodes" else "unknown"
            
            # Create episode metadata
            metadata = EpisodeMetadata(
                gene_symbol=gene_symbol,
                episode_type=episode_type,
                export_timestamp=datetime.fromtimestamp(file_path.stat().st_mtime),
                file_path=file_path,
                file_size=file_size,
                checksum=checksum,
                validation_status=IngestionStatus.PENDING
            )
            
            # Create GraphitiEpisode
            episode = GraphitiEpisode(
                episode_name=episode_data.get("episode_name", f"{episode_type}_{gene_symbol}"),
                episode_body=episode_data.get("episode_body", ""),
                source=episode_data.get("source", "dagster_pipeline"),
                source_description=episode_data.get("source_description", f"Episode from {file_path.name}"),
                group_id=episode_data.get("group_id", self.settings.graphiti_group_id),
                metadata=metadata
            )
            
            return episode
            
        except json.JSONDecodeError as e:
            raise IngestionError(f"Invalid JSON in episode file {file_path}: {e}")
        except Exception as e:
            raise IngestionError(f"Failed to load episode from {file_path}: {e}")

    def _validate_file_integrity(self, file_path: Path, expected_checksum: Optional[str] = None) -> bool:
        """Validate file integrity using checksum.
        
        Args:
            file_path: Path to file
            expected_checksum: Expected MD5 checksum (if None, skip validation)
            
        Returns:
            True if file is valid
            
        Raises:
            FileIntegrityError: If checksum validation fails
        """
        if expected_checksum is None:
            return True
            
        actual_checksum = self._calculate_file_checksum(file_path)
        
        if actual_checksum != expected_checksum:
            raise FileIntegrityError(
                f"Checksum mismatch for {file_path}: "
                f"expected {expected_checksum}, got {actual_checksum}"
            )
        
        return True

    def _get_episode_processing_order(self, episodes: List[GraphitiEpisode]) -> List[GraphitiEpisode]:
        """Sort episodes by recommended processing order.
        
        Args:
            episodes: List of episodes to sort
            
        Returns:
            Episodes sorted by processing priority
        """
        # Define processing order (same as in GraphitiClient)
        episode_order = [
            "gene_profile", "gwas_evidence", "eqtl_evidence", 
            "literature_evidence", "pathway_evidence", "integration"
        ]
        
        def get_priority(episode: GraphitiEpisode) -> int:
            episode_type = episode.metadata.episode_type
            try:
                return episode_order.index(episode_type)
            except ValueError:
                return len(episode_order)  # Unknown types go last
        
        return sorted(episodes, key=get_priority)

    async def process_export_directory(
        self, 
        export_dir: Path, 
        validate_files: bool = True,
        force_reingest: bool = False,
        episode_types_filter: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Process complete export directory.
        
        Args:
            export_dir: Path to export directory
            validate_files: Whether to validate file checksums
            force_reingest: Whether to re-ingest already processed episodes
            episode_types_filter: Optional list of episode types to process
            
        Returns:
            Dict containing processing results
        """
        start_time = datetime.now()
        logger.info(f"Starting export directory processing: {export_dir}")
        
        try:
            # Load and validate manifest
            manifest = self._load_manifest(export_dir)
            
            # Discover episode files
            episode_files = self._discover_episode_files(export_dir)
            
            if not episode_files:
                return {
                    "status": IngestionStatus.FAILED,
                    "error": "No episode files found in export directory",
                    "export_id": manifest.export_id,
                    "processing_time": (datetime.now() - start_time).total_seconds()
                }
            
            # Load episodes from files
            episodes = []
            load_errors = []
            
            for file_path in episode_files:
                try:
                    episode = self._load_episode_from_file(file_path, validate_checksum=validate_files)
                    
                    # Apply episode type filter if provided
                    if episode_types_filter and episode.metadata.episode_type not in episode_types_filter:
                        continue
                    
                    # Skip already processed episodes unless forcing reingest
                    if not force_reingest and episode.episode_name in self._processed_episodes:
                        logger.info(f"Skipping already processed episode: {episode.episode_name}")
                        continue
                    
                    episodes.append(episode)
                    
                except Exception as e:
                    error_msg = f"Failed to load episode from {file_path}: {str(e)}"
                    load_errors.append(error_msg)
                    logger.error(error_msg)
            
            if not episodes and not load_errors:
                return {
                    "status": IngestionStatus.SUCCESS,
                    "message": "All episodes already processed (use force_reingest=True to reprocess)",
                    "export_id": manifest.export_id,
                    "processing_time": (datetime.now() - start_time).total_seconds()
                }
            
            # Sort episodes by processing order
            episodes = self._get_episode_processing_order(episodes)
            
            # Process episodes through GraphitiClient
            ingestion_result = await self.graphiti_client.add_episodes_batch(episodes)
            
            # Track processed episodes
            for episode in episodes:
                if episode.episode_name not in [result.get("episode_name") for result in ingestion_result.get("episode_results", []) if result.get("status") == IngestionStatus.FAILED]:
                    self._processed_episodes.add(episode.episode_name)
            
            # Combine results
            processing_time = (datetime.now() - start_time).total_seconds()
            
            result = {
                "status": ingestion_result.get("status", IngestionStatus.FAILED),
                "export_id": manifest.export_id,
                "export_timestamp": manifest.export_timestamp.isoformat(),
                "dagster_run_id": manifest.dagster_run_id,
                "total_files_discovered": len(episode_files),
                "total_episodes_loaded": len(episodes),
                "load_errors": load_errors,
                "processing_time": processing_time,
                "ingestion_results": ingestion_result
            }
            
            logger.info(f"Completed export processing: {manifest.export_id} in {processing_time:.2f}s")
            return result
            
        except (ManifestValidationError, FileIntegrityError) as e:
            error_msg = f"Export validation failed: {str(e)}"
            logger.error(error_msg)
            return {
                "status": IngestionStatus.FAILED,
                "error": error_msg,
                "processing_time": (datetime.now() - start_time).total_seconds()
            }
        except Exception as e:
            error_msg = f"Unexpected error processing export: {str(e)}"
            logger.error(error_msg)
            return {
                "status": IngestionStatus.FAILED,
                "error": error_msg,
                "processing_time": (datetime.now() - start_time).total_seconds()
            }

    async def process_single_episode(
        self, 
        episode: GraphitiEpisode, 
        validate_episode: bool = True,
        force_reingest: bool = False
    ) -> Dict[str, Any]:
        """Process a single episode.
        
        Args:
            episode: Episode to process
            validate_episode: Whether to validate episode before ingestion
            force_reingest: Whether to re-ingest if already processed
            
        Returns:
            Dict containing processing result
        """
        start_time = datetime.now()
        
        try:
            # Check if already processed
            if not force_reingest and episode.episode_name in self._processed_episodes:
                return {
                    "status": IngestionStatus.SUCCESS,
                    "message": f"Episode {episode.episode_name} already processed",
                    "processing_time": (datetime.now() - start_time).total_seconds()
                }
            
            # Process through GraphitiClient
            result = await self.graphiti_client.add_episode(episode)
            
            # Track if successful
            if result.get("status") == IngestionStatus.SUCCESS:
                self._processed_episodes.add(episode.episode_name)
            
            result["processing_time"] = (datetime.now() - start_time).total_seconds()
            return result
            
        except Exception as e:
            error_msg = f"Failed to process episode {episode.episode_name}: {str(e)}"
            logger.error(error_msg)
            return {
                "status": IngestionStatus.FAILED,
                "episode_name": episode.episode_name,
                "error": error_msg,
                "processing_time": (datetime.now() - start_time).total_seconds()
            }

    def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics.
        
        Returns:
            Dict containing processing stats
        """
        return {
            "total_processed_episodes": len(self._processed_episodes),
            "processed_episode_names": list(self._processed_episodes),
            "timestamp": datetime.now().isoformat()
        }

    def clear_processing_history(self) -> None:
        """Clear the history of processed episodes."""
        self._processed_episodes.clear()
        logger.info("Processing history cleared")


# Convenience function for creating IngestionService
def create_ingestion_service(settings: Settings, graphiti_client: GraphitiClient) -> IngestionService:
    """Create and return an IngestionService instance.
    
    Args:
        settings: Application settings
        graphiti_client: Initialized GraphitiClient
        
    Returns:
        Configured IngestionService instance
    """
    return IngestionService(settings, graphiti_client)
