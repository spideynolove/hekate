# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hekate is an autonomous multi-agent development system that orchestrates AI coding agents across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter) with intelligent routing, quota management, and 24/7 autonomous development capabilities.

## Architecture

The system follows a layered architecture:
- **User Layer**: Epic creation via Beads CLI
- **Supervisor Layer**: Python orchestrator managing agent pools and routing
- **Agent Layer**: 14 concurrent agents (2 Claude, 4 GLM, 6 DeepSeek, 2 OpenRouter)
- **Execution Layer**: Isolated Git worktrees with TDD enforcement via Superpowers
- **Verification Layer**: Staged cascade from cheap to expensive providers

Key components in `supervisor/`:
- `supervisor.py` - Main orchestrator
- `quota.py` - Quota tracking with Redis persistence
- `router.py` - Provider-aware routing based on complexity/quota
- `agent.py` - Process management for agent pools
- `beads.py` - Beads task graph client
- `verifier.py` - Multi-stage verification cascade
- `mcporter_helper.py` - Token optimization via MCPorter

## Development Commands

# Install dependencies
cd supervisor && pip install -r requirements.txt

# Run all unit tests
cd supervisor && pytest tests/ -v

# Run integration tests
cd supervisor && pytest tests/test_integration.py -v -m integration

# Start supervisor
cd supervisor && python supervisor.py

# Health check
hekate --health-check  # or ~/.local/bin/hekate-health-check

## Environment Setup

Requires Python 3.10+, Redis 7+, and external tools (Beads CLI, Superpowers, MCPorter).

### Prerequisites Installation

Hekate requires external tools (Beads CLI, Superpowers, MCPorter, Redis, Python).

**Automated setup (recommended):**
```bash
./scripts/setup-prerequisites.sh
```

This interactive script detects your OS and installs all prerequisites with prompts.

**Manual setup:**
See individual tool documentation below for manual installation.

#### 1. Beads CLI
Task management system for AI agents. Required for epic/task orchestration.

[Documentation](https://github.com/steveyegge/beads)

#### 2. Superpowers Plugin
Claude Code plugin for autonomous development enforcement (TDD, quality gates).

[Documentation](https://github.com/anthropics/claude-code/blob/main/plugins/README.md)

#### 3. MCPorter (Optional)
Token optimization for on-demand MCP tool invocation. Reduces token usage by ~43%.

[Documentation](https://github.com/steipete/mcporter)

### Hekate Installation

```bash
# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Create virtual environment
uv venv
source .venv/bin/activate

# Install Hekate
uv pip install -e .

# Copy default config
mkdir -p ~/.hekate
cp src/hekate/config.yaml ~/.hekate/

# Edit config with your API keys
nano ~/.hekate/config.yaml
```

### API Keys Configuration

Configure provider functions in `~/.bashrc`:

```bash
# Source secrets (optional - if you keep keys separate)
if [ -f ~/.secrets ]; then
    source ~/.secrets
fi

# DeepSeek (free tier)
deepseek() {
    export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
    export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY}"
    claude "$@"
}

# Z.AI GLM (medium tier)
glm() {
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export ANTHROPIC_AUTH_TOKEN="${Z_AI_API_KEY}"
    claude "$@"
}

# OpenRouter (fallback/API)
opr() {
    export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
    export ANTHROPIC_AUTH_TOKEN="${OPENROUTER_API_KEY}"
    claude "$@"
}
```

Then reload: `source ~/.bashrc`