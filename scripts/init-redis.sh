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

log_info "Hekate Redis Initialization"
log_info "=============================="
echo

# Check if Redis is available
if ! command -v redis-cli &>/dev/null; then
    log_error "redis-cli not found. Please install Redis first:"
    echo "  - macOS: brew install redis && brew services start redis"
    echo "  - Debian/Ubuntu: sudo apt install redis-server && sudo systemctl start redis"
    echo "  - Docker: docker run -d --name redis -p 6379:6379 redis:alpine"
    exit 1
fi

# Test Redis connection
if ! redis-cli ping &>/dev/null; then
    log_error "Redis is not running. Please start Redis:"
    echo "  - macOS: brew services start redis"
    echo "  - Debian/Ubuntu: sudo systemctl start redis-server"
    echo "  - Docker: docker start redis"
    exit 1
fi

log_success "Redis is running"

# Clear any existing Hekate data
log_info "Checking for existing Hekate data..."
EXISTING_KEYS=$(redis-cli --scan --pattern 'hekate:*' 2>/dev/null | wc -l)
if [ "$EXISTING_KEYS" -gt 0 ]; then
    log_warn "Found $EXISTING_KEYS existing Hekate keys"
    read -p "Clear existing data? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        redis-cli --scan --pattern 'hekate:*' | xargs redis-cli del
        log_success "Cleared existing Hekate data"
    else
        log_info "Keeping existing data"
    fi
fi

# Initialize provider quota limits
log_info "Initializing provider quotas..."

echo
log_info "Enter your provider quota limits (or press Enter for defaults):"
read -p "Claude quota [50]: " CLAUDE_QUOTA
CLAUDE_QUOTA=${CLAUDE_QUOTA:-50}

read -p "GLM quota [100]: " GLM_QUOTA
GLM_QUOTA=${GLM_QUOTA:-100}

read -p "DeepSeek quota [1000]: " DEEPSEEK_QUOTA
DEEPSEEK_QUOTA=${DEEPSEEK_QUOTA:-1000}

read -p "OpenRouter quota [100]: " OPENROUTER_QUOTA
OPENROUTER_QUOTA=${OPENROUTER_QUOTA:-100}

echo
log_info "Setting quota limits..."

# Set quota limits with 24-hour TTL
redis-cli SET "quota:claude:limit" "$CLAUDE_QUOTA" > /dev/null
redis-cli SET "quota:glm:limit" "$GLM_QUOTA" > /dev/null
redis-cli SET "quota:deepseek:limit" "$DEEPSEEK_QUOTA" > /dev/null
redis-cli SET "quota:openrouter:limit" "$OPENROUTER_QUOTA" > /dev/null

# Initialize counters to 0
redis-cli SET "quota:claude:count" "0" > /dev/null
redis-cli SET "quota:glm:count" "0" > /dev/null
redis-cli SET "quota:deepseek:count" "0" > /dev/null
redis-cli SET "quota:openrouter:count" "0" > /dev/null

# Set window start time
WINDOW_START=$(date +%s)
redis-cli SET "quota:claude:window_start" "$WINDOW_START" > /dev/null
redis-cli SET "quota:glm:window_start" "$WINDOW_START" > /dev/null
redis-cli SET "quota:deepseek:window_start" "$WINDOW_START" > /dev/null
redis-cli SET "quota:openrouter:window_start" "$WINDOW_START" > /dev/null

log_success "Quota limits initialized"

# Initialize complexity-to-provider mapping
log_info "Initializing complexity-to-provider mapping..."

cat > /tmp/hekate_complexity_mapping.json <<'EOF'
{
  "1": "deepseek",
  "2": "deepseek",
  "3": "deepseek",
  "4": "deepseek",
  "5": "glm",
  "6": "glm",
  "7": "glm",
  "8": "claude",
  "9": "claude",
  "10": "claude"
}
EOF

for complexity in {1..10}; do
    provider=$(cat /tmp/hekate_complexity_mapping.json | grep "\"$complexity\"" | cut -d'"' -f4)
    redis-cli SET "routing:complexity:$complexity" "$provider" > /dev/null
done

rm -f /tmp/hekate_complexity_mapping.json

log_success "Complexity mapping initialized"

# Set up worktrees directory
WORKTREES_DIR="$HOME/hekate-worktrees"
log_info "Creating worktrees directory at $WORKTREES_DIR..."
mkdir -p "$WORKTREES_DIR"
log_success "Worktrees directory ready"

echo
log_info "=============================="
log_success "Hekate Redis initialization complete!"
echo
log_info "Next steps:"
echo "  1. Run ./scripts/install-hooks.sh to install Claude Code hooks"
echo "  2. Restart Claude Code to load hooks"
echo "  3. Create an epic: 'Create epic: My first epic'"
echo
