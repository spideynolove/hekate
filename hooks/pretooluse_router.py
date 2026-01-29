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

def find_best_provider_by_pattern(features, current_provider):
    """Find the best provider based on historical patterns"""
    # Create feature hash
    feature_str = json.dumps(features, sort_keys=True)
    feature_hash = str(hash(feature_str))

    # Check for exact pattern match
    pattern_key = f'routing:pattern:{feature_hash}'
    pattern_data = safe_redis_command(['redis-cli', 'GET', pattern_key])

    if pattern_data:
        try:
            pattern = json.loads(pattern_data)
            success_rate = pattern.get('successes', 0) / pattern.get('attempts', 1)
            if success_rate > 0.7 and pattern.get('attempts', 0) >= 3:
                # We have enough data with good success rate
                return pattern.get('provider', current_provider)
        except:
            pass

    # Check for complexity-based patterns
    complexity = features.get('complexity', 5)

    # Get stats for each provider at this complexity level
    provider_scores = {}
    for provider in ['claude', 'glm', 'deepseek', 'openrouter']:
        stats_key = f'provider:complexity:{provider}:{complexity}'
        stats_data = safe_redis_command(['redis-cli', 'GET', stats_key])

        if stats_data:
            try:
                stats = json.loads(stats_data)
                success_rate = stats.get('success_rate', 0.5)
                attempts = stats.get('attempts', 0)

                if attempts >= 5:
                    # Score = success_rate, but prioritize data confidence
                    provider_scores[provider] = (success_rate, attempts)
            except:
                pass

    if provider_scores:
        # Find best provider by highest success rate with sufficient attempts
        best_provider = max(provider_scores.items(), key=lambda x: (x[1][0], x[1][1]))
        if best_provider[1][1] >= 5:  # Minimum confidence threshold
            return best_provider[0]

    return current_provider

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Get assigned provider (from complexity mapping)
    base_provider = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:provider'], 'auto')

    # Get task complexity
    complexity = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], '5')

    # Build features for pattern matching
    features = {
        'complexity': int(complexity) if complexity.isdigit() else 5,
        'tool_type': tool_name,
        'is_write_op': tool_name in ['Write', 'Edit', 'MultiEdit'],
        'is_read_op': tool_name in ['Read', 'Glob', 'Grep'],
        'is_test': 'test' in str(tool_input).lower(),
    }

    # Try to find better provider based on patterns
    assigned_provider = find_best_provider_by_pattern(features, base_provider)

    if assigned_provider != base_provider:
        print(f"[HEKATE] Pattern-based routing: {base_provider} → {assigned_provider}", file=sys.stderr)

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
