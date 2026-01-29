# Hekate

Multi-agent coordination plugin for Claude Code.

## Overview

Hekate is a **Claude Code plugin** providing hooks-based autonomous multi-agent coordination across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter).

**Features:**
- **Epic Decomposition**: Automatic task breakdown via OpenRouter
- **Smart Routing**: Complexity-based provider selection
- **Semantic Memory**: Cross-agent learning with ChromaDB
- **Quota Management**: Automatic provider switching
- **Verification Cascade**: Async verification prefetch (60% time savings)
- **Real-time Monitoring**: Dashboard + pattern analysis

## Installation

```bash
# Install plugin (development)
ln -s /path/to/hekate ~/.claude/plugins/hekate
claude plugin enable hekate

# Install prerequisites
cd ~/.claude/plugins/hekate
./scripts/setup-prerequisites.sh
./scripts/init-redis.sh
```

See [docs/INSTALL.md](docs/INSTALL.md) for details.

### Configuration

Set environment variables in `~/.bashrc`:

```bash
# Required for epic decomposition
export OPENROUTER_API_KEY="sk-or-..."

# Required for providers
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."
```

Then reload: `source ~/.bashrc`

## Usage

```bash
# In Claude Code
create epic: Build REST API for user authentication
```

System automatically:
1. Decomposes epic into tasks
2. Spawns parallel agents by complexity
3. Routes to optimal providers
4. Shares solutions via memory
5. Verifies and completes tasks

See [docs/USAGE.md](docs/USAGE.md) for complete guide.

## Monitoring

```bash
# Real-time dashboard
${CLAUDE_PLUGIN_ROOT}/scripts/hekate-dashboard.py

# Pattern analysis
${CLAUDE_PLUGIN_ROOT}/scripts/hekate-analyze.py
```

## Architecture

**No supervisor daemon** - All coordination via Claude Code hooks:

- 11 hooks coordinate epic → tasks → agents → completion
- Redis for shared state
- Beads CLI for task management
- ChromaDB for semantic memory

### Provider Routing

| Complexity | Provider | Pool Size |
|------------|----------|-----------|
| 1-4 (low) | DeepSeek | 6 agents |
| 5-7 (medium) | GLM | 4 agents |
| 8-10 (high) | Claude | 2 agents |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Documentation

- [Plugin Overview](docs/README.md)
- [Installation Guide](docs/INSTALL.md)
- [Architecture Details](docs/ARCHITECTURE.md)
- [Usage Guide](docs/USAGE.md)

## Development

Plugin uses symlink for rapid iteration:

```bash
ln -s /path/to/hekate ~/.claude/plugins/hekate
```

Changes to hooks are immediately active (no reinstall needed).

## License

MIT
