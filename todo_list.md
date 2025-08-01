Complete TODO List: PD Graphiti Service Development
Phase 1: Project Foundation & Configuration (Day 1)
1.1 Environment Configuration

 Create .env.example with all required environment variables:
OPENAI_API_KEY=your_openai_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GRAPHITI_GROUP_ID=pd_target_discovery
EXPORT_DIRECTORY=../pd-target-identification/exports
LOG_LEVEL=INFO

 Create config.py using pydantic Settings to load environment variables with validation
 Create .gitignore (include .env, __pycache__, .pytest_cache, *.pyc, etc.)
 Test: Environment variables load correctly and config validation works

1.2 Basic Models & Types

 Create base models in models/:

EpisodeMetadata (gene_symbol, episode_type, export_timestamp, etc.)
GraphitiEpisode (episode_body, source, source_description, group_id)
IngestionStatus enum (PENDING, PROCESSING, SUCCESS, FAILED)


 Create request models in models/requests/:

IngestDirectoryRequest (directory_path, validate_files)
HealthCheckRequest (optional ping data)


 Create response models in models/responses/:

IngestionResponse (status, message, episodes_processed, errors)
HealthResponse (status, neo4j_connected, graphiti_ready)
StatusResponse (current_operation, progress, last_ingestion)


 Test: All models serialize/deserialize correctly with pydantic

Phase 2: Core Services Development (Day 2-3)
2.1 Graphiti Client Service

 Create graphiti_client.py with GraphitiClient class:

__init__(): Initialize graphiti-core with Neo4j connection and OpenAI
initialize_database(): Set up Graphiti indices (call once)
add_episode(episode_data): Wrapper around graphiti.add_memory()
test_connection(): Verify Neo4j and OpenAI connectivity
get_graph_stats(): Return node/edge counts for monitoring


 Expected behaviors:

Handle graphiti-core async properly in dedicated event loop
Retry failed connections with exponential backoff
Validate episode format before sending to Graphiti
Return detailed error messages for troubleshooting


 Test: Mock graphiti-core and verify all methods work correctly

2.2 File Processing Service

 Create ingestion_service.py with IngestionService class:

load_export_directory(path): Read manifest.json and validate structure
validate_episode_files(): Check checksums and file integrity
parse_episode_file(filepath): Load and validate individual episode JSON
process_episodes_in_order(): Ingest episodes following recommended sequence
handle_ingestion_error(): Log errors, quarantine bad files, continue processing


 Expected behaviors:

Process episodes in exact order: gene_profile → gwas → eqtl → literature → pathway → integration
Track progress (X of Y episodes processed)
Handle individual episode failures without stopping batch
Generate detailed ingestion report with statistics


 Test: Create mock export directory with sample episodes and verify processing

2.3 File Monitoring Service

 Create file_monitor.py with FileMonitor class using watchdog:

start_monitoring(directory): Watch for new export directories
on_new_export_detected(): Trigger ingestion when manifest.json appears
stop_monitoring(): Clean shutdown of file watchers


 Expected behaviors:

Detect new exports within 5 seconds of creation
Ignore incomplete exports (no manifest.json)
Prevent duplicate processing of same export
Log all file system events for debugging


 Test: Create export directory and verify detection triggers correctly

Phase 3: API Layer Development (Day 3-4)
3.1 Health Check Endpoints

 Create api/health.py with health check routes:

GET /health: Basic service health (always returns 200 if running)
GET /health/deep: Test Neo4j connection, OpenAI API, Graphiti initialization
GET /ready: Readiness probe for Kubernetes deployment


 Expected behaviors:

/health responds in <100ms
/health/deep verifies all external dependencies
Return detailed error messages when dependencies fail


 Test: Mock external services and verify health checks work correctly

3.2 Ingestion Endpoints

 Create api/endpoints.py with main API routes:

POST /ingest/directory: Trigger ingestion of specific export directory
GET /status: Current ingestion status and progress
GET /stats: Knowledge graph statistics (nodes, edges, last update)
POST /ingest/episode: Single episode ingestion (for testing)


 Expected behaviors:

/ingest/directory validates path exists and starts background ingestion
/status returns real-time progress during ingestion
All endpoints return proper HTTP status codes
Handle concurrent requests gracefully


 Test: Use httpx to test all endpoints with various input scenarios

3.3 FastAPI Application Setup

 Create main.py with FastAPI app:

Configure CORS, logging, exception handlers
Include health and ingestion routers
Add startup/shutdown events for service initialization
Background task management for long-running ingestions


 Expected behaviors:

App starts in <10 seconds
Graceful shutdown (finish current ingestion before stopping)
Proper error handling and logging for all requests
OpenAPI documentation available at /docs


 Test: Start application and verify all routes accessible

Phase 4: Integration & Testing (Day 4-5)
4.1 Integration with Real Graphiti

 Set up Neo4j database (Docker or Neo4j Desktop)
 Configure OpenAI API with valid key
 Test real graphiti-core integration:

Initialize Graphiti database successfully
Ingest one sample episode from your export
Query the knowledge graph to verify episode was processed
Test error scenarios (invalid episode format, connection failures)


 Expected behaviors:

Episodes create proper nodes and relationships in Neo4j
Knowledge graph queries return expected results
Error handling works with real Graphiti limitations


 Test: End-to-end ingestion of sample episodes with verification

4.2 Integration with Dagster Export

 Test with real export directory from your Dagster pipeline:

Copy latest export from pd-target-identification/exports/
Run ingestion service against real 81-episode export
Verify all episode types process correctly
Check knowledge graph contains all 14 genes


 Expected behaviors:

Process all 81 episodes without errors
Maintain proper ingestion order
Generate complete ingestion report
Knowledge graph queryable with gene information


 Test: Full pipeline from Dagster export → Service ingestion → Neo4j verification

4.3 Comprehensive Testing Suite

 Unit tests for all services:

Test GraphitiClient with mocked graphiti-core
Test IngestionService with sample episode files
Test FileMonitor with temporary directories


 API tests with httpx:

Test all endpoints with valid/invalid inputs
Test concurrent requests and rate limiting
Test error handling and status codes


 Integration tests:

End-to-end ingestion workflow
File monitoring with real directory changes
Database integration with test Neo4j instance


 Test: Achieve >90% code coverage and all tests pass

Phase 5: Production Readiness (Day 5-6)
5.1 Docker Configuration

 Create docker/Dockerfile:

Multi-stage build with Python 3.12
Install dependencies and copy source code
Configure proper user permissions and security
Health check command for container orchestration


 Create docker/docker-compose.yml:

Service container with volume mounts for exports
Neo4j container with persistent storage
Network configuration for service communication
Environment variable configuration


 Test: Build and run entire stack with Docker Compose

5.2 Operational Features

 Add logging configuration:

Structured JSON logging for production
Log levels configurable via environment
Request/response logging for debugging
Error tracking with stack traces


 Add monitoring endpoints:

Prometheus metrics for ingestion rates and errors
Memory and CPU usage statistics
Knowledge graph growth metrics


 Add configuration validation:

Validate all required environment variables on startup
Test external connections during initialization
Fail fast with clear error messages


 Test: Deploy with monitoring and verify metrics collection

5.3 Documentation & Deployment

 Create comprehensive README.md:

Installation and setup instructions
API documentation with examples
Configuration options and environment variables
Troubleshooting guide


 Create deployment guide:

Docker deployment instructions
Kubernetes manifests (optional)
Production configuration recommendations
Backup and recovery procedures


 Test: Follow documentation to deploy fresh instance

Phase 6: End-to-End Validation (Day 6)
6.1 Complete Pipeline Test

 Run full Dagster pipeline to generate fresh export
 Deploy Graphiti service with monitoring
 Trigger ingestion via API call from Dagster
 Verify knowledge graph contains all expected data
 Test research queries:

Search for SNCA gene profile
Find genes with strong GWAS evidence
Query multi-evidence integration data


 Test operational scenarios:

Service restart during ingestion
Neo4j connection failure and recovery
Invalid episode format handling



6.2 Performance & Reliability Testing

 Load testing:

Process multiple export directories simultaneously
Test with larger episode sets (if available)
Measure ingestion throughput and memory usage


 Reliability testing:

Network interruption scenarios
Disk space exhaustion handling
Memory pressure testing


 Monitoring validation:

Verify all metrics are collected correctly
Test alerting on ingestion failures
Validate log aggregation and searching



Success Criteria
✅ Service Running Successfully When:

FastAPI service starts and responds to health checks
Can ingest all 81 episodes from Dagster export without errors
Knowledge graph contains queryable data for all 14 genes
File monitoring detects new exports automatically
API endpoints respond correctly to Dagster integration calls
Docker deployment works with proper monitoring
Full documentation allows independent deployment

✅ Integration Complete When:

Dagster can trigger ingestion via API call
Service processes episodes in proper order with progress tracking
Knowledge graph supports research queries like "Why is SNCA ranked #1?"
Operational monitoring shows ingestion success rates and performance
Error handling provides actionable debugging information

This roadmap takes you from zero to a production-ready microservice that seamlessly integrates with your excellent Dagster pipeline while handling all the Graphiti complexity in its dedicated environment.