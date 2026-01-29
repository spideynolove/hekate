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
        return None
    except:
        return None

def get_provider_env(provider):
    """Get environment variables for a provider"""
    env = os.environ.copy()

    if provider == 'claude':
        # Use default Claude
        pass
    elif provider == 'glm':
        env['ANTHROPIC_BASE_URL'] = 'https://api.z.ai/api/anthropic'
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('Z_AI_API_KEY', '')
        env['ANTHROPIC_DEFAULT_OPUS_MODEL'] = 'glm-4.7'
    elif provider == 'deepseek':
        env['ANTHROPIC_BASE_URL'] = 'https://api.deepseek.com/anthropic'
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('DEEPSEEK_API_KEY', '')
    elif provider == 'openrouter':
        env['ANTHROPIC_BASE_URL'] = 'https://openrouter.ai/api'
        env['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('OPENROUTER_API_KEY', '')

    return env

def spawn_agent_for_task(task_id, worktree, provider):
    """Spawn a Claude Code session for a task"""
    # Create worktree if it doesn't exist
    if not os.path.exists(worktree):
        result = subprocess.run([
            'git', 'worktree', 'add', '-b', f'task-{task_id}', worktree
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[HEKATE] Failed to create worktree for {task_id}", file=sys.stderr)
            return None

    # Get provider environment
    env = get_provider_env(provider)

    # Set task ID for SessionStart hook
    env['HEKATE_TASK_ID'] = task_id
    env['HEKATE_PROVIDER'] = provider

    # Spawn Claude Code in background
    # Note: We use a simple wrapper script since we can't pass env vars easily
    pid = subprocess.Popen([
        'claude', str(worktree)
    ], env=env, start_new_session=True).pid

    return pid

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_response = input_data.get('tool_response', {})
    tool_name = tool_response.get('tool_name', '')

    # Only trigger after Beads commands
    # Try to match 'bd' command or common Beads patterns
    command = None
    if tool_name == 'Bash':
        command = tool_response.get('tool_input', {}).get('command', '')

    if not command or not command.startswith('bd '):
        sys.exit(0)

    # Check if this was a task creation (bd create)
    if 'create' not in command and 'init' not in command:
        sys.exit(0)

    print(f"[HEKATE] Checking for pending tasks...", file=sys.stderr)

    # Get active epics from Redis
    epic_keys = safe_redis_command(['redis-cli', 'KEYS', 'epic:*:status'], '')
    if not epic_keys:
        sys.exit(0)

    spawned_count = 0

    for epic_key in epic_keys.split('\n'):
        if not epic_key:
            continue

        epic_id = epic_key.split(':')[1]
        status = safe_redis_command(['redis-cli', 'GET', epic_key], '')

        if status != 'active':
            continue

        # Get pending tasks for this epic
        # We need to check Beads for tasks
        tasks_json = safe_beads_command(['bd', 'list', '--json'])
        if not tasks_json:
            continue

        try:
            tasks = json.loads(tasks_json)
            pending_tasks = []

            for task in tasks:
                task_id = task.get('id', '')
                task_status = task.get('status', 'unknown')

                # Check if this task belongs to our epic
                epic_for_task = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:epic_id'], '')
                if epic_for_task != epic_id:
                    continue

                # Check if already claimed
                claimed = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:claimed'], 'false')
                if claimed == 'true':
                    continue

                if task_status in ['open', 'pending']:
                    complexity = int(safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], '5'))
                    provider = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:provider'], 'auto')
                    pending_tasks.append({
                        'id': task_id,
                        'complexity': complexity,
                        'provider': provider,
                        'description': task.get('title', task.get('description', ''))
                    })
        except:
            continue

        if not pending_tasks:
            continue

        print(f"[HEKATE] Found {len(pending_tasks)} pending tasks for epic {epic_id}", file=sys.stderr)

        # Group by provider and spawn agents
        provider_limits = {
            'claude': 2,
            'glm': 4,
            'deepseek': 6,
            'openrouter': 2,
            'auto': 2
        }

        provider_counts = {p: 0 for p in provider_limits.keys()}

        worktrees_dir = Path.home() / 'hekate-worktrees'

        for task in pending_tasks:
            task_id = task['id']
            provider = task['provider']

            # Check provider limit
            if provider_counts.get(provider, 0) >= provider_limits.get(provider, 2):
                continue

            worktree = str(worktrees_dir / task_id)

            # Spawn agent
            pid = spawn_agent_for_task(task_id, worktree, provider)
            if pid:
                # Track in Redis
                safe_redis_command(['redis-cli', 'SET', f'agent:{pid}:task_id', task_id])
                safe_redis_command(['redis-cli', 'SET', f'agent:{pid}:provider', provider])
                safe_redis_command(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))])
                safe_redis_command(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'])

                # Mark task as claimed
                safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:claimed', 'true'])
                safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:session_pid', str(pid)])
                safe_redis_command(['redis-cli', 'SET', f'task:{task_id}:status', 'in_progress'])

                # Update Beads status
                safe_beads_command(['bd', 'update', task_id, '--status', 'in_progress'])

                provider_counts[provider] = provider_counts.get(provider, 0) + 1
                spawned_count += 1

                print(f"[HEKATE] Spawned agent for {task_id} (provider={provider}, pid={pid})", file=sys.stderr)

    if spawned_count > 0:
        print(f"[HEKATE] Spawned {spawned_count} agents total", file=sys.stderr)

    sys.exit(0)

if __name__ == '__main__':
    main()
