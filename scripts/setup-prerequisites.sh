#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

ask_yes_no() {
    local prompt="$1"
    local default="${2:-n}"
    local yn

    if [[ "$default" == "y" ]]; then
        prompt="$prompt [Y/n]"
    else
        prompt="$prompt [y/N]"
    fi

    while true; do
        read -rp "$prompt " yn
        yn=${yn:-$default}
        case $yn in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo "Please answer yes or no." ;;
        esac
    done
}

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ -f /etc/debian_version ]]; then
        echo "debian"
    elif [[ -f /etc/redhat-release ]]; then
        echo "redhat"
    else
        echo "linux"
    fi
}

check_command() {
    command -v "$1" &>/dev/null
}

check_docker_running() {
    check_command docker && docker info &>/dev/null
}

check_redis_available() {
    if check_command redis-cli && redis-cli ping &>/dev/null; then
        return 0
    fi
    if check_docker_running && docker ps --format '{{.Names}}' | grep -q '^redis$'; then
        return 0
    fi
    return 1
}

detect_python_setup() {
    local has_python=0
    local has_uv=0
    local python_path=""

    if check_command python3; then
        has_python=1
        python_path=$(command -v python3)
    fi

    if check_command uv; then
        has_uv=1
    fi

    echo "$has_python|$has_uv|$python_path"
}

detect_node_setup() {
    local has_node=0
    local has_npm=0
    local node_path=""
    local install_method=""

    if check_command node; then
        has_node=1
        node_path=$(command -v node)
    fi

    if check_command npm; then
        has_npm=1
    fi

    if [[ -n "${NVM_DIR:-}" ]] || check_command nvm; then
        install_method="nvm"
    elif check_command brew && [[ -d "$(brew --prefix)/opt/node" ]]; then
        install_method="brew"
    elif check_command docker; then
        install_method="docker"
    fi

    echo "$has_node|$has_npm|$node_path|$install_method"
}

detect_go_setup() {
    local has_go=0
    local go_path=""
    local install_method=""

    if check_command go; then
        has_go=1
        go_path=$(command -v go)
    fi

    if [[ -d "$HOME/go" ]]; then
        install_method="local"
    elif check_command docker; then
        install_method="docker"
    fi

    echo "$has_go|$go_path|$install_method"
}

log_info "Hekate Prerequisites Check"
log_info "============================"
echo

OS=$(detect_os)
log_info "Detected OS: $OS"
echo

log_info "Checking existing installations..."
echo

REDIS_AVAILABLE=0
if check_redis_available; then
    REDIS_AVAILABLE=1
    log_success "Redis: Available (running)"
    if check_docker_running && docker ps --format '{{.Names}}' | grep -q '^redis$'; then
        log_info "  └─ Running in Docker"
    fi
elif check_command redis-cli; then
    log_warn "Redis: Installed but not running"
    if check_docker_running; then
        log_info "  └─ Docker is available - can run Redis in container"
    fi
elif check_docker_running; then
    log_warn "Redis: Not found (but Docker available)"
else
    log_warn "Redis: Not found"
fi

PYTHON_SETUP=$(detect_python_setup)
IFS='|' read -r HAS_PYTHON HAS_UV PYTHON_PATH <<< "$PYTHON_SETUP"
if [[ $HAS_PYTHON -eq 1 ]]; then
    log_success "Python: Found at $PYTHON_PATH"
else
    log_warn "Python: Not found"
fi
if [[ $HAS_UV -eq 1 ]]; then
    log_success "uv: Found ($(uv --version 2>&1 | head -1))"
else
    log_warn "uv: Not found"
fi

NODE_SETUP=$(detect_node_setup)
IFS='|' read -r HAS_NODE HAS_NPM NODE_PATH NODE_METHOD <<< "$NODE_SETUP"
if [[ $HAS_NODE -eq 1 ]]; then
    log_success "Node.js: Found at $NODE_PATH"
    if [[ -n "$NODE_METHOD" ]]; then
        log_info "  └─ Install method: $NODE_METHOD"
    fi
else
    log_warn "Node.js: Not found"
fi

GO_SETUP=$(detect_go_setup)
IFS='|' read -r HAS_GO GO_PATH GO_METHOD <<< "$GO_SETUP"
if [[ $HAS_GO -eq 1 ]]; then
    log_success "Go: Found at $GO_PATH"
    if [[ -n "$GO_METHOD" ]]; then
        log_info "  └─ Install method: $GO_METHOD"
    fi
else
    log_warn "Go: Not found"
fi

if check_command bd; then
    log_success "Beads CLI: Already installed"
else
    log_warn "Beads CLI: Not found"
fi

if check_command claude && [[ "$(claude plugin list 2>/dev/null)" =~ superpowers ]]; then
    log_success "Superpowers: Already installed"
elif check_command claude; then
    log_warn "Superpowers: Not installed (Claude Code available)"
else
    log_warn "Claude Code: Not found (required for Superpowers)"
fi

if check_command mcporter || npm list -g @mcporter/mcporter &>/dev/null; then
    log_success "MCPorter: Already installed"
else
    log_info "MCPorter: Not found (optional)"
fi

echo
log_info "============================"
echo

if [[ $REDIS_AVAILABLE -eq 0 ]]; then
    log_warn "Redis is required but not available."
    if check_docker_running; then
        if ask_yes_no "Start Redis in Docker container?" "y"; then
            log_info "Starting Redis in Docker..."
            docker run -d --name redis -p 6379:6379 redis:alpine
            log_success "Redis started in Docker"
            REDIS_AVAILABLE=1
        fi
    else
        log_info "To start Redis manually:"
        echo "  - macOS: brew services start redis"
        echo "  - Debian/Ubuntu: sudo systemctl start redis-server"
        echo "  - Docker: docker run -d --name redis -p 6379:6379 redis:alpine"
    fi
    echo
fi

if [[ $HAS_GO -eq 0 ]] && ! check_command bd; then
    log_warn "Beads CLI requires Go."
    if check_docker_running && ask_yes_no "Use Docker for Go tools instead?" "n"; then
        log_info "You can run Beads CLI in Docker:"
        echo "  docker run --rm -v \${PWD}:/app -w /app golang:latest go install github.com/steveyegge/beads/cmd/bd@latest"
        log_warn "Note: Go tools in Docker will need \$GOPATH mounted for persistence."
    elif ask_yes_no "Install Go now?" "n"; then
        log_info "Install Go from https://go.dev/dl/ or:"
        case $OS in
            macos)
                echo "  brew install go"
                ;;
            debian)
                echo "  sudo apt install golang-go"
                ;;
            *)
                echo "  Visit https://go.dev/dl/"
                ;;
        esac
        log_warn "After installing Go, run: go install github.com/steveyegge/beads/cmd/bd@latest"
    fi
    echo
fi

if [[ $HAS_GO -eq 1 ]] && ! check_command bd; then
    if ask_yes_no "Install Beads CLI via go install?" "y"; then
        log_info "Installing Beads CLI..."
        go install github.com/steveyegge/beads/cmd/bd@latest
        log_success "Beads CLI installed to $(go env GOPATH)/bin/bd"
        log_warn "Ensure \$(go env GOPATH)/bin is in your PATH"
    fi
    echo
fi

if ! check_command claude; then
    log_warn "Claude Code not found. Required for Superpowers."
    log_info "Install from: https://claude.ai/code"
    echo
fi

if check_command claude && ! [[ "$(claude plugin list 2>/dev/null)" =~ superpowers ]]; then
    if ask_yes_no "Install Superpowers plugin?" "y"; then
        log_info "Installing Superpowers..."
        claude plugin add superpowers
        log_success "Superpowers installed"
    fi
    echo
fi

if ! check_command mcporter && [[ $HAS_NODE -eq 1 ]]; then
    if ask_yes_no "Install MCPorter? (Optional - reduces token usage by ~43%)" "n"; then
        log_info "Installing MCPorter..."
        npm install -g @mcporter/mcporter
        log_success "MCPorter installed"
    fi
    echo
fi

echo
log_info "============================"
log_info "Setup complete!"
echo

log_info "Next steps:"
echo "  1. Ensure all required tools are in your PATH"
echo "  2. Configure provider functions in ~/.bashrc:"
echo "     export ANTHROPIC_AUTH_TOKEN='your-api-key'"
echo "  3. Copy and edit Hekate config:"
echo "     mkdir -p ~/.hekate"
echo "     cp src/hekate/config.yaml ~/.hekate/"
echo "     nano ~/.hekate/config.yaml"
echo
