# PD Graphiti Service Docker Configuration

This directory contains the production-ready Docker configuration for the PD Graphiti Service, including multi-stage Dockerfile, docker-compose configurations, and deployment scripts.

## Quick Start

### Prerequisites

- Docker Engine 20.10+
- Docker Compose V2
- OpenAI API key
- At least 4GB RAM available for containers

### Development Setup

1. **Copy environment template:**
   ```bash
   cp env.template .env
   ```

2. **Edit `.env` file with your configuration:**
   ```bash
   # Required - add your OpenAI API key
   OPENAI_API_KEY=your_actual_openai_api_key
   
   # Optional - use defaults for development
   NEO4J_PASSWORD=demodemo
   ```

3. **Start the development stack:**
   ```bash
   docker-compose up -d
   ```

4. **Check service health:**
   ```bash
   curl http://localhost:8000/health
   ```

### Production Setup

1. **Copy and configure environment:**
   ```bash
   cp env.template .env
   # Edit .env with production values
   ```

2. **Create production data directories:**
   ```bash
   sudo mkdir -p /opt/pd-graphiti/{data/neo4j,logs}
   sudo chown -R 1001:1001 /opt/pd-graphiti
   ```

3. **Deploy with production overrides:**
   ```bash
   docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

## Architecture

### Multi-Stage Dockerfile

The Dockerfile uses a multi-stage build approach:

- **Builder Stage**: Installs dependencies and compiles bytecode
- **Runtime Stage**: Minimal production image with security hardening

### Security Features

- Non-root user (UID/GID 1001)
- Read-only root filesystem where possible
- No new privileges
- Minimal base image (python:3.12-slim)
- Proper signal handling with tini

### Health Checks

- **Liveness**: `/health/live` - Basic application responsiveness
- **Readiness**: `/health/ready` - Service and dependency readiness
- **Deep Health**: `/health/deep` - Comprehensive dependency testing

## Container Services

### pd-graphiti-service

**Ports:**
- 8000: Main application API
- 8001: Metrics endpoint

**Volumes:**
- `/app/exports`: Export data (read-only)
- `/app/logs`: Application logs
- `/app/data`: Temporary application data

**Resource Limits:**
- Memory: 2GB limit, 1GB reservation
- CPU: 1.0 cores

### neo4j

**Ports:**
- 7474: HTTP interface
- 7687: Bolt protocol

**Volumes:**
- `/data`: Database files
- `/logs`: Neo4j logs
- `/var/lib/neo4j/import`: Data import
- `/plugins`: Neo4j plugins

**Performance Tuning:**
- Heap: 512MB-2GB (dev) / 1GB-4GB (prod)
- Page cache: 1GB (dev) / 2GB (prod)

## Configuration Files

### docker-compose.yml
Main configuration with production defaults

### docker-compose.override.yml
Development overrides (automatically loaded)

### docker-compose.prod.yml
Production overrides with enhanced security and performance

### env.template
Environment variable template

## Usage Commands

### Development

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f pd-graphiti-service

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

### Production

```bash
# Deploy production stack
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale application (if needed)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale pd-graphiti-service=2

# Update to new version
docker-compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Monitoring

```bash
# Health check
curl http://localhost:8000/health/ready

# Metrics (if enabled)
curl http://localhost:8001/metrics

# Container stats
docker stats pd-graphiti-service pd-neo4j

# Service logs
docker-compose logs -f --tail=100
```

### Maintenance

```bash
# Backup Neo4j data
docker-compose exec neo4j neo4j-admin database dump neo4j /data/backups/backup-$(date +%Y%m%d).dump

# Clean up unused images
docker image prune -f

# View volume usage
docker system df -v
```

## Environment Variables

### Required
- `OPENAI_API_KEY`: Your OpenAI API key
- `NEO4J_PASSWORD`: Secure password for Neo4j

### Optional
- `LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR (default: INFO)
- `SERVICE_PORT`: Application port (default: 8000)
- `NEO4J_USER`: Neo4j username (default: neo4j)
- `GRAPHITI_GROUP_ID`: Group identifier (default: pd_target_discovery)
- `EXPORT_SOURCE_PATH`: Path to export data (default: ../pd-target-identification/src/exports)

## Troubleshooting

### Service Won't Start
1. Check environment variables: `docker-compose config`
2. Check logs: `docker-compose logs pd-graphiti-service`
3. Verify Neo4j is healthy: `docker-compose ps`

### Connection Issues
1. Verify network: `docker network ls`
2. Test Neo4j connectivity: `docker-compose exec pd-graphiti-service python -c "from src.pd_graphiti_service.graphiti_client import GraphitiClient; import asyncio; print(asyncio.run(GraphitiClient().test_connection()))"`

### Performance Issues
1. Monitor resources: `docker stats`
2. Check memory limits in docker-compose.prod.yml
3. Review Neo4j memory settings

### Data Persistence
- Neo4j data: `docker volume inspect pd-neo4j-data`
- Application logs: `docker volume inspect pd-graphiti-logs`

## Security Considerations

1. **Secrets Management**: Store sensitive values in Docker secrets or external secret management
2. **Network Security**: Use custom networks and firewall rules in production
3. **Image Security**: Regularly update base images and scan for vulnerabilities
4. **Access Control**: Implement proper authentication and authorization
5. **Monitoring**: Set up logging aggregation and monitoring in production