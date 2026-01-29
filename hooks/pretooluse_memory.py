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

def find_relevant_memories(task_id, current_command):
    """Find memories relevant to the current task/command"""
    relevant_memories = []

    # Get recent memories from inbox
    inbox_items = safe_redis_command(['redis-cli', 'LRANGE', 'memory:inbox:recent', '0', '9'], '')
    if not inbox_items:
        return []

    # Get current task info
    task_description = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:description'], '')
    current_provider = safe_redis_command(['redis-cli', 'GET', f'task:{task_id}:provider'], 'unknown')

    command_lower = current_command.lower() if current_command else ''
    task_desc_lower = task_description.lower() if task_description else ''

    # Keywords that indicate relevance
    relevance_keywords = {
        'bug': ['fix', 'bug', 'error', 'issue', 'debug', 'patch'],
        'test': ['test', 'spec', 'assert'],
        'feature': ['implement', 'add', 'create', 'feature'],
        'setup': ['install', 'setup', 'config', 'configure'],
        'refactor': ['refactor', 'clean', 'optimize'],
    }

    # Determine current context type
    current_context = None
    for context_type, keywords in relevance_keywords.items():
        if any(keyword in command_lower for keyword in keywords):
            current_context = context_type
            break

    # Parse memories
    for item in inbox_items.split('\n'):
        if not item:
            continue
        try:
            memory = json.loads(item)
            pattern = memory.get('pattern', {})
            pattern_type = pattern.get('type', 'general')
            provider = memory.get('provider', 'unknown')

            # Skip if from same provider (already know this)
            if provider == current_provider:
                continue

            # Skip if too old (> 30 minutes)
            memory_time = memory.get('timestamp', 0)
            if time.time() - memory_time > 1800:
                continue

            # Check relevance
            is_relevant = False
            relevance_reason = None

            # Same pattern type
            if current_context == pattern_type:
                is_relevant = True
                relevance_reason = f"same pattern type ({pattern_type})"

            # Check for keyword overlap
            command_snippet = pattern.get('command_snippet', '')
            snippet_lower = command_snippet.lower()

            for context_type, keywords in relevance_keywords.items():
                if any(keyword in command_lower for keyword in keywords) and \
                   any(keyword in snippet_lower for keyword in keywords):
                    is_relevant = True
                    relevance_reason = f"related ({context_type})"
                    break

            if is_relevant:
                memory_age = int((time.time() - memory_time) / 60)  # minutes ago
                relevant_memories.append({
                    'pattern': pattern,
                    'provider': provider,
                    'task_id': memory.get('task_id', 'unknown'),
                    'age_minutes': memory_age,
                    'reason': relevance_reason
                })
        except:
            continue

    return relevant_memories[:5]  # Max 5 relevant memories

def format_memory_context(memories):
    """Format memories as additional context"""
    if not memories:
        return ""

    context_parts = []
    context_parts.append("[HEKATE MEMORY] Recent relevant work from other agents:")
    context_parts.append("")

    for memory in memories:
        pattern = memory['pattern']
        provider = memory['provider']
        age = memory['age_minutes']
        reason = memory['reason']
        task_id = memory['task_id']

        context_parts.append(f"  • {provider} agent ({age}m ago, {reason}):")
        context_parts.append(f"    {pattern.get('command_snippet', 'unknown')[:80]}")
        context_parts.append(f"    Task: {task_id}")
        context_parts.append("")

    return "\n".join(context_parts)

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

    # Extract current command
    current_command = None
    if tool_name == 'Bash':
        current_command = tool_input.get('command', '')

    # Find relevant memories
    relevant_memories = find_relevant_memories(task_id, current_command)

    if not relevant_memories:
        sys.exit(0)

    # Format and inject context
    memory_context = format_memory_context(relevant_memories)

    if memory_context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": memory_context
            }
        }
        print(json.dumps(output))

        print(f"[HEKATE MEMORY] Injected {len(relevant_memories)} relevant memories", file=sys.stderr)

    sys.exit(0)

if __name__ == '__main__':
    main()
