# Hekate: Autonomous Multi-Agent Development System

Autonomous development system with Beads orchestration, provider routing, and quality enforcement.

## Installation

### Using UV (recommended)
```bash
# Install UV if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Install with UV
uv sync
uv run hekate --help
```

### Using pip
```bash
# Clone repository
git clone https://github.com/spideynolove/hekate.git
cd hekate

# Install system-wide
pip install .

# Or create virtual environment
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Configuration
```bash
# Copy default config
mkdir -p ~/.hekate
cp src/hekate/config.yaml ~/.hekate/

# Edit API keys and provider settings
nano ~/.hekate/config.yaml
```

## Quick Start

1. **Configure your provider functions** (add to ~/.bashrc):
   ```bash
   deepseek() {
       export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
       export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY}"
       claude "$@"
   }

   glm() {
       export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"
       export ANTHROPIC_AUTH_TOKEN="${Z_AI_API_KEY}"
       claude "$@"
   }

   opr() {
       export ANTHROPIC_BASE_URL="https://openrouter.ai/api"
       export ANTHROPIC_AUTH_TOKEN="${OPENROUTER_API_KEY}"
       claude "$@"
   }
   ```

2. **Start the supervisor:**
   ```bash
   hekate
   ```

3. **Create an epic in another terminal:**
   ```bash
   mkdir ~/hekate-projects/my-project
   cd ~/hekate-projects/my-project
   bd init
   bd create "OAuth 2.0 System" --type epic --priority 0
   ```

3. **System automatically handles:**
   - Planning agent decomposes epic into tasks
   - Router assigns tasks to providers based on complexity + quota
   - Agents implement with TDD (Superpowers enforces)
   - Verification cascade reviews (GLM → Claude if needed)
   - Merge to integration branch per epic
   - Claude reviews complete epic
   - Merge to main

## System Status

### Service Control
```bash
systemctl status ai-agent-supervisor
systemctl start ai-agent-supervisor
systemctl stop ai-agent-supervisor
```

### Health Check
```bash
/home/hung/ai-agents/scripts/health-check.sh
```

### Provider Quota
```bash
redis-cli get quota:claude:count
redis-cli get quota:glm:count
```

### Active Agents
```bash
redis-cli keys "agent:*:heartbeat"
```

## Monitoring

Supervisor logs: `/home/hung/ai-agents/logs/supervisor.log`
Agent logs: `/home/hung/ai-agents/logs/agents/`

### Metrics (Prometheus format)
```
agent_tasks_claimed_total{provider="claude",complexity="medium"} 142
provider_quota_remaining{provider="claude"} 23
provider_quota_percentage{provider="glm"} 88
verification_pass_rate{provider="glm"} 0.91
cascade_rate 0.15
```

## Architecture

### Layers
1. **Orchestration**: Beads task graph + Redis coordination
2. **Routing**: Provider selection based on complexity + quota
3. **Execution**: Agent pools spawn `claude` with env overrides
4. **Verification**: Staged cascade (cheap → expensive)
5. **Quality**: Superpowers auto-triggering skills

### Components
- `supervisor.py`: Main loop orchestrates everything
- `quota.py`: Time-windowed quota tracking
- `router.py`: Provider selection logic
- `agent.py`: Process spawning + heartbeat
- `beads.py`: Task management client
- `verifier.py`: Review workflows

### Data Flow
Epic created → Planning agent decomposes → Tasks in Beads → Supervisor routes → Agent spawned → Implementation → Verification → Cascade if needed → Merge to integration → Claude epic review → Merge to main

## Provider Configuration

### Environment Setup
```bash
# ~/.secrets loaded by ~/.bashrc
export DEEPSEEK_API_KEY=sk-...
export Z_AI_API_KEY=...
export OPENROUTER_API_KEY=sk-or-...
```

### Agent Functions
Provider functions in ~/.bashrc spawn agents with correct environment:

```bash
deepseek() { export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"; export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY}"; claude "$@" --dangerously-skip-permissions; }
glm() { export ANTHROPIC_BASE_URL="https://api.z.ai/api/anthropic"; export ANTHROPIC_AUTH_TOKEN="${Z_AI_API_KEY}"; ANTHROPIC_DEFAULT_OPUS_MODEL="glm-4.7"; claude "$@" --dangerously-skip-permissions; }
opr() { export ANTHROPIC_BASE_URL="https://openrouter.ai/api"; export ANTHROPIC_AUTH_TOKEN="${OPENROUTER_API_KEY}"; ANTHROPIC_DEFAULT_OPUS_MODEL="anthropic/claude-sonnet-4.5"; claude "$@" --dangerously-skip-permissions; }
```

### Provider Mapping
| Provider | Cost | Pool Size | Use Case |
|----------|------|-----------|---------|
| Claude | Premium | 2 agents | Planning, complex arch, reviews |
| GLM | Medium | 4 agents | Medium features, verification |
| DeepSeek | Free | 6 agents | Simple CRUD, implementation |
| OpenRouter | API | 2 agents | Fallback/routing |

## Manual Intervention

### Stop Specific Agent
```bash
redis-cli keys "agent:*:task" | xargs redis-cli del
```

### Reset Provider Quota
```bash
redis-cli del quota:claude:count quota:claude:window_start
```

### Emergency Shutdown
```bash
killall supervisor.py  # Graceful shutdown via KeyboardInterrupt
```

## Documentation

- [Usage Guide](docs/USAGE.md)
- [Architecture Details](docs/ARCHITECTURE.md)
- [Agent Runtime Documentation](../AGENTs.md)