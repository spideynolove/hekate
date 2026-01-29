---
name: hekate-agent-workflow
description: Hekate multi-agent workflow patterns and conventions
---

# Hekate Agent Workflow

## Task Completion Convention

When completing a task, commit with explicit marker:
```bash
git add .
git commit -m "Complete task-abc123: Implemented feature X"
```

This triggers `posttooluse_complete_task.py` to mark task as complete in Redis.

## Epic Creation

```bash
create epic: Build authentication system
```

Triggers `userpromptsubmit_decompose.py` to:
1. Call OpenRouter API for task decomposition
2. Create tasks in Beads with complexity ratings
3. Store epic metadata in Redis
4. Assign providers based on complexity

## Provider Assignment

| Complexity | Provider | Pool Size |
|------------|----------|-----------|
| 1-4 (low) | DeepSeek | 6 agents |
| 5-7 (medium) | GLM | 4 agents |
| 8-10 (high) | Claude | 2 agents |

## Subagent Execution

When assigned a task:
1. Check Redis for task details: `redis-cli GET "task:{id}:description"`
2. Execute implementation
3. Commit with "Complete task-{id}" marker
4. Hook auto-detects completion

## Memory System

### Store Solutions
After solving a problem, the solution is automatically stored in semantic memory via `posttooluse_memory.py`.

### Retrieve Related Solutions
`pretooluse_memory.py` injects similar past solutions when starting new tasks.

## Verification

High-complexity tasks trigger `posttooluse_verify_prefetch.py` to start verification in parallel.

## Troubleshooting

### Task stuck in pending
```bash
bd show {task-id}
redis-cli GET "task:{task-id}:status"
```

### Agent not spawning
Check `posttooluse_spawn_agents.py` logs in `~/.hekate/logs/`

### Quota exhausted
```bash
redis-cli SET "quota:claude:count" "0"
```
