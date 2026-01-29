# Hekate Phase 1: Task Lifecycle Management - Implementation Complete

**Date:** 2026-01-29
**Status:** Phase 1 Complete
**Files:** 4 hooks, 2 scripts

## What Was Implemented

### Hooks Created

1. **sessionstart_init.py** - Agent initialization
   - Detects if session is a Hekate-spawned agent
   - Loads task context from Redis + Beads
   - Injects task details into agent context

2. **userpromptsubmit_decompose.py** - Epic decomposition
   - Detects epic creation commands
   - Calls OpenRouter API to decompose epic into tasks
   - Creates tasks in Beads with priority mapping
   - Stores complexity in Redis (not Beads - workaround for missing --complexity flag)
   - Injects confirmation context to user

3. **pretooluse_router.py** - Provider routing & quota management
   - Checks quota for assigned provider
   - Switches to alternative if quota exhausted
   - Updates environment variables for provider switching
   - Tracks usage in Redis

4. **posttooluse_spawn_agents.py** - Parallel agent spawning
   - Triggers after Beads commands (async, non-blocking)
   - Finds pending tasks for active epics
   - Groups by complexity/desired provider
   - Spawns Claude Code sessions with provider env vars
   - Tracks agents in Redis with heartbeat

5. **posttooluse_complete_task.py** - Task completion detection
   - Detects git commit as completion signal
   - Marks task complete in Beads + Redis
   - Updates epic progress
   - Announces epic completion

### Scripts Created

1. **init-redis.sh** - Redis initialization
   - Sets up provider quota limits
   - Initializes complexity-to-provider mapping
   - Creates worktrees directory
   - Interactive quota configuration

2. **install-hooks.sh** - Hooks installation
   - Copies hooks to ~/.claude/hooks/
   - Updates Claude Code settings.json
   - Registers all hooks with correct matchers
   - Backs up existing settings

## Key Architecture Decisions

### Beads Limitations & Workarounds

| Plan Feature | Beads Reality | Solution |
|-------------|---------------|----------|
| `--complexity` flag | Doesn't exist | Store in Redis separately |
| `--metadata` flag | Doesn't exist | Store in Redis separately |
| `--filter` flag | Doesn't exist | Filter in Python after `bd list --json` |
| Complexity for routing | Not in Beads | Redis lookup: `task:{id}:complexity` |

### Agent Spawning

Since Claude Code lacks `--project` and `--hook provider` flags:
- Spawn sessions with `claude <worktree_path>`
- Set `HEKATE_TASK_ID` and `HEKATE_PROVIDER` environment variables
- SessionStart hook reads these to initialize agent

### Provider Switching

Environment variables set in PreToolUse hook:
```python
# GLM example
os.environ['ANTHROPIC_BASE_URL'] = 'https://api.z.ai/api/anthropic'
os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ['Z_AI_API_KEY']
os.environ['ANTHROPIC_DEFAULT_OPUS_MODEL'] = 'glm-4.7'
```

## Installation

```bash
# 1. Initialize Redis
cd /home/hung/Public/new-repos/hekate
./scripts/init-redis.sh

# 2. Install hooks
./scripts/install-hooks.sh

# 3. Set environment variables
export OPENROUTER_API_KEY="sk-or-..."
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."

# 4. Restart Claude Code
# (Hooks load at startup)
```

## Usage

```bash
# Create an epic
create epic: Build a REST API for user authentication

# System automatically:
# 1. Decomposes epic into tasks via OpenRouter
# 2. Creates tasks in Beads with priorities
# 3. Spawns parallel Claude Code agents
# 4. Routes to providers based on complexity
# 5. Detects completion via git commits
```

## Redis Schema (Phase 1)

```
# Epic state
epic:{id}:status → "planning" | "active" | "complete"
epic:{id}:task_count → integer
epic:{id}:complete_count → integer
epic:{id}:description → string
epic:{id}:tasks → set of task IDs

# Task state
task:{id}:complexity → integer (1-10)
task:{id}:epic_id → epic ID
task:{id}:provider → "claude" | "glm" | "deepseek" | "auto"
task:{id}:status → "pending" | "in_progress" | "complete"
task:{id}:claimed → "true" | "false"
task:{id}:session_pid → process ID

# Agent tracking
agent:{pid}:task_id → task ID
agent:{pid}:provider → provider name
agent:{pid}:heartbeat → timestamp (TTL: 30s)

# Provider quota
quota:{provider}:count → integer
quota:{provider}:limit → integer
quota:{provider}:window_start → timestamp

# Routing
routing:complexity:{1-10} → provider for this complexity

# Session mapping
session:{session_id}:task_id → task ID
session:{session_id}:provider → provider
```

## Testing

```bash
# Test epic creation
echo "create epic: Test epic with simple task" | python3 hooks/userpromptsubmit_decompose.py

# Check Redis
redis-cli GET "epic:*:status"
redis-cli KEYS "task:*"

# Check Beads
bd list --json
```

## Known Limitations

1. **Beads query filtering**: No native filter support, must load all tasks and filter in Python
2. **Agent spawning**: No clean way to pass provider to Claude Code, using env vars workaround
3. **Session tracking**: Uses environment variables since Claude Code lacks hook-to-session communication
4. **Async limitations**: `async: true` is fire-and-forget, no way to get results back

## Next Steps (Phase 2)

1. Enhanced routing with historical pattern matching
2. ML-based provider selection from past outcomes
3. Cross-agent learning inbox (semantic memory)
4. Verification cascade with prefetch

## Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Epic decomposition works | Yes | ✅ |
| Tasks created in Beads | Yes | ✅ |
| Agents spawn with correct provider | Untested | ⏳ |
| Quota tracking works | Yes | ✅ |
| Task completion detected | Yes | ✅ |
| Epic completion announced | Yes | ✅ |
