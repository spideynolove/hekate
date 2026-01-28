# Hekate: Hooks-Based Architecture Design

**Date:** 2026-01-29
**Status:** Design Complete
**Author:** Claude (glm-4.7)
**Type:** Complete Architecture Replacement

## Executive Summary

Transform Hekate from a supervisor-based Python daemon to a Claude Code hooks-based system. The new architecture eliminates `supervisor.py` and `agent.py`, replacing them with lightweight hooks that coordinate via Redis and use Beads CLI as the external orchestrator.

**Key Benefits:**
- Zero infrastructure - no daemon required
- Lower latency - direct hook execution vs polling
- Fault isolation - hook failures don't crash entire system
- Simpler deployment - just install hooks, no process management

**Priority Implementation Order:**
1. Task lifecycle management (D)
2. Provider routing (B)
3. Semantic memory (A)
4. Verification cascade (C)
5. Observability (E)

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER WORKFLOW                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  User: "Create OAuth 2.0 epic"                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ [UserPromptSubmit hook fires]                            │    │
│  │  1. Extract epic description                            │    │
│  │  2. Call OpenRouter API: decompose + estimate complexity│    │
│  │  3. For each task: `bd create --complexity N "..."`     │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Beads Task Graph Created                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Task 1: complexity=9 ──────┐                             │    │
│  │ Task 2: complexity=7 ──────┼─── Epic: OAuth 2.0         │    │
│  │ Task 3: complexity=5 ──────┤                             │    │
│  │ Task 4: complexity=3 ──────┘                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  [PostToolUse async hook fires]                                  │
│  1. Read all pending tasks from Beads                           │
│  2. Group by complexity:                                         │
│     - complexity 8-10 → spawn 2 sessions (Claude)               │
│     - complexity 5-7  → spawn 4 sessions (GLM)                 │
│     - complexity 1-4  → spawn 6 sessions (DeepSeek)            │
│  3. For each session:                                            │
│     - `claude --project ~/hekate-worktrees/{task-id} &`         │
│     - Store PID in Redis: agent:{pid}:task → {task-id}         │
│  4. Mark tasks as "in-progress" in Beads                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PARALLEL EXECUTION (12 Claude Code sessions)                    │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐      │
│  │ Session 1      │  │ Session 2      │  │ Session 3-12   │      │
│  │ Task 1 (c=9)   │  │ Task 2 (c=7)   │  │ Tasks 3-4...  │      │
│  │ Provider:      │  │ Provider:      │  │ Provider:      │      │
│  │   claude       │  │   glm         │  │   deepseek    │      │
│  │                │  │                │  │                │      │
│  │ [PreToolUse    │  │ [PreToolUse    │  │ [PreToolUse    │      │
│  │  hook checks   │  │  hook checks   │  │  hook checks   │      │
│  │  quota]        │  │  quota]        │  │  quota]        │      │
│  └────────────────┘  └────────────────┘  └────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  TASK COMPLETE                                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ [PostToolUse hook]                                       │    │
│  │  1. Mark task complete in Beads                          │    │
│  │  2. Update Redis: task:{id}:status = "complete"          │    │
│  │  3. Session exits                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Redis Schema

```
# Task State (replaces supervisor.py state)
task:{id}:status            → "pending" | "in_progress" | "complete" | "failed"
task:{id}:complexity        → integer (1-10)
task:{id}:provider          → "claude" | "glm" | "deepseek" | "openrouter"
task:{id}:session_id        → Claude Code session identifier
task:{id}:claimed_at        → timestamp

# Agent Tracking (replaces agent.py)
agent:{pid}:task_id         → task ID
agent:{pid}:provider        → provider name
agent:{pid}:heartbeat       → timestamp (TTL: 30s)
agent:{pid}:worktree        → path to git worktree

# Provider Quota
quota:{provider}:count      → integer
quota:{provider}:window_start → timestamp
quota:{provider}:limit      → integer (default: 50 for claude, 100 for glm, etc.)

# Epic State
epic:{id}:status            → "planning" | "active" | "complete"
epic:{id}:task_count        → integer
epic:{id}:complete_count    → integer

# Session Mapping (new)
session:{session_id}:task_id → task ID

# Phase 2: Enhanced Routing
routing:history:{task_hash}  → JSON {provider, success, duration, timestamp}
provider:stats:{provider}    → JSON {total_tasks, success_rate, avg_duration}
routing:pattern:{feature_hash} → best_provider_for_this_pattern

# Phase 3: Semantic Memory
memory:prefetch:{session_id}  → JSON {relevant_tasks, learnings, last_updated}
memory:inbox:*                → JSONL {pattern, solution, timestamp, agent_id}

# Phase 4: Verification Cascade
verify:prefetch:{task_id}       → JSON {provider, result, confidence, timestamp}
cascade:pattern:{context}        → JSON {skip_deepseek, direct_glm, success_rate}

# Phase 5: Observability
metrics:agent_tasks_total      → "agent_tasks_total{provider=\"claude\",complexity=\"high\"} 142"
metrics:provider_quota_remaining → "provider_quota_remaining{provider=\"claude\"} 23"
alerts:quota_warning           → JSON {provider, remaining, threshold}
```

## Phase 1: Task Lifecycle Management

### UserPromptSubmit Hook - Epic Decomposition

**File:** `~/.claude/hooks/userpromptsubmit_decompose.py`

```python
#!/usr/bin/env python3
import json, sys, subprocess, os, time
from pathlib import Path

input_data = json.load(sys.stdin)
prompt = input_data.get('prompt', '')
session_id = input_data.get('session_id', '')

# Check if this is an epic creation command
if not any(word in prompt.lower() for word in ['epic', 'create epic', 'new epic']):
    sys.exit(0)

# Extract epic description
epic_description = prompt
for prefix in ['create epic', 'new epic', 'epic:']:
    if prefix in epic_description.lower():
        epic_description = epic_description.lower().split(prefix, 1)[1].strip()
        break

print(f"[HEKATE] Decomposing epic: {epic_description[:50]}...", file=sys.stderr)

# Call OpenRouter API for decomposition
import requests
response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json"
    },
    json={
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [{
            "role": "system",
            "content": """Decompose the epic into tasks. For each task:
1. Provide a clear description
2. Estimate complexity (1-10):
   - 1-3: Simple CRUD, config changes
   - 4-6: Medium features, some logic
   - 7-8: Complex features, multiple components
   - 9-10: Architecture, complex integrations

Return JSON only:
{
  "tasks": [
    {"description": "...", "complexity": 7},
    ...
  ]
}"""
        }, {
            "role": "user",
            "content": f"Epic: {epic_description}"
        }]
    }
)

result = response.json()
tasks = json.loads(result['choices'][0]['message']['content'])['tasks']

# Create epic ID from timestamp
epic_id = f"epic-{int(time.time())}"
subprocess.run(['redis-cli', 'SET', f'epic:{epic_id}:status', 'planning'], capture_output=True)
subprocess.run(['redis-cli', 'SET', f'epic:{epic_id}:task_count', str(len(tasks))], capture_output=True)

# Create tasks via Beads CLI
for i, task in enumerate(tasks):
    task_desc = task['description']
    complexity = task['complexity']

    subprocess.run([
        'bd', 'create',
        f'[{epic_id}] {task_desc}',
        f'--complexity', str(complexity),
        '--metadata', f'epic={epic_id},priority={10-complexity}'
    ], capture_output=True)

    print(f"[HEKATE] Created task {i+1}/{len(tasks)} (complexity={complexity})", file=sys.stderr)

# Update epic status
subprocess.run(['redis-cli', 'SET', f'epic:{epic_id}:status', 'active'], capture_output=True)

# Provide context back to user
output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": f"\n[HEKATE] Epic {epic_id} decomposed into {len(tasks)} tasks.\nTasks created in Beads. Parallel agents will be spawned automatically.\n"
    }
}
print(json.dumps(output))

sys.exit(0)
```

### PostToolUse Async Hook - Parallel Agent Spawning

**File:** `~/.claude/hooks/posttooluse_spawn_agents.py`

```python
#!/usr/bin/env python3
import json, sys, subprocess, os, time
from pathlib import Path

input_data = json.load(sys.stdin)
tool_response = input_data.get('tool_response', {})

if isinstance(tool_response, dict) and tool_response.get('tool_name') != 'bd':
    sys.exit(0)

epic_keys = subprocess.run(
    ['redis-cli', 'KEYS', 'epic:*:status'],
    capture_output=True, text=True
).stdout.strip().split('\n')

if not epic_keys or epic_keys == ['']:
    sys.exit(0)

for epic_key in epic_keys:
    epic_id = epic_key.split(':')[1]
    status = subprocess.run(
        ['redis-cli', 'GET', epic_key],
        capture_output=True, text=True
    ).stdout.strip()

    if status != 'active':
        continue

    tasks_json = subprocess.run([
        'bd', 'list', '--filter', f'epic={epic_id}',
        '--format', 'json'
    ], capture_output=True, text=True)

    if tasks_json.returncode != 0:
        continue

    try:
        tasks = json.loads(tasks_json.stdout)
        pending_tasks = [t for t in tasks if t.get('status') == 'pending']
    except:
        continue

    if not pending_tasks:
        continue

    print(f"[HEKATE] Spawning {len(pending_tasks)} agents for epic {epic_id}", file=sys.stderr)

    claude_tasks = [t for t in pending_tasks if t.get('complexity', 5) >= 8]
    glm_tasks = [t for t in pending_tasks if 5 <= t.get('complexity', 5) <= 7]
    deepseek_tasks = [t for t in pending_tasks if t.get('complexity', 5) <= 4]

    spawned_count = 0

    for task in claude_tasks[:2]:
        task_id = task['id']
        worktree = f"{Path.home()}/hekate-worktrees/{task_id}"

        subprocess.run(['git', 'worktree', 'add', '-b', f'task-{task_id}', worktree], capture_output=True)

        provider = "claude"
        env = os.environ.copy()
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('ANTHROPIC_API_KEY', '')

        pid = subprocess.Popen([
            'claude', '--project', worktree,
            '--hook', 'provider', provider
        ], env=env).pid

        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:task_id', task_id], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:provider', provider], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))], capture_output=True)
        subprocess.run(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'], capture_output=True)

        subprocess.run(['bd', 'update', task_id, '--status', 'in-progress'], capture_output=True)

        spawned_count += 1

    for task in glm_tasks[:4]:
        task_id = task['id']
        worktree = f"{Path.home()}/hekate-worktrees/{task_id}"

        subprocess.run(['git', 'worktree', 'add', '-b', f'task-{task_id}', worktree], capture_output=True)

        provider = "glm"
        env = os.environ.copy()
        env['ANTHROPIC_BASE_URL'] = "https://api.z.ai/api/anthropic"
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ['Z_AI_API_KEY']
        env['ANTHROPIC_DEFAULT_OPUS_MODEL'] = "glm-4.7"

        pid = subprocess.Popen([
            'claude', '--project', worktree,
            '--hook', 'provider', provider
        ], env=env).pid

        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:task_id', task_id], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:provider', provider], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))], capture_output=True)
        subprocess.run(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'], capture_output=True)

        subprocess.run(['bd', 'update', task_id, '--status', 'in-progress'], capture_output=True)

        spawned_count += 1

    for task in deepseek_tasks[:6]:
        task_id = task['id']
        worktree = f"{Path.home()}/hekate-worktrees/{task_id}"

        subprocess.run(['git', 'worktree', 'add', '-b', f'task-{task_id}', worktree], capture_output=True)

        provider = "deepseek"
        env = os.environ.copy()
        env['ANTHROPIC_BASE_URL'] = "https://api.deepseek.com/anthropic"
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ['DEEPSEEK_API_KEY']

        pid = subprocess.Popen([
            'claude', '--project', worktree,
            '--hook', 'provider', provider
        ], env=env).pid

        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:task_id', task_id], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:provider', provider], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))], capture_output=True)
        subprocess.run(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'], capture_output=True)

        subprocess.run(['bd', 'update', task_id, '--status', 'in-progress'], capture_output=True)

        spawned_count += 1

sys.exit(0)
```

### PreToolUse Hook - Provider Routing

**File:** `~/.claude/hooks/pretooluse_router.py`

```python
#!/usr/bin/env python3
import json, sys, subprocess, os, time
from pathlib import Path

input_data = json.load(sys.stdin)
tool_name = input_data.get('tool_name', '')
tool_input = input_data.get('tool_input', {})
session_id = input_data.get('session_id', '')

task_id = subprocess.run(
    ['redis-cli', 'GET', f'session:{session_id}:task_id'],
    capture_output=True, text=True
).stdout.strip()

if not task_id:
    sys.exit(0)

task_info = subprocess.run(
    ['bd', 'show', task_id, '--format', 'json'],
    capture_output=True, text=True
)

if task_info.returncode != 0:
    sys.exit(0)

task = json.loads(task_info.stdout)
complexity = int(task.get('complexity', 5))
assigned_provider = task.get('provider', 'auto')

quota_count = int(subprocess.run(
    ['redis-cli', 'GET', f'quota:{assigned_provider}:count'],
    capture_output=True, text=True
).stdout.strip() or '0')

quota_limit = int(subprocess.run(
    ['redis-cli', 'GET', f'quota:{assigned_provider}:limit'],
    capture_output=True, text=True
).stdout.strip() or '50')

if quota_count >= quota_limit:
    print(f"[HEKATE] Provider {assigned_provider} quota exhausted, finding alternative...", file=sys.stderr)

    for alt_provider in ['deepseek', 'glm', 'openrouter']:
        alt_count = int(subprocess.run(
            ['redis-cli', 'GET', f'quota:{alt_provider}:count'],
            capture_output=True, text=True
        ).stdout.strip() or '0')

        alt_limit = int(subprocess.run(
            ['redis-cli', 'GET', f'quota:{alt_provider}:limit'],
            capture_output=True, text=True
        ).stdout.strip() or '100')

        if alt_count < alt_limit:
            print(f"[HEKATE] Switching to {alt_provider}", file=sys.stderr)

            if alt_provider == 'deepseek':
                os.environ['ANTHROPIC_BASE_URL'] = "https://api.deepseek.com/anthropic"
                os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ['DEEPSEEK_API_KEY']
            elif alt_provider == 'glm':
                os.environ['ANTHROPIC_BASE_URL'] = "https://api.z.ai/api/anthropic"
                os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ['Z_AI_API_KEY']
                os.environ['ANTHROPIC_DEFAULT_OPUS_MODEL'] = "glm-4.7"
            elif alt_provider == 'openrouter':
                os.environ['ANTHROPIC_BASE_URL'] = "https://openrouter.ai/api"
                os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ['OPENROUTER_API_KEY']

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": f"\n[HEKATE ROUTER] Provider {assigned_provider} quota exhausted. Switched to {alt_provider} for this task.\n"
                }
            }
            print(json.dumps(output))
            break

subprocess.run(['redis-cli', 'INCR', f'quota:{assigned_provider}:count'], capture_output=True)

pid = os.getpid()
subprocess.run(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))], capture_output=True)
subprocess.run(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'], capture_output=True)

sys.exit(0)
```

### SessionStart Hook - Agent Initialization

**File:** `~/.claude/hooks/sessionstart_init.py`

```python
#!/usr/bin/env python3
import json, sys, subprocess, os
from pathlib import Path

input_data = json.load(sys.stdin)
session_id = input_data.get('session_id', '')

hekate_pid = os.environ.get('HEKATE_PARENT_PID')

if hekate_pid:
    task_id = subprocess.run(
        ['redis-cli', 'GET', f'agent:{hekate_pid}:task_id'],
        capture_output=True, text=True
    ).stdout.strip()

    if task_id:
        subprocess.run([
            'redis-cli', 'SET', f'session:{session_id}:task_id', task_id
        ], capture_output=True)

        task_info = subprocess.run(
            ['bd', 'show', task_id, '--format', 'json'],
            capture_output=True, text=True
        )

        if task_info.returncode == 0:
            task = json.loads(task_info.stdout)

            context = f"""
[HEKATE AGENT]
Session ID: {session_id}
Task ID: {task_id}
Task: {task.get('description', '')}
Complexity: {task.get('complexity', 'unknown')}
Epic: {task.get('epic', 'unknown')}

You are an autonomous agent working on this task. When complete, the system will automatically detect completion and mark the task as done.
"""

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context
                }
            }
            print(json.dumps(output))

sys.exit(0)
```

### PostToolUse Hook - Task Completion

**File:** `~/.claude/hooks/posttooluse_complete_task.py`

```python
#!/usr/bin/env python3
import json, sys, subprocess, os, time
from pathlib import Path

input_data = json.load(sys.stdin)
tool_response = input_data.get('tool_response', {})
session_id = input_data.get('session_id', '')

task_id = subprocess.run(
    ['redis-cli', 'GET', f'session:{session_id}:task_id'],
    capture_output=True, text=True
).stdout.strip()

if not task_id:
    sys.exit(0)

epic_id = subprocess.run(
    ['bd', 'show', task_id, '--metadata', 'epic'],
    capture_output=True, text=True
).stdout.strip()

tool_name = tool_response.get('tool_name', '')

if tool_name == 'Bash':
    command = tool_response.get('tool_input', {}).get('command', '')
    if 'git commit' in command or 'git push' in command:
        print(f"[HEKATE] Task {task_id} appears complete", file=sys.stderr)

        subprocess.run(['bd', 'update', task_id, '--status', 'complete'], capture_output=True)
        subprocess.run(['redis-cli', 'SET', f'task:{task_id}:status', 'complete'], capture_output=True)
        subprocess.run(['redis-cli', 'INCR', f'epic:{epic_id}:complete_count'], capture_output=True)

        task_count = int(subprocess.run(
            ['redis-cli', 'GET', f'epic:{epic_id}:task_count'],
            capture_output=True, text=True
        ).stdout.strip() or '0')

        complete_count = int(subprocess.run(
            ['redis-cli', 'GET', f'epic:{epic_id}:complete_count'],
            capture_output=True, text=True
        ).stdout.strip() or '0')

        if complete_count >= task_count:
            print(f"[HEKATE] Epic {epic_id} complete!", file=sys.stderr)
            subprocess.run(['redis-cli', 'SET', f'epic:{epic_id}:status', 'complete'], capture_output=True)

            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": f"\n[HEKATE] Epic {epic_id} is complete! All tasks finished.\n"
                }
            }
            print(json.dumps(output))

sys.exit(0)
```

### Claude Code Configuration

**File:** `~/.claude/config.json`

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/hooks/sessionstart_init.py"
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/hooks/userpromptsubmit_decompose.py",
        "timeout": 30
      }]
    }],
    "PreToolUse": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/hooks/pretooluse_router.py",
        "timeout": 2
      }]
    }],
    "PostToolUse": [{
      "matcher": "bd",
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.claude/hooks/posttooluse_spawn_agents.py",
        "async": true,
        "timeout": 60
      }]
    }]
  }
}
```

## Phase 2: Enhanced Provider Routing

Add historical routing decisions and machine learning.

**Redis additions:**
```
routing:history:{task_hash}  → JSON {provider, success, duration, timestamp}
provider:stats:{provider}    → JSON {total_tasks, success_rate, avg_duration}
routing:pattern:{feature_hash} → best_provider_for_this_pattern
```

**Enhanced PreToolUse with pattern matching:**
```python
# Get task features
task_features = {
    'complexity': complexity,
    'has_tests': 'test' in task.get('description', '').lower(),
    'is_feature': 'feature' in task.get('tags', []),
    'is_bugfix': 'bug' in task.get('tags', []),
    'file_count': len(task.get('files_affected', [])),
}

feature_hash = hash(json.dumps(task_features, sort_keys=True))
best_provider = subprocess.run(
    ['redis-cli', 'GET', f'routing:pattern:{feature_hash}'],
    capture_output=True, text=True
).stdout.strip()

if best_provider:
    assigned_provider = best_provider
```

## Phase 3: Semantic Memory

Cross-agent learning to prevent repeated mistakes.

**Redis additions:**
```
memory:prefetch:{session_id}  → JSON {relevant_tasks, learnings, last_updated}
memory:inbox:*                → JSONL {pattern, solution, timestamp, agent_id}
memory:inbox:TTL              → 3600
```

**PostToolUse memory storage:**
```python
# Detect bug fixes
solution_indicators = ['fix', 'solve', 'resolve', 'patch', 'correct']
if any(indicator in command.lower() for indicator in solution_indicators):
    pattern = {
        'type': 'bugfix',
        'command_snippet': command[:100],
        'timestamp': int(time.time()),
        'agent_id': os.getpid(),
    }
    subprocess.run(['redis-cli', 'LPUSH', 'memory:inbox:recent', json.dumps(pattern)], capture_output=True)
```

**PreToolUse memory injection:**
```python
inbox_items = subprocess.run(['redis-cli', 'LRANGE', 'memory:inbox:recent', '0', '9'], capture_output=True, text=True).stdout.strip().split('\n')
relevant_context = []
for item in inbox_items:
    pattern = json.loads(item)
    relevant_context.append(f"- Agent {pattern['agent_id']} solved similar issue: {pattern['command_snippet']}")
```

## Phase 4: Verification Cascade

Prefetch verification results to save time.

**Redis additions:**
```
verify:prefetch:{task_id}       → JSON {provider, result, confidence, timestamp}
verify:prefetch:TTL             → 600
cascade:pattern:{context}        → JSON {skip_deepseek, direct_glm, success_rate}
```

**PostToolUse async prefetch:**
```python
# Complexity-based cascade strategy
if complexity <= 4:
    providers_to_check = ['deepseek']
elif complexity <= 7:
    providers_to_check = ['deepseek', 'glm']
else:
    providers_to_check = ['glm', 'claude']

for provider in providers_to_check:
    prefetch_data = {
        'task_id': task_id,
        'provider': provider,
        'status': 'pending',
        'timestamp': int(time.time())
    }
    subprocess.run(['redis-cli', 'SET', f'verify:prefetch:{task_id}:{provider}', json.dumps(prefetch_data)], capture_output=True)
```

## Phase 5: Observability

Real-time monitoring and alerts.

**Redis additions:**
```
metrics:agent_tasks_total      → "agent_tasks_total{provider=\"claude\",complexity=\"high\"} 142"
metrics:provider_quota_remaining → "provider_quota_remaining{provider=\"claude\"} 23"
alerts:quota_warning           → JSON {provider, remaining, threshold}
```

**Dashboard script:** `scripts/hekate-dashboard.py`
- Displays active agents, epic progress, quota status
- Real-time alerts for quota exhaustion
- Prometheus-compatible metrics export

## Installation

**File:** `scripts/install-hooks.sh`

```bash
#!/bin/bash
set -e

HOOKS_DIR="$HOME/.claude/hooks"
CONFIG_DIR="$HOME/.claude"

echo "Installing Hekate hooks..."

mkdir -p "$HOOKS_DIR"
mkdir -p "$CONFIG_DIR/hekate/lib"

cp hooks/*.py "$HOOKS_DIR/"
chmod +x "$HOOKS_DIR"/*.py

cp lib/*.py "$CONFIG_DIR/hekate/lib/"

# Merge hooks into config.json
python3 - <<'EOF'
import json

config_path = "$CONFIG_DIR/config.json"
hooks_config = {
    "hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/sessionstart_init.py"}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/userpromptsubmit_decompose.py", "timeout": 30}]}],
        "PreToolUse": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/pretooluse_router.py", "timeout": 2}]}],
        "PostToolUse": [{"matcher": "bd", "hooks": [{"type": "command", "command": "python3 ~/.claude/hooks/posttooluse_spawn_agents.py", "async": true, "timeout": 60}]}]
    }
}

try:
    with open(config_path, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

config.update(hooks_config)

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
EOF

echo "Hooks installed to $HOOKS_DIR"
echo "Restart Claude Code to load hooks"
```

## File Structure

```
hekate/
├── scripts/
│   ├── install-hooks.sh
│   ├── setup-prerequisites.sh
│   ├── monitor-epics.py
│   └── hekate-dashboard.py
├── hooks/
│   ├── sessionstart_init.py
│   ├── userpromptsubmit_decompose.py
│   ├── pretooluse_router.py
│   ├── posttooluse_spawn_agents.py
│   ├── posttooluse_complete_task.py
│   ├── posttooluse_memory.py
│   ├── posttooluse_verify_prefetch.py
│   └── posttooluse_metrics.py
├── tests/
│   ├── test_sessionstart.py
│   ├── test_decompose.py
│   ├── test_router.py
│   ├── test_spawning.py
│   └── test_e2e.py
├── src/hekate/
│   └── config.yaml
├── docs/
│   └── plans/
│       └── 2026-01-29-hooks-based-architecture.md
├── CLAUDE.md
└── README.md
```

## Implementation Timeline

| Phase | Tasks | Duration |
|-------|-------|----------|
| **0** | Prerequisites, Redis running | 30min |
| **1a** | SessionStart, PreToolUse (basic) | 2-3h |
| **1b** | UserPromptSubmit (decomposition) | 2-3h |
| **1c** | PostToolUse (spawning, completion) | 3-4h |
| **1d** | Testing Phase 1 | 2-3h |
| **2** | Enhanced routing with history | 4-6h |
| **3** | Semantic memory inbox | 4-6h |
| **4** | Verification cascade | 3-4h |
| **5** | Observability/dashboard | 2-3h |
| **6** | End-to-end testing | 3-4h |

**Total:** 30-40 hours

## Error Handling

| Hook Type | Failure Mode | Behavior |
|-----------|--------------|----------|
| SessionStart | Hook script error | Log error, continue without init |
| UserPromptSubmit | OpenRouter API down | Skip decomposition, notify user |
| PreToolUse | Redis unavailable | Skip routing, use default |
| PreToolUse | All providers exhausted | Block action (exit 1) |
| PostToolUse | Spawn failure | Log error, try next task |
| PostToolUse | Async timeout | Kill subprocess, continue |

**Graceful degradation pattern:**
```python
def safe_redis_command(cmd, default=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return default
```

## Migration from Current Hekate

**Files to delete:**
- `src/hekate/supervisor.py` - Replaced by hooks
- `src/hekate/agent.py` - Claude Code manages processes
- `src/hekate/router.py` - Logic moved to PreToolUse hook
- `src/hekate/quota.py` - Logic moved to PreToolUse hook
- `src/hekate/verifier.py` - Logic moved to PostToolUse hooks

**Files to keep:**
- `src/hekate/beads.py` - Beads client library (may be needed)
- `src/hekate/mcporter_helper.py` - Token optimization

**Configuration changes:**
- No more systemd service
- No supervisor process
- Hooks registered in `~/.claude/config.json`

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Epic decomposition time | <30s | OpenRouter API latency |
| Agent spawn latency | <5s | Hook execution time |
| Provider routing accuracy | >85% | Success rate by provider |
| Task failure rate | <10% | Beads task status |
| Cross-agent learning hits | >5 per day | Memory inbox access |
| Verification time saved | >60% | Prefetch cache hit rate |

## References

- Claude Code Hooks Documentation: `docs/Claude-cc-async-hooks.md`
- Current Hekate Architecture: `docs/ARCHITECTURE.md`
- Beads CLI Documentation: https://github.com/steveyegge/beads
