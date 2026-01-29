#!/usr/bin/env python3
import json, sys, subprocess, os
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
    except:
        return None

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    source = input_data.get('source', 'startup')

    # Check if this is a Hekate-spawned agent
    task_id = os.environ.get('HEKATE_TASK_ID')
    provider = os.environ.get('HEKATE_PROVIDER')

    if not task_id:
        # Not a Hekate agent, exit silently
        sys.exit(0)

    print(f"[HEKATE] Initializing agent for task {task_id}", file=sys.stderr)

    # Store session mapping
    safe_redis_command(['redis-cli', 'SET', f'session:{session_id}:task_id', task_id])
    safe_redis_command(['redis-cli', 'SET', f'session:{session_id}:provider', provider])

    # Get task details from Beads
    task_info = safe_beads_command(['bd', 'show', task_id])
    if not task_info:
        print(f"[HEKATE] Could not fetch task info from Beads", file=sys.stderr)
        sys.exit(0)

    # Get complexity from Redis
    complexity = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], 'unknown')
    epic_id = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:epic_id'], 'unknown')

    # Get epic description
    epic_description = safe_redis_command(['redis-cli', 'GET', f'epic:{epic_id}:description'], '')

    # Parse task description from Beads output
    # Format: "bd-xxxx [P0] [open] Task description here"
    task_description = task_id
    for line in task_info.split('\n'):
        if line.strip() and not line.startswith('Created') and not line.startswith('Status'):
            # Extract description part
            parts = line.split(']', 2)
            if len(parts) >= 2:
                task_description = parts[-1].strip()
                break

    # Build context
    context = f"""
[HEKATE AGENT SESSION]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Session ID: {session_id}
Task ID: {task_id}
Provider: {provider}
Complexity: {complexity}/10

Epic: {epic_id}
{epic_description[:100] if epic_description else ''}

Task: {task_description}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You are an autonomous Hekate agent working on this task.

Guidelines:
• Focus on completing the specific task described above
• Write tests first (TDD) when implementing features
• Commit your work when the task is complete
• The system will automatically detect completion and update status

When you believe the task is complete:
1. Run tests to verify your work
2. Commit with a descriptive message
3. The system will mark the task as complete automatically
"""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context
        }
    }

    print(json.dumps(output))
    sys.exit(0)

if __name__ == '__main__':
    main()
