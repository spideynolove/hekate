#!/usr/bin/env python3
import json, sys, subprocess, os, time
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
    tool_response = input_data.get('tool_response', {})
    tool_name = tool_response.get('tool_name', '')

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Check for task completion signal (git commit)
    if tool_name == 'Bash':
        command = tool_response.get('tool_input', {}).get('command', '')

        if 'git commit' in command or 'git push' in command:
            print(f"[HEKATE] Task {task_id} appears complete", file=sys.stderr)

            # Get epic ID
            epic_id = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:epic_id'])
            if not epic_id:
                sys.exit(0)

            # Mark task complete in Beads
            safe_beads_command(['bd', 'close', task_id, '--reason', 'Completed by agent'])

            # Update Redis
            safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:status', 'complete'])

            # Update epic progress
            new_count = safe_redis_command(['redis-cli', 'INCR', f'epic:{epic_id}:complete_count'])

            # Get total task count
            task_count = int(safe_redis_command(['redis-cli', 'GET', f'epic:{epic_id}:task_count'], '0') or '0')

            print(f"[HEKATE] Epic {epic_id} progress: {new_count}/{task_count} tasks complete", file=sys.stderr)

            # Check if epic is complete
            if new_count and task_count and int(new_count) >= int(task_count):
                print(f"[HEKATE] Epic {epic_id} is complete!", file=sys.stderr)

                # Mark epic complete
                safe_redis_command(['redis-cli', 'SET', f'epic:{epic_id}:status', 'complete'])

                # Inject completion context
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": f"\n[HEKATE] Epic {epic_id} is complete! All {task_count} tasks finished.\n"
                    }
                }
                print(json.dumps(output))

    sys.exit(0)

if __name__ == '__main__':
    main()
