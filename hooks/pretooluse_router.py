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

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    tool_name = input_data.get('tool_name', '')

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Get assigned provider
    assigned_provider = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:provider'], 'auto')

    # Check quota for assigned provider
    quota_count = int(safe_redis_command(['redis-cli', 'GET', f'quota:{assigned_provider}:count'], '0') or '0')
    quota_limit = int(safe_redis_command(['redis-cli', 'GET', f'quota:{assigned_provider}:limit'], '50') or '50')

    # Check if quota window expired (24 hours)
    window_start = safe_redis_command(['redis-cli', 'GET', f'quota:{assigned_provider}:window_start'])
    if window_start:
        window_start = int(window_start)
        current_time = int(time.time())
        if current_time - window_start > 86400:  # 24 hours
            # Reset quota
            safe_redis_command(['redis-cli', 'SET', f'quota:{assigned_provider}:count', '0'])
            safe_redis_command(['redis-cli', 'SET', f'quota:{assigned_provider}:window_start', str(current_time)])
            quota_count = 0

    # If quota exhausted, find alternative
    if quota_count >= quota_limit:
        print(f"[HEKATE] Provider {assigned_provider} quota exhausted ({quota_count}/{quota_limit})", file=sys.stderr)

        # Try alternative providers in order
        for alt_provider in ['deepseek', 'glm', 'openrouter', 'claude']:
            if alt_provider == assigned_provider:
                continue

            alt_count = int(safe_redis_command(['redis-cli', 'GET', f'quota:{alt_provider}:count'], '0') or '0')
            alt_limit = int(safe_redis_command(['redis-cli', 'GET', f'quota:{alt_provider}:limit'], '100') or '100')

            if alt_count < alt_limit:
                print(f"[HEKATE] Switching to {alt_provider} ({alt_count}/{alt_limit} available)", file=sys.stderr)

                # Update environment variables for the provider
                if alt_provider == 'deepseek':
                    os.environ['ANTHROPIC_BASE_URL'] = 'https://api.deepseek.com/anthropic'
                    os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('DEEPSEEK_API_KEY', '')
                elif alt_provider == 'glm':
                    os.environ['ANTHROPIC_BASE_URL'] = 'https://api.z.ai/api/anthropic'
                    os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('Z_AI_API_KEY', '')
                    os.environ['ANTHROPIC_DEFAULT_OPUS_MODEL'] = 'glm-4.7'
                elif alt_provider == 'openrouter':
                    os.environ['ANTHROPIC_BASE_URL'] = 'https://openrouter.ai/api'
                    os.environ['ANTHROPIC_AUTH_TOKEN'] = os.environ.get('OPENROUTER_API_KEY', '')

                # Use the alternative provider for this request
                assigned_provider = alt_provider
                break

    # Increment quota for the actual provider being used
    safe_redis_command(['redis-cli', 'INCR', f'quota:{assigned_provider}:count'])

    # Update heartbeat for this agent
    pid = os.getpid()
    safe_redis_command(['redis-cli', 'SET', f'agent:{pid}:heartbeat', str(int(time.time()))])
    safe_redis_command(['redis-cli', 'EXPIRE', f'agent:{pid}:heartbeat', '30'])

    sys.exit(0)

if __name__ == '__main__':
    main()
