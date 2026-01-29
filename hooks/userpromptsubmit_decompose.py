#!/usr/bin/env python3
import json, sys, subprocess, os, time, re
from pathlib import Path

def safe_redis_command(cmd, default=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return default

def safe_beads_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout
    except subprocess.TimeoutExpired:
        print("[HEKATE] Beads command timeout", file=sys.stderr)
    except Exception as e:
        print(f"[HEKATE] Beads error: {e}", file=sys.stderr)
    return None

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = input_data.get('prompt', '')
    session_id = input_data.get('session_id', '')

    if not prompt:
        sys.exit(0)

    # Check if this is an epic creation command
    epic_patterns = [
        r'(?:create|new)\s+epic:\s*(.+)',
        r'epic:\s*(.+)',
        r'create\s+epic\s+(.+)',
        r'new\s+epic\s+(.+)',
    ]

    epic_description = None
    for pattern in epic_patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            epic_description = match.group(1).strip()
            break

    if not epic_description:
        sys.exit(0)

    print(f"[HEKATE] Decomposing epic: {epic_description[:50]}...", file=sys.stderr)

    # Check if OpenRouter API key is available
    openrouter_key = os.environ.get('OPENROUTER_API_KEY')
    if not openrouter_key:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"\n[HEKATE] OPENROUTER_API_KEY not found. Please set it in your environment.\n"
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    # Call OpenRouter API for decomposition
    try:
        import requests
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{
                    "role": "system",
                    "content": """Decompose the epic into tasks. For each task:
1. Provide a clear description (max 100 chars)
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
            },
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code}")

        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

        # Extract JSON from response (in case there's extra text)
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group(0)

        tasks = json.loads(content).get('tasks', [])

        if not tasks:
            raise Exception("No tasks returned from decomposition")

    except Exception as e:
        print(f"[HEKATE] Decomposition failed: {e}", file=sys.stderr)
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"\n[HEKATE] Epic decomposition failed: {e}\nYou can create tasks manually using 'bd create'.\n"
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    # Create epic ID from timestamp
    epic_id = f"epic-{int(time.time())}"

    # Initialize epic in Redis
    safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:status', 'planning'])
    safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:task_count', str(len(tasks))])
    safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:complete_count', '0'])
    safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:description', epic_description])

    # Create tasks via Beads CLI and store complexity in Redis
    task_ids = []
    for i, task in enumerate(tasks):
        task_desc = task['description']
        complexity = task.get('complexity', 5)

        # Priority is inverse of complexity (1 = highest priority in Beads)
        priority = max(1, 11 - complexity)

        # Create task in Beads
        result = safe_beads_command([
            'bd', 'create', f'[{epic_id}] {task_desc}',
            '-p', str(priority)
        ])

        if not result:
            print(f"[HEKATE] Failed to create task {i+1}", file=sys.stderr)
            continue

        # Extract task ID from Beads output
        # Beads typically outputs: "Created issue bd-xxxx"
        task_id_match = re.search(r'bd-[a-f0-9]+', result)
        if task_id_match:
            task_id = task_id_match.group(0)
            task_ids.append(task_id)

            # Store complexity in Redis
            safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:complexity', str(complexity)])
            safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:epic_id', epic_id])
            safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:status', 'pending'])

            # Get provider for this complexity
            provider = safe_redis_command(['redis-cli', 'GET', f'routing:complexity:{complexity}'], 'auto')
            safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:provider', provider])

            print(f"[HEKATE] Created task {i+1}/{len(tasks)}: {task_id} (complexity={complexity}, provider={provider})", file=sys.stderr)

    # Update epic status
    safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:status', 'active'])

    # Store task list for epic
    safe_redis_command(['redis-cli', 'SADD', f'epic:{epic_id}:tasks'] + task_ids)

    # Provide context back to user
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"\n[HEKATE] Epic {epic_id} decomposed into {len(tasks)} tasks.\nTasks created in Beads: {', '.join(task_ids[:5])}{'...' if len(task_ids) > 5 else ''}\n\nAgent spawning will begin automatically after epic creation.\n"
        }
    }
    print(json.dumps(output))

    sys.exit(0)

if __name__ == '__main__':
    main()
