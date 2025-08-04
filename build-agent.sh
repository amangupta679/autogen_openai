#!/bin/bash

# AutoGen AI Code Correction Agent - Production Build Script
# ===========================================================
# Build, package, and prepare the containerized AI agent for distribution

set -euo pipefail

# Configuration
AGENT_NAME="autogen-ai-agent"
AGENT_VERSION="${AGENT_VERSION:-1.0.0}"
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COMPANY="${COMPANY:-YourCompany}"
REGISTRY="${REGISTRY:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level="$1"
    local color="$2"
    shift 2
    echo -e "${color}[$(date '+%Y-%m-%d %H:%M:%S')] [${level}]${NC} $*"
}

# Function definitions
log_info() { log "INFO" "$BLUE" "$@"; }
log_success() { log "SUCCESS" "$GREEN" "$@"; }
log_warning() { log "WARNING" "$YELLOW" "$@"; }
log_error() { log "ERROR" "$RED" "$@"; }
log_header() { log "HEADER" "$PURPLE" "$@"; }

# Error handler
error_handler() {
    log_error "Build failed at line $1"
    log_error "Check the output above for details"
    exit 1
}

trap 'error_handler ${LINENO}' ERR

# Display banner
display_banner() {
    cat << 'EOF'
================================================================================
  🤖 AutoGen AI Code Correction Agent - Production Build System
================================================================================
   
   Building proprietary IP container for automated code quality improvement
   
   Copyright © 2024 - All Rights Reserved
   Licensed IP - Unauthorized distribution prohibited
   
================================================================================
EOF
}

# Validate prerequisites
validate_prerequisites() {
    log_info "Validating build prerequisites..."
    
    local required_commands=("docker" "git")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        log_error "Missing required commands: ${missing_commands[*]}"
        log_error "Please install the missing dependencies and try again"
        exit 1
    fi
    
    # Check Docker daemon
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon is not running"
        log_error "Please start Docker and try again"
        exit 1
    fi
    
    # Check if .env exists
    if [[ ! -f ".env" ]]; then
        log_warning ".env file not found"
        log_warning "Using environment variables or defaults"
        if [[ -f ".env.template" ]]; then
            log_info "Template available at .env.template"
        fi
    fi
    
    log_success "Prerequisites validated"
}

# Clean previous builds
clean_build_artifacts() {
    log_info "Cleaning previous build artifacts..."
    
    # Remove old containers
    if docker container ls -a --format "table {{.Names}}" | grep -q "^${AGENT_NAME}"; then
        log_info "Removing existing container: ${AGENT_NAME}"
        docker container rm -f "${AGENT_NAME}" >/dev/null 2>&1 || true
    fi
    
    # Clean up dangling images
    local dangling_images=$(docker images -f "dangling=true" -q)
    if [[ -n "$dangling_images" ]]; then
        log_info "Removing dangling images"
        docker rmi $dangling_images >/dev/null 2>&1 || true
    fi
    
    # Create required directories
    mkdir -p data/{downloads,logs,repo} build-artifacts
    
    log_success "Build environment cleaned"
}

# Build the container image
build_container() {
    log_header "Building AutoGen AI Agent Container"
    
    local image_tag="${AGENT_NAME}:${AGENT_VERSION}"
    local latest_tag="${AGENT_NAME}:latest"
    
    log_info "Building image: ${image_tag}"
    
    # Build with build args
    docker build \
        --build-arg BUILD_DATE="${BUILD_DATE}" \
        --build-arg VERSION="${AGENT_VERSION}" \
        --build-arg VENDOR="${COMPANY}" \
        --tag "${image_tag}" \
        --tag "${latest_tag}" \
        . || {
        log_error "Docker build failed"
        exit 1
    }
    
    log_success "Container built successfully: ${image_tag}"
    
    # Display image information
    log_info "Image details:"
    docker images "${AGENT_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
}

# Run security scan (if available)
security_scan() {
    log_info "Running security analysis..."
    
    if command -v docker-scout >/dev/null 2>&1; then
        log_info "Running Docker Scout security scan"
        docker scout quickview "${AGENT_NAME}:${AGENT_VERSION}" || {
            log_warning "Security scan completed with warnings"
        }
    elif command -v trivy >/dev/null 2>&1; then
        log_info "Running Trivy security scan"
        trivy image "${AGENT_NAME}:${AGENT_VERSION}" || {
            log_warning "Security scan completed with warnings"
        }
    else
        log_warning "No security scanning tools available"
        log_warning "Consider installing docker-scout or trivy for security analysis"
    fi
}

# Test the built container
test_container() {
    log_info "Testing container functionality..."
    
    # Basic functionality test
    log_info "Running basic health check"
    docker run --rm "${AGENT_NAME}:${AGENT_VERSION}" python -c "
import autogen
import openai
import git
import matplotlib
import seaborn
import numpy
print('✅ All dependencies are working correctly')
print('🤖 AutoGen AI Agent is ready for deployment')
" || {
        log_error "Container functionality test failed"
        exit 1
    }
    
    log_success "Container functionality test passed"
}

# Export container for distribution
export_container() {
    log_info "Exporting container for distribution..."
    
    local export_file="build-artifacts/${AGENT_NAME}-${AGENT_VERSION}.tar"
    
    log_info "Creating distributable package: ${export_file}"
    docker save "${AGENT_NAME}:${AGENT_VERSION}" -o "${export_file}"
    
    # Compress the export
    log_info "Compressing package..."
    gzip "${export_file}"
    
    local final_package="${export_file}.gz"
    local package_size=$(du -h "${final_package}" | cut -f1)
    
    log_success "Package created: ${final_package} (${package_size})"
    
    # Generate checksums for integrity
    log_info "Generating integrity checksums..."
    cd build-artifacts
    sha256sum "$(basename "${final_package}")" > "$(basename "${final_package}").sha256"
    md5sum "$(basename "${final_package}")" > "$(basename "${final_package}").md5"
    cd ..
    
    log_success "Integrity checksums generated"
}

# Generate deployment documentation
generate_documentation() {
    log_info "Generating deployment documentation..."
    
    local doc_file="build-artifacts/DEPLOYMENT_GUIDE.md"
    
    cat > "${doc_file}" << EOF
# AutoGen AI Code Correction Agent - Deployment Guide

## Package Information
- **Agent Name**: ${AGENT_NAME}
- **Version**: ${AGENT_VERSION}
- **Build Date**: ${BUILD_DATE}
- **Vendor**: ${COMPANY}

## Quick Start

### 1. Load the Container Image
\`\`\`bash
# Extract and load the image
gunzip ${AGENT_NAME}-${AGENT_VERSION}.tar.gz
docker load -i ${AGENT_NAME}-${AGENT_VERSION}.tar
\`\`\`

### 2. Set Up Environment
\`\`\`bash
# Copy environment template
cp .env.template .env

# Edit .env with your actual values
nano .env
\`\`\`

### 3. Deploy with Docker Compose
\`\`\`bash
# Start the agent
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f autogen-ai-agent
\`\`\`

### 4. Manual Docker Run (Alternative)
\`\`\`bash
docker run -d \\
  --name autogen-code-corrector \\
  --env-file .env \\
  -v \$(pwd)/data/downloads:/app/downloads \\
  -v \$(pwd)/data/logs:/app/logs \\
  -v \$(pwd)/data/repo:/app/repo \\
  -p 8080:8080 \\
  ${AGENT_NAME}:${AGENT_VERSION}
\`\`\`

## Configuration

### Required Environment Variables
- \`OPENAI_API_KEY\`: Your OpenAI API key
- \`GITLAB_TOKEN\`: GitLab access token
- \`SONAR_TOKEN\`: SonarQube authentication token
- \`SONAR_HOST_URL\`: SonarQube server URL
- \`CI_PROJECT_KEY\`: Project identifier

### Optional Configuration
See \`.env.template\` for all available configuration options.

## Support and Licensing

This is proprietary software. For support or licensing inquiries:
- Email: licensing@company.com
- Version: ${AGENT_VERSION}
- Build: ${BUILD_DATE}

## Integrity Verification

Verify package integrity before deployment:
\`\`\`bash
sha256sum -c ${AGENT_NAME}-${AGENT_VERSION}.tar.gz.sha256
md5sum -c ${AGENT_NAME}-${AGENT_VERSION}.tar.gz.md5
\`\`\`
EOF

    log_success "Deployment guide created: ${doc_file}"
}

# Generate build manifest
generate_manifest() {
    log_info "Generating build manifest..."
    
    local manifest_file="build-artifacts/BUILD_MANIFEST.json"
    local git_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    local git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    
    cat > "${manifest_file}" << EOF
{
  "agent": {
    "name": "${AGENT_NAME}",
    "version": "${AGENT_VERSION}",
    "build_date": "${BUILD_DATE}",
    "vendor": "${COMPANY}",
    "license": "Proprietary"
  },
  "build": {
    "git_commit": "${git_commit}",
    "git_branch": "${git_branch}",
    "builder": "$(whoami)@$(hostname)",
    "build_os": "$(uname -sr)",
    "docker_version": "$(docker --version | cut -d' ' -f3 | tr -d ',')"
  },
  "package": {
    "format": "docker_image",
    "compression": "gzip",
    "checksums": {
      "sha256": "$(cat build-artifacts/${AGENT_NAME}-${AGENT_VERSION}.tar.gz.sha256 2>/dev/null | cut -d' ' -f1 || echo 'pending')",
      "md5": "$(cat build-artifacts/${AGENT_NAME}-${AGENT_VERSION}.tar.gz.md5 2>/dev/null | cut -d' ' -f1 || echo 'pending')"
    }
  },
  "components": {
    "python_version": "3.10",
    "autogen_version": "$(grep autogen requirements.txt | cut -d'=' -f3)",
    "openai_version": "$(grep openai requirements.txt | cut -d'>' -f2)"
  }
}
EOF

    log_success "Build manifest created: ${manifest_file}"
}

# Main build orchestration
main() {
    display_banner
    
    log_header "Starting AutoGen AI Agent Build Process"
    
    validate_prerequisites
    clean_build_artifacts
    build_container
    security_scan
    test_container
    export_container
    generate_documentation
    generate_manifest
    
    log_header "🎉 Build Process Completed Successfully!"
    
    log_success "Deliverables created in build-artifacts/:"
    ls -la build-artifacts/ | tail -n +2 | while read -r line; do
        log_info "  $line"
    done
    
    log_info ""
    log_info "Next Steps:"
    log_info "1. Review the generated deployment guide"
    log_info "2. Test the container in your target environment"
    log_info "3. Distribute the .tar.gz package to authorized users"
    log_info "4. Ensure proper IP protection and licensing compliance"
    
    if [[ -n "${REGISTRY:-}" ]]; then
        log_info ""
        log_info "To push to registry:"
        log_info "  docker tag ${AGENT_NAME}:${AGENT_VERSION} ${REGISTRY}/${AGENT_NAME}:${AGENT_VERSION}"
        log_info "  docker push ${REGISTRY}/${AGENT_NAME}:${AGENT_VERSION}"
    fi
}

# Execute main function
main "$@"
