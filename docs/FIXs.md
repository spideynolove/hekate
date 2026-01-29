## MCPorter Context Pollution Problem

| Issue | Without MCPorter | With MCPorter | Alternative |
|-------|-----------------|---------------|-------------|
| MCP tool schema loading | 10k-15k tokens per session | 0 tokens (compiled binaries) | Direct MCP server calls via stdio |
| Tool discovery overhead | Full schema in every context | On-demand compilation | Lazy loading pattern |
| Token efficiency | ~100k tokens/session wasted | ~5k tokens baseline | Custom MCP wrapper |

## MCPorter Alternatives

### Alternative 1: Direct MCP Server Integration

**Pattern:** Call MCP servers directly via stdio, bypass Claude Code's MCP registration

```python
import json
import subprocess

class MCPDirectClient:
    def __init__(self, server_command):
        self.process = subprocess.Popen(
            server_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    
    def call_tool(self, tool_name, arguments):
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        
        response = json.loads(self.process.stdout.readline())
        return response['result']
    
    def close(self):
        self.process.terminate()
```

**Hook integration:**

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / '.hekate/lib'))
from mcp_direct import MCPDirectClient

input_data = json.load(sys.stdin)
tool_name = input_data.get('tool_name')

if tool_name == 'beads_query':
    client = MCPDirectClient(['npx', '@beads/mcp-server'])
    result = client.call_tool('list_tasks', {'status': 'pending'})
    client.close()
    
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"Beads tasks: {result}"
        }
    }
    print(json.dumps(output))

sys.exit(0)
```

**Token savings:** 10k-15k per session (equivalent to MCPorter)

### Alternative 2: Hook-Based Tool Registry

**Pattern:** Hooks maintain local tool cache, inject only needed tools

```python
#!/usr/bin/env python3
import json
import sys
import redis

r = redis.Redis()
input_data = json.load(sys.stdin)
session_id = input_data.get('session_id')

registered_tools = r.smembers(f'session:{session_id}:tools')
prompt = input_data.get('prompt', '')

needed_tools = []
if 'beads' in prompt.lower() or 'task' in prompt.lower():
    needed_tools.append('beads')
if 'memory' in prompt.lower() or 'remember' in prompt.lower():
    needed_tools.append('memory')

new_tools = [t for t in needed_tools if t not in registered_tools]

if new_tools:
    tool_schemas = []
    for tool in new_tools:
        schema = r.get(f'tool_schema:{tool}')
        if schema:
            tool_schemas.append(schema.decode())
            r.sadd(f'session:{session_id}:tools', tool)
    
    if tool_schemas:
        context = f"\nAvailable tools:\n" + "\n".join(tool_schemas)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context
            }
        }
        print(json.dumps(output))

sys.exit(0)
```

**File location:** `hooks/userpromptsubmit_tool_registry.py`

### Alternative 3: Compile MCP Tools to Skills

**Pattern:** Convert MCP tools to Claude Code skills at setup time

```bash
#!/bin/bash

SKILLS_DIR="$HOME/.claude/skills"
mkdir -p "$SKILLS_DIR"

compile_beads_skill() {
    cat > "$SKILLS_DIR/beads-tools/SKILL.md" << 'EOF'
---
name: beads-tools
description: Task management via Beads CLI
---

Available operations:

list_tasks(status: str) -> List[Task]
get_task(id: str) -> Task
update_task(id: str, status: str) -> bool
create_task(title: str, complexity: int) -> Task

Use bash commands:
- List: `bd list --status pending`
- Get: `bd show {id}`
- Update: `bd update {id} --status complete`
- Create: `bd create "{title}" --complexity {N}`
EOF
}

compile_beads_skill
```

**Token savings:** Skills load on-demand, ~2k tokens vs 10k for full MCP schema

**File location:** `scripts/compile-mcp-to-skills.sh`

## Hekate Codebase Improvements

### Improvement 1: Remove Agent Spawning, Use Subagents

**File:** `hooks/posttooluse_spawn_agents.py`

**Current broken approach:**
```python
subprocess.Popen(['claude', '--provider', provider, '--task', task_id])
```

**Replace with:**

```python
#!/usr/bin/env python3
import json
import sys
import redis

r = redis.Redis()
input_data = json.load(sys.stdin)
tool_name = input_data.get('tool_name')
tool_output = input_data.get('tool_response', {})

if 'epic decomposed' in str(tool_output).lower():
    epic_id = r.get('latest_epic_id')
    tasks = r.smembers(f'epic:{epic_id}:tasks')
    
    for task_id in tasks:
        complexity = int(r.get(f'task:{task_id}:complexity') or 5)
        
        if complexity >= 8:
            provider = 'claude'
        elif complexity >= 5:
            provider = 'glm'
        else:
            provider = 'deepseek'
        
        r.hset(f'task:{task_id}:meta', 'assigned_provider', provider)
    
    task_list = '\n'.join([f"- Task {t}: complexity {r.get(f'task:{t}:complexity')}" 
                           for t in tasks])
    
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"Tasks assigned:\n{task_list}\n\nUse subagents to execute each task."
        }
    }
    print(json.dumps(output))

sys.exit(0)
```

**Subagent invocation pattern:**

```
Claude receives task assignment context
Claude spawns subagent: `@agent-deepseek implement task-123`

In subagent SessionStart hook:
- Load task-123 details from Redis
- Set provider env vars based on assigned_provider
- Inject task context
```

**File:** `hooks/sessionstart_init.py` (modified)

```python
#!/usr/bin/env python3
import json
import sys
import os
import redis

r = redis.Redis()
input_data = json.load(sys.stdin)
session_id = input_data.get('session_id')

task_id = r.get(f'session:{session_id}:task_id')
if not task_id:
    sys.exit(0)

task_data = r.hgetall(f'task:{task_id}:meta')
provider = task_data.get(b'assigned_provider', b'deepseek').decode()

provider_configs = {
    'claude': {
        'ANTHROPIC_BASE_URL': 'https://api.anthropic.com',
        'ANTHROPIC_AUTH_TOKEN': os.environ.get('ANTHROPIC_API_KEY')
    },
    'glm': {
        'ANTHROPIC_BASE_URL': 'https://api.z.ai/api/anthropic',
        'ANTHROPIC_AUTH_TOKEN': os.environ.get('Z_AI_API_KEY')
    },
    'deepseek': {
        'ANTHROPIC_BASE_URL': 'https://api.deepseek.com/anthropic',
        'ANTHROPIC_AUTH_TOKEN': os.environ.get('DEEPSEEK_API_KEY')
    }
}

if provider in provider_configs:
    for key, value in provider_configs[provider].items():
        os.environ[key] = value

task_description = r.get(f'task:{task_id}:description')
task_complexity = r.get(f'task:{task_id}:complexity')

context = f"""Task Assignment:
ID: {task_id.decode()}
Provider: {provider}
Complexity: {task_complexity.decode()}
Description: {task_description.decode()}

Execute this task and commit when complete with message: "Complete task-{task_id.decode()}"
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

### Improvement 2: Fix Task Completion Detection

**File:** `hooks/posttooluse_complete_task.py`

**Replace git commit detection with explicit marker:**

```python
#!/usr/bin/env python3
import json
import sys
import re
import redis

r = redis.Redis()
input_data = json.load(sys.stdin)
tool_name = input_data.get('tool_name')
tool_input = input_data.get('tool_input', {})

if tool_name != 'Bash':
    sys.exit(0)

command = tool_input.get('command', '')
commit_match = re.search(r'git commit.*"Complete task-(\w+)"', command)

if commit_match:
    task_id = commit_match.group(1)
    
    r.set(f'task:{task_id}:status', 'complete')
    r.incr(f'task:{task_id}:completed_at', int(time.time()))
    
    epic_id = r.get(f'task:{task_id}:epic_id')
    if epic_id:
        r.incr(f'epic:{epic_id}:complete_count')
        total = int(r.get(f'epic:{epic_id}:task_count') or 0)
        complete = int(r.get(f'epic:{epic_id}:complete_count') or 0)
        
        if complete >= total:
            r.set(f'epic:{epic_id}:status', 'complete')
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": f"Epic {epic_id.decode()} complete! All {total} tasks finished."
                }
            }
            print(json.dumps(output))

sys.exit(0)
```

### Improvement 3: Fix Quota Race Conditions

**File:** `hooks/pretooluse_router.py`

**Add Lua script for atomic quota check:**

```python
#!/usr/bin/env python3
import json
import sys
import redis

r = redis.Redis()

QUOTA_CHECK_SCRIPT = """
local provider = ARGV[1]
local limit = tonumber(ARGV[2])
local window = tonumber(ARGV[3])

local count_key = "quota:" .. provider .. ":count"
local window_key = "quota:" .. provider .. ":window_start"

local current_time = tonumber(ARGV[4])
local window_start = tonumber(redis.call('GET', window_key) or '0')

if current_time - window_start > window then
    redis.call('SET', count_key, '0')
    redis.call('SET', window_key, tostring(current_time))
    window_start = current_time
end

local count = tonumber(redis.call('GET', count_key) or '0')

if count >= limit then
    return {0, count}
end

redis.call('INCR', count_key)
return {1, count + 1}
"""

quota_check = r.register_script(QUOTA_CHECK_SCRIPT)

input_data = json.load(sys.stdin)
session_id = input_data.get('session_id')

task_id = r.get(f'session:{session_id}:task_id')
if not task_id:
    sys.exit(0)

assigned_provider = r.hget(f'task:{task_id}:meta', 'assigned_provider')
if not assigned_provider:
    assigned_provider = b'deepseek'

provider = assigned_provider.decode()

limits = {
    'claude': 45,
    'glm': 180,
    'deepseek': 999999
}

import time
result = quota_check(args=[provider, limits.get(provider, 1000), 18000, int(time.time())])
allowed, current_count = result

if not allowed:
    fallback = 'glm' if provider == 'claude' else 'deepseek'
    result = quota_check(args=[fallback, limits.get(fallback, 1000), 18000, int(time.time())])
    allowed, current_count = result
    
    if allowed:
        r.hset(f'task:{task_id}:meta', 'assigned_provider', fallback)
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"Quota exhausted for {provider}, switched to {fallback}"
            }
        }
        print(json.dumps(output))

sys.exit(0)
```

### Improvement 4: Implement Semantic Memory

**File:** `scripts/setup-prerequisites.sh` (add ML dependencies)

**Insert after line 3842:**

```bash
if [[ $HAS_PYTHON -eq 1 ]]; then
    if ask_yes_no "Install semantic memory dependencies? (ChromaDB, sentence-transformers)" "y"; then
        log_info "Installing ML dependencies..."
        if [[ $HAS_UV -eq 1 ]]; then
            uv pip install chromadb sentence-transformers
        else
            pip install chromadb sentence-transformers
        fi
        log_success "ML dependencies installed"
        
        log_info "Initializing vector database..."
        python3 -c "import chromadb; client = chromadb.PersistentClient(path='$HOME/.hekate/memory'); client.get_or_create_collection('sessions')"
        log_success "Vector database initialized at ~/.hekate/memory"
    fi
    echo
fi
```

**File:** `hooks/posttooluse_memory.py`

```python
#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError:
    sys.exit(0)

input_data = json.load(sys.stdin)
tool_name = input_data.get('tool_name')
tool_output = input_data.get('tool_response', {})

if tool_name != 'Bash':
    sys.exit(0)

content = str(tool_output)
if len(content) < 50:
    sys.exit(0)

client = chromadb.PersistentClient(path=str(Path.home() / '.hekate/memory'))
collection = client.get_or_create_collection('sessions')

session_id = input_data.get('session_id')
task_id = input_data.get('task_id', 'unknown')

model = SentenceTransformer('all-MiniLM-L6-v2')
embedding = model.encode(content[:500])

collection.add(
    embeddings=[embedding.tolist()],
    documents=[content[:500]],
    metadatas=[{
        'session_id': session_id,
        'task_id': task_id,
        'tool_name': tool_name,
        'timestamp': int(time.time())
    }],
    ids=[f"{session_id}_{int(time.time())}"]
)

sys.exit(0)
```

**File:** `hooks/pretooluse_memory.py`

```python
#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    import chromadb
    from sentence_transformers import SentenceTransformer
except ImportError:
    sys.exit(0)

input_data = json.load(sys.stdin)
transcript_path = input_data.get('transcript_path')

if not transcript_path or not Path(transcript_path).exists():
    sys.exit(0)

with open(transcript_path) as f:
    lines = f.readlines()
    thinking_blocks = [l for l in lines if '"type":"thinking"' in l]
    if not thinking_blocks:
        sys.exit(0)
    
    last_thinking = thinking_blocks[-1][-1500:]

client = chromadb.PersistentClient(path=str(Path.home() / '.hekate/memory'))
collection = client.get_collection('sessions')

model = SentenceTransformer('all-MiniLM-L6-v2')
query_embedding = model.encode(last_thinking)

results = collection.query(
    query_embeddings=[query_embedding.tolist()],
    n_results=2,
    where={"timestamp": {"$gte": int(time.time()) - 86400 * 7}}
)

if not results['documents'][0]:
    sys.exit(0)

distances = results['distances'][0]
if distances[0] > 0.4:
    sys.exit(0)

context = "\n[Semantic Memory]\n"
for doc, dist, meta in zip(results['documents'][0], distances, results['metadatas'][0]):
    similarity = 1 - dist
    if similarity >= 0.65:
        context += f"- ({similarity:.2f}) {doc[:200]}\n"

output = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": context
    }
}
print(json.dumps(output))
sys.exit(0)
```

### Improvement 5: Optimize Hook Latency

**File:** `.claude/settings.local.json`

```json
{
  "enabledPlugins": {
    "feature-dev@claude-plugins-official": true
  },
  "hooks": {
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.hekate/hooks/sessionstart_init.py",
        "timeout": 3
      }]
    }],
    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ~/.hekate/hooks/userpromptsubmit_decompose.py",
        "timeout": 30
      }]
    }],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.hekate/hooks/pretooluse_router.py",
          "timeout": 1
        }]
      },
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.hekate/hooks/pretooluse_memory.py",
          "timeout": 2
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.hekate/hooks/posttooluse_complete_task.py",
            "async": false,
            "timeout": 1
          },
          {
            "type": "command",
            "command": "python3 ~/.hekate/hooks/posttooluse_memory.py",
            "async": true,
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 ~/.hekate/hooks/posttooluse_track_outcome.py",
            "async": true,
            "timeout": 3
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.hekate/hooks/posttooluse_verify_prefetch.py",
          "async": true,
          "timeout": 10
        }]
      }
    ]
  }
}
```

**Changes:**
- Removed `.*` matchers (too broad)
- Separated sync (blocking) from async hooks
- Reduced timeout for fast operations
- Limited memory injection to high-value tools

### Improvement 6: Add Redis Cleanup

**File:** `scripts/redis-cleanup.sh` (new)

```bash
#!/bin/bash

redis-cli --scan --pattern "agent:*:heartbeat" | while read key; do
    ttl=$(redis-cli ttl "$key")
    if [[ $ttl -eq -1 ]]; then
        redis-cli del "$key"
    fi
done

redis-cli --scan --pattern "task:*:claimed" | while read key; do
    claimed=$(redis-cli get "$key")
    task_id=$(echo "$key" | cut -d: -f2)
    agent_key=$(redis-cli --scan --pattern "agent:*:task_id" | xargs -I {} redis-cli hget {} "$task_id")
    
    if [[ -z "$agent_key" && "$claimed" == "true" ]]; then
        redis-cli set "$key" "false"
        redis-cli set "task:${task_id}:status" "pending"
    fi
done

redis-cli --scan --pattern "verify:prefetch:*" | while read key; do
    ttl=$(redis-cli ttl "$key")
    if [[ $ttl -lt 0 ]]; then
        redis-cli del "$key"
    fi
done
```

**Cron setup:**

```bash
*/5 * * * * ~/.hekate/scripts/redis-cleanup.sh >> ~/.hekate/logs/cleanup.log 2>&1
```

### Improvement 7: Add OpenRouter Fallback

**File:** `hooks/userpromptsubmit_decompose.py`

```python
#!/usr/bin/env python3
import json
import sys
import os
import requests

def decompose_via_openrouter(epic_description):
    response = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers={
            'Authorization': f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            'HTTP-Referer': 'https://github.com/hekate',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'anthropic/claude-3.5-sonnet',
            'messages': [{
                'role': 'user',
                'content': f'Decompose this epic into tasks with complexity 1-10:\n{epic_description}'
            }]
        },
        timeout=30
    )
    return response.json()

def decompose_via_direct_api(epic_description):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return None
    
    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'claude-3-5-sonnet-20241022',
            'max_tokens': 2000,
            'messages': [{
                'role': 'user',
                'content': f'Decompose this epic into tasks with complexity 1-10:\n{epic_description}'
            }]
        },
        timeout=30
    )
    return response.json()

input_data = json.load(sys.stdin)
prompt = input_data.get('prompt', '')

if not ('create epic:' in prompt.lower() or 'new epic:' in prompt.lower()):
    sys.exit(0)

epic_description = prompt.split(':', 1)[1].strip()

try:
    result = decompose_via_openrouter(epic_description)
except Exception as e:
    try:
        result = decompose_via_direct_api(epic_description)
    except Exception as e2:
        output = {
            "decision": "block",
            "reason": f"Epic decomposition failed: {str(e)}, fallback failed: {str(e2)}"
        }
        print(json.dumps(output))
        sys.exit(0)

tasks = parse_tasks_from_response(result)

import redis
r = redis.Redis()
epic_id = f"epic_{int(time.time())}"

r.set(f'epic:{epic_id}:description', epic_description)
r.set(f'epic:{epic_id}:status', 'planning')
r.set(f'epic:{epic_id}:task_count', len(tasks))
r.set('latest_epic_id', epic_id)

for i, task in enumerate(tasks):
    task_id = f'task_{epic_id}_{i}'
    r.set(f'task:{task_id}:description', task['description'])
    r.set(f'task:{task_id}:complexity', task['complexity'])
    r.set(f'task:{task_id}:epic_id', epic_id)
    r.set(f'task:{task_id}:status', 'pending')
    r.sadd(f'epic:{epic_id}:tasks', task_id)

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": f"Epic {epic_id} created with {len(tasks)} tasks"
    }
}
print(json.dumps(output))
sys.exit(0)
```

### Improvement 8: Add Performance Metrics

**File:** `hooks/posttooluse_metrics.py`

```python
#!/usr/bin/env python3
import json
import sys
import time
import redis

r = redis.Redis()
input_data = json.load(sys.stdin)

tool_name = input_data.get('tool_name')
session_id = input_data.get('session_id')
task_id = r.get(f'session:{session_id}:task_id')

if task_id:
    provider = r.hget(f'task:{task_id}:meta', 'assigned_provider')
    complexity = r.get(f'task:{task_id}:complexity')
    
    if provider and complexity:
        metric_key = f"metrics:tool_use:{provider.decode()}:{complexity.decode()}:{tool_name}"
        r.incr(metric_key)
        r.expire(metric_key, 86400 * 7)

sys.exit(0)
```

## Summary of Changes

| File | Change Type | Lines Changed | Priority |
|------|-------------|---------------|----------|
| `posttooluse_spawn_agents.py` | Complete rewrite | ~100 | P0 |
| `sessionstart_init.py` | Add provider switching | +50 | P0 |
| `posttooluse_complete_task.py` | Fix detection logic | ~80 | P0 |
| `pretooluse_router.py` | Add Lua script | +40 | P0 |
| `setup-prerequisites.sh` | Add ML deps | +15 | P1 |
| `posttooluse_memory.py` | Implement ChromaDB | +60 | P1 |
| `pretooluse_memory.py` | Implement retrieval | +50 | P1 |
| `.claude/settings.local.json` | Optimize matchers | ~30 | P1 |
| `redis-cleanup.sh` | New file | +30 | P2 |
| `userpromptsubmit_decompose.py` | Add fallback | +40 | P2 |
| `posttooluse_metrics.py` | Add tracking | +20 | P2 |

**Total effort:** 5-7 days for P0+P1 changes