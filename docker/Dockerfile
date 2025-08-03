# Multi-stage build for pd-graphiti-service
FROM python:3.12-slim as builder

# Set environment variables for build
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv for faster dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first (for better layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies with production settings
RUN uv sync --frozen --no-dev --compile-bytecode

# Production runtime stage
FROM python:3.12-slim as runtime

# Set production environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user with specific UID/GID for security
RUN groupadd -r -g 1001 appuser && \
    useradd -r -u 1001 -g appuser -s /bin/false -c "App User" appuser

# Set working directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application source with proper ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser main.py ./

# Create directories for volumes with proper permissions
RUN mkdir -p /app/exports /app/logs /app/data && \
    chown -R appuser:appuser /app && \
    chmod -R 755 /app

# Switch to non-root user early for security
USER appuser

# Health check using Python instead of curl for reliability
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live', timeout=10)" || exit 1

# Expose ports (documentation only, controlled by docker-compose)
EXPOSE 8000 8001

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Run the application with production settings
CMD ["python", "-m", "uvicorn", "src.pd_graphiti_service.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--access-log", \
     "--log-level", "info"]
