# Installation Guide

## Prerequisites

Hekate requires:
- Redis 7+
- Python 3.10+
- Beads CLI
- Claude Code with Superpowers plugin

## Automated Setup

```bash
cd ~/.claude/plugins/hekate
./scripts/setup-prerequisites.sh
```

This installs all dependencies interactively.

## Manual Setup

### 1. Install Redis

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt install redis-server
sudo systemctl start redis-server
```

**Docker:**
```bash
docker run -d --name redis -p 6379:6379 redis:alpine
```

### 2. Install Beads CLI

```bash
npm install -g @steveyegge/beads
# or
go install github.com/steveyegge/beads/cmd/bd@latest
```

### 3. Install Python Dependencies

```bash
source /home/hung/env/.venv/bin/activate
uv pip install chromadb requests
```

### 4. Install Hekate Plugin

**Development (symlink):**
```bash
ln -s /path/to/hekate ~/.claude/plugins/hekate
claude plugin enable hekate
```

**Production (future):**
```bash
claude plugin add hekate
```

### 5. Configure API Keys

Add to `~/.bashrc`:

```bash
# Required for epic decomposition
export OPENROUTER_API_KEY="sk-or-..."

# Required for providers
export Z_AI_API_KEY="..."
export DEEPSEEK_API_KEY="sk-..."
```

Then reload: `source ~/.bashrc`

### 6. Initialize Redis

```bash
cd ~/.claude/plugins/hekate
./scripts/init-redis.sh
```

## Verification

```bash
# Check Redis
redis-cli ping

# Check Beads
bd --version

# Check plugin
claude plugin list | grep hekate

# Test epic creation
claude
> create epic: Build hello world app
```

## Troubleshooting

### Hooks Not Loading

```bash
# Check plugin is enabled
claude plugin list

# Check hooks.json syntax
cat ~/.claude/plugins/hekate/hooks/hooks.json | python3 -m json.tool
```

### Redis Not Running

```bash
# Check status
redis-cli ping

# Start Redis
sudo systemctl start redis-server  # Linux
brew services start redis           # macOS
```

### Beads Not Found

```bash
# Check installation
which bd
bd --version

# Reinstall if needed
npm install -g @steveyegge/beads
```

## Next Steps

See [USAGE.md](USAGE.md) for how to create epics and monitor agents.
