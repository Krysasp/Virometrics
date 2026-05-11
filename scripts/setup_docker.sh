#!/bin/bash
# One-click Docker installation and setup script for Virometrics

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"
CONFIG_FILE="$PROJECT_DIR/config/docker.conf"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_warning "Docker not found, installing..."
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io
        log_success "Docker installed"
    else
        log_success "Docker is installed ($(docker --version))"
    fi
}

# Check if Docker Compose is installed
check_compose() {
    if ! docker compose version &> /dev/null; then
        log_warning "Docker Compose not found, installing..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        log_success "Docker Compose installed"
    else
        log_success "Docker Compose is installed ($(docker compose version))"
    fi
}

# Check if Redis is available
check_redis() {
    if ! command -v redis-cli &> /dev/null; then
        log_warning "Redis CLI not found, installing..."
        sudo apt-get update
        sudo apt-get install -y redis-tools
        log_success "Redis tools installed"
    else
        log_success "Redis CLI is installed ($(redis-cli --version))"
    fi
}

# Create required directories
setup_directories() {
    log_info "Setting up directories..."
    mkdir -p "$PROJECT_DIR/data/uploads"
    mkdir -p "$PROJECT_DIR/data/outputs"
    mkdir -p "$PROJECT_DIR/data/checkpoints"
    mkdir -p "$PROJECT_DIR/data/logs"
    log_success "Directories created"
}

# Create .env file if not exists
setup_env() {
    local env_file="$PROJECT_DIR/.env"
    if [ ! -f "$env_file" ]; then
        log_info "Creating .env file..."
        cat > "$env_file" <<EOF
# Virometrics Environment Variables

# Flask settings
FLASK_DEBUG=false
SECRET_KEY=your-secret-key-change-in-production

# Redis settings
REDIS_URL=redis://localhost:6379/0

# Worker settings
WORKER_NAME=worker1
WORKER_REPLICAS=2
GPU_ENABLED=false

# Resource limits
MAX_CONCURRENT_JOBS=5
JOB_TIMEOUT=3600
EOF
        log_success ".env file created"
    else
        log_success ".env file already exists"
    fi
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    cd "$PROJECT_DIR"
    docker compose build
    log_success "Docker images built"
}

# Start services
start_services() {
    log_info "Starting Virometrics services..."
    cd "$PROJECT_DIR"
    docker compose up -d
    log_success "Services started"
}

# Stop services
stop_services() {
    log_info "Stopping Virometrics services..."
    cd "$PROJECT_DIR"
    docker compose down
    log_success "Services stopped"
}

# Restart services
restart_services() {
    log_info "Restarting Virometrics services..."
    cd "$PROJECT_DIR"
    docker compose restart
    log_success "Services restarted"
}

# Show status
show_status() {
    log_info "Virometrics services status:"
    cd "$PROJECT_DIR"
    docker compose ps
}

# Show logs
show_logs() {
    local service=${1:-web}
    log_info "Showing logs for $service..."
    cd "$PROJECT_DIR"
    docker compose logs -f "$service"
}

# Health check
health_check() {
    log_info "Running health check..."
    if curl -s http://localhost:8000/health > /dev/null; then
        log_success "Web service is healthy"
    else
        log_error "Web service is not responding"
    fi
}

# Main installation
install() {
    log_info "=== Virometrics Docker Installation ==="
    
    check_docker
    check_compose
    setup_directories
    setup_env
    
    log_info ""
    log_info "Build images? (y/n)"
    read -r build_choice
    if [[ "$build_choice" =~ ^[Yy]$ ]]; then
        build_images
    fi
    
    log_info ""
    log_info "Start services? (y/n)"
    read -r start_choice
    if [[ "$start_choice" =~ ^[Yy]$ ]]; then
        start_services
        sleep 5
        health_check
    fi
    
    log_info ""
    log_success "=== Installation Complete ==="
    log_info "Access dashboard at: http://localhost:8000/web/"
    log_info "API endpoint: http://localhost:8000/api"
}

# Parse command line arguments
case "${1:-install}" in
    install)
        install
        ;;
    build)
        build_images
        ;;
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "${2:-web}"
        ;;
    health)
        health_check
        ;;
    clean)
        log_info "Cleaning up..."
        cd "$PROJECT_DIR"
        docker compose down -v
        docker rmi virometrics-web virometrics-worker virometrics-worker-gpu 2>/dev/null || true
        log_success "Cleanup complete"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Usage: $0 {install|build|start|stop|restart|status|logs|health|clean}"
        exit 1
        ;;
esac
