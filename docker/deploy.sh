#!/bin/bash

# PD Graphiti Service Deployment Script
# This script handles the deployment of the PD Graphiti Service stack

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
ENV_FILE="${SCRIPT_DIR}/.env"
ENV_TEMPLATE="${SCRIPT_DIR}/env.template"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
PD Graphiti Service Deployment Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    dev         Start development environment
    prod        Start production environment
    stop        Stop all services
    restart     Restart all services
    logs        Show service logs
    health      Check service health
    clean       Clean up containers and volumes
    backup      Backup Neo4j database
    restore     Restore Neo4j database

Options:
    -h, --help      Show this help message
    -v, --verbose   Enable verbose output
    --build         Force rebuild of images
    --no-cache      Build without Docker cache

Examples:
    $0 dev                  # Start development environment
    $0 prod --build         # Start production with rebuild
    $0 logs -f              # Follow service logs
    $0 backup               # Backup database
    $0 clean                # Clean up everything

EOF
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check Docker Compose
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose V2 is not available"
        exit 1
    fi
    
    # Check environment file
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warn "Environment file not found at $ENV_FILE"
        if [[ -f "$ENV_TEMPLATE" ]]; then
            log_info "Copying template to $ENV_FILE"
            cp "$ENV_TEMPLATE" "$ENV_FILE"
            log_warn "Please edit $ENV_FILE with your configuration before proceeding"
            exit 1
        else
            log_error "No environment template found"
            exit 1
        fi
    fi
    
    # Check required environment variables
    if ! grep -q "OPENAI_API_KEY=.*[^=]" "$ENV_FILE"; then
        log_error "OPENAI_API_KEY is not set in $ENV_FILE"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Development environment
start_dev() {
    log_info "Starting development environment..."
    
    local build_flag=""
    if [[ "${BUILD:-false}" == "true" ]]; then
        build_flag="--build"
    fi
    
    cd "$SCRIPT_DIR"
    docker compose up -d $build_flag
    
    log_info "Waiting for services to be ready..."
    sleep 10
    
    check_health
}

# Production environment
start_prod() {
    log_info "Starting production environment..."
    
    # Check production directories
    if [[ ! -d "/opt/pd-graphiti" ]]; then
        log_warn "Production directories not found. Creating them..."
        sudo mkdir -p /opt/pd-graphiti/{data/neo4j,logs}
        sudo chown -R 1001:1001 /opt/pd-graphiti
        log_success "Production directories created"
    fi
    
    local build_flag=""
    if [[ "${BUILD:-false}" == "true" ]]; then
        build_flag="--build"
    fi
    
    cd "$SCRIPT_DIR"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d $build_flag
    
    log_info "Waiting for services to be ready..."
    sleep 15
    
    check_health
}

# Stop services
stop_services() {
    log_info "Stopping services..."
    
    cd "$SCRIPT_DIR"
    docker compose down
    
    log_success "Services stopped"
}

# Restart services
restart_services() {
    log_info "Restarting services..."
    
    stop_services
    sleep 3
    
    if [[ "${MODE:-dev}" == "prod" ]]; then
        start_prod
    else
        start_dev
    fi
}

# Show logs
show_logs() {
    cd "$SCRIPT_DIR"
    docker compose logs "${@:1}"
}

# Health check
check_health() {
    log_info "Checking service health..."
    
    # Wait for application to be ready
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -sf http://localhost:8000/health/live > /dev/null 2>&1; then
            log_success "Service is healthy!"
            break
        fi
        
        log_info "Waiting for service... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        log_error "Service health check failed after $max_attempts attempts"
        log_info "Checking service logs..."
        show_logs pd-graphiti-service --tail=20
        exit 1
    fi
    
    # Show service status
    log_info "Service status:"
    curl -s http://localhost:8000/health/ready | python -m json.tool || log_warn "Could not get detailed health status"
    
    log_info "Services:"
    docker compose ps
}

# Clean up
clean_up() {
    log_warn "This will remove all containers, volumes, and data. Are you sure? (y/N)"
    read -r response
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        log_info "Cleaning up..."
        
        cd "$SCRIPT_DIR"
        docker compose down -v --remove-orphans
        docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v --remove-orphans 2>/dev/null || true
        
        # Clean up images
        docker image prune -f
        
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

# Backup database
backup_database() {
    log_info "Creating Neo4j database backup..."
    
    local backup_name="backup-$(date +%Y%m%d_%H%M%S).dump"
    local backup_dir="/tmp/neo4j-backups"
    
    mkdir -p "$backup_dir"
    
    cd "$SCRIPT_DIR"
    docker compose exec neo4j neo4j-admin database dump neo4j "/tmp/$backup_name"
    docker cp "$(docker compose ps -q neo4j):/tmp/$backup_name" "$backup_dir/"
    
    log_success "Backup created: $backup_dir/$backup_name"
}

# Restore database
restore_database() {
    log_warn "This will replace the current database. Are you sure? (y/N)"
    read -r response
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        log_info "Available backups:"
        ls -la /tmp/neo4j-backups/*.dump 2>/dev/null || {
            log_error "No backups found in /tmp/neo4j-backups/"
            exit 1
        }
        
        echo "Enter backup filename:"
        read -r backup_file
        
        if [[ -f "/tmp/neo4j-backups/$backup_file" ]]; then
            log_info "Restoring from $backup_file..."
            
            cd "$SCRIPT_DIR"
            docker compose stop neo4j
            docker cp "/tmp/neo4j-backups/$backup_file" "$(docker compose ps -aq neo4j):/tmp/"
            docker compose start neo4j
            
            # Wait for Neo4j to be ready
            sleep 10
            
            docker compose exec neo4j neo4j-admin database load neo4j "/tmp/$backup_file" --overwrite-destination=true
            docker compose restart neo4j
            
            log_success "Database restored from $backup_file"
        else
            log_error "Backup file not found"
            exit 1
        fi
    else
        log_info "Restore cancelled"
    fi
}

# Main script logic
main() {
    local command="${1:-}"
    
    # Parse global options
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                set -x
                shift
                ;;
            --build)
                BUILD=true
                shift
                ;;
            --no-cache)
                export DOCKER_BUILDKIT=1
                export COMPOSE_DOCKER_CLI_BUILD=1
                shift
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Get command
    command="${1:-}"
    shift 2>/dev/null || true
    
    case "$command" in
        dev)
            check_prerequisites
            start_dev
            ;;
        prod)
            MODE=prod
            check_prerequisites
            start_prod
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        logs)
            show_logs "$@"
            ;;
        health)
            check_health
            ;;
        clean)
            clean_up
            ;;
        backup)
            backup_database
            ;;
        restore)
            restore_database
            ;;
        ""|help)
            show_help
            ;;
        *)
            log_error "Unknown command: $command"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"