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

"""Structured logging configuration for the PD Graphiti Service."""

import logging
import logging.config
import sys
from typing import Any, Dict, Optional
import structlog
from datetime import datetime


def configure_structured_logging(
    log_level: str = "INFO",
    enable_json: bool = True,
    service_name: str = "pd-graphiti-service",
    service_version: str = "0.1.0"
) -> None:
    """
    Configure structured logging with JSON output for production.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_json: Whether to output JSON formatted logs
        service_name: Name of the service for log context
        service_version: Version of the service for log context
    """
    
    # Configure structlog
    processors = [
        # Add service context to all logs
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        # Add service metadata
        _add_service_context(service_name, service_version),
    ]
    
    if enable_json:
        # Production JSON logging
        processors.extend([
            # structlog.processors.dict_tracebacks,  # Temporarily disabled due to recursion issue
            structlog.processors.JSONRenderer(sort_keys=True)
        ])
    else:
        # Development console logging
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True)
        ])
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        context_class=dict,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Configure uvicorn loggers to use our format
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


def _add_service_context(service_name: str, service_version: str):
    """Add service context to log records."""
    def processor(logger, method_name, event_dict):
        event_dict.update({
            "service": service_name,
            "version": service_version,
            "environment": "production",  # Could be configurable
        })
        return event_dict
    return processor


class RequestLoggingMiddleware:
    """Middleware for logging HTTP requests and responses."""
    
    def __init__(self, app, logger: Optional[structlog.BoundLogger] = None):
        self.app = app
        self.logger = logger or structlog.get_logger(__name__)
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        request_id = self._generate_request_id()
        start_time = datetime.now()
        
        # Extract request info
        method = scope["method"]
        path = scope["path"]
        query_string = scope.get("query_string", b"").decode()
        client_ip = self._get_client_ip(scope)
        
        # Log request
        self.logger.info(
            "request_started",
            request_id=request_id,
            method=method,
            path=path,
            query_string=query_string,
            client_ip=client_ip,
            timestamp=start_time.isoformat()
        )
        
        # Capture response
        response_info = {"status_code": None, "headers": {}}
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                response_info["status_code"] = message["status"]
                response_info["headers"] = dict(message.get("headers", []))
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
            
            # Log successful response
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self.logger.info(
                "request_completed",
                request_id=request_id,
                method=method,
                path=path,
                status_code=response_info["status_code"],
                duration_seconds=duration,
                client_ip=client_ip,
                timestamp=end_time.isoformat()
            )
            
        except Exception as exc:
            # Log error response
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self.logger.error(
                "request_failed",
                request_id=request_id,
                method=method,
                path=path,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_seconds=duration,
                client_ip=client_ip,
                timestamp=end_time.isoformat(),
                exc_info=True
            )
            raise
    
    def _generate_request_id(self) -> str:
        """Generate a unique request ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _get_client_ip(self, scope: dict) -> str:
        """Extract client IP from request scope."""
        # Try to get from headers first (for proxies)
        headers = dict(scope.get("headers", []))
        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode().split(",")[0].strip()
        
        real_ip = headers.get(b"x-real-ip")
        if real_ip:
            return real_ip.decode()
        
        # Fall back to direct client IP
        client = scope.get("client")
        if client:
            return client[0]
        
        return "unknown"


def get_logger(name: str, **context) -> structlog.BoundLogger:
    """
    Get a logger with optional context.
    
    Args:
        name: Logger name (typically __name__)
        **context: Additional context to bind to the logger
    
    Returns:
        Bound logger instance
    """
    logger = structlog.get_logger(name)
    if context:
        logger = logger.bind(**context)
    return logger


class ErrorTracker:
    """Track and log application errors with stack traces."""
    
    def __init__(self, logger: Optional[structlog.BoundLogger] = None):
        self.logger = logger or get_logger(__name__)
    
    def track_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ) -> str:
        """
        Track an error with full context and stack trace.
        
        Args:
            error: The exception that occurred
            context: Additional context information
            user_message: User-friendly error message
        
        Returns:
            Error tracking ID for correlation
        """
        import uuid
        error_id = str(uuid.uuid4())
        
        error_context = {
            "error_id": error_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_message": user_message,
        }
        
        if context:
            error_context.update(context)
        
        self.logger.error(
            "application_error",
            **error_context,
            exc_info=True
        )
        
        return error_id


# Global error tracker instance
error_tracker = ErrorTracker()


def log_function_call(func_name: str, **kwargs):
    """Decorator to log function calls for debugging."""
    def decorator(func):
        async def async_wrapper(*args, **func_kwargs):
            logger = get_logger(func.__module__)
            logger.debug(
                "function_call_start",
                function=func_name,
                args=len(args),
                kwargs=list(func_kwargs.keys()),
                **kwargs
            )
            
            try:
                result = await func(*args, **func_kwargs)
                logger.debug(
                    "function_call_success",
                    function=func_name,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(
                    "function_call_error",
                    function=func_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    **kwargs,
                    exc_info=True
                )
                raise
        
        def sync_wrapper(*args, **func_kwargs):
            logger = get_logger(func.__module__)
            logger.debug(
                "function_call_start",
                function=func_name,
                args=len(args),
                kwargs=list(func_kwargs.keys()),
                **kwargs
            )
            
            try:
                result = func(*args, **func_kwargs)
                logger.debug(
                    "function_call_success",
                    function=func_name,
                    **kwargs
                )
                return result
            except Exception as e:
                logger.error(
                    "function_call_error",
                    function=func_name,
                    error=str(e),
                    error_type=type(e).__name__,
                    **kwargs,
                    exc_info=True
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
