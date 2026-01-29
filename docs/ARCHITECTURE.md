# Architecture Details

## System Overview

Hekate is a **hooks-based autonomous multi-agent development system** that orchestrates AI agents across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter) entirely within Claude Code. No supervisor daemon required - all coordination happens through Claude Code hooks.

## Prerequisites

Hekate requires external tools to be installed separately.

**Automated setup (recommended):**
```bash
./scripts/setup-prerequisites.sh
```

| Tool | Purpose | Required |
|------|---------|----------|
| **Beads CLI** | Task orchestration | Yes |
| **Superpowers** | TDD enforcement, quality gates | Yes |
| **MCPorter** | Token optimization (43% reduction) | Optional |
| **Redis** | State management | Yes |
| **Python + uv** | Runtime and dependencies | Yes |

See [CLAUDE.md](../CLAUDE.md) for detailed manual installation instructions.

## Core Components

### Hooks-Based Orchestration

The system uses **Claude Code hooks** for all coordination. Hooks are Python scripts that receive JSON input via stdin and return JSON output via stdout.

#### Session Hooks

**sessionstart_init.py**: Initialize spawned agents with task context
- Detects Hekate-spawned agents via `HEKATE_TASK_ID` environment variable
- Loads task context from Redis + Beads
- Injects task details into agent session

#### User Interaction Hooks

**userpromptsubmit_decompose.py**: Epic decomposition via OpenRouter
- Detects "create epic:" patterns in user input
- Calls OpenRouter API for task breakdown with complexity estimates
- Creates tasks in Beads with priority-based on complexity
- Stores complexity mapping in Redis (Beads lacks --complexity flag)

#### Pre-Tool Hooks

**pretooluse_router.py**: Provider routing + quota management
- Checks quota before each tool use
- Switches provider via environment variables if quota exhausted
- Pattern-based routing using learned outcomes
- Complexity-based routing (1-4: DeepSeek, 5-7: GLM, 8-10: Claude)

**pretooluse_memory.py**: Inject semantic memories
- Searches memory inbox for relevant solutions
- Keyword-based relevance matching
- Age-aware filtering (skip >30min old)
- Injects max 5 relevant memories into context

**pretooluse_verify_inject.py**: Inject verification results
- Checks for async verification prefetch completion
- Formats verification results with provider/status/confidence
- Allows agents to act on prefetched verification

#### Post-Tool Hooks (async)

**posttooluse_spawn_agents.py**: Spawn parallel agents
- Reads pending tasks from Beads
- Groups by complexity tiers (1-4, 5-7, 8-10)
- Spawns Claude Code sessions with provider environment variables
- Tracks agents in Redis with heartbeat monitoring

**posttooluse_complete_task.py**: Detect task completion
- Monitors for git commit/git push commands
- Updates Beads task status to complete
- Marks tasks complete in Redis
- Checks if epic is fully complete

**posttooluse_track_outcome.py**: Track routing outcomes
- Records task features and routing decisions
- Stores in routing:history and routing:pattern:{hash}
- Builds ML dataset for provider selection learning
- Updates complexity-based success statistics

**posttooluse_memory.py**: Store solutions in memory
- Detects bug fixes, refactors, features in code changes
- Stores in shared memory inbox with TTL (1-2 hours)
- Enables cross-agent learning to prevent duplicate work

**posttooluse_verify_prefetch.py**: Start verification cascade
- Triggers after Write/Edit operations
- Complexity-based cascade: 1-4 (DeepSeek), 5-7 (DeepSeek→GLM), 8-10 (GLM→Claude)
- Async execution saves ~60% time through prefetch

**posttooluse_metrics.py**: Collect metrics
- Tracks task completion by provider/complexity
- Monitors quota remaining
- Generates alerts when quota ≤5

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

# Routing learning
routing:history → List of routing decisions
routing:pattern:{hash} → Learned pattern data
provider:stats:{provider} → JSON stats
provider:complexity:{provider}:{N} → Complexity-specific stats

# Semantic memory
memory:inbox:recent → List of learned patterns (1h TTL)
memory:inbox:type:{type} → Pattern-type inbox (2h TTL)
memory:inbox:provider:{provider} → Provider-specific (1h TTL)

# Verification cache
verify:prefetch:{task_id}:{provider} → Verification intent/result (10m TTL)

# Metrics & alerts
metrics:agent_tasks_total:{provider}:{complexity} → Counter
metrics:provider_quota_remaining:{provider} → Integer
alerts:quota_warning → JSON (5m TTL)
```

## Data Flow Architecture

```
User: "create epic: Build REST API"
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ UserPromptSubmit Hook                                            │
│  ├─ Call OpenRouter API for decomposition                       │
│  ├─ Create tasks in Beads with priorities                       │
│  └─ Store complexity in Redis (no --complexity flag in Beads)   │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ PostToolUse Hook (async) - Bash                                 │
│  ├─ Read pending tasks from Beads                               │
│  ├─ Group by complexity (1-4, 5-7, 8-10)                        │
│  ├─ Spawn Claude Code sessions with HEKATE_TASK_ID env var      │
│  └─ Track agents in Redis with heartbeat TTL                    │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ SessionStart Hook - Each Spawned Agent                          │
│  ├─ Detect HEKATE_TASK_ID environment variable                  │
│  ├─ Load task context from Redis + Beads                        │
│  └─ Inject task details into agent session                      │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ PreToolUse Hooks - Every Tool Use                               │
│  ├─ Check quota and switch provider if needed (env vars)        │
│  ├─ Inject relevant semantic memories (max 5)                   │
│  └─ Inject prefetched verification results                      │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ PostToolUse Hooks (async) - After Tool Use                      │
│  ├─ Track outcomes for routing learning                         │
│  ├─ Store solutions in shared memory (1-2h TTL)                │
│  ├─ Start verification prefetch (Write/Edit only)              │
│  └─ Collect metrics (task counts, quota remaining)             │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ PostToolUse Hook (async) - Git Commit Detection                 │
│  ├─ Detect "git commit" or "git push" commands                 │
│  ├─ Mark task complete in Beads + Redis                        │
│  └─ Check if epic is complete (all tasks done)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Provider Routing

### Complexity-Based Routing

| Complexity | Provider | Rationale |
|------------|----------|-----------|
| 1-4 | DeepSeek | Fast, free tier |
| 5-7 | GLM | Medium cost, good quality |
| 8-10 | Claude | Premium, best for complex work |

### Quota Management

- **5-hour rolling windows** for subscription providers
- **Buffer protection**: 20% (Claude), 3% (GLM) emergency reserves
- **Automatic cascade**: DeepSeek → GLM → OpenRouter → Claude for fallbacks
- **Dynamic switching**: Environment variable manipulation in PreToolUse hook

### Pattern-Based Learning

The system learns from routing outcomes:
- Exact feature hash matching for repeat patterns
- Complexity-based statistics for provider selection
- Minimum 3 attempts before pattern becomes usable
- Fallback to base routing if insufficient data

## Quality Assurance

### Verification Cascade

Complexity-based async prefetch saves ~60% time:

| Complexity | Cascade | Time Savings |
|------------|---------|--------------|
| 1-4 | DeepSeek only | Baseline |
| 5-7 | DeepSeek → GLM | ~40% (prefetch) |
| 8-10 | GLM → Claude | ~60% (prefetch) |

### Semantic Memory

- **Shared inbox** with 1-2 hour TTL for memory decay
- **Pattern types**: bugfix, test, refactor, feature
- **Relevance matching**: Keyword-based with age filtering
- **Cross-agent learning**: Prevents duplicate work across providers

### TDD Enforcement

- **Superpowers plugin** enforces red-green-refactor
- **Test before code**: No implementation without passing tests
- **Quality gates**: Lint, type check, test coverage

## Performance Characteristics

### Resource Requirements

| Component | CPU | RAM | I/O |
|-----------|-----|-----|-----|
| Claude Code | 1-2 cores | 500MB | Low |
| Agent Process | 2-4 cores | 1-2GB | Medium |
| Redis | 1 core | 256MB | High |
| Total (12 agents) | 12+ cores | 16-32GB | High |

### Scaling Limits

- **Concurrent agents**: 12 agents (2 Claude, 4 GLM, 6 DeepSeek)
- **Task throughput**: ~50-100 tasks/day depending on complexity
- **Cost optimization**: ~70% savings vs full Claude via routing

### Reliability Features

- **Atomic task claiming**: Redis prevents double execution
- **Agent heartbeats**: 30-second TTL detection
- **Graceful degradation**: Provider cascades for fallback
- **Error recovery**: Failed tasks re-queued for retry

## Monitoring & Observability

### Real-Time Dashboard

```bash
./scripts/hekate-dashboard.py
```

Shows:
- Active agents (PID, provider, task, heartbeat)
- Epic progress (status, completion %)
- Quota status (visual bar chart, alerts)
- Alerts (quota warnings, stuck agents)
- Prometheus metrics export (`--prometheus` flag)

### Pattern Analysis

```bash
./scripts/hekate-analyze.py
```

Shows:
- Learned routing patterns
- Provider performance statistics
- Complexity-based success rates
- Recent routing decisions

### Redis Inspection

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

## Deployment Architecture

### Directory Structure

```
~/.claude/                      # Claude Code config
├── hooks/                      # Installed hooks
│   ├── sessionstart_init.py
│   ├── userpromptsubmit_decompose.py
│   ├── pretooluse_*.py         # Pre-tool hooks
│   └── posttooluse_*.py        # Post-tool hooks
└── settings.json               # Hook registration

~/.hekate/                      # User data directory
└── config.yaml                 # Provider/quota config

/opt/hekate/                    # System installation (optional)
└── ...
```

### Production Deployment

1. **Automated setup**: Prerequisites + hooks installation
2. **Redis initialization**: `./scripts/init-redis.sh`
3. **Hooks registration**: `./scripts/install-hooks.sh`
4. **Restart Claude Code**: Load all hooks
5. **Test epic**: "create epic: Build hello world app"

### Monitoring Stack

- **Real-time dashboard**: 2-second refresh with live metrics
- **Pattern analysis**: Historical routing performance
- **Prometheus export**: `--prometheus` flag for metrics scraping
- **Alert rules**: Quota warnings, stuck agent detection
