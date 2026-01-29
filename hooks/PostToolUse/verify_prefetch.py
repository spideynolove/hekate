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

def should_prefetch_verification(tool_name, tool_input):
    """Check if we should prefetch verification based on tool usage"""
    # Prefetch after code changes
    if tool_name in ['Write', 'Edit', 'MultiEdit']:
        return True

    # Prefetch after git operations (indicating work completion)
    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        if 'git' in command and ('commit' in command or 'add' in command):
            return True

    return False

def get_verification_providers(complexity):
    """Get list of providers for verification cascade based on complexity"""
    complexity = int(complexity) if complexity and complexity.isdigit() else 5

    if complexity <= 4:
        # Low complexity: DeepSeek only
        return ['deepseek']
    elif complexity <= 7:
        # Medium complexity: DeepSeek → GLM
        return ['deepseek', 'glm']
    else:
        # High complexity: GLM → Claude
        return ['glm', 'claude']

def start_verification_async(task_id, provider, complexity):
    """Start async verification (stores intent in Redis)"""
    prefetch_data = {
        'task_id': task_id,
        'provider': provider,
        'complexity': complexity,
        'status': 'pending',
        'timestamp': int(time.time())
    }

    key = f'verify:prefetch:{task_id}:{provider}'
    safe_redis_command(['redis-cli', 'SET', key, json.dumps(prefetch_data)])
    safe_redis_command(['redis-cli', 'EXPIRE', key, '600'])  # 10 minutes

    # In a real implementation, this would spawn a background process
    # to call the provider API directly. For now, we store the intent.
    #
    # The actual verification would:
    # 1. Get task requirements from Beads
    # 2. Call provider API with verification prompt
    # 3. Store result in Redis with status='complete'
    # 4. Update the verify:prefetch key

    return key

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

    # Check if we should prefetch
    if not should_prefetch_verification(tool_name, tool_input):
        sys.exit(0)

    # Get task complexity
    complexity = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:complexity'], '5')

    # Get verification providers for this complexity
    providers = get_verification_providers(complexity)

    print(f"[HEKATE VERIFY] Prefetching verification for {task_id} (c={complexity})", file=sys.stderr)

    # Start verification for each provider
    for provider in providers:
        key = start_verification_async(task_id, provider, complexity)
        print(f"[HEKATE VERIFY] → {provider}: Queued (expires 10min)", file=sys.stderr)

    sys.exit(0)

if __name__ == '__main__':
    main()
