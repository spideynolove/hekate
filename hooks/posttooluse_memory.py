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

def is_solution_pattern(command, output):
    """Detect if this command represents a solution worth remembering"""
    solution_indicators = [
        'fix', 'solve', 'resolve', 'patch', 'correct',
        'repair', 'debug', 'working'
    ]

    error_indicators = [
        'error', 'fail', 'bug', 'issue', 'broken',
        'not working', 'exception', 'traceback'
    ]

    command_lower = command.lower()
    output_lower = output.lower() if output else ''

    # Check if command looks like it's fixing something
    has_solution_word = any(indicator in command_lower for indicator in solution_indicators)

    # Check if it's addressing an error
    has_error_context = any(indicator in command_lower for indicator in error_indicators)

    # Check if output shows success
    output_indicates_success = (
        'success' in output_lower or
        'fixed' in output_lower or
        'resolved' in output_lower or
        ('error' in command_lower and 'error' not in output_lower)
    )

    # Also remember test additions and significant refactors
    is_test_addition = 'test' in command_lower and any(word in command_lower for word in ['add', 'create', 'write'])
    is_significant = (
        'refactor' in command_lower or
        'optimize' in command_lower or
        'implement' in command_lower
    )

    return (
        (has_solution_word and has_error_context) or
        (has_solution_word and output_indicates_success) or
        is_test_addition or
        is_significant
    )

def extract_pattern(command, output, tool_name):
    """Extract a reusable pattern from this operation"""
    command_lower = command.lower()

    # Determine pattern type
    if 'fix' in command_lower or 'bug' in command_lower:
        pattern_type = 'bugfix'
    elif 'test' in command_lower:
        pattern_type = 'test'
    elif 'refactor' in command_lower:
        pattern_type = 'refactor'
    elif 'implement' in command_lower or 'add' in command_lower:
        pattern_type = 'feature'
    elif 'install' in command_lower or 'setup' in command_lower:
        pattern_type = 'setup'
    else:
        pattern_type = 'general'

    # Extract the core command (remove file paths, specific values)
    core_command = command
    # Remove long strings/paths
    core_command = re.sub(r'["\'][^"\']*["\']', '""', core_command)
    core_command = re.sub(r'/[\w\-./]+', '/path', core_command)
    # Truncate if too long
    if len(core_command) > 200:
        core_command = core_command[:197] + '...'

    return {
        'type': pattern_type,
        'tool': tool_name,
        'command_snippet': core_command,
        'original_command': command[:200],  # Store for reference
    }

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

    # Get provider for this session
    provider = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:provider'], 'unknown')

    # Extract command for Bash tools
    command = None
    if tool_name == 'Bash':
        command = tool_input.get('command', '')

    if not command:
        sys.exit(0)

    # Get output
    output = tool_response.get('result', '')
    if isinstance(output, dict):
        output = str(output)

    # Check if this is a solution pattern
    if not is_solution_pattern(command, output):
        sys.exit(0)

    # Extract pattern
    pattern = extract_pattern(command, output, tool_name)

    # Create memory entry
    memory_entry = {
        'pattern': pattern,
        'task_id': task_id,
        'provider': provider,
        'agent_pid': os.getpid(),
        'timestamp': int(time.time()),
        'success': tool_response.get('success', True)
    }

    # Store in shared inbox
    safe_redis_command(['redis-cli', 'LPUSH', 'memory:inbox:recent', json.dumps(memory_entry)])
    # Keep last 100 entries
    safe_redis_command(['redis-cli', 'LTRIM', 'memory:inbox:recent', '0', '99'])
    # Set TTL to 1 hour (memory decay)
    safe_redis_command(['redis-cli', 'EXPIRE', 'memory:inbox:recent', '3600'])

    # Also store by pattern type for targeted lookups
    pattern_type_key = f'memory:inbox:type:{pattern["type"]}'
    safe_redis_command(['redis-cli', 'LPUSH', pattern_type_key, json.dumps(memory_entry)])
    safe_redis_command(['redis-cli', 'LTRIM', pattern_type_key, '0', '49'])
    safe_redis_command(['redis-cli', 'EXPIRE', pattern_type_key, '7200'])  # 2 hours

    # Store by provider for agent-to-agent learning
    provider_key = f'memory:inbox:provider:{provider}'
    safe_redis_command(['redis-cli', 'LPUSH', provider_key, json.dumps(memory_entry)])
    safe_redis_command(['redis-cli', 'LTRIM', provider_key, '0', '49'])
    safe_redis_command(['redis-cli', 'EXPIRE', provider_key, '3600'])

    print(f"[HEKATE MEMORY] Stored {pattern['type']} pattern from {provider}", file=sys.stderr)

    sys.exit(0)

if __name__ == '__main__':
    main()
