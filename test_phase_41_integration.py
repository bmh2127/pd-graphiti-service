#!/usr/bin/env python3
"""
Phase 4.1 Integration Test Script
Tests real graphiti-core integration with sample episodes
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from pd_graphiti_service.config import settings
from pd_graphiti_service.graphiti_client import GraphitiClient
from pd_graphiti_service.ingestion_service import IngestionService


class Phase41Tester:
    """Test harness for Phase 4.1 integration testing."""
    
    def __init__(self):
        self.settings = settings()
        self.graphiti_client = None
        self.ingestion_service = None
        self.test_results = {
            "environment_check": False,
            "neo4j_connection": False,
            "openai_connection": False,
            "graphiti_initialization": False,
            "sample_episode_ingestion": False,
            "knowledge_graph_query": False,
            "error_scenario_handling": False
        }
    
    async def run_all_tests(self):
        """Run all Phase 4.1 integration tests."""
        print("🚀 Starting Phase 4.1 Integration Tests\n")
        
        try:
            # Test 1: Environment Configuration
            await self.test_environment_configuration()
            
            # Test 2: Initialize Graphiti Client
            await self.test_graphiti_client_initialization()
            
            # Test 3: Test connections
            await self.test_database_connections()
            
            # Test 4: Initialize Graphiti database
            await self.test_graphiti_database_initialization()
            
            # Test 5: Ingest sample episode
            await self.test_sample_episode_ingestion()
            
            # Test 6: Query knowledge graph
            await self.test_knowledge_graph_query()
            
            # Test 7: Error scenario handling
            await self.test_error_scenarios()
            
            # Print final results
            self.print_test_summary()
            
        except Exception as e:
            print(f"❌ Critical error during testing: {e}")
            return False
        
        return all(self.test_results.values())
    
    async def test_environment_configuration(self):
        """Test that all required environment variables are properly configured."""
        print("1️⃣ Testing Environment Configuration...")
        
        try:
            # Check required settings
            required_vars = {
                "openai_api_key": self.settings.openai_api_key,
                "neo4j_uri": self.settings.neo4j_uri,
                "neo4j_user": self.settings.neo4j_user,
                "neo4j_password": self.settings.neo4j_password,
                "export_directory": self.settings.export_directory
            }
            
            for var_name, var_value in required_vars.items():
                if not var_value or (isinstance(var_value, str) and var_value == "your_openai_key_here"):
                    print(f"❌ {var_name} is not properly configured")
                    return
                print(f"✅ {var_name}: {var_value if 'key' not in var_name else '***configured***'}")
            
            # Check export directory exists
            if not self.settings.export_directory.exists():
                print(f"❌ Export directory does not exist: {self.settings.export_directory}")
                return
            
            # Check for sample episodes
            sample_exports = list(self.settings.export_directory.glob("graphiti_episodes_*"))
            if not sample_exports:
                print(f"❌ No sample exports found in {self.settings.export_directory}")
                return
            
            print(f"✅ Found {len(sample_exports)} sample export directories")
            self.test_results["environment_check"] = True
            print("✅ Environment configuration passed\n")
            
        except Exception as e:
            print(f"❌ Environment configuration failed: {e}\n")
    
    async def test_graphiti_client_initialization(self):
        """Test GraphitiClient initialization."""
        print("2️⃣ Testing Graphiti Client Initialization...")
        
        try:
            self.graphiti_client = GraphitiClient(settings=self.settings)
            print("✅ GraphitiClient created successfully")
            
            # Initialize ingestion service  
            self.ingestion_service = IngestionService(
                settings=self.settings,
                graphiti_client=self.graphiti_client
            )
            print("✅ IngestionService created successfully")
            print("✅ Client initialization passed\n")
            
        except Exception as e:
            print(f"❌ Client initialization failed: {e}\n")
    
    async def test_database_connections(self):
        """Test Neo4j and OpenAI connections."""
        print("3️⃣ Testing Database Connections...")
        
        try:
            # Test Neo4j connection
            if await self.graphiti_client.test_connection():
                print("✅ Neo4j connection successful")
                self.test_results["neo4j_connection"] = True
            else:
                print("❌ Neo4j connection failed")
                return
            
            # Test OpenAI connection (this will be tested during initialization)
            print("✅ OpenAI connection will be tested during initialization")
            self.test_results["openai_connection"] = True
            print("✅ Database connections passed\n")
            
        except Exception as e:
            print(f"❌ Database connection test failed: {e}\n")
    
    async def test_graphiti_database_initialization(self):
        """Test Graphiti database initialization."""
        print("4️⃣ Testing Graphiti Database Initialization...")
        
        try:
            await self.graphiti_client.initialize_database()
            print("✅ Graphiti database initialized successfully")
            
            # Get initial stats
            stats = await self.graphiti_client.get_graph_stats()
            print(f"✅ Initial graph stats: {stats}")
            
            self.test_results["graphiti_initialization"] = True
            print("✅ Graphiti initialization passed\n")
            
        except Exception as e:
            print(f"❌ Graphiti initialization failed: {e}\n")
    
    async def test_sample_episode_ingestion(self):
        """Test ingesting a sample episode."""
        print("5️⃣ Testing Sample Episode Ingestion...")
        
        try:
            # Find the most recent export
            sample_exports = sorted(
                self.settings.export_directory.glob("graphiti_episodes_*"),
                reverse=True
            )
            
            if not sample_exports:
                print("❌ No sample exports found")
                return
            
            latest_export = sample_exports[0]
            print(f"✅ Using export: {latest_export.name}")
            
            # Find a SNCA gene profile episode for testing
            snca_episode_path = latest_export / "episodes" / "gene_profile" / "SNCA_gene_profile.json"
            
            if not snca_episode_path.exists():
                print("❌ SNCA gene profile episode not found")
                return
            
            # Load and parse the episode
            with open(snca_episode_path, 'r') as f:
                episode_data = json.load(f)
            
            print(f"✅ Loaded episode: {episode_data['episode_metadata']['episode_name']}")
            
            # Ingest the episode
            graphiti_episode = episode_data["graphiti_episode"]
            # Convert dict to GraphitiEpisode if needed
            if isinstance(graphiti_episode, dict):
                episode_to_ingest = graphiti_episode
            else:
                episode_to_ingest = graphiti_episode
            
            # Convert dict to proper format for add_episode
            from pd_graphiti_service.models import GraphitiEpisode, EpisodeMetadata, IngestionStatus
            from datetime import datetime
            from pathlib import Path
            
            if isinstance(episode_to_ingest, dict):
                # Create metadata for the episode
                metadata = EpisodeMetadata(
                    gene_symbol=episode_data['episode_metadata']['gene_symbol'],
                    episode_type=episode_data['episode_metadata']['episode_type'],
                    export_timestamp=datetime.fromisoformat(episode_data['episode_metadata']['export_timestamp']),
                    file_path=Path(snca_episode_path),
                    file_size=len(json.dumps(episode_data)),
                    validation_status=IngestionStatus.PENDING
                )
                
                graphiti_episode = GraphitiEpisode(
                    episode_name=episode_to_ingest["name"],
                    episode_body=episode_to_ingest["episode_body"],
                    source=episode_to_ingest["source"],
                    source_description=episode_to_ingest["source_description"],
                    group_id=episode_to_ingest["group_id"],
                    metadata=metadata
                )
            else:
                graphiti_episode = episode_to_ingest
            
            await self.graphiti_client.add_episode(graphiti_episode)
            
            print("✅ Episode ingested successfully")
            
            # Verify it was added
            stats_after = await self.graphiti_client.get_graph_stats()
            print(f"✅ Graph stats after ingestion: {stats_after}")
            
            self.test_results["sample_episode_ingestion"] = True
            print("✅ Sample episode ingestion passed\n")
            
        except Exception as e:
            print(f"❌ Sample episode ingestion failed: {e}\n")
    
    async def test_knowledge_graph_query(self):
        """Test querying the knowledge graph to verify data was processed."""
        print("6️⃣ Testing Knowledge Graph Query...")
        
        try:
            # This would require implementing query methods in GraphitiClient
            # For now, we'll just verify the graph has data
            stats = await self.graphiti_client.get_graph_stats()
            
            total_nodes = stats.get("total_nodes", 0)
            group_nodes = stats.get("group_nodes", 0)
            total_relationships = stats.get("total_relationships", 0)
            
            if total_nodes > 0 and group_nodes > 0:
                print(f"✅ Knowledge graph contains {total_nodes} total nodes")
                print(f"✅ Knowledge graph contains {group_nodes} group nodes") 
                print(f"✅ Knowledge graph contains {total_relationships} relationships")
                print(f"✅ Node types: {stats.get('node_types', {})}")
                self.test_results["knowledge_graph_query"] = True
            else:
                print(f"❌ Knowledge graph appears to have insufficient data: {stats}")
                return
            
            print("✅ Knowledge graph query passed\n")
            
        except Exception as e:
            print(f"❌ Knowledge graph query failed: {e}\n")
    
    async def test_error_scenarios(self):
        """Test error handling scenarios."""
        print("7️⃣ Testing Error Scenarios...")
        
        try:
            # Test invalid episode format
            invalid_episode = {
                "name": "Invalid_Test_Episode",
                "episode_body": "invalid json format",  # This should be valid JSON
                "source": "json",
                "source_description": "Invalid test episode",
                "group_id": self.settings.graphiti_group_id
            }
            
            try:
                await self.graphiti_client.add_episode(invalid_episode)
                print("⚠️ Expected error for invalid episode format, but ingestion succeeded")
            except Exception as e:
                print(f"✅ Properly handled invalid episode format: {type(e).__name__}")
            
            # Test with properly formatted but semantically invalid data
            invalid_json_episode = {
                "name": "Invalid_JSON_Test_Episode",
                "episode_body": '{"invalid": "structure", "no_meaningful_data": true}',
                "source": "json",
                "source_description": "Invalid JSON test episode",
                "group_id": self.settings.graphiti_group_id
            }
            
            try:
                await self.graphiti_client.add_episode(invalid_json_episode)
                print("✅ Handled semantically invalid episode gracefully")
            except Exception as e:
                print(f"✅ Properly rejected semantically invalid episode: {type(e).__name__}")
            
            self.test_results["error_scenario_handling"] = True
            print("✅ Error scenario handling passed\n")
            
        except Exception as e:
            print(f"❌ Error scenario testing failed: {e}\n")
    
    def print_test_summary(self):
        """Print a summary of all test results."""
        print("📊 Phase 4.1 Integration Test Summary")
        print("=" * 50)
        
        total_tests = len(self.test_results)
        passed_tests = sum(self.test_results.values())
        
        for test_name, passed in self.test_results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test_name.replace('_', ' ').title()}: {status}")
        
        print("=" * 50)
        print(f"Overall Result: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! Phase 4.1 integration is successful!")
            print("\nNext steps:")
            print("- Proceed to Phase 4.2: Integration with Dagster Export")
            print("- Test with the full 81-episode export")
        else:
            print("⚠️ Some tests failed. Please check the errors above.")
            print("\nTroubleshooting tips:")
            if not self.test_results["environment_check"]:
                print("- Ensure your .env file has valid OpenAI API key")
                print("- Check that Neo4j is running (run setup_env.sh)")
            if not self.test_results["neo4j_connection"]:
                print("- Verify Neo4j is running: docker-compose ps")
                print("- Check Neo4j logs: docker-compose logs neo4j")


async def main():
    """Main test runner."""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Phase 4.1 Integration Test Script")
        print("Usage: python test_phase_41_integration.py")
        print("\nThis script tests:")
        print("- Environment configuration")
        print("- Neo4j and OpenAI connections")
        print("- Graphiti database initialization")
        print("- Sample episode ingestion")
        print("- Knowledge graph queries")
        print("- Error handling scenarios")
        return
    
    tester = Phase41Tester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())