#!/bin/bash

# AutoGen AI Code Correction Agent - Production Entrypoint
# =========================================================
# Proprietary IP - Production-ready container bootstrap

set -euo pipefail

# Configuration
LOG_DIR="/app/logs"
LOG_FILE="${LOG_DIR}/agent-$(date +%Y%m%d-%H%M%S).log"
PID_FILE="/tmp/agent.pid"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Logging function
log() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*" | tee -a "${LOG_FILE}"
}

# Error handler
error_handler() {
    log "ERROR" "Agent execution failed at line $1"
    log "ERROR" "Check logs for details: ${LOG_FILE}"
    exit 1
}

# Set up error handling
trap 'error_handler ${LINENO}' ERR

# Signal handlers for graceful shutdown
cleanup() {
    log "INFO" "Received shutdown signal, cleaning up..."
    if [[ -f "${PID_FILE}" ]]; then
        local pid=$(cat "${PID_FILE}")
        if kill -0 "${pid}" 2>/dev/null; then
            log "INFO" "Terminating agent process ${pid}"
            kill -TERM "${pid}" 2>/dev/null || true
            sleep 2
            kill -KILL "${pid}" 2>/dev/null || true
        fi
        rm -f "${PID_FILE}"
    fi
    log "INFO" "Cleanup completed"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Validation function
validate_environment() {
    log "INFO" "Validating environment configuration..."
    
    local required_vars=("OPENAI_API_KEY" "GITLAB_TOKEN")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("${var}")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log "ERROR" "Missing required environment variables: ${missing_vars[*]}"
        log "ERROR" "Please ensure all required secrets are provided"
        exit 1
    fi
    
    # Validate API key format (basic check)
    if [[ ! "${OPENAI_API_KEY}" =~ ^sk-proj- ]]; then
        log "WARN" "OpenAI API key format appears unusual"
    fi
    
    log "INFO" "Environment validation passed"
}

# Dependency check
check_dependencies() {
    log "INFO" "Checking system dependencies..."
    
    # Check Python modules
    python -c "
import sys
required_modules = ['autogen', 'openai', 'git', 'matplotlib', 'seaborn', 'numpy']
missing_modules = []

for module in required_modules:
    try:
        __import__(module)
    except ImportError:
        missing_modules.append(module)

if missing_modules:
    print(f'ERROR: Missing Python modules: {missing_modules}', file=sys.stderr)
    sys.exit(1)
else:
    print('All required Python modules are available')
" || {
        log "ERROR" "Python dependency check failed"
        exit 1
    }
    
    # Check git availability
    if ! command -v git >/dev/null 2>&1; then
        log "ERROR" "Git is not available in the container"
        exit 1
    fi
    
    log "INFO" "All dependencies are satisfied"
}

# Pre-execution setup
setup_execution_environment() {
    log "INFO" "Setting up execution environment..."
    
    # Set up git configuration if not exists
    if ! git config --global user.name >/dev/null 2>&1; then
        git config --global user.name "AutoGen AI Agent"
        git config --global user.email "ai-agent@company.com"
        log "INFO" "Git configuration initialized"
    fi
    
    # Create required directories
    mkdir -p /app/downloads /app/repo
    
    # Set permissions
    chmod 755 /app/downloads /app/repo
    
    log "INFO" "Execution environment ready"
}

# IP Protection Notice
display_ip_notice() {
    cat << 'EOF'
================================================================================
    AutoGen AI Code Correction Agent - Proprietary IP
================================================================================
    
    🤖 CONFIDENTIAL SOFTWARE - UNAUTHORIZED USE PROHIBITED
    
    This container contains proprietary artificial intelligence technology
    for automated code quality improvement and defect resolution.
    
    Copyright © 2024 - All Rights Reserved
    Licensed for authorized use only.
    
    Contact: licensing@company.com for usage rights
    
================================================================================
EOF
}

# Main execution function
main() {
    log "INFO" "Starting AutoGen AI Code Correction Agent"
    
    # Display IP notice
    display_ip_notice
    
    # Run validation and setup
    validate_environment
    check_dependencies
    setup_execution_environment
    
    log "INFO" "Launching AI code correction pipeline..."
    
    # Store PID for cleanup
    echo $$ > "${PID_FILE}"
    
    # Execute the agent with output redirection
    if [[ "${1:-}" == "python" && "${2:-}" == "autogen_agent.py" ]]; then
        # Direct execution
        python autogen_agent.py 2>&1 | tee -a "${LOG_FILE}"
    elif [[ -n "${1:-}" ]]; then
        # Custom command execution
        log "INFO" "Executing custom command: $*"
        exec "$@" 2>&1 | tee -a "${LOG_FILE}"
    else
        # Default agent execution
        python autogen_agent.py 2>&1 | tee -a "${LOG_FILE}"
    fi
    
    local exit_code=$?
    
    # Cleanup PID file
    rm -f "${PID_FILE}"
    
    if [[ ${exit_code} -eq 0 ]]; then
        log "INFO" "AI code correction completed successfully"
        log "INFO" "Generated reports are available in /app/downloads"
        log "INFO" "Full execution log: ${LOG_FILE}"
    else
        log "ERROR" "AI code correction failed with exit code ${exit_code}"
        exit ${exit_code}
    fi
}

# Execute main function with all arguments
main "$@"
