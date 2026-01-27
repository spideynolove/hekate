# Usage Guide

## Prerequisites

Before using Hekate, ensure you have installed:

- **Beads CLI**: `brew install beads` or `go install github.com/steveyegge/beads/cmd/bd@latest`
- **Superpowers**: `claude plugin add superpowers` (for TDD enforcement)
- **MCPorter** (optional): `npm install -g @mcporter/mcporter` (for token optimization)

See [CLAUDE.md](../CLAUDE.md) for detailed setup instructions.

## Creating an Epic

1. **Initialize Beads project:**
   ```bash
   cd ~/hekate-projects/my-project
   bd init
   ```

2. **Create epic:**
   ```bash
   bd create "User Authentication System" --type epic --priority 0
   ```

3. **Monitor progress:**
   ```bash
   bd status
   bd show epic-id
   ```

## System Automatically:

### Phase 1: Planning (Claude)
- Planning agent decomposes epic into tasks
- Each task gets complexity assessment, file scope, acceptance criteria

### Phase 2: Implementation (DeepSeek → GLM → Claude)
- Tasks routed to cheapest available provider
- Agents spawn with isolated git worktrees
- TDD enforced via Superpowers

### Phase 3: Verification Cascade (DeepSeek → GLM → Claude)
- DeepSeek does basic checks
- GLM reviews code quality + acceptance
- Claude handles failures/guidance

### Phase 4: Integration
- Tasks merge to integration branch
- Claude epic review
- Merge to main

## Manual Intervention

### Force Task Routing
```bash
# Emergency Claude assignment
redis-cli set "task:bd-123:force_provider" "claude"
```

### Skip Verification
```bash
# For urgent fixes
redis-cli set "task:bd-123:skip_verification" "1"
```

### Monitor Specific Agent
```bash
# Get agent logs
redis-cli hget "agent:agent-claude-123:logs" "stdout"

# Check heartbeat
redis-cli ttl "agent:agent-claude-123:heartbeat"
```

## Troubleshooting

### Supervisor Not Starting
```bash
cd supervisor
python -c "from supervisor import Supervisor; import yaml; print('Config valid')"
tail -f ~/.hekate/logs/supervisor.log
```

### Agents Failing
```bash
# Check provider functions
glm --version  # Should work
deepseek --version

# Check Redis connectivity
redis-cli ping
redis-cli keys "agent:*"
```

### Task Stuck
```bash
# Check task status in Beads
bd show bd-123
bd update bd-123 --metadata status=failed reason="stuck"

# Force reset
redis-cli del "task:bd-123:owner" "agent:*:task"
```

### Quota Issues
```bash
# Check current usage
redis-cli get quota:claude:count
redis-cli get quota:claude:window_start

# Manual quota reset (emergency)
redis-cli del quota:claude:*
```

## Performance Tuning

### Agent Pool Sizes
Edit `supervisor/config.yaml`:
```yaml
providers:
  claude:
    pool_size: 3  # Increase for more parallelism
  deepseek:
    pool_size: 8  # Increase for simple tasks
```

### Verification Thresholds
```yaml
routing:
  verification_providers: ["glm", "openrouter"]  # Add backup
```

### Cycle Time
```yaml
# In supervisor.py
time.sleep(5)  # Faster iterations for development
```