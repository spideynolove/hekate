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
    tool_response = input_data.get('tool_response', {})
    tool_name = tool_response.get('tool_name', '')

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Get provider for this session
    provider = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:provider'], 'unknown')

    # Get task complexity
    complexity = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], '5')

    # Determine complexity label for metrics
    complexity_val = int(complexity) if complexity.isdigit() else 5
    if complexity_val <= 4:
        complexity_label = 'low'
    elif complexity_val <= 7:
        complexity_label = 'medium'
    else:
        complexity_label = 'high'

    # Update task counter metric
    metric_key = f'metrics:agent_tasks_total:{provider}:{complexity_label}'
    safe_redis_command(['redis-cli', 'INCR', metric_key])

    # Check quota and update quota remaining metric
    quota_count = int(safe_redis_command(['redis-cli', 'GET', f'quota:{provider}:count'], '0') or '0')
    quota_limit = int(safe_redis_command(['redis-cli', 'GET', f'quota:{provider}:limit'], '50') or '50')
    quota_remaining = quota_limit - quota_count

    safe_redis_command([
        'redis-cli', 'SET',
        f'metrics:provider_quota_remaining:{provider}',
        str(quota_remaining)
    ])

    # Alert if quota low
    if quota_remaining <= 5:
        alert = {
            'type': 'quota',
            'severity': 'critical' if quota_remaining == 0 else 'warning',
            'provider': provider,
            'remaining': quota_remaining,
            'threshold': 5,
            'timestamp': int(time.time())
        }
        safe_redis_command(['redis-cli', 'SET', 'alerts:quota_warning', json.dumps(alert)])
        safe_redis_command(['redis-cli', 'EXPIRE', 'alerts:quota_warning', '300'])  # 5 minutes

    sys.exit(0)

if __name__ == '__main__':
    main()
