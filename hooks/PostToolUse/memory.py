#!/usr/bin/env python3
import json, sys, subprocess, os, time, requests
from pathlib import Path

try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

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

    has_solution_word = any(indicator in command_lower for indicator in solution_indicators)
    has_error_context = any(indicator in command_lower for indicator in error_indicators)

    output_indicates_success = (
        'success' in output_lower or
        'fixed' in output_lower or
        'resolved' in output_lower or
        ('error' in command_lower and 'error' not in output_lower)
    )

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

    core_command = command
    import re
    core_command = re.sub(r'["\'][^"\']*["\']', '""', core_command)
    core_command = re.sub(r'/[\w\-./]+', '/path', core_command)
    if len(core_command) > 200:
        core_command = core_command[:197] + '...'

    return {
        'type': pattern_type,
        'tool': tool_name,
        'command_snippet': core_command,
        'original_command': command[:200],
    }

def get_embedding_openrouter(text):
    """Generate embedding using OpenRouter API (primary)"""
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return None

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/text-embedding-3-small",
                "input": text[:500]
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        print(f"[HEKATE MEMORY] OpenRouter embedding failed: {e}", file=sys.stderr)
    return None

def get_embedding_voyage(text):
    """Generate embedding using Voyage AI API (fallback - code optimized)"""
    api_key = os.environ.get('VOYAGE_API_KEY')
    if not api_key:
        return None

    try:
        response = requests.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "voyage-code-3",
                "input": text[:500],
                "input_type": "document"
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        print(f"[HEKATE MEMORY] Voyage embedding failed: {e}", file=sys.stderr)
    return None

def get_embedding(text):
    """Try OpenRouter first, fallback to Voyage AI"""
    embedding = get_embedding_openrouter(text)
    if embedding:
        print("[HEKATE MEMORY] Using OpenRouter embeddings", file=sys.stderr)
        return embedding, "openrouter"

    embedding = get_embedding_voyage(text)
    if embedding:
        print("[HEKATE MEMORY] Using Voyage AI embeddings (fallback)", file=sys.stderr)
        return embedding, "voyage"

    print("[HEKATE MEMORY] All embedding providers failed", file=sys.stderr)
    return None, None

def main():
    if not CHROMADB_AVAILABLE:
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    tool_response = input_data.get('tool_response', {})
    tool_name = tool_response.get('tool_name', '')
    tool_input = tool_response.get('tool_input', {})

    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    provider = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:provider'], 'unknown')
    command = tool_input.get('command', '') if tool_name == 'Bash' else None
    output = tool_response.get('result', '')

    if not command:
        sys.exit(0)

    if not is_solution_pattern(command, str(output)):
        sys.exit(0)

    pattern = extract_pattern(command, str(output), tool_name)

    doc_text = f"{pattern['type']}: {pattern['command_snippet']}"

    embedding, embedding_provider = get_embedding(doc_text)
    if not embedding:
        sys.exit(0)

    client = chromadb.PersistentClient(path=str(Path.home() / '.hekate/memory'))
    collection = client.get_or_create_collection('sessions')

    collection.add(
        embeddings=[embedding],
        documents=[doc_text],
        metadatas=[{
            'session_id': session_id,
            'task_id': task_id,
            'provider': provider,
            'pattern_type': pattern['type'],
            'tool': pattern['tool'],
            'embedding_provider': embedding_provider,
            'timestamp': int(time.time())
        }],
        ids=[f"{session_id}_{int(time.time())}_{tool_name}"]
    )

    print(f"[HEKATE MEMORY] Stored {pattern['type']} pattern", file=sys.stderr)
    sys.exit(0)

if __name__ == '__main__':
    main()
