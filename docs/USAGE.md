# Usage Guide

## Prerequisites

Before using Hekate, install required external tools:

**Automated setup (recommended):**
```bash
./scripts/setup-prerequisites.sh
```

This interactive script installs:
- Beads CLI (task orchestration)
- Superpowers plugin (TDD enforcement)
- Redis (state management)
- Python + uv (dependency management)

For detailed manual setup, see [CLAUDE.md](../CLAUDE.md).

## Installation

```bash
# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Initialize Redis with quota limits
./scripts/init-redis.sh

# Install Claude Code hooks
./scripts/install-hooks.sh

# Restart Claude Code to load hooks
```

## Configuration

Set environment variables in `~/.bashrc`:

```bash
# Provider API keys
export OPENROUTER_API_KEY="sk-or-..."  # For epic decomposition
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."
```

Then reload: `source ~/.bashrc`

## Creating an Epic

### Via Claude Code (Recommended)

Simply type in Claude Code:

```
create epic: Build REST API for user authentication
```

**What happens automatically:**

1. **Epic Decomposition** (UserPromptSubmit hook)
   - OpenRouter API breaks epic into tasks
   - Each task gets complexity estimate (1-10)
   - Tasks created in Beads with priority-based on complexity

2. **Agent Spawning** (PostToolUse hook, async)
   - Pending tasks grouped by complexity (1-4, 5-7, 8-10)
   - Parallel Claude Code sessions spawned with provider env vars
   - Agents tracked in Redis with heartbeat monitoring

3. **Task Execution**
   - Each agent receives task context via SessionStart hook
   - Provider selected based on complexity + quota
   - Semantic memories injected for cross-agent learning
   - TDD enforced via Superpowers plugin

4. **Verification Cascade** (PostToolUse hook, async)
   - After code changes, async verification starts
   - Complexity-based cascade: DeepSeek → GLM → Claude
   - Results injected on next tool use (~60% time savings)

5. **Task Completion** (PostToolUse hook, async)
   - Git commit detected → task marked complete
   - Beads updated + Redis state synced
   - Epic progress tracked

### Via Beads CLI (Manual)

```bash
# Initialize Beads project
cd ~/hekate-projects/my-project
bd init

# Create epic manually
bd create "User Authentication System" -p 0

# Add tasks manually (complexity stored in Redis)
bd create "[epic-1] Design database schema" -p 7
redis-cli set "task:bd-2:complexity" "8"

bd create "[epic-1] Implement user model" -p 5
redis-cli set "task:bd-3:complexity" "6"

# Monitor progress
bd list
bd show bd-2
```

## Monitoring

### Real-Time Dashboard

```bash
./scripts/hekate-dashboard.py
```

Shows:
- Active agents (PID, provider, task, heartbeat)
- Epic progress (status, completion %)
- Quota status (visual bar chart, alerts)
- Metrics (tasks completed, success rates)

**Prometheus export:**
```bash
./scripts/hekate-dashboard.py --prometheus
```

### Pattern Analysis

```bash
./scripts/hekate-analyze.py
```

Shows:
- Learned routing patterns
- Provider performance statistics
- Complexity-based success rates
- Recent routing decisions

### Redis Commands

```bash
# Epic status
redis-cli keys "epic:*:status"
redis-cli get "epic:epic-123:description"
redis-cli get "epic:epic-123:complete_count"

# Task status
redis-cli get "task:bd-123:complexity"
redis-cli get "task:bd-123:provider"
redis-cli get "task:bd-123:status"

# Active agents
redis-cli keys "agent:*:heartbeat"

# Quota status
redis-cli get "quota:claude:count"
redis-cli get "quota:claude:limit"

# Learned patterns
redis-cli keys "routing:pattern:*"

# Memory inbox
redis-cli lrange "memory:inbox:recent" 0 9
```

## Manual Intervention

### Force Task Routing

```bash
# Route specific task to provider
redis-cli set "task:bd-123:force_provider" "claude"
```

### Skip Verification

```bash
# For urgent fixes
redis-cli set "task:bd-123:skip_verification" "1"
```

### Reset Stuck Agent

```bash
# Clear agent claim
redis-cli del "agent:12345:heartbeat"

# Reset task ownership
redis-cli del "task:bd-123:claimed"
```

### Manual Quota Reset

```bash
# Emergency quota reset
redis-cli del "quota:claude:*"
```

## Troubleshooting

### Hooks Not Loading

```bash
# Check hooks are installed
ls -la ~/.claude/hooks/

# Check settings.json
cat ~/.claude/settings.json | grep -A 20 hooks

# Restart Claude Code
```

### Redis Not Running

```bash
# Check Redis status
redis-cli ping

# Start Redis
sudo systemctl start redis-server

# Check Redis logs
sudo journalctl -u redis-server -f
```

### Beads Not Found

```bash
# Check Beads installation
which bd
bd --version

# Install Beads
npm install -g @steveyegge/beads
```

### Agents Not Spawning

```bash
# Check hook logs
cat ~/.claude/logs/posttooluse_spawn_agents.log

# Check Redis for pending tasks
redis-cli keys "task:*:status"

# Manually test hook
echo '{"tool_name":"Bash","command":"echo test"}' | \
  python3 ~/.claude/hooks/posttooluse_spawn_agents.py
```

### Provider Switching Not Working

```bash
# Check environment variables
env | grep ANTHROPIC

# Check quota status
redis-cli get "quota:claude:count"
redis-cli get "quota:deepseek:count"

# Test provider function
glm --version
deepseek --version
```

## Advanced Usage

### Custom Complexity Thresholds

Edit `hooks/pretooluse_router.py`:

```python
def get_provider_for_complexity(complexity):
    if complexity <= 3:  # Lower threshold
        return 'deepseek'
    elif complexity <= 8:  # Wider medium range
        return 'glm'
    else:
        return 'claude'
```

### Custom Verification Cascade

Edit `hooks/posttooluse_verify_prefetch.py`:

```python
def get_verification_providers(complexity):
    if complexity <= 4:
        return ['deepseek', 'glm']  # Add GLM for simple tasks
    elif complexity <= 7:
        return ['glm', 'claude']  # Skip DeepSeek
    else:
        return ['claude']  # Claude only for complex
```

### Memory Inbox Customization

Edit `hooks/posttooluse_memory.py`:

```python
# Adjust TTL
MEMORY_TTL = 7200  # 2 hours (default: 3600)

# Add new pattern types
def detect_pattern_type(command, output):
    if 'optimization' in command_lower:
        return 'optimization'
```

## Performance Tuning

### Agent Concurrency

Edit `hooks/posttooluse_spawn_agents.py`:

```python
MAX_AGENTS_PER_TIER = 6  # Default: varies by provider
```

### Quota Limits

Edit `scripts/init-redis.sh`:

```bash
DEFAULT_CLAUDE_LIMIT=100  # Default: 50
DEFAULT_GLM_LIMIT=500     # Default: 200
DEFAULT_DEEPSEEK_LIMIT=1000  # Default: 500
```

### Verification Timeout

Edit `hooks/posttooluse_verify_prefetch.py`:

```python
VERIFICATION_TIMEOUT = 30  # Default: 10 seconds
```

## Best Practices

### Epic Writing

- **Be specific**: "Build REST API" → "Build REST API for user authentication"
- **Include scope**: "Add OAuth2 login with Google and GitHub providers"
- **Define constraints**: "Must pass OWASP security scan"

### Task Decomposition

- **Granular tasks**: 1-4 hours per task
- **Testable outcomes**: Each task should have verifiable acceptance criteria
- **Dependencies clear**: Specify if task B requires task A

### Monitoring

- **Check dashboard daily**: Review quota status and agent health
- **Analyze patterns weekly**: Use `hekate-analyze` to review routing decisions
- **Review memory inbox**: Check for recurring patterns that could be automated

### Cost Optimization

- **Use DeepSeek for simple tasks**: Complexity 1-4
- **Reserve Claude for complex work**: Complexity 8-10
- **Compile Hekate skills**: On-demand loading reduces token usage
- **Monitor quota daily**: Set up alerts for low quota
