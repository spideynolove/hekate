#!/usr/bin/env python3
"""
Hekate Real-Time Dashboard

Shows live metrics, active agents, epic progress, quota status, and alerts.
Updates every 2 seconds.
"""

import subprocess, json, sys, time, os
from datetime import datetime

def safe_redis_command(cmd, default=None):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return default

def get_epic_status():
    """Get status of all epics"""
    epic_keys = safe_redis_command(['redis-cli', 'KEYS', 'epic:*:status'], '')
    epics = []

    if epic_keys:
        for key in epic_keys.split('\n'):
            if not key:
                continue
            epic_id = key.split(':')[1]
            status = safe_redis_command(['redis-cli', 'GET', key], '')
            task_count = safe_redis_command(['redis-cli', 'GET', f'epic:{epic_id}:task_count'], '0')
            complete_count = safe_redis_command(['redis-cli', 'GET', f'epic:{epic_id}:complete_count'], '0')
            description = safe_redis_command(['redis-cli', 'GET', f'epic:{epic_id}:description'], '')

            epics.append({
                'id': epic_id,
                'status': status,
                'tasks': int(task_count or '0'),
                'complete': int(complete_count or '0'),
                'description': description[:50] if description else ''
            })

    return epics

def get_agent_status():
    """Get status of all running agents"""
    agent_keys = safe_redis_command(['redis-cli', 'KEYS', 'agent:*:heartbeat'], '')
    agents = []

    if agent_keys:
        for key in agent_keys.split('\n'):
            if not key:
                continue
            pid = key.split(':')[1]
            heartbeat = safe_redis_command(['redis-cli', 'GET', key], '')
            task_id = safe_redis_command(['redis-cli', 'GET', f'agent:{pid}:task_id'], '')
            provider = safe_redis_command(['redis-cli', 'GET', f'agent:{pid}:provider'], '')

            if heartbeat:
                age = int(time.time()) - int(heartbeat)
                agents.append({
                    'pid': pid,
                    'task_id': task_id[:20] if task_id else 'unknown',
                    'provider': provider,
                    'heartbeat_age': age
                })

    return agents

def get_quota_status():
    """Get quota status for all providers"""
    quotas = {}
    for provider in ['claude', 'glm', 'deepseek', 'openrouter']:
        count = int(safe_redis_command(['redis-cli', 'GET', f'quota:{provider}:count'], '0') or '0')
        limit = int(safe_redis_command(['redis-cli', 'GET', f'quota:{provider}:limit'], '50') or '50')
        remaining = limit - count

        quotas[provider] = {
            'count': count,
            'limit': limit,
            'remaining': remaining,
            'percentage': (remaining / limit * 100) if limit > 0 else 0
        }

    return quotas

def get_alerts():
    """Get active alerts"""
    alerts = []

    # Quota warnings
    quotas = get_quota_status()
    for provider, data in quotas.items():
        if data['remaining'] <= 5:
            alerts.append({
                'type': 'quota',
                'severity': 'warning' if data['remaining'] > 0 else 'critical',
                'provider': provider,
                'message': f"{provider} quota: {data['remaining']} remaining"
            })

    # Stuck agents (no heartbeat for > 60s)
    agents = get_agent_status()
    for agent in agents:
        if agent['heartbeat_age'] > 60:
            alerts.append({
                'type': 'stuck_agent',
                'severity': 'warning',
                'pid': agent['pid'],
                'message': f"Agent {agent['pid']} no heartbeat for {agent['heartbeat_age']}s"
            })

    return alerts

def get_metrics():
    """Get Hekate metrics"""
    metrics = {}

    # Get provider stats
    for provider in ['claude', 'glm', 'deepseek', 'openrouter']:
        stats_key = f'provider:stats:{provider}'
        stats = safe_redis_command(['redis-cli', 'GET', stats_key])
        if stats:
            try:
                data = json.loads(stats)
                metrics[f'tasks_total_{provider}'] = data.get('total_tasks', 0)
                metrics[f'tasks_success_rate_{provider}'] = data.get('success_rate', 0.0)
            except:
                pass

    return metrics

def render_dashboard():
    """Render the dashboard"""
    os.system('clear' if os.name != 'nt' else 'cls')

    print("=" * 70)
    print(" HEKATE DASHBOARD")
    print(" " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 70)

    # Alerts
    alerts = get_alerts()
    if alerts:
        print("\n⚠️  ALERTS")
        print("-" * 70)
        for alert in alerts[:5]:
            severity_symbol = "🔴" if alert['severity'] == 'critical' else "🟡"
            print(f"{severity_symbol} {alert['message']}")

    # Epics
    print("\n📊 EPICS")
    print("-" * 70)
    epics = get_epic_status()

    if not epics:
        print("No epics found")
    else:
        for epic in epics:
            status_symbol = "🟢" if epic['status'] == 'complete' else "🟡" if epic['status'] == 'active' else "⚪"
            progress = f"{epic['complete']}/{epic['tasks']}"
            print(f"{status_symbol} {epic['id']:20} | {progress:8} | {epic['description'][:30]}")

    # Agents
    agents = get_agent_status()
    print(f"\n🤖 Active Agents: {len(agents)}")
    if agents:
        print("-" * 70)
        for agent in agents[:8]:
            age_str = f"{agent['heartbeat_age']}s ago"
            print(f"  PID {agent['pid']:8} | {agent['provider']:10} | {agent['task_id']:20} | {age_str}")

    # Quota
    quotas = get_quota_status()
    print("\n💳 QUOTA STATUS")
    print("-" * 70)
    for provider, data in quotas.items():
        remaining = data['remaining']
        percentage = data['percentage']

        if percentage > 50:
            status = "🟢"
        elif percentage > 20:
            status = "🟡"
        else:
            status = "🔴"

        bar_length = int(percentage / 5)
        bar = "█" * bar_length + "░" * (20 - bar_length)
        print(f"{status} {provider.upper():12} | {remaining:4}/{data['limit']:<4} | [{bar}] {percentage:.0f}%")

    # Metrics
    metrics = get_metrics()
    if metrics:
        print("\n📈 METRICS (since start)")
        print("-" * 70)
        for key, value in sorted(metrics.items()):
            if 'success_rate' in key:
                provider = key.replace('tasks_success_rate_', '')
                print(f"  {provider.upper():12} success rate: {value*100:.1f}%")
            elif 'tasks_total' in key and value > 0:
                provider = key.replace('tasks_total_', '')
                print(f"  {provider.upper():12} tasks completed: {value}")

    print("\n" + "=" * 70)
    print(" Press Ctrl+C to exit | Type 'hekate-analyze' for learned patterns")
    print("=" * 70 + "\n")

def export_prometheus_metrics():
    """Export metrics in Prometheus format"""
    quotas = get_quota_status()
    agents = get_agent_status()
    metrics = get_metrics()

    prometheus_lines = []

    # Quota metrics
    for provider, data in quotas.items():
        prometheus_lines.append(f'hekate_quota_remaining{{provider="{provider}"}} {data["remaining"]}')

    # Agent count
    prometheus_lines.append(f'hekate_agents_active {len(agents)}')

    # Task metrics
    for key, value in metrics.items():
        if 'tasks_total' in key:
            provider = key.replace('tasks_total_', '')
            prometheus_lines.append(f'hekate_tasks_total{{provider="{provider}"}} {value}')
        elif 'success_rate' in key:
            provider = key.replace('tasks_success_rate_', '')
            prometheus_lines.append(f'hekate_success_rate{{provider="{provider}"}} {value}')

    return '\n'.join(prometheus_lines)

def main():
    # Check if --prometheus flag is passed
    if len(sys.argv) > 1 and sys.argv[1] == '--prometheus':
        print(export_prometheus_metrics())
        return

    print("Starting Hekate Dashboard...")
    print("Press Ctrl+C to exit\n")

    try:
        while True:
            render_dashboard()
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n\nDashboard stopped. Use 'hekate-analyze' for detailed patterns.")

if __name__ == '__main__':
    main()
