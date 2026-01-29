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

log_info "Hekate Hooks Installation"
log_info "==========================="
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HOOKS_SRC="$PROJECT_ROOT/hooks"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"

# Check if hooks directory exists
if [ ! -d "$HOOKS_SRC" ]; then
    log_error "Hooks source directory not found: $HOOKS_SRC"
    exit 1
fi

# Create Claude hooks directory
log_info "Creating hooks directory at $CLAUDE_HOOKS_DIR..."
mkdir -p "$CLAUDE_HOOKS_DIR"
log_success "Hooks directory ready"

# Copy hooks
log_info "Copying Hekate hooks..."
cp "$HOOKS_SRC"/*.py "$CLAUDE_HOOKS_DIR/"
chmod +x "$CLAUDE_HOOKS_DIR"/*.py
log_success "Hooks copied and made executable"

# List installed hooks
echo
log_info "Installed hooks:"
for hook in "$CLAUDE_HOOKS_DIR"/*.py; do
    if [ -f "$hook" ]; then
        log_success "  $(basename "$hook")"
    fi
done

# Update settings.json
log_info "Updating Claude Code settings..."
SETTINGS_FILE="$HOME/.claude/settings.json"

# Backup existing settings
if [ -f "$SETTINGS_FILE" ]; then
    cp "$SETTINGS_FILE" "$SETTINGS_FILE.hekate-backup-$(date +%s)"
    log_info "Backed up existing settings to $SETTINGS_FILE.hekate-backup-<timestamp>"
fi

# Create or update settings.json with Hekate hooks
python3 - <<EOF
import json
import os

settings_file = "$SETTINGS_FILE"
claude_hooks_dir = "$CLAUDE_HOOKS_DIR"

# Hekate hooks configuration
hekate_hooks = {
    "hooks": {
        "SessionStart": [{
            "matcher": "startup|resume",
            "hooks": [{
                "type": "command",
                "command": f"python3 {claude_hooks_dir}/sessionstart_init.py"
            }]
        }],
        "UserPromptSubmit": [{
            "hooks": [{
                "type": "command",
                "command": f"python3 {claude_hooks_dir}/userpromptsubmit_decompose.py",
                "timeout": 30
            }]
        }],
        "PreToolUse": [{
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/pretooluse_router.py",
                    "timeout": 2
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/pretooluse_memory.py",
                    "timeout": 3
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/pretooluse_verify_inject.py",
                    "timeout": 3
                }
            ]
        }],
        "PostToolUse": [{
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_spawn_agents.py",
                    "async": True,
                    "timeout": 60
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_complete_task.py",
                    "async": True,
                    "timeout": 10
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_track_outcome.py",
                    "async": True,
                    "timeout": 5
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_memory.py",
                    "async": True,
                    "timeout": 3
                }
            ]
        },
        {
            "matcher": "Write|Edit",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_track_outcome.py",
                    "async": True,
                    "timeout": 5
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_verify_prefetch.py",
                    "async": True,
                    "timeout": 10
                },
                {
                    "type": "command",
                    "command": f"python3 {claude_hooks_dir}/posttooluse_metrics.py",
                    "async": True,
                    "timeout": 3
                }
            ]
        },
        {
            "matcher": "Read|Grep|Glob",
            "hooks": [{
                "type": "command",
                "command": f"python3 {claude_hooks_dir}/posttooluse_track_outcome.py",
                "async": True,
                "timeout": 5
            }]
        }]
    }
}

# Load existing settings
try:
    with open(settings_file, 'r') as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
except json.JSONDecodeError:
    print("Warning: Existing settings.json is invalid, creating new one", file=sys.stderr)
    settings = {}

# Merge hooks (deep merge for hooks key)
if 'hooks' in settings:
    # Merge existing hooks with Hekate hooks
    for event, hooks_list in hekate_hooks['hooks'].items():
        if event not in settings['hooks']:
            settings['hooks'][event] = []
        settings['hooks'][event].extend(hooks_list)
else:
    settings['hooks'] = hekate_hooks['hooks']

# Write updated settings
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print("Settings updated successfully")
EOF

if [ $? -eq 0 ]; then
    log_success "Claude Code settings updated"
else
    log_error "Failed to update settings.json"
    exit 1
fi

echo
log_info "==========================="
log_success "Hekate hooks installation complete!"
echo
log_info "Next steps:"
echo "  1. Initialize Redis: ./scripts/init-redis.sh"
echo "  2. Restart Claude Code to load hooks"
echo "  3. Test: 'create epic: Build hello world app'"
echo
log_warn "Note: Make sure you have OPENROUTER_API_KEY set for epic decomposition"
echo
