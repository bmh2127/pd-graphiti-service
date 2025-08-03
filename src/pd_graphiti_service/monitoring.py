"""
PD Discovery Platform - Parkinson's Disease Target Discovery Knowledge Graph Service

Copyright (C) 2025 PD Discovery Platform Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""Monitoring and metrics collection for the PD Graphiti Service."""

import time
import psutil
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from prometheus_client import (
    Counter, Histogram, Gauge, Info, CollectorRegistry, 
    generate_latest, CONTENT_TYPE_LATEST
)
from fastapi import FastAPI, Response
from prometheus_fastapi_instrumentator import Instrumentator
import structlog

from .logging_config import get_logger


class MetricsCollector:
    """Collect and expose application metrics."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self.logger = get_logger(__name__)
        
        # Application info
        self.app_info = Info(
            'pd_graphiti_service_info',
            'Application information',
            registry=self.registry
        )
        self.app_info.info({
            'version': '0.1.0',
            'service': 'pd-graphiti-service'
        })
        
        # Ingestion metrics
        self.ingestion_requests_total = Counter(
            'pd_graphiti_ingestion_requests_total',
            'Total number of ingestion requests',
            ['status', 'source_type'],
            registry=self.registry
        )
        
        self.ingestion_duration = Histogram(
            'pd_graphiti_ingestion_duration_seconds',
            'Time spent processing ingestion requests',
            ['source_type'],
            registry=self.registry
        )
        
        self.ingestion_episodes_total = Counter(
            'pd_graphiti_episodes_processed_total',
            'Total number of episodes processed',
            ['status'],
            registry=self.registry
        )
        
        self.ingestion_failures_total = Counter(
            'pd_graphiti_ingestion_failures_total',
            'Total number of ingestion failures',
            ['error_type', 'source_type'],
            registry=self.registry
        )
        
        # Knowledge graph metrics
        self.knowledge_graph_nodes = Gauge(
            'pd_graphiti_knowledge_graph_nodes_total',
            'Total number of nodes in the knowledge graph',
            registry=self.registry
        )
        
        self.knowledge_graph_edges = Gauge(
            'pd_graphiti_knowledge_graph_edges_total',
            'Total number of edges in the knowledge graph',
            registry=self.registry
        )
        
        self.knowledge_graph_entities = Gauge(
            'pd_graphiti_knowledge_graph_entities_total',
            'Total number of entities by type',
            ['entity_type'],
            registry=self.registry
        )
        
        # System metrics
        self.system_memory_usage = Gauge(
            'pd_graphiti_memory_usage_bytes',
            'Memory usage in bytes',
            ['type'],
            registry=self.registry
        )
        
        self.system_cpu_usage = Gauge(
            'pd_graphiti_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        self.database_connection_pool = Gauge(
            'pd_graphiti_database_connections',
            'Database connection pool metrics',
            ['status'],
            registry=self.registry
        )
        
        # Background task metrics
        self.background_tasks_total = Gauge(
            'pd_graphiti_background_tasks_total',
            'Number of background tasks',
            ['status'],
            registry=self.registry
        )
        
        # File monitoring metrics
        self.file_monitoring_events = Counter(
            'pd_graphiti_file_events_total',
            'File monitoring events',
            ['event_type', 'status'],
            registry=self.registry
        )
        
        # Health check metrics
        self.health_check_duration = Histogram(
            'pd_graphiti_health_check_duration_seconds',
            'Health check duration',
            ['check_type'],
            registry=self.registry
        )
        
        self.health_check_status = Gauge(
            'pd_graphiti_health_check_status',
            'Health check status (1=healthy, 0=unhealthy)',
            ['service'],
            registry=self.registry
        )
        
        # Start system metrics collection
        self._start_system_metrics_collection()
    
    def _start_system_metrics_collection(self):
        """Start collecting system metrics periodically."""
        import asyncio
        asyncio.create_task(self._collect_system_metrics_loop())
    
    async def _collect_system_metrics_loop(self):
        """Periodically collect system metrics."""
        while True:
            try:
                await self.collect_system_metrics()
                await asyncio.sleep(30)  # Collect every 30 seconds
            except Exception as e:
                self.logger.error("Failed to collect system metrics", error=str(e))
                await asyncio.sleep(60)  # Wait longer on error
    
    async def collect_system_metrics(self):
        """Collect current system metrics."""
        try:
            # Memory metrics
            memory = psutil.virtual_memory()
            self.system_memory_usage.labels(type='used').set(memory.used)
            self.system_memory_usage.labels(type='available').set(memory.available)
            self.system_memory_usage.labels(type='total').set(memory.total)
            
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage.set(cpu_percent)
            
            # Process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            self.system_memory_usage.labels(type='process_rss').set(process_memory.rss)
            self.system_memory_usage.labels(type='process_vms').set(process_memory.vms)
            
        except Exception as e:
            self.logger.error("Failed to collect system metrics", error=str(e))
    
    def record_ingestion_request(self, status: str, source_type: str = "unknown"):
        """Record an ingestion request."""
        self.ingestion_requests_total.labels(
            status=status,
            source_type=source_type
        ).inc()
    
    def record_ingestion_duration(self, duration: float, source_type: str = "unknown"):
        """Record ingestion duration."""
        self.ingestion_duration.labels(source_type=source_type).observe(duration)
    
    def record_episode_processed(self, status: str):
        """Record a processed episode."""
        self.ingestion_episodes_total.labels(status=status).inc()
    
    def record_ingestion_failure(self, error_type: str, source_type: str = "unknown"):
        """Record an ingestion failure."""
        self.ingestion_failures_total.labels(
            error_type=error_type,
            source_type=source_type
        ).inc()
    
    def update_knowledge_graph_metrics(self, stats: Dict[str, Any]):
        """Update knowledge graph metrics."""
        if 'nodes' in stats:
            self.knowledge_graph_nodes.set(stats['nodes'])
        
        if 'edges' in stats:
            self.knowledge_graph_edges.set(stats['edges'])
        
        if 'entities' in stats:
            for entity_type, count in stats['entities'].items():
                self.knowledge_graph_entities.labels(entity_type=entity_type).set(count)
    
    def update_database_connections(self, active: int, idle: int, total: int):
        """Update database connection metrics."""
        self.database_connection_pool.labels(status='active').set(active)
        self.database_connection_pool.labels(status='idle').set(idle)
        self.database_connection_pool.labels(status='total').set(total)
    
    def update_background_tasks(self, running: int, completed: int, failed: int):
        """Update background task metrics."""
        self.background_tasks_total.labels(status='running').set(running)
        self.background_tasks_total.labels(status='completed').set(completed)
        self.background_tasks_total.labels(status='failed').set(failed)
    
    def record_file_event(self, event_type: str, status: str):
        """Record a file monitoring event."""
        self.file_monitoring_events.labels(
            event_type=event_type,
            status=status
        ).inc()
    
    def record_health_check(self, check_type: str, duration: float, healthy: bool):
        """Record a health check result."""
        self.health_check_duration.labels(check_type=check_type).observe(duration)
        self.health_check_status.labels(service=check_type).set(1 if healthy else 0)
    
    def get_metrics(self) -> str:
        """Get formatted metrics for Prometheus."""
        return generate_latest(self.registry).decode('utf-8')


class MonitoringInstrumentator:
    """FastAPI monitoring instrumentator."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.instrumentator = Instrumentator()
    
    def instrument_app(self, app: FastAPI) -> FastAPI:
        """Instrument a FastAPI application with monitoring."""
        
        # Add Prometheus metrics endpoint
        @app.get("/metrics", include_in_schema=False)
        async def metrics():
            """Prometheus metrics endpoint."""
            return Response(
                content=self.metrics_collector.get_metrics(),
                media_type=CONTENT_TYPE_LATEST
            )
        
        # Add custom metrics endpoint
        @app.get("/api/v1/metrics", tags=["Monitoring"])
        async def custom_metrics():
            """Custom application metrics endpoint."""
            return {
                "timestamp": datetime.now().isoformat(),
                "service": "pd-graphiti-service",
                "version": "0.1.0",
                "metrics": {
                    "system": await self._get_system_metrics(),
                    "application": await self._get_application_metrics()
                }
            }
        
        # Instrument the app
        self.instrumentator.instrument(app)
        self.instrumentator.expose(app, endpoint="/prometheus")
        
        return app
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        try:
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            process = psutil.Process()
            
            return {
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "percent": memory.percent,
                    "process_rss": process.memory_info().rss,
                    "process_vms": process.memory_info().vms
                },
                "cpu": {
                    "percent": cpu_percent,
                    "count": psutil.cpu_count()
                },
                "disk": {
                    "usage": psutil.disk_usage('/').percent
                }
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def _get_application_metrics(self) -> Dict[str, Any]:
        """Get current application metrics."""
        # This would be filled with application-specific metrics
        return {
            "uptime": time.time() - getattr(self, '_start_time', time.time()),
            "requests_per_second": 0,  # Would be calculated from actual metrics
            "error_rate": 0,  # Would be calculated from actual metrics
        }


# Global metrics collector instance
metrics_collector = MetricsCollector()


def setup_monitoring(app: FastAPI) -> MonitoringInstrumentator:
    """Set up monitoring for the FastAPI application."""
    instrumentator = MonitoringInstrumentator(metrics_collector)
    return instrumentator.instrument_app(app)


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector."""
    return metrics_collector


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, name: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.labels = labels or {}
        self.start_time = None
        self.logger = get_logger(__name__)
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        self.logger.debug(
            "operation_completed",
            operation=self.name,
            duration_seconds=duration,
            success=exc_type is None,
            **self.labels
        )
        
        if exc_type is None:
            # Record successful operation
            metrics_collector.record_ingestion_duration(
                duration, 
                self.labels.get('source_type', 'unknown')
            )
        else:
            # Record failed operation
            metrics_collector.record_ingestion_failure(
                error_type=exc_type.__name__,
                source_type=self.labels.get('source_type', 'unknown')
            )


def timer(name: str, **labels):
    """
    Create a performance timer context manager.
    
    Usage:
        with timer("operation_name", source_type="api"):
            # timed operation
    """
    return PerformanceTimer(name, labels)


def timer_decorator(name: str, **labels):
    """Decorator for timing function execution."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            with PerformanceTimer(name, labels):
                return await func(*args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            with PerformanceTimer(name, labels):
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
