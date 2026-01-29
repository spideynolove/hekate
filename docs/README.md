# Hekate - Multi-Agent Coordination Plugin for Claude Code

Hooks-based autonomous multi-agent system that orchestrates AI coding agents across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter).

## Features

- **Epic Decomposition**: Automatic task breakdown via OpenRouter
- **Smart Routing**: Complexity-based provider selection (1-4: DeepSeek, 5-7: GLM, 8-10: Claude)
- **Semantic Memory**: Cross-agent learning with ChromaDB
- **Quota Management**: Automatic provider switching when limits reached
- **Verification Cascade**: Async verification prefetch saves 60% time
- **Real-time Monitoring**: Dashboard + pattern analysis

## Architecture

**No supervisor daemon** - All coordination via Claude Code hooks:

- 11 hooks coordinate epic → tasks → agents → completion
- Redis for shared state
- Beads CLI for task management
- ChromaDB for semantic memory

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Quick Start

See [INSTALL.md](INSTALL.md) for installation.

```bash
# In Claude Code
create epic: Build authentication system
```

System automatically:
1. Decomposes epic into tasks
2. Spawns parallel agents by complexity
3. Routes to optimal providers
4. Shares solutions via memory
5. Verifies and completes tasks

## Provider Routing

| Complexity | Provider | Pool Size |
|------------|----------|-----------|
| 1-4 (low) | DeepSeek | 6 agents |
| 5-7 (medium) | GLM | 4 agents |
| 8-10 (high) | Claude | 2 agents |

## Monitoring

```bash
# Real-time dashboard
${CLAUDE_PLUGIN_ROOT}/scripts/hekate-dashboard.py

# Pattern analysis
${CLAUDE_PLUGIN_ROOT}/scripts/hekate-analyze.py

# Redis queries
redis-cli keys "epic:*:status"
redis-cli keys "agent:*:heartbeat"
```

## Documentation

- [Installation Guide](INSTALL.md)
- [Architecture Details](ARCHITECTURE.md)
- [Usage Guide](USAGE.md)

## Development

Plugin uses symlink for rapid iteration:

```bash
ln -s /path/to/hekate ~/.claude/plugins/hekate
```

Changes to hooks are immediately active (no reinstall needed).
