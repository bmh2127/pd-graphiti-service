"""
Performance and operational testing for PD Graphiti Service.

This module contains tests for Phase 6.2:
- Load testing for ingestion pipeline performance
- Reliability testing for network failures and resource exhaustion  
- Monitoring validation for metrics and alerting systems

These tests are designed to run separately from regular unit/integration tests
as they may be long-running, resource-intensive, or require special setup.

Usage:
    # Run all performance tests
    pytest tests/performance/ -v
    
    # Run only load tests  
    pytest -m load -v
    
    # Run reliability tests
    pytest -m reliability -v
    
    # Run monitoring tests
    pytest -m monitoring -v
    
    # Skip slow/long-running tests
    pytest -m "not slow" -v
"""