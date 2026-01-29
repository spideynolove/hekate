---
name: redis-cli
description: Direct Redis operations for Hekate state management
---

# Redis CLI Operations

## Hekate Schema

### Epic State
```bash
redis-cli GET "epic:{id}:status"
redis-cli SET "epic:{id}:status" "active"
redis-cli GET "epic:{id}:task_count"
redis-cli GET "epic:{id}:complete_count"
```

### Task State
```bash
redis-cli GET "task:{id}:complexity"
redis-cli GET "task:{id}:provider"
redis-cli GET "task:{id}:status"
redis-cli HGET "task:{id}:meta" "assigned_provider"
```

### Agent Tracking
```bash
redis-cli KEYS "agent:*:heartbeat"
redis-cli TTL "agent:{pid}:heartbeat"
redis-cli GET "agent:{pid}:task_id"
```

### Provider Quota
```bash
redis-cli GET "quota:claude:count"
redis-cli GET "quota:claude:limit"
redis-cli GET "quota:claude:window_start"
```

### Routing & Learning
```bash
redis-cli LRANGE "routing:history" 0 9
redis-cli GET "routing:complexity:5"
redis-cli KEYS "routing:pattern:*"
```

### Semantic Memory
```bash
redis-cli LRANGE "memory:inbox:recent" 0 9
redis-cli LLEN "memory:inbox:recent"
```

### Verification
```bash
redis-cli KEYS "verify:prefetch:*"
redis-cli GET "verify:prefetch:{task_id}:{provider}"
```

## Common Queries

### Check system status
```bash
redis-cli --scan --pattern "epic:*:status"
redis-cli --scan --pattern "agent:*:heartbeat" | wc -l
```

### Reset quota
```bash
redis-cli SET "quota:claude:count" "0"
```

### Clear learned patterns
```bash
redis-cli --scan --pattern "routing:pattern:*" | xargs redis-cli del
```
