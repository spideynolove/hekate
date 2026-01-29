# Hekate: Hooks-Based Autonomous Multi-Agent Development System

Autonomous development system using Claude Code hooks, Beads orchestration, provider routing, and semantic memory.

## Overview

Hekate is now a **hooks-based system** that runs entirely within Claude Code. No supervisor daemon required.

**Architecture:**
- **Hooks-based orchestration**: Claude Code hooks coordinate all activity
- **Beads CLI**: Task management and dependency tracking
- **Redis**: Shared state for coordination
- **Multi-provider routing**: Claude, GLM, DeepSeek, OpenRouter
- **Semantic memory**: Cross-agent learning to prevent duplicate work
- **Verification cascade**: Async prefetch for 60% time savings

## Installation

### Prerequisites

```bash
# Automated setup (recommended)
./scripts/setup-prerequisites.sh
```

This installs:
- Beads CLI (task orchestration)
- Superpowers plugin (TDD enforcement)
- MCPorter (optional, token optimization)
- Redis (state management)
- Python + uv (dependencies)

### Setup

```bash
# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Initialize Redis with quota limits
./scripts/init-redis.sh

# Install Claude Code hooks
./scripts/install-hooks.sh

# Restart Claude Code to load hooks
```

### Configuration

Set environment variables in `~/.bashrc`:

```bash
# Provider API keys
export OPENROUTER_API_KEY="sk-or-..."  # For epic decomposition
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."
```

## Quick Start

```bash
# Create an epic (in Claude Code)
create epic: Build REST API for user authentication
```

**What happens automatically:**
1. **Epic decomposition**: OpenRouter breaks epic into tasks with complexity estimates
2. **Tasks created in Beads**: Each task gets a priority based on complexity
3. **Parallel agents spawned**: 2 Claude + 4 GLM + 6 DeepSeek sessions (by complexity)
4. **Provider routing**: Smart routing based on learned patterns + quota
5. **Semantic memory**: Agents learn from each other's solutions
6. **Verification cascade**: Async verification saves 60% time
7. **Task completion**: Git commits auto-detect completion

## Monitoring

### Real-Time Dashboard
```bash
./scripts/hekate-dashboard.py
```

Shows:
- Active agents (PID, provider, task, heartbeat)
- Epic progress (status, completion %)
- Quota status (visual bar chart, alerts)
- Alerts (quota warnings, stuck agents)

### Pattern Analysis
```bash
./scripts/hekate-analyze.py
```

Shows:
- Learned routing patterns
- Provider performance statistics
- Complexity-based success rates
- Recent routing decisions

### Redis Commands

```bash
# Quota status
redis-cli get quota:claude:count
redis-cli get quota:claude:limit

# Active agents
redis-cli keys "agent:*:heartbeat"

# Epic status
redis-cli keys "epic:*:status"

# Learned patterns
redis-cli keys "routing:pattern:*"

# Memory inbox
redis-cli lrange memory:inbox:recent 0 9
```

## Architecture

### Hooks-Based Workflow

```
User: "create epic: Build API"
  ↓
[UserPromptSubmit Hook]
  ├─ Call OpenRouter API for decomposition
  ├─ Create tasks in Beads with priorities
  └─ Store complexity in Redis
  ↓
[PostToolUse Hook - Async]
  ├─ Read pending tasks from Beads
  ├─ Group by complexity (1-4, 5-7, 8-10)
  ├─ Spawn Claude Code sessions with provider env vars
  └─ Track agents in Redis
  ↓
[SessionStart Hook - Each Agent]
  ├─ Load task context from Redis + Beads
  └─ Inject task details into agent
  ↓
[PreToolUse Hooks - Each Tool Use]
  ├─ Check quota and switch provider if needed
  ├─ Inject relevant semantic memories
  └─ Inject prefetched verification results
  ↓
[PostToolUse Hooks - Async]
  ├─ Track outcomes for learning
  ├─ Store solutions in shared memory
  └─ Start verification prefetch
  ↓
[Bash with git commit]
  ├─ Detect task completion
  ├─ Mark complete in Beads + Redis
  └─ Check if epic is complete
```

### Provider Routing

| Complexity | Provider | Rationale |
|------------|----------|-----------|
| 1-4 | DeepSeek | Fast, free tier |
| 5-7 | GLM | Medium cost, good quality |
| 8-10 | Claude | Premium, best for complex work |

### Redis Schema

```
# Epic state
epic:{id}:status → "planning" | "active" | "complete"
epic:{id}:task_count → integer
epic:{id}:complete_count → integer
epic:{id}:description → string

# Task state
task:{id}:complexity → integer (1-10)
task:{id}:epic_id → epic ID
task:{id}:provider → "claude" | "glm" | "deepseek"
task:{id}:status → "pending" | "in_progress" | "complete"
task:{id}:claimed → "true" | "false"

# Agent tracking
agent:{pid}:task_id → task ID
agent:{pid}:provider → provider name
agent:{pid}:heartbeat → timestamp (TTL: 30s)

# Provider quota
quota:{provider}:count → integer
quota:{provider}:limit → integer
quota:{provider}:window_start → timestamp

# Session mapping
session:{session_id}:task_id → task ID
session:{session_id}:provider → provider

# Phase 2: Enhanced routing
routing:history → List of routing decisions
routing:pattern:{hash} → Learned pattern data
provider:stats:{provider} → JSON stats
provider:complexity:{provider}:{N} → Complexity-specific stats

# Phase 3: Semantic memory
memory:inbox:recent → List of learned patterns (1h TTL)
memory:inbox:type:{type} → Pattern-type inbox (2h TTL)
memory:inbox:provider:{provider} → Provider-specific (1h TTL)

# Phase 4: Verification
verify:prefetch:{task_id}:{provider} → Verification intent/result (10m TTL)

# Phase 5: Metrics & alerts
metrics:agent_tasks_total:{provider}:{complexity} → Counter
metrics:provider_quota_remaining:{provider} → Integer
alerts:quota_warning → JSON (5m TTL)
```

## Hooks

### Session Hooks

| Hook | Purpose |
|------|---------|
| `sessionstart_init.py` | Agent initialization with task context |

### User Interaction Hooks

| Hook | Purpose |
|------|---------|
| `userpromptsubmit_decompose.py` | Epic decomposition via OpenRouter |

### Tool Hooks (Pre/Post)

| Hook | Purpose | Matcher |
|------|---------|---------|
| `pretooluse_router.py` | Provider routing + quota | `.*` |
| `pretooluse_memory.py` | Inject semantic memories | `.*` |
| `pretooluse_verify_inject.py` | Inject verification results | `.*` |
| `posttooluse_spawn_agents.py` | Spawn parallel agents (async) | `Bash` |
| `posttooluse_complete_task.py` | Detect task completion | `Bash` |
| `posttooluse_track_outcome.py` | Track routing outcomes (async) | `Bash`, `Write|Edit|Read|Grep|Glob` |
| `posttooluse_memory.py` | Store solutions in memory (async) | `Bash` |
| `posttooluse_verify_prefetch.py` | Start verification (async) | `Write|Edit` |
| `posttooluse_metrics.py` | Collect metrics (async) | `Write|Edit` |

## Provider Configuration

### API Keys

```bash
# Required for epic decomposition
export OPENROUTER_API_KEY="sk-or-..."

# Required for providers
export Z_AI_API_KEY="..."          # GLM
export DEEPSEEK_API_KEY="sk-..."     # DeepSeek
```

### Provider Functions

No wrapper functions needed - hooks manage provider switching via environment variables.

## File Structure

```
hekate/
├── hooks/                           # Claude Code hooks
│   ├── sessionstart_init.py
│   ├── userpromptsubmit_decompose.py
│   ├── pretooluse_router.py
│   ├── pretooluse_memory.py
│   ├── pretooluse_verify_inject.py
│   ├── posttooluse_spawn_agents.py
│   ├── posttooluse_complete_task.py
│   ├── posttooluse_track_outcome.py
│   ├── posttooluse_memory.py
│   ├── posttooluse_verify_prefetch.py
│   └── posttooluse_metrics.py
├── scripts/
│   ├── setup-prerequisites.sh    # Prerequisites installer
│   ├── init-redis.sh              # Redis initialization
│   ├── install-hooks.sh           # Hooks installation
│   ├── hekate-dashboard.py         # Real-time dashboard
│   └── hekate-analyze.py           # Pattern analysis
├── src/hekate/
│   ├── __init__.py                 # BeadsClient export
│   ├── beads.py                    # Beads client library
│   └── config.yaml                 # Default configuration
├── docs/
│   ├── plans/
│   │   ├── 2026-01-29-hooks-based-architecture.md
│   │   └── 2026-01-29-phase1-implementation.md
│   ├── ARCHITECTURE.md
│   └── USAGE.md
├── CLAUDE.md
└── README.md
```

## Documentation

- [Architecture Details](docs/ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)
- [Hooks Architecture Design](docs/plans/2026-01-29-hooks-based-architecture.md)
- [Phase 1 Implementation](docs/plans/2026-01-29-phase1-implementation.md)
