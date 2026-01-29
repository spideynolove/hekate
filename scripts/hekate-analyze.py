#!/usr/bin/env python3
"""
Hekate Routing Analysis Tool

Shows learned routing patterns and provider performance statistics.
"""

import subprocess, json, sys
from datetime import datetime

def safe_redis_command(cmd, default=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return default

def get_provider_stats():
    """Get statistics for each provider"""
    stats = {}
    for provider in ['claude', 'glm', 'deepseek', 'openrouter']:
        key = f'provider:stats:{provider}'
        data = safe_redis_command(['redis-cli', 'GET', key])
        if data:
            try:
                stats[provider] = json.loads(data)
            except:
                stats[provider] = {}
        else:
            stats[provider] = {}
    return stats

def get_complexity_stats():
    """Get complexity-specific statistics"""
    stats = {}
    # Get all complexity stats keys
    keys = safe_redis_command(['redis-cli', 'KEYS', 'provider:complexity:*'], '')
    if keys:
        for key in keys.split('\n'):
            if not key:
                continue
            data = safe_redis_command(['redis-cli', 'GET', key])
            if data:
                try:
                    stats[key] = json.loads(data)
                except:
                    pass
    return stats

def get_routing_patterns():
    """Get learned routing patterns"""
    patterns = {}
    keys = safe_redis_command(['redis-cli', 'KEYS', 'routing:pattern:*'], '')
    if keys:
        for key in keys.split('\n'):
            if not key:
                continue
            data = safe_redis_command(['redis-cli', 'GET', key])
            if data:
                try:
                    patterns[key] = json.loads(data)
                except:
                    pass
    return patterns

def get_recent_history(count=20):
    """Get recent routing history"""
    history = safe_redis_command(['redis-cli', 'LRANGE', 'routing:history', '0', str(count-1)], '')
    if history:
        try:
            return [json.loads(item) for item in history.split('\n') if item]
        except:
            return []
    return []

def format_provider_stats(stats):
    """Format provider statistics for display"""
    output = []
    output.append("\n" + "="*70)
    output.append(" PROVIDER STATISTICS")
    output.append("="*70)
    output.append("")

    for provider, data in sorted(stats.items()):
        if not data:
            output.append(f"{provider.upper():12} | No data yet")
            continue

        total = data.get('total_tasks', 0)
        successful = data.get('successful_tasks', 0)
        rate = data.get('success_rate', 0.0)

        status = "✓" if rate > 0.8 else "≈" if rate > 0.5 else "✗"

        output.append(f"{status} {provider.upper():12} | {total:4} tasks | {successful:4} success | {rate:.1%} rate")

    return "\n".join(output)

def format_complexity_stats(stats):
    """Format complexity-specific statistics"""
    output = []
    output.append("\n" + "="*70)
    output.append(" COMPLEXITY-BASED PERFORMANCE")
    output.append("="*70)
    output.append("")
    output.append("Complexity | Provider   | Success Rate | Attempts")
    output.append("----------|------------|-------------|----------")

    # Group by complexity and provider
    by_complexity = {}
    for key, data in sorted(stats.items()):
        if not data:
            continue
        # Parse key: provider:complexity:{provider}:{complexity}
        parts = key.split(':')
        if len(parts) >= 4:
            provider = parts[2]
            complexity = parts[3]
            if complexity not in by_complexity:
                by_complexity[complexity] = {}
            by_complexity[complexity][provider] = data

    for complexity in sorted(by_complexity.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        providers = by_complexity[complexity]
        for provider, data in sorted(providers.items()):
            rate = data.get('success_rate', 0.0)
            attempts = data.get('attempts', 0)
            if attempts >= 3:  # Only show with sufficient data
                output.append(f"{complexity:9} | {provider:10} | {rate*100:6.1f}%      | {attempts:8}")

    return "\n".join(output) if output else "No sufficient data yet"

def format_patterns(patterns):
    """Format learned routing patterns"""
    output = []
    output.append("\n" + "="*70)
    output.append(" LEARNED ROUTING PATTERNS")
    output.append("="*70)
    output.append("")

    # Show patterns with most attempts
    sorted_patterns = sorted(
        [(k, v) for k, v in patterns.items() if v.get('attempts', 0) >= 3],
        key=lambda x: x[1].get('attempts', 0),
        reverse=True
    )[:10]

    if not sorted_patterns:
        output.append("No learned patterns yet (need 3+ attempts per pattern)")
    else:
        output.append("Pattern (features)                    | Provider | Success | Attempts")
        output.append("-" * 70)

        for key, data in sorted_patterns:
            features = data.get('features', {})
            provider = data.get('provider', 'unknown')
            successes = data.get('successes', 0)
            attempts = data.get('attempts', 0)
            rate = successes / attempts if attempts > 0 else 0

            # Create feature summary
            feature_parts = []
            if 'complexity' in features:
                feature_parts.append f"c={features['complexity']}"
            if 'tool_type' in features:
                feature_parts.append f"tool={features['tool_type'][:8]}"

            feature_str = ', '.join(feature_parts)[:30]

            output.append(f"{feature_str:32} | {provider:8} | {rate:6.0%} | {attempts:8}")

    return "\n".join(output)

def format_recent_history(history):
    """Format recent routing decisions"""
    output = []
    output.append("\n" + "="*70)
    output.append(" RECENT ROUTING DECISIONS")
    output.append("="*70)
    output.append("")

    for item in history[-10:]:
        provider = item.get('provider', 'unknown')
        task_id = item.get('task_id', 'unknown')[:20]
        success = "✓" if item.get('success', False) else "✗"
        tool = item.get('tool_name', 'unknown')[:12]
        features = item.get('features', {})
        complexity = features.get('complexity', '?')

        timestamp = item.get('timestamp', 0)
        if timestamp:
            time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')
        else:
            time_str = '???:??'

        output.append(f"{time_str} | {success} {provider:10} | c={complexity} | {tool:12} | {task_id}")

    return "\n".join(output)

def main():
    print("\n" + "╔" + "═"*68 + "╗")
    print("║" + " "*15 + "HEKATE ROUTING ANALYSIS" + " "*31 + "║")
    print("╚" + "═"*68 + "╝")

    # Get all data
    provider_stats = get_provider_stats()
    complexity_stats = get_complexity_stats()
    patterns = get_routing_patterns()
    recent_history = get_recent_history()

    # Display all sections
    print(format_provider_stats(provider_stats))
    print(format_complexity_stats(complexity_stats))
    print(format_patterns(patterns))
    print(format_recent_history(recent_history))

    print("\n" + "="*70)
    print(" Type 'hekate-analyze' again to refresh statistics")
    print("="*70 + "\n")

if __name__ == '__main__':
    main()
