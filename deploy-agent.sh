
set -euo pipefail


AGENT_NAME="autogen-ai-agent"
AGENT_VERSION="${AGENT_VERSION:-latest}"
DEPLOY_MODE="${DEPLOY_MODE:-docker-compose}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }


show_usage() {
    cat << EOF
AutoGen AI Code Correction Agent - Deployment Script

Usage: $0 [OPTIONS]

Options:
    -h, --help          Show this help message
    -m, --mode MODE     Deployment mode (docker-compose|docker|build)
    -v, --version VER   Agent version to deploy (default: latest)
    -s, --stop          Stop the running agent
    -r, --restart       Restart the agent
    --cleanup           Clean up all agent containers and images

Environment Variables:
    DEPLOY_MODE         Deployment mode (docker-compose|docker|build)
    AGENT_VERSION       Version to deploy

Examples:
    $0                          # Deploy with docker-compose (default)
    $0 -m docker               # Deploy with docker run
    $0 -m build                # Build and deploy locally
    $0 --stop                  # Stop running agent
    $0 --cleanup               # Clean up everything

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -m|--mode)
                DEPLOY_MODE="$2"
                shift 2
                ;;
            -v|--version)
                AGENT_VERSION="$2"
                shift 2
                ;;
            -s|--stop)
                stop_agent
                exit 0
                ;;
            -r|--restart)
                restart_agent
                exit 0
                ;;
            --cleanup)
                cleanup_agent
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

display_ip_notice() {
    cat << 'EOF'
================================================================================
    🤖 AutoGen AI Code Correction Agent - Proprietary IP
================================================================================
    
    CONFIDENTIAL SOFTWARE - DEPLOYMENT RESTRICTED
    
    This deployment script handles proprietary artificial intelligence
    technology for automated code quality improvement.
    
    Copyright © 2024 - All Rights Reserved
    Licensed for authorized use only.
    
    Ensure compliance with licensing terms before proceeding.
    
================================================================================
EOF
}

validate_environment() {
    log_info "Validating deployment environment..."
    

    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running"
        exit 1
    fi

    if [[ "$DEPLOY_MODE" == "docker-compose" ]]; then
        if ! command -v docker-compose >/dev/null 2>&1; then
            log_error "docker-compose is not installed"
            exit 1
        fi
        
        if [[ ! -f "docker-compose.yml" ]]; then
            log_error "docker-compose.yml not found"
            exit 1
        fi
    fi
    
    # Check .env file
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.template" ]]; then
            log_warning ".env file not found, but template exists"
            log_info "Please copy .env.template to .env and configure it"
            read -p "Continue with template? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
            cp .env.template .env
            log_info "Template copied to .env - please edit it with your values"
        else
            log_error ".env file not found and no template available"
            exit 1
        fi
    fi

    # Validate required environment variables
    source .env
    local required_vars=("OPENAI_API_KEY" "GITLAB_TOKEN")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done

    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_error "Missing required environment variables: ${missing_vars[*]}"
        log_error "Please update your .env file"
        exit 1
    fi
    log_success "Environment validation passed"
}

# Prepare deployment directories
prepare_directories() {
    log_info "Preparing deployment directories..."
    
    local dirs=("data/downloads" "data/logs" "data/repo")
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            log_info "Created directory: $dir"
        fi
    done
    
    # Set appropriate permissions
    chmod 755 data data/downloads data/logs data/repo
    
    log_success "Directories prepared"
}

# Deploy with docker-compose
deploy_with_compose() {
    log_info "Deploying with docker-compose..."
    
    # Pull/build the latest images
    docker-compose build --pull autogen-ai-agent || {
        log_error "Failed to build agent image"
        exit 1
    }
    
    # Start services
    docker-compose up -d || {
        log_error "Failed to start services"
        exit 1
    }
    
    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 10
    
    # Check status
    docker-compose ps
    
    log_success "Agent deployed successfully with docker-compose"
    log_info "View logs with: docker-compose logs -f autogen-ai-agent"
    log_info "Stop with: docker-compose down"
}

# Deploy with docker run
deploy_with_docker() {
    log_info "Deploying with docker run..."
    
    # Stop existing container if running
    if docker ps -a --format "{{.Names}}" | grep -q "^autogen-code-corrector$"; then
        log_info "Stopping existing container..."
        docker stop autogen-code-corrector >/dev/null 2>&1 || true
        docker rm autogen-code-corrector >/dev/null 2>&1 || true
    fi
    
    # Run the container
    docker run -d \
        --name autogen-code-corrector \
        --env-file .env \
        -v "$(pwd)/data/downloads:/app/downloads" \
        -v "$(pwd)/data/logs:/app/logs" \
        -v "$(pwd)/data/repo:/app/repo" \
        -p 8080:8080 \
        --restart unless-stopped \
        "${AGENT_NAME}:${AGENT_VERSION}" || {
        log_error "Failed to start container"
        exit 1
    }
    
    log_success "Agent deployed successfully with docker run"
    log_info "View logs with: docker logs -f autogen-code-corrector"
    log_info "Stop with: docker stop autogen-code-corrector"
}

# Build and deploy locally
build_and_deploy() {
    log_info "Building and deploying locally..."
    
    if [[ ! -f "build-agent.sh" ]]; then
        log_error "build-agent.sh not found"
        exit 1
    fi
    
    # Make build script executable
    chmod +x build-agent.sh
    
    # Run build
    ./build-agent.sh || {
        log_error "Build failed"
        exit 1
    }
    
    # Deploy with docker-compose
    deploy_with_compose
}

# Stop agent
stop_agent() {
    log_info "Stopping AutoGen AI Agent..."
    
    # Stop docker-compose services
    if [[ -f "docker-compose.yml" ]]; then
        docker-compose down >/dev/null 2>&1 || true
    fi
    
    # Stop standalone container
    if docker ps --format "{{.Names}}" | grep -q "^autogen-code-corrector$"; then
        docker stop autogen-code-corrector >/dev/null 2>&1 || true
    fi
    
    log_success "Agent stopped"
}

# Restart agent
restart_agent() {
    log_info "Restarting AutoGen AI Agent..."
    
    stop_agent
    sleep 2
    
    if [[ -f "docker-compose.yml" ]]; then
        deploy_with_compose
    else
        deploy_with_docker
    fi
}

# Cleanup everything
cleanup_agent() {
    log_warning "This will remove all agent containers and images!"
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cleanup cancelled"
        exit 0
    fi
    
    log_info "Cleaning up AutoGen AI Agent..."
    
    # Stop and remove containers
    stop_agent
    
    # Remove containers
    docker rm autogen-code-corrector >/dev/null 2>&1 || true
    
    # Remove images
    docker images "${AGENT_NAME}" --format "{{.Repository}}:{{.Tag}}" | while read -r image; do
        log_info "Removing image: $image"
        docker rmi "$image" >/dev/null 2>&1 || true
    done
    
    # Remove networks
    docker network rm autogen-ai-network >/dev/null 2>&1 || true
    
    # Clean up volumes (optional)
    read -p "Also remove persistent data volumes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf data/
        log_info "Data volumes removed"
    fi
    
    log_success "Cleanup completed"
}

# Show deployment status
show_status() {
    log_info "AutoGen AI Agent Status:"
    echo
    
    # Check docker-compose services
    if [[ -f "docker-compose.yml" ]] && docker-compose ps >/dev/null 2>&1; then
        echo "Docker Compose Services:"
        docker-compose ps
        echo
    fi
    
    # Check standalone container
    if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -q autogen; then
        echo "Standalone Containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(NAMES|autogen)"
        echo
    fi
    
    # Check images
    if docker images "${AGENT_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}" | tail -n +2 | grep -q .; then
        echo "Available Images:"
        docker images "${AGENT_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    fi
}

# Main deployment function
main() {
    display_ip_notice
    
    log_info "Starting AutoGen AI Agent deployment..."
    log_info "Mode: $DEPLOY_MODE, Version: $AGENT_VERSION"
    
    validate_environment
    prepare_directories
    
    case "$DEPLOY_MODE" in
        "docker-compose")
            deploy_with_compose
            ;;
        "docker")
            deploy_with_docker
            ;;
        "build")
            build_and_deploy
            ;;
        *)
            log_error "Invalid deployment mode: $DEPLOY_MODE"
            log_error "Valid modes: docker-compose, docker, build"
            exit 1
            ;;
    esac
    
    echo
    show_status
    
    log_success "🎉 AutoGen AI Agent deployment completed!"
    log_info "The agent is now running and ready to process code corrections"
}

# Parse arguments and run
parse_args "$@"
main
