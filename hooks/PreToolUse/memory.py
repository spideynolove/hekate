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
    except:
        pass
    return None

def get_embedding_voyage(text):
    """Generate embedding using Voyage AI API (fallback - query type for code)"""
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
                "input_type": "query"
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data["data"][0]["embedding"]
    except:
        pass
    return None

def get_embedding(text):
    """Try OpenRouter first, fallback to Voyage AI"""
    embedding = get_embedding_openrouter(text)
    if embedding:
        return embedding

    return get_embedding_voyage(text)

def main():
    if not CHROMADB_AVAILABLE:
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    tool_name = input_data.get('tool_name', '')
    tool_input = input_data.get('tool_input', {})

    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    current_provider = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:provider'], 'unknown')
    command = tool_input.get('command', '') if tool_name == 'Bash' else None

    if not command:
        sys.exit(0)

    query_embedding = get_embedding(f"command: {command}")
    if not query_embedding:
        sys.exit(0)

    client = chromadb.PersistentClient(path=str(Path.home() / '.hekate/memory'))
    collection = client.get_or_create_collection('sessions')

    cutoff_time = int(time.time()) - 7200
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,
        where={"timestamp": {"$gte": cutoff_time}}
    )

    if not results['documents'][0]:
        sys.exit(0)

    relevant_memories = []
    for doc, distance, meta in zip(
        results['documents'][0],
        results['distances'][0],
        results['metadatas'][0]
    ):
        similarity = 1 - distance
        if similarity < 0.65:
            continue
        if meta.get('provider') == current_provider:
            continue

        relevant_memories.append({
            'content': doc,
            'similarity': similarity,
            'provider': meta.get('provider'),
            'pattern_type': meta.get('pattern_type'),
            'task_id': meta.get('task_id'),
            'age_minutes': int((time.time() - meta.get('timestamp', 0)) / 60)
        })

    if not relevant_memories:
        sys.exit(0)

    context_parts = ["[HEKATE SEMANTIC MEMORY] Similar work from other agents:", ""]
    for mem in relevant_memories[:3]:
        context_parts.append(f"  • {mem['provider']} ({mem['age_minutes']}m ago, {mem['similarity']:.2f} similar)")
        context_parts.append(f"    Type: {mem['pattern_type']}")
        context_parts.append(f"    {mem['content'][:100]}")
        context_parts.append(f"    Task: {mem['task_id']}")
        context_parts.append("")

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": "\n".join(context_parts)
        }
    }
    print(json.dumps(output))
    print(f"[HEKATE MEMORY] Injected {len(relevant_memories)} semantic memories", file=sys.stderr)
    sys.exit(0)

if __name__ == '__main__':
    main()
