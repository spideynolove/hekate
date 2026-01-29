---
name: hekate-monitoring
description: Real-time monitoring and metrics for Hekate multi-agent system
---

# Hekate Monitoring Commands

## Dashboard
```bash
cd ~/Public/new-repos/hekate
./scripts/hekate-dashboard.py
```

## Pattern Analysis
```bash
./scripts/hekate-analyze.py
```

## Prometheus Metrics Export
```bash
./scripts/hekate-dashboard.py --prometheus
```

## Manual Health Checks

### Active Epics
```bash
redis-cli --scan --pattern "epic:*:status" | while read key; do
    status=$(redis-cli GET "$key")
    echo "$key: $status"
done
```

### Active Agents
```bash
redis-cli --scan --pattern "agent:*:heartbeat" | while read key; do
    pid=$(echo "$key" | cut -d: -f2)
    task=$(redis-cli GET "agent:$pid:task_id")
    provider=$(redis-cli GET "agent:$pid:provider")
    echo "Agent $pid: task=$task provider=$provider"
done
```

### Quota Status
```bash
for provider in claude glm deepseek; do
    count=$(redis-cli GET "quota:$provider:count" || echo "0")
    limit=$(redis-cli GET "quota:$provider:limit" || echo "?")
    echo "$provider: $count/$limit"
done
```

### Learned Patterns
```bash
redis-cli LRANGE "routing:history" 0 9
redis-cli --scan --pattern "routing:pattern:*" | while read key; do
    echo "$key: $(redis-cli GET "$key")"
done
```

## Alert Detection

### Quota Warnings
```bash
redis-cli GET "alerts:quota_warning"
```

### Stale Agents (no heartbeat in 30s)
```bash
redis-cli --scan --pattern "agent:*:heartbeat" | while read key; do
    ttl=$(redis-cli TTL "$key")
    if [ "$ttl" -lt 0 ]; then
        echo "Stale: $key"
    fi
done
```
