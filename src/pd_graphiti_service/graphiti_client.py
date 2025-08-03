"""Graphiti client for knowledge graph operations."""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

import openai
from graphiti_core import Graphiti
from graphiti_core.llm_client import LLMConfig, OpenAIClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import Settings
from .models import GraphitiEpisode, IngestionStatus

logger = logging.getLogger(__name__)


class GraphitiConnectionError(Exception):
    """Raised when Graphiti connection fails."""
    pass


class GraphitiValidationError(Exception):
    """Raised when episode validation fails."""
    pass


class GraphitiClient:
    """Client for interacting with Graphiti knowledge graph."""
    
    def __init__(self, settings: Settings):
        """Initialize GraphitiClient with settings.
        
        Args:
            settings: Application settings containing Neo4j and OpenAI credentials
        """
        self.settings = settings
        self._graphiti: Optional[Graphiti] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._database_initialized = False
        
        # Configure OpenAI client
        openai.api_key = settings.openai_api_key
        
        logger.info(f"GraphitiClient initialized with group_id: {settings.graphiti_group_id}")

    async def _get_graphiti(self) -> Graphiti:
        """Get or create Graphiti instance with configured LLM models."""
        if self._graphiti is None:
            # Configure LLM client with specified models
            llm_config = LLMConfig(
                model=self.settings.openai_model,
                small_model=self.settings.openai_small_model
            )
            
            llm_client = OpenAIClient(config=llm_config)
            
            self._graphiti = Graphiti(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
                llm_client=llm_client
            )
            logger.info(f"Created Graphiti instance with models: {self.settings.openai_model} (main), {self.settings.openai_small_model} (small)")
        return self._graphiti

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((GraphitiConnectionError, ConnectionError))
    )
    async def initialize_database(self) -> Dict[str, Any]:
        """Initialize Graphiti database indices and schema.
        
        Returns:
            Dict containing initialization status and details
            
        Raises:
            GraphitiConnectionError: If database initialization fails
        """
        try:
            graphiti = await self._get_graphiti()
            
            # Initialize database indices
            await graphiti.build_indices_and_constraints()
            
            self._database_initialized = True
            
            result = {
                "status": "success",
                "message": "Graphiti database initialized successfully",
                "timestamp": datetime.now().isoformat(),
                "neo4j_uri": self.settings.neo4j_uri,
                "group_id": self.settings.graphiti_group_id
            }
            
            logger.info("Graphiti database initialized successfully")
            return result
            
        except Exception as e:
            error_msg = f"Failed to initialize Graphiti database: {str(e)}"
            logger.error(error_msg)
            raise GraphitiConnectionError(error_msg) from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((GraphitiConnectionError, ConnectionError))
    )
    async def test_connection(self) -> Dict[str, Any]:
        """Test connections to Neo4j and OpenAI.
        
        Returns:
            Dict containing connection test results
        """
        result = {
            "neo4j_connected": False,
            "openai_accessible": False,
            "graphiti_ready": False,
            "errors": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Test Neo4j connection
        try:
            graphiti = await self._get_graphiti()
            
            # Test basic Neo4j connectivity with a simple query
            driver = graphiti.driver
            async with driver.session() as session:
                await session.run("RETURN 1 as test")
            
            result["neo4j_connected"] = True
            logger.info("Neo4j connection test successful")
            
        except Exception as e:
            error_msg = f"Neo4j connection failed: {str(e)}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        
        # Test OpenAI API accessibility
        try:
            # Simple test call to OpenAI
            client = openai.OpenAI(api_key=self.settings.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
            
            result["openai_accessible"] = True
            logger.info("OpenAI API test successful")
            
        except Exception as e:
            error_msg = f"OpenAI API connection failed: {str(e)}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        
        # Overall Graphiti readiness
        result["graphiti_ready"] = (
            result["neo4j_connected"] and 
            result["openai_accessible"] and 
            self._database_initialized
        )
        
        return result

    def _validate_episode(self, episode: GraphitiEpisode) -> None:
        """Validate episode data before sending to Graphiti.
        
        Args:
            episode: Episode to validate
            
        Raises:
            GraphitiValidationError: If episode validation fails
        """
        errors = []
        
        # Check required fields
        if not episode.episode_name:
            errors.append("episode_name is required")
        
        if not episode.episode_body:
            errors.append("episode_body is required")
            
        if not episode.source:
            errors.append("source is required")
            
        # Check episode body is not too large (Graphiti limit)
        if len(episode.episode_body) > 100000:  # 100KB limit
            errors.append(f"episode_body too large: {len(episode.episode_body)} chars (max 100,000)")
        
        # Check episode name format
        if not episode.episode_name.replace("_", "").replace("-", "").isalnum():
            errors.append("episode_name should contain only alphanumeric characters, hyphens, and underscores")
        
        if errors:
            raise GraphitiValidationError(f"Episode validation failed: {'; '.join(errors)}")

    async def add_episode(self, episode: GraphitiEpisode) -> Dict[str, Any]:
        """Add a single episode to the knowledge graph.
        
        Args:
            episode: Complete episode data to ingest
            
        Returns:
            Dict containing ingestion result details
            
        Raises:
            GraphitiValidationError: If episode validation fails
            GraphitiConnectionError: If ingestion fails
        """
        start_time = time.time()
        
        try:
            # Validate episode before ingestion
            self._validate_episode(episode)
            
            # Get Graphiti instance
            graphiti = await self._get_graphiti()
            
            # Add episode to knowledge graph
            from datetime import datetime
            from graphiti_core.nodes import EpisodeType
            
            # Convert string source to EpisodeType enum
            if isinstance(episode.source, str):
                if episode.source == "json":
                    source_type = EpisodeType.json
                elif episode.source == "text":
                    source_type = EpisodeType.text
                else:
                    source_type = EpisodeType.message
            else:
                source_type = episode.source
            
            # Prepare episode body with concise instructions for complex content
            processed_body = self._prepare_episode_body(episode.episode_body)
            
            # Add episode with extended timeout (300s for complex episodes)
            result = await asyncio.wait_for(
                graphiti.add_episode(
                    name=episode.episode_name,
                    episode_body=processed_body,
                    source_description=episode.source_description,
                    reference_time=datetime.now(),
                    source=source_type,
                    group_id=episode.group_id or self.settings.graphiti_group_id
                ),
                timeout=300  # 5 minutes for complex episodes (was 180s)
            )
            
            processing_time = time.time() - start_time
            
            response = {
                "status": IngestionStatus.SUCCESS,
                "episode_name": episode.episode_name,
                "processing_time_seconds": processing_time,
                "graphiti_node_id": getattr(result, 'node_id', None),
                "group_id": episode.group_id or self.settings.graphiti_group_id,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Successfully ingested episode: {episode.episode_name} in {processing_time:.2f}s")
            return response
            
        except GraphitiValidationError:
            # Re-raise validation errors
            raise
        
        except asyncio.TimeoutError:
            processing_time = time.time() - start_time
            error_msg = f"Episode {episode.episode_name} processing timeout after {processing_time:.1f}s"
            logger.error(error_msg)
            
            return {
                "status": IngestionStatus.FAILED,
                "episode_name": episode.episode_name,
                "processing_time_seconds": processing_time,
                "error_message": error_msg,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Failed to ingest episode {episode.episode_name}: {str(e)}"
            logger.error(error_msg)
            
            return {
                "status": IngestionStatus.FAILED,
                "episode_name": episode.episode_name,
                "processing_time_seconds": processing_time,
                "error_message": error_msg,
                "timestamp": datetime.now().isoformat()
            }

    def _prepare_episode_body(self, episode_body: str) -> str:
        """Prepare episode body with concise instructions for complex content."""
        import json
        
        # For very complex content or known problematic patterns, add concise instructions
        if (len(episode_body) > 3000 or 
            episode_body.count('"') > 50):  # Complex JSON or large content
            
            if episode_body.startswith("{"):
                try:
                    data = json.loads(episode_body)
                    # Add processing instruction for concise responses
                    instruction = "IMPORTANT: Generate a concise response under 1000 tokens. Focus on key entities and relationships only."
                    
                    if isinstance(data, dict):
                        data["processing_instruction"] = instruction
                    else:
                        data = {"processing_instruction": instruction, "original_data": data}
                    
                    return json.dumps(data)
                except:
                    # If not valid JSON, just prepend instruction
                    return f"CONCISE RESPONSE REQUIRED (under 1000 tokens): {episode_body}"
            else:
                return f"CONCISE RESPONSE REQUIRED (under 1000 tokens): {episode_body}"
        
        return episode_body

    async def add_episodes_batch(self, episodes: List[GraphitiEpisode]) -> Dict[str, Any]:
        """Add multiple episodes to the knowledge graph in recommended order.
        
        Args:
            episodes: List of episodes to ingest
            
        Returns:
            Dict containing batch ingestion results
        """
        start_time = time.time()
        results = []
        successful = 0
        failed = 0
        
        # Sort episodes by recommended ingestion order
        episode_order = [
            "gene_profile", "gwas_evidence", "eqtl_evidence", 
            "literature_evidence", "pathway_evidence", "integration"
        ]
        
        def get_episode_priority(episode: GraphitiEpisode) -> int:
            episode_type = episode.metadata.episode_type
            try:
                return episode_order.index(episode_type)
            except ValueError:
                return len(episode_order)  # Unknown types go last
        
        sorted_episodes = sorted(episodes, key=get_episode_priority)
        
        logger.info(f"Starting batch ingestion of {len(episodes)} episodes")
        
        # Process episodes sequentially to maintain order
        for episode in sorted_episodes:
            try:
                result = await self.add_episode(episode)
                results.append(result)
                
                if result["status"] == IngestionStatus.SUCCESS:
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
                error_result = {
                    "status": IngestionStatus.FAILED,
                    "episode_name": episode.episode_name,
                    "error_message": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                results.append(error_result)
                logger.error(f"Batch ingestion error for {episode.episode_name}: {str(e)}")
        
        total_time = time.time() - start_time
        
        return {
            "status": IngestionStatus.SUCCESS if failed == 0 else IngestionStatus.FAILED,
            "total_episodes": len(episodes),
            "successful": successful,
            "failed": failed,
            "total_processing_time_seconds": total_time,
            "episode_results": results,
            "timestamp": datetime.now().isoformat()
        }

    async def get_graph_stats(self) -> Dict[str, Any]:
        """Get knowledge graph statistics.
        
        Returns:
            Dict containing graph statistics
        """
        try:
            graphiti = await self._get_graphiti()
            
            # Get basic graph statistics
            driver = graphiti.driver
            stats = {}
            
            async with driver.session() as session:
                # Count total nodes
                result = await session.run("MATCH (n) RETURN count(n) as node_count")
                record = await result.single()
                stats["total_nodes"] = record["node_count"] if record else 0
                
                # Count total relationships
                result = await session.run("MATCH ()-[r]->() RETURN count(r) as rel_count")
                record = await result.single()
                stats["total_relationships"] = record["rel_count"] if record else 0
                
                # Count nodes by group_id
                result = await session.run(
                    "MATCH (n) WHERE n.group_id = $group_id RETURN count(n) as group_nodes",
                    group_id=self.settings.graphiti_group_id
                )
                record = await result.single()
                stats["group_nodes"] = record["group_nodes"] if record else 0
                
                # Get node type distribution
                result = await session.run(
                    "MATCH (n) WHERE n.group_id = $group_id "
                    "RETURN labels(n) as labels, count(n) as count",
                    group_id=self.settings.graphiti_group_id
                )
                
                node_types = {}
                async for record in result:
                    labels = record["labels"]
                    count = record["count"]
                    if labels:
                        # Use first label as primary type
                        node_type = labels[0]
                        node_types[node_type] = node_types.get(node_type, 0) + count
                
                stats["node_types"] = node_types
            
            stats["group_id"] = self.settings.graphiti_group_id
            stats["timestamp"] = datetime.now().isoformat()
            
            logger.info(f"Retrieved graph stats: {stats['total_nodes']} nodes, {stats['total_relationships']} relationships")
            return stats
            
        except Exception as e:
            error_msg = f"Failed to retrieve graph statistics: {str(e)}"
            logger.error(error_msg)
            raise GraphitiConnectionError(error_msg) from e

    async def close(self) -> None:
        """Close Graphiti client and cleanup resources."""
        if self._graphiti:
            await self._graphiti.close()
            self._graphiti = None
            logger.info("Graphiti client closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._loop and self._loop.is_running():
            # Schedule cleanup if loop is running
            self._loop.create_task(self.close())
        else:
            # Run cleanup in new loop if needed
            try:
                asyncio.run(self.close())
            except Exception as e:
                logger.warning(f"Error during cleanup: {e}")


# Convenience function for creating GraphitiClient
def create_graphiti_client(settings: Settings) -> GraphitiClient:
    """Create and return a GraphitiClient instance.
    
    Args:
        settings: Application settings
        
    Returns:
        Configured GraphitiClient instance
    """
    return GraphitiClient(settings)
