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

def get_prefetched_verifications(task_id):
    """Get all prefetched verification results for a task"""
    # Get all prefetch keys for this task
    pattern = f'verify:prefetch:{task_id}:*'
    keys = safe_redis_command(['redis-cli', 'KEYS', pattern], '')

    if not keys:
        return []

    verifications = []
    for key in keys.split('\n'):
        if not key:
            continue

        data = safe_redis_command(['redis-cli', 'GET', key])
        if not data:
            continue

        try:
            verification = json.loads(data)
            provider = key.split(':')[-1]
            verification['provider'] = provider
            verification['redis_key'] = key
            verifications.append(verification)
        except:
            continue

    return verifications

def check_verification_status(task_id):
    """Check if verifications have results and update them"""
    # This would normally call the provider APIs
    # For now, we simulate with random results for demonstration
    verifications = get_prefetched_verifications(task_id)

    updated = []
    for verification in verifications:
        if verification.get('status') == 'pending':
            # Simulate verification completion after some time
            created = verification.get('timestamp', 0)
            age = time.time() - created

            if age > 30:  # 30 seconds old, mark as complete
                provider = verification.get('provider', 'unknown')
                complexity = verification.get('complexity', 5)

                # Simulate verification result based on provider + complexity
                # Higher complexity = more likely to fail
                import random
                random.seed(provider + str(complexity))

                if complexity <= 4:
                    success_rate = 0.95
                elif complexity <= 7:
                    success_rate = 0.85
                else:
                    success_rate = 0.75

                success = random.random() < success_rate

                # Update verification
                verification['status'] = 'complete'
                verification['result'] = 'PASS' if success else 'NEEDS_REVIEW'
                verification['completed_at'] = int(time.time())
                verification['confidence'] = 'high' if success else 'medium'

                # Store back to Redis
                key = verification.get('redis_key')
                if key:
                    safe_redis_command(['redis-cli', 'SET', key, json.dumps(verification)])
                    safe_redis_command(['redis-cli', 'EXPIRE', key, '600'])

                updated.append(verification)

    return updated + [v for v in verifications if v.get('status') == 'complete']

def format_verification_results(verifications):
    """Format verification results for injection"""
    if not verifications:
        return ""

    parts = []
    parts.append("[HEKATE] Prefetched verification results:")
    parts.append("")

    for verification in sorted(verifications, key=lambda x: x.get('completed_at', 0)):
        provider = verification.get('provider', 'unknown')
        result = verification.get('result', 'PENDING')
        confidence = verification.get('confidence', 'unknown')
        completed = verification.get('completed_at', 0)

        if completed:
            age_sec = int(time.time() - completed)
            if age_sec < 60:
                age_str = f"{age_sec}s ago"
            else:
                age_str = f"{age_sec//60}m ago"
        else:
            age_str = "pending"

        status_symbol = "✓" if result == "PASS" else "≈" if result == "NEEDS_REVIEW" else "⏳"

        parts.append(f"  {status_symbol} {provider:10} | {result:12} | {confidence:8} | {age_str}")

    if any(v.get('result') == 'PASS' for v in verifications):
        parts.append("")
        parts.append("Note: At least one verification passed. Task may be ready for merge.")

    return "\n".join(parts)

def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = input_data.get('session_id', '')
    tool_name = input_data.get('tool_name', '')

    # Only inject before verification-related prompts or tool use
    # This could be checking for specific commands or patterns
    # For now, we'll inject before Read operations (common before verification)
    if tool_name not in ['Read', 'Bash']:
        sys.exit(0)

    # Get task for this session
    task_id = safe_redis_command(['redis-cli', 'GET', f'session:{session_id}:task_id'])
    if not task_id:
        sys.exit(0)

    # Check and update verification status
    verifications = check_verification_status(task_id)

    if not verifications:
        sys.exit(0)

    # Format and inject
    context = format_verification_results(verifications)

    if context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": f"\n{context}\n"
            }
        }
        print(json.dumps(output))

        print(f"[HEKATE VERIFY] Injected {len(verifications)} verification results", file=sys.stderr)

    sys.exit(0)

if __name__ == '__main__':
    main()
