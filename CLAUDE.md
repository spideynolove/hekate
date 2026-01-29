# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hekate is a **hooks-based autonomous multi-agent system** that runs entirely within Claude Code. It orchestrates AI coding agents across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter) with intelligent routing, semantic memory, and verification cascades.

## Architecture (Hooks-Based)

**No supervisor daemon** - Claude Code hooks coordinate everything via Redis.

### Key Components

- **Beads CLI**: Task management and dependency tracking
- **Redis**: Shared state for coordination
- **11 Hooks**: Coordinate epic decomposition, agent spawning, routing, memory, verification
- **5 Scripts**: Installation, monitoring, analysis

### Hook Types

| Hook | Purpose |
|------|---------|
| `sessionstart_init.py` | Agent initialization |
| `userpromptsubmit_decompose.py` | Epic decomposition |
| `pretooluse_router.py` | Provider routing + quota |
| `pretooluse_memory.py` | Inject semantic memories |
| `pretooluse_verify_inject.py` | Inject verification results |
| `posttooluse_spawn_agents.py` | Spawn parallel agents |
| `posttooluse_complete_task.py` | Detect task completion |
| `posttooluse_track_outcome.py` | Track routing outcomes |
| `posttooluse_memory.py` | Store solutions in memory |
| `posttooluse_verify_prefetch.py` | Start verification |
| `posttooluse_metrics.py` | Collect metrics |

## Development Commands

# Initialize Redis with quota limits
./scripts/init-redis.sh

# Install Claude Code hooks
./scripts/install-hooks.sh

# Real-time dashboard
./scripts/hekate-dashboard.py

# Pattern analysis
./scripts/hekate-analyze.py

# Prometheus metrics export
./scripts/hekate-dashboard.py --prometheus

## Environment Setup

Requires Python 3.10+, Redis 7+, and external tools (Beads CLI, Superpowers, MCPorter).

### Prerequisites Installation

**Automated setup (recommended):**
```bash
./scripts/setup-prerequisites.sh
```

**Manual setup:**
- **Beads CLI**: `brew install beads` or `go install github.com/steveyegge/beads/cmd/bd@latest`
- **Superpowers**: `claude plugin add superpowers`
- **MCPorter**: `npm install -g @mcporter/mcporter` (optional)
- **Redis**: `brew install redis` or `docker run -d --name redis -p 6379:6379 redis:alpine`

## Installation & Setup

```bash
# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Initialize Redis
./scripts/init-redis.sh

# Install hooks
./scripts/install-hooks.sh

# Restart Claude Code to load hooks
```

### API Keys Configuration

Set in `~/.bashrc`:

```bash
# Required for epic decomposition
export OPENROUTER_API_KEY="sk-or-..."

# Required for providers
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."
```

## Provider Routing

| Complexity | Provider | Pool Size |
|------------|----------|-----------|
| 1-4 (low) | DeepSeek | 6 agents |
| 5-7 (medium) | GLM | 4 agents |
| 8-10 (high) | Claude | 2 agents |

## Redis Schema

```
# Epic state
epic:{id}:status → "planning" | "active" | "complete"
epic:{id}:task_count → integer
epic:{id}:complete_count → integer

# Task state
task:{id}:complexity → integer (1-10)
task:{id}:provider → "claude" | "glm" | "deepseek"
task:{id}:status → "pending" | "in_progress" | "complete"

# Agent tracking
agent:{pid}:task_id → task ID
agent:{pid}:provider → provider name
agent:{pid}:heartbeat → timestamp (TTL: 30s)

# Provider quota
quota:{provider}:count → integer
quota:{provider}:limit → integer
quota:{provider}:window_start → timestamp

# Routing & learning
routing:history → List of routing decisions
routing:pattern:{hash} → Learned pattern data
provider:stats:{provider} → JSON stats

# Semantic memory
memory:inbox:recent → List of learned patterns (1h TTL)
memory:inbox:type:{type} → Pattern-type inbox

# Verification
verify:prefetch:{task_id}:{provider} → Verification intent (10m TTL)

# Metrics
metrics:agent_tasks_total:{provider}:{complexity} → Counter
metrics:provider_quota_remaining:{provider} → Integer
alerts:quota_warning → JSON (5m TTL)
```

## Usage Pattern

1. **Create epic**: `create epic: Build authentication system`
2. **Automatic decomposition**: OpenRouter breaks epic into tasks with complexity
3. **Parallel agents**: 2 Claude + 4 GLM + 6 DeepSeek sessions spawned
4. **Smart routing**: Learned patterns guide provider selection
5. **Cross-agent learning**: Solutions shared via memory inbox
6. **Verification prefetch**: Async verification saves time
7. **Auto-completion**: Git commits trigger task completion

## Monitoring

```bash
# Real-time dashboard
./scripts/hekate-dashboard.py

# Pattern analysis
./scripts/hekate-analyze.py

# Redis queries
redis-cli keys "epic:*:status"
redis-cli keys "agent:*:heartbeat"
redis-cli lrange routing:history 0 9
redis-cli lrange memory:inbox:recent 0 9
```

## Key Design Decisions

### Beads Limitations & Workarounds

| Plan Feature | Beads Reality | Solution |
|-------------|---------------|----------|
| `--complexity` flag | Doesn't exist | Store in Redis separately |
| `--metadata` flag | Doesn't exist | Store in Redis separately |
| `--filter` flag | Doesn't exist | Filter in Python after `bd list --json` |

### Agent Spawning

Claude Code lacks `--project` and `--hook provider` flags:
- Spawn with `claude <worktree_path>`
- Set `HEKATE_TASK_ID` and `HEKATE_PROVIDER` environment variables
- SessionStart hook reads these to initialize agent

### Provider Switching

Environment variables set in PreToolUse hook:
```python
os.environ['ANTHROPIC_BASE_URL'] = "https://api.z.ai/api/anthropic"
os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ['Z_AI_API_KEY']
```

## File Structure

```
hekate/
├── hooks/                           # Claude Code hooks (11 files)
├── scripts/                         # Setup & monitoring (5 files)
├── src/hekate/
│   ├── __init__.py                 # BeadsClient export
│   ├── beads.py                    # Beads client library
│   └── config.yaml                 # Default configuration
├── docs/
│   └── plans/
│       ├── 2026-01-29-hooks-based-architecture.md
│       └── 2026-01-29-phase1-implementation.md
├── CLAUDE.md
└── README.md
```

## Common Patterns

### Creating an Epic

```bash
# In Claude Code
create epic: Add OAuth 2.0 authentication

# System automatically:
# 1. Decomposes epic into 5-10 tasks
# 2. Estimates complexity for each task
# 3. Creates tasks in Beads with priorities
# 4. Spawns parallel agents based on complexity
```

### Checking System Status

```bash
# Active epics
redis-cli keys "epic:*:status"

# Active agents
redis-cli keys "agent:*:heartbeat"

# Learned patterns
redis-cli keys "routing:pattern:*"

# Memory inbox
redis-cli lrange memory:inbox:recent 0 -1
```

### Resetting State

```bash
# Clear quota
redis-cli del quota:claude:count

# Clear learned patterns
redis-cli --scan --pattern "routing:pattern:*" | xargs redis-cli del

# Clear memory
redis-cli del memory:inbox:recent
```
