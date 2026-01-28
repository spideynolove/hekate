#!/usr/bin/env bash
# Hekate Prerequisites Setup Script
# Automates installation of Beads, Superpowers, and MCPorter

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

success() { echo -e "${GREEN}✓ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
info() { echo -e "${BLUE}ℹ $1${NC}"; }

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/debian_version ]; then
            echo "debian"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)

# Install Go if not present
install_go() {
    if command_exists go; then
        success "Go already installed ($(go version))"
        return
    fi

    info "Installing Go..."
    case "$OS" in
        "macos")
            if command_exists brew; then
                brew install go
            else
                error "Homebrew not found. Please install from https://brew.sh/"
                exit 1
            fi
            ;;
        "debian"|"linux")
            wget https://go.dev/dl/go1.23.0.linux-amd64.tar.gz
            sudo tar -C /usr/local -xzf go1.23.0.linux-amd64.tar.gz
            echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
            export PATH=$PATH:/usr/local/go/bin
            ;;
    esac
    success "Go installed"
}

# Install Node.js if not present
install_nodejs() {
    if command_exists node && command_exists npm; then
        success "Node.js already installed ($(node --version))"
        return
    fi

    info "Installing Node.js..."
    case "$OS" in
        "macos")
            if command_exists brew; then
                brew install node
            else
                error "Homebrew not found. Please install from https://brew.sh/"
                exit 1
            fi
            ;;
        "debian"|"linux")
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y nodejs
            ;;
    esac
    success "Node.js installed"
}

# Check and install Beads CLI
check_beads() {
    echo ""
    info "Checking Beads CLI..."
    if command_exists bd; then
        success "Beads CLI already installed ($(bd --version))"
        return 0
    fi

    warn "Beads CLI not found"

    # Offer to install
    read -p "Install Beads CLI? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Installing Beads CLI..."

        if command_exists brew; then
            brew install beads
        elif command_exists go; then
            go install github.com/steveyegge/beads/cmd/bd@latest
            export PATH=$PATH:$(go env GOPATH)/bin
            echo 'export PATH=$PATH:$(go env GOPATH)/bin' >> ~/.bashrc
        else
            error "Neither Homebrew nor Go found. Cannot install Beads."
            error "Install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            return 1
        fi

        if command_exists bd; then
            success "Beads CLI installed successfully"
        else
            error "Beads CLI installation failed"
            return 1
        fi
    else
        warn "Skipping Beads CLI installation"
    fi
    return 0
}

# Check and install Superpowers
check_superpowers() {
    echo ""
    info "Checking Superpowers plugin..."

    # Check if marketplace is registered
    if command_exists claude && claude plugin list 2>/dev/null | grep -q marketplace; then
        if command_exists claude && claude /help 2>/dev/null | grep -q superpowers; then
            success "Superpowers plugin already installed"
            return 0
        fi
    fi

    warn "Superpowers plugin not found"

    # Offer to install
    read -p "Install Superpowers plugin? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Installing Superpowers plugin..."

        # Check if marketplace is registered
        if ! command_exists claude || ! claude plugin list 2>/dev/null | grep -q marketplace; then
            info "Registering Superpowers marketplace..."
            claude /plugin marketplace add obra/superpowers-marketplace || {
                error "Failed to register marketplace"
                return 1
            }
        fi

        # Install from marketplace
        claude /plugin install superpowers@superpowers-marketplace || {
            error "Failed to install Superpowers"
            return 1
        }

        if claude /help 2>/dev/null | grep -q superpowers; then
            success "Superpowers plugin installed successfully"
        else
            warn "Superpowers installed but not yet showing in /help"
        fi
    else
        warn "Skipping Superpowers installation"
    fi
    return 0
}

# Check and install MCPorter
check_mcporter() {
    echo ""
    info "Checking MCPorter..."

    if command_exists mcporter; then
        success "MCPorter already installed ($(mcporter --version))"
        return 0
    fi

    warn "MCPorter not found (optional but recommended)"

    # Offer to install
    read -p "Install MCPorter? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command_exists npm; then
            info "Installing MCPorter (optional - for token optimization)..."
            npm install -g @mcporter/mcporter

            if command_exists mcporter; then
                success "MCPorter installed successfully"

                # Offer to initialize
                read -p "Initialize MCPorter configuration? [y/N] " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    mcporter init
                    success "MCPorter initialized"
                else
                    info "Skipping MCPorter initialization"
                fi
            else
                warn "MCPorter installation may have failed"
            fi
        else
            warn "npm not found. Skipping MCPorter installation."
        fi
    else
        info "Skipping MCPorter installation"
    fi
    return 0
}

# Check Redis
check_redis() {
    echo ""
    info "Checking Redis..."

    if command_exists redis-cli && redis-cli ping >/dev/null 2>&1; then
        success "Redis is running"
        return 0
    elif command_exists redis-cli; then
        warn "Redis installed but not running"
        read -p "Start Redis? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if command_exists systemctl; then
                sudo systemctl start redis-server || sudo systemctl start redis
            else
                redis-server --daemonize yes
            fi
            if redis-cli ping >/dev/null 2>&1; then
                success "Redis started"
            else
                warn "Redis failed to start"
            fi
        fi
    else
        warn "Redis not found"
        read -p "Install Redis? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            case "$OS" in
                "macos")
                    brew install redis
                    brew services start redis
                    ;;
                "debian"|"linux")
                    sudo apt update
                    sudo apt install -y redis-server
                    sudo systemctl start redis
                    ;;
            esac
            if command_exists redis-cli && redis-cli ping >/dev/null 2>&1; then
                success "Redis installed and started"
            else
                warn "Redis installation may have failed"
            fi
        fi
    fi
    return 0
}

# Check Python and uv
check_python() {
    echo ""
    info "Checking Python environment..."

    if command_exists python3 || command_exists python; then
        success "Python found"
    else
        error "Python not found"
        return 1
    fi

    if command_exists uv; then
        success "uv package manager found"
    else
        warn "uv not found (recommended for Python dependency management)"
        read -p "Install uv? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            info "Installing uv..."
            curl -LsSf https://astral.sh/uv/install.sh | sh
            success "uv installed"
        fi
    fi
    return 0
}

# Copy Hekate config
check_config() {
    echo ""
    info "Checking Hekate configuration..."

    CONFIG_DIR="$HOME/.hekate"
    CONFIG_FILE="$CONFIG_DIR/config.yaml"

    if [ -f "$CONFIG_FILE" ]; then
        success "Hekate config exists at $CONFIG_FILE"
        return 0
    fi

    warn "Hekate config not found"
    read -p "Create Hekate config directory and copy default config? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p "$CONFIG_DIR"

        # Find the config file in the package
        if [ -f "src/hekate/config.yaml" ]; then
            cp src/hekate/config.yaml "$CONFIG_FILE/"
            success "Config copied to $CONFIG_FILE"
            info "Edit $CONFIG_FILE with your API keys before running Hekate"
        else
            error "Default config not found at src/hekate/config.yaml"
            return 1
        fi
    fi
    return 0
}

# Main installation flow
main() {
    clear
    echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     Hekate Prerequisites Setup                      ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "This script will check for and optionally install:"
    echo "  • Beads CLI (required)"
    echo "  • Superpowers plugin (required)"
    echo "  • MCPorter (optional, recommended)"
    echo "  • Redis (required)"
    echo "  • Python + uv (required)"
    echo ""
    echo "OS detected: $OS"
    echo ""

    # Check/install prerequisites
    check_python
    check_redis
    check_beads
    check_superpowers
    check_mcporter
    check_config

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║               Setup Complete!                    ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit ~/.hekate/config.yaml with your API keys"
    echo "  2. Source ~/.bashrc to reload provider functions"
    echo "  3. Run: hekate"
    echo ""

    # Show status summary
    echo -e "${BLUE}Status Summary:${NC}"
    echo "  Beads CLI: $(command_exists bd && echo "✓ Installed" || echo "✗ Not installed")"
    echo "  Superpowers: $(claude /plugin list 2>/dev/null | grep -q superpowers && echo "✓ Installed" || echo "✗ Not installed")"
    echo "  MCPorter: $(command_exists mcporter && echo "✓ Installed" || echo "✗ Not installed")"
    echo "  Redis: $(redis-cli ping >/dev/null 2>&1 && echo "✓ Running" || command_exists redis-cli && echo "⚠ Installed but not running" || echo "✗ Not installed")"
    echo "  Python: $(command_exists python3 || command_exists python && echo "✓ Found" || echo "✗ Not found")"
}

# Run main
main "$@"
