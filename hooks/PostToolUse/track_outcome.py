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
    tool_input = tool_response.get('tool_input', {})

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Get the provider that was used for this task
    provider = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:provider'], 'unknown')

    # Get task complexity
    complexity = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], '5')

    # Extract task features for pattern matching
    task_info_result = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:description'])
    task_description = task_info_result if task_info_result else task_id

    # Build feature hash for pattern learning
    features = {
        'complexity': int(complexity) if complexity.isdigit() else 5,
        'tool_type': tool_name,
        'is_write_op': tool_name in ['Write', 'Edit', 'MultiEdit'],
        'is_read_op': tool_name in ['Read', 'Glob', 'Grep'],
        'is_test': 'test' in str(tool_input).lower(),
    }

    # Create feature hash
    feature_str = json.dumps(features, sort_keys=True)
    feature_hash = str(hash(feature_str))

    # Record routing outcome
    timestamp = int(time.time())

    # Check if tool execution was successful
    success = True
    if tool_response.get('success') == False:
        success = False

    # Record individual routing decision
    routing_record = {
        'task_id': task_id,
        'provider': provider,
        'complexity': complexity,
        'tool_name': tool_name,
        'success': success,
        'timestamp': timestamp,
        'features': features
    }

    # Store in routing history
    safe_redis_command(['redis-cli', 'LPUSH', 'routing:history', json.dumps(routing_record)])
    safe_redis_command(['redis-cli', 'LTRIM', 'routing:history', '0', '999'])  # Keep last 1000

    # Store by feature hash for pattern learning
    pattern_key = f'routing:pattern:{feature_hash}'
    existing = safe_redis_command(['redis-cli', 'GET', pattern_key])

    if existing:
        try:
            pattern_data = json.loads(existing)
            pattern_data['attempts'] = pattern_data.get('attempts', 0) + 1
            if success:
                pattern_data['successes'] = pattern_data.get('successes', 0) + 1
            pattern_data['last_used'] = timestamp
            safe_redis_command(['redis-cli', 'SET', pattern_key, json.dumps(pattern_data)])
            safe_redis_command(['redis-cli', 'EXPIRE', pattern_key, '86400'])  # 24 hours
        except:
            pass
    else:
        pattern_data = {
            'features': features,
            'provider': provider,
            'attempts': 1,
            'successes': 1 if success else 0,
            'created_at': timestamp,
            'last_used': timestamp
        }
        safe_redis_command(['redis-cli', 'SET', pattern_key, json.dumps(pattern_data)])
        safe_redis_command(['redis-cli', 'EXPIRE', pattern_key, '86400'])

    # Update provider stats
    provider_stats_key = f'provider:stats:{provider}'
    provider_stats = safe_redis_command(['redis-cli', 'GET', provider_stats_key])

    if provider_stats:
        try:
            stats = json.loads(provider_stats)
            stats['total_tasks'] = stats.get('total_tasks', 0) + 1
            if success:
                stats['successful_tasks'] = stats.get('successful_tasks', 0) + 1
            # Update success rate
            stats['success_rate'] = stats.get('successful_tasks', 0) / stats.get('total_tasks', 1)
            safe_redis_command(['redis-cli', 'SET', provider_stats_key, json.dumps(stats)])
        except:
            pass
    else:
        stats = {
            'total_tasks': 1,
            'successful_tasks': 1 if success else 0,
            'success_rate': 1.0 if success else 0.0,
            'created_at': timestamp
        }
        safe_redis_command(['redis-cli', 'SET', provider_stats_key, json.dumps(stats)])

    # Update complexity-specific stats
    complexity_stats_key = f'provider:complexity:{provider}:{complexity}'
    complexity_stats = safe_redis_command(['redis-cli', 'GET', complexity_stats_key])

    if complexity_stats:
        try:
            cstats = json.loads(complexity_stats)
            cstats['attempts'] = cstats.get('attempts', 0) + 1
            if success:
                cstats['successes'] = cstats.get('successes', 0) + 1
            cstats['success_rate'] = cstats.get('successes', 0) / cstats.get('attempts', 1)
            safe_redis_command(['redis-cli', 'SET', complexity_stats_key, json.dumps(cstats)])
        except:
            pass
    else:
        cstats = {
            'attempts': 1,
            'successes': 1 if success else 0,
            'success_rate': 1.0 if success else 0.0
        }
        safe_redis_command(['redis-cli', 'SET', complexity_stats_key, json.dumps(cstats)])

    sys.exit(0)

if __name__ == '__main__':
    main()
