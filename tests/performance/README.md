# Phase 6.2 Performance & Reliability Testing Suite

This directory contains comprehensive tests for Phase 6.2 of the PD Graphiti Service development, focusing on load testing, reliability testing, and monitoring validation.

## Test Categories

### 🚀 Load Testing (`test_load_testing.py`)
Tests ingestion pipeline performance and scalability:
- **Single Episode Performance**: Baseline performance metrics
- **Batch Ingestion Performance**: Throughput testing with multiple episodes 
- **Directory Ingestion Performance**: Full export directory processing
- **Concurrent Request Performance**: Multi-threaded load testing
- **Resource Usage Patterns**: Memory and CPU consumption analysis
- **Scalability Limits**: Maximum episode size and stress testing

### 🛡️ Reliability Testing (`test_reliability_testing.py`)
Tests service resilience under failure conditions:
- **Network Resilience**: Connection failures and timeouts
- **Resource Exhaustion**: Memory pressure and CPU load handling
- **Service Resilience**: Graceful shutdown and error recovery
- **Failure Injection**: Simulated network and system failures

### 📊 Monitoring Validation (`test_monitoring_validation.py`)
Tests observability and monitoring systems:
- **Metrics Collection**: Prometheus metrics and custom endpoints
- **Logging Validation**: Structured logging and error tracking
- **Alerting Mechanisms**: Error rate and resource monitoring
- **Observability Features**: Request tracing and debug information

## Prerequisites

### Required Services
- **Neo4j Database**: Running on port 7688 (test port)
- **OpenAI API Key**: Set in environment (can be mock for some tests)

### Python Dependencies
```bash
cd pd-graphiti-service
pip install -e .[dev]
# or with uv
uv sync --dev
```

### Docker Services (Recommended)
```bash
cd pd-graphiti-service/docker
docker-compose up -d neo4j  # Start only Neo4j for testing
```

## Running Tests

### Quick Start - All Performance Tests
```bash
# Run all Phase 6.2 tests
pytest tests/performance/ -v

# Run with detailed output
pytest tests/performance/ -v -s
```

### Selective Test Execution

#### By Test Category
```bash
# Load testing only
pytest -m load -v

# Reliability testing only  
pytest -m reliability -v

# Monitoring validation only
pytest -m monitoring -v
```

#### By Performance Impact
```bash
# Fast tests only (exclude slow/long-running)
pytest tests/performance/ -m "not slow" -v

# Slow tests only (long-running performance tests)
pytest -m slow -v
```

#### By Infrastructure Requirements
```bash
# Tests requiring real Neo4j connection
pytest -m requires_neo4j -v

# Tests requiring OpenAI API access
pytest -m requires_openai -v

# Tests that can run with mocked services
pytest -m "not requires_neo4j and not requires_openai" -v
```

### Individual Test Files
```bash
# Load testing only
pytest tests/performance/test_load_testing.py -v

# Reliability testing only
pytest tests/performance/test_reliability_testing.py -v

# Monitoring validation only
pytest tests/performance/test_monitoring_validation.py -v
```

### Specific Test Classes or Methods
```bash
# Test specific performance aspects
pytest tests/performance/test_load_testing.py::TestIngestionPerformance -v

# Test specific reliability scenarios
pytest tests/performance/test_reliability_testing.py::TestNetworkResilience -v

# Test specific monitoring features
pytest tests/performance/test_monitoring_validation.py::TestMetricsCollection -v
```

## Test Configuration

### Environment Variables
```bash
# Test database (different from production)
export NEO4J_URI="bolt://localhost:7688"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="testpassword123"

# OpenAI API (use test key or mock)
export OPENAI_API_KEY="your-test-api-key"

# Test-specific settings
export GRAPHITI_GROUP_ID="performance_test_group"
export LOG_LEVEL="INFO"
```

### Custom Test Settings
Performance tests use a separate configuration to avoid conflicts:
- **Neo4j**: Port 7688 (instead of 7687)
- **Service**: Port 8004 (instead of 8000)
- **Metrics**: Port 8005 (instead of 8001)
- **Group ID**: `performance_test_group`

## Test Output and Analysis

### Performance Metrics
Tests output detailed performance metrics:
```
Single episode performance: 2.34s, memory delta: 12.5MB
Batch performance: 20 episodes in 45.67s
Throughput: 0.44 episodes/sec
Memory delta: 156.2MB
```

### Resource Usage Analysis
```
Memory usage: Baseline=245.1MB, Peak=412.3MB, Final=267.8MB
Memory growth: 22.7MB
CPU usage: Average=45.2%, Peak=78.9%
```

### Reliability Test Results
```
Concurrent failure test: 7 successful, 3 failed
Request completed in 3.45s under CPU load
Stress test results:
  Success rate: 84%
  Average duration: 2.12s
```

## Performance Benchmarks

### Expected Performance Thresholds

#### Single Episode Ingestion
- **Duration**: < 5.0 seconds
- **Memory Increase**: < 50MB
- **Success Rate**: > 95%

#### Batch Ingestion (20 episodes)
- **Throughput**: > 2.0 episodes/second
- **Memory Increase**: < 200MB
- **Success Rate**: > 90%

#### Directory Ingestion (100 episodes)
- **Throughput**: > 1.0 episodes/second
- **Memory Increase**: < 500MB
- **Processing Time**: < 120 seconds

#### Concurrent Load (10 requests)
- **Average Duration**: < 10.0 seconds
- **Throughput**: > 0.5 requests/second
- **Success Rate**: > 80%

### Resource Limits

#### Memory
- **Peak Usage**: < 2GB above baseline
- **Memory Growth**: < 100MB per 100 episodes
- **Memory Leaks**: < 50MB residual growth

#### CPU
- **Average Load**: < 80%
- **Peak Load**: < 95%
- **Response Under Load**: < 25 seconds

## Troubleshooting

### Common Issues

#### Neo4j Connection Failures
```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check port availability
netstat -an | grep 7688

# Start test Neo4j instance
cd pd-graphiti-service/docker
docker-compose up -d neo4j
```

#### OpenAI API Errors
```bash
# Use mock responses for most tests
export OPENAI_API_KEY="mock-key-for-testing"

# Or skip tests requiring real API
pytest -m "not requires_openai" -v
```

#### Memory/Resource Issues
```bash
# Run lighter test suite
pytest tests/performance/ -m "not slow" -v

# Reduce batch sizes in tests
# Edit conftest.py to reduce large_episode_batch size
```

#### Test Timeouts
```bash
# Increase timeouts for slow systems
pytest tests/performance/ --timeout=300 -v

# Run individual test categories
pytest -m load -v  # Then run others separately
```

### Test Environment Cleanup
```bash
# Clean up test data
docker-compose down -v  # Removes volumes too

# Reset test database
docker exec pd-neo4j cypher-shell -u neo4j -p testpassword123 "MATCH (n) DETACH DELETE n"
```

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Phase 6.2 Performance Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: docker-compose up -d
        working-directory: ./docker
      - name: Run performance tests
        run: |
          pytest tests/performance/ -m "not slow" --junitxml=performance-results.xml
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: performance-test-results
          path: performance-results.xml
```

### Load Testing Schedule
- **Daily**: Fast performance tests (`-m "not slow"`)
- **Weekly**: Full performance suite including slow tests
- **Pre-release**: Complete reliability and monitoring validation
- **On-demand**: Stress testing and scalability analysis

## Contributing

When adding new performance tests:

1. **Use appropriate markers**: `@pytest.mark.load`, `@pytest.mark.reliability`, `@pytest.mark.monitoring`
2. **Add performance assertions**: Include specific thresholds and expectations
3. **Document resource requirements**: Specify if tests need real services vs mocks
4. **Include cleanup**: Ensure tests don't leave residual state
5. **Add to CI**: Include new tests in appropriate test categories

### Test Naming Convention
- `test_load_*`: Load and performance testing
- `test_reliability_*`: Failure injection and resilience
- `test_monitoring_*`: Observability and metrics validation

---

## Results Analysis

After running Phase 6.2 tests, analyze results to:

1. **Identify Performance Bottlenecks**: Look for slow operations and high resource usage
2. **Validate Reliability**: Ensure graceful failure handling and recovery
3. **Verify Monitoring**: Confirm metrics collection and alerting work correctly
4. **Document Findings**: Update performance benchmarks and operational runbooks

This comprehensive testing suite ensures your PD Graphiti Service is production-ready with verified performance characteristics, reliable operation under stress, and complete observability for operational monitoring.