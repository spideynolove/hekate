# Agent Configuration

This document details the four agent types managed by the Hekate supervisor, their configurations, and setup requirements.

## Agent Overview

Hekate orchestrates 14 agents across four providers for autonomous development tasks:

| Provider | Count | Pricing | Use Case | Quota Limits |
|----------|-------|---------|----------|--------------|
| Claude | 2 | Premium | Planning, complex arch, reviews | 45 msg/5h (20% buffer) |
| GLM | 4 | Medium | Medium features, verification | 180 msg/5h (3% buffer) |
| DeepSeek | 6 | Free/API | Simple CRUD | Unlimited |
| OpenRouter | 2 | API | Fallback/routing | Provider-dependent |

## Provider Setup

Add these functions to your `~/.bashrc` for provider switching:

```bash
deepseek() {
    export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
    export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY}"
    claude "$@"
}

glm() {
    export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
    export ANTHROPIC_AUTH_TOKEN="${Z_AI_API_KEY}"
    claude "$@"
}

opr() {
    export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
    export ANTHROPIC_AUTH_TOKEN="${OPENROUTER_API_KEY}"
    claude "$@"
}

claude() {
    export ANTHROPIC_BASE_URL="https://api.anthropic.com"
    export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_API_KEY}"
    claude "$@"
}
```

## Required Environment Variables

Set these API keys in your environment or supervisor `.env`:

```bash
ANTHROPIC_API_KEY      # for Claude agents
Z_AI_API_KEY           # for GLM agents
DEEPSEEK_API_KEY       # for DeepSeek agents
OPENROUTER_API_KEY     # for OpenRouter agents
```

## Agent Invocation

The supervisor spawns agents via subprocess calls. Each agent gets:

1. **Isolated git worktree** for task execution
2. **Provider-specific environment** (env vars + URL overrides)
3. **Superpowers enforcement** (TDD, quality gates)
4. **Hekate skills** (on-demand tool loading)

Example supervisor agent spawning:
```python
import subprocess
import os

def spawn_agent(provider, task_id, worktree_path):
    env = os.environ.copy()
    env.update(provider_config[provider])

    # Spawn claude process with provider environment
    cmd = [provider, '.',  # calls bash function above
           '--task-id', task_id,
           '--worktree', worktree_path]

    return subprocess.Popen(cmd, env=env, cwd=worktree_path)
```

## Routing Rules

Agent selection follows complexity and quota constraints:

- **Simple CRUD**: DeepSeek → OpenRouter
- **Medium Features**: GLM → DeepSeek → OpenRouter
- **Complex/Arch**: Claude → GLM → OpenRouter
- **Planning**: Claude → OpenRouter
- **Review**: Claude → GLM

## Task Claiming Protocol

Agents claim tasks using Redis-based atomic locking:

```python
def claim_task(task_id):
    # Atomic SETNX with TTL for task reservation
    lock_key = f"task:{task_id}:lock"
    claim_key = f"task:{task_id}:claimed"

    # Set lock with 5-minute expiration
    if redis.set(lock_key, "claimed", nx=True, ex=300):
        # Double-check task still unclaimed
        if not redis.exists(claim_key):
            redis.set(claim_key, provider_name, ex=3600)  # 1h claim
            return True

    return False
```

## Worktree Naming Convention

Worktrees are created with structured paths: `~/.hekate/worktrees/{task_id}-{provider}-{timestamp}/`

Example:
- `bd-123-claude-1734539200/`
- `bd-456-deepseek-1734542900/`

Each worktree gets its own Git repository state for isolated development.

## Verification Handoff Mechanism

Tasks proceed through staged verification cascade:

```python
# After agent completes implementation
def queue_verification(task_id, implementation_path):
    # Phase 1: DeepSeek cheap verification
    redis.lpush("verification:phase1", f"{task_id}:{implementation_path}")

# Verifier picks up and cascades:
# P1: DeepSeek → lpush "phase2" if minor issues
# P2: GLM review → lpush "claude_fix" if major issues
# P3: Claude fixes → push to integration branch
```

## Beads Task Queue Reading

Supervisor polls Beads task graph using JSON parsing:

```bash
# Get ready tasks
bd ready --json > /tmp/tasks.json

# Format: [{"id": "bd-123", "type": "task", "phase": "phase1", ...}]
```

Supervisor filters unclaimed tasks and creates agent assignments with appropriate provider routing based on task complexity metadata.