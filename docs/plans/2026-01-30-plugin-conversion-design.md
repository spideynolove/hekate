# Hekate Plugin Conversion Design

**Date:** 2026-01-30
**Status:** Approved for Implementation

## Overview

Convert Hekate from a standalone hooks-based system to a proper Claude Code plugin with:
- Published plugin structure (like Superpowers)
- Clean break migration (no backward compatibility)
- Symlink development workflow (rapid iteration)
- Required dependencies documented (user installs separately)

## Current State

Hekate is a hooks-based multi-agent system with:
- 11 hooks in flat `hooks/` directory with prefix naming
- Settings in `.claude/settings.local.json` (repo) and `~/.claude/settings.json` (global)
- Manual installation via `scripts/install-hooks.sh`
- Documentation inconsistencies (AGENTs.md describes old supervisor architecture)

**Blockers:**
- Hooks not installed (files don't exist at configured paths)
- Path mismatch between settings files
- No plugin structure

## Design

### 1. Directory Organization

```
hekate/
├── .claude-plugin/
│   └── plugin.json                 # Plugin manifest
├── hooks/
│   ├── hooks.json                  # Hook configuration (plugin format)
│   ├── PreToolUse/
│   │   ├── router.py               # Provider routing + quota
│   │   ├── memory.py               # Inject semantic memories
│   │   └── verify_inject.py       # Inject verification results
│   ├── PostToolUse/
│   │   ├── complete_task.py        # Detect task completion
│   │   ├── memory.py               # Store solutions
│   │   ├── spawn_agents.py         # Spawn parallel agents
│   │   ├── track_outcome.py        # Track routing outcomes
│   │   ├── verify_prefetch.py      # Start verification
│   │   └── metrics.py              # Collect metrics
│   ├── UserPromptSubmit/
│   │   └── decompose.py            # Epic decomposition
│   └── SessionStart/
│       └── init.py                 # Agent initialization
├── skills/
│   ├── beads-tools/
│   │   └── SKILL.md
│   ├── redis-cli/
│   │   └── SKILL.md
│   ├── hekate-monitoring/
│   │   └── SKILL.md
│   └── hekate-agent-workflow/
│       └── SKILL.md
├── scripts/
│   ├── setup-prerequisites.sh      # Install dependencies
│   ├── init-redis.sh               # Initialize Redis state
│   ├── hekate-dashboard.py         # Real-time monitoring
│   ├── hekate-analyze.py           # Pattern analysis
│   └── redis-cleanup.sh            # Cleanup cron job
├── docs/
│   ├── README.md                   # Plugin overview
│   ├── INSTALL.md                  # Installation guide
│   ├── ARCHITECTURE.md             # Current architecture doc
│   └── plans/                      # Design documents
├── README.md                       # Main project README
└── CHANGELOG.md                    # Version history
```

**Benefits:**
- Hooks organized by event type (clear purpose)
- No naming conflicts (multiple `memory.py` files in different folders)
- Easy to find related hooks
- Scales well as hooks grow

### 2. Plugin Manifest

**.claude-plugin/plugin.json:**

```json
{
  "name": "hekate",
  "version": "1.0.0",
  "description": "Hooks-based autonomous multi-agent system for coordinating AI agents across multiple LLM providers",
  "author": "spideynolove",
  "repository": "https://github.com/spideynolove/hekate",
  "license": "MIT",

  "components": {
    "hooks": "hooks/hooks.json",
    "skills": "skills/",
    "scripts": "scripts/"
  },

  "dependencies": {
    "external": [
      "redis >= 7.0",
      "python >= 3.10",
      "beads-cli"
    ],
    "python": [
      "chromadb",
      "requests"
    ]
  },

  "documentation": {
    "readme": "docs/README.md",
    "install": "docs/INSTALL.md",
    "architecture": "docs/ARCHITECTURE.md"
  }
}
```

### 3. Hook Configuration

**hooks/hooks.json** (plugin format with wrapper):

```json
{
  "description": "Hekate multi-agent coordination hooks",
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume",
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/SessionStart/init.py",
        "timeout": 5
      }]
    }],

    "UserPromptSubmit": [{
      "hooks": [{
        "type": "command",
        "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/UserPromptSubmit/decompose.py",
        "timeout": 30
      }]
    }],

    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/router.py",
          "timeout": 2
        }]
      },
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PreToolUse/memory.py",
          "timeout": 3
        }]
      }
    ],

    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/complete_task.py",
            "async": false,
            "timeout": 2
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/spawn_agents.py",
            "async": true,
            "timeout": 60
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/memory.py",
            "async": true,
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/track_outcome.py",
            "async": true,
            "timeout": 3
          },
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/metrics.py",
            "async": true,
            "timeout": 2
          }
        ]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/PostToolUse/verify_prefetch.py",
          "async": true,
          "timeout": 10
        }]
      }
    ]
  }
}
```

**Key features:**
- Uses `${CLAUDE_PLUGIN_ROOT}` for portable paths
- Specific matchers for efficiency (not `.*`)
- `async: true` for non-blocking operations
- Tight timeouts for fast hooks
- Folder-based paths clean and clear

### 4. Installation & Development Workflow

**For end users (eventual published plugin):**

```bash
# Install from registry (future)
claude plugin add hekate

# Or install from local path (development)
claude plugin add /path/to/hekate
```

**For active development (symlink approach):**

```bash
# 1. One-time setup: Create symlink
ln -s /home/hung/Public/new-repos/hekate ~/.claude/plugins/hekate

# 2. Install prerequisites
cd /home/hung/Public/new-repos/hekate
./scripts/setup-prerequisites.sh

# 3. Initialize Redis
./scripts/init-redis.sh

# 4. Enable plugin in Claude Code
claude plugin enable hekate

# That's it! Changes to hooks are immediately active (no reinstall needed)
```

**Development workflow:**

```bash
# Edit hook in repo
vim hooks/PreToolUse/router.py

# Changes are live immediately (symlink)
# Test by running Claude Code in a project
claude /path/to/test-project
```

### 5. Migration from Current Setup

**Current state cleanup:**

```bash
# 1. Backup current settings
cp ~/.claude/settings.json ~/.claude/settings.json.backup

# 2. Remove old hook registrations from settings.json
# (Manually edit ~/.claude/settings.json and remove hooks section)

# 3. Remove old .claude/settings.local.json from repo
rm /home/hung/Public/new-repos/hekate/.claude/settings.local.json

# 4. Optional: Clean up old hook installations
rm -rf ~/.claude/hooks/pretooluse_*.py
rm -rf ~/.claude/hooks/posttooluse_*.py
rm -rf ~/.claude/hooks/userpromptsubmit_*.py
rm -rf ~/.claude/hooks/sessionstart_*.py
```

**Restructure hooks in repo:**

```bash
cd /home/hung/Public/new-repos/hekate

# Create new folder structure
mkdir -p hooks/{PreToolUse,PostToolUse,UserPromptSubmit,SessionStart}

# Move existing hooks to folders
mv hooks/pretooluse_router.py hooks/PreToolUse/router.py
mv hooks/pretooluse_memory.py hooks/PreToolUse/memory.py
mv hooks/pretooluse_verify_inject.py hooks/PreToolUse/verify_inject.py

mv hooks/posttooluse_complete_task.py hooks/PostToolUse/complete_task.py
mv hooks/posttooluse_memory.py hooks/PostToolUse/memory.py
mv hooks/posttooluse_spawn_agents.py hooks/PostToolUse/spawn_agents.py
mv hooks/posttooluse_track_outcome.py hooks/PostToolUse/track_outcome.py
mv hooks/posttooluse_verify_prefetch.py hooks/PostToolUse/verify_prefetch.py
mv hooks/posttooluse_metrics.py hooks/PostToolUse/metrics.py

mv hooks/userpromptsubmit_decompose.py hooks/UserPromptSubmit/decompose.py
mv hooks/sessionstart_init.py hooks/SessionStart/init.py

# Remove __pycache__
rm -rf hooks/__pycache__
```

**Create plugin files:**

```bash
# Create plugin manifest
mkdir -p .claude-plugin

# Create hooks configuration
# (See section 3 for full content)
```

**Install as plugin:**

```bash
# Symlink for development
ln -s /home/hung/Public/new-repos/hekate ~/.claude/plugins/hekate

# Verify plugin is recognized
claude plugin list
```

### 6. Documentation Updates

**New files to create:**

- `docs/README.md` - Plugin overview
- `docs/INSTALL.md` - Installation guide
- `CHANGELOG.md` - Version history

**Files to update:**

- `README.md` - Point to plugin installation
- `CLAUDE.md` - Remove installation section, reference plugin docs
- `docs/ARCHITECTURE.md` - Already accurate (hooks-based)
- `docs/USAGE.md` - Already accurate

**Files to delete/archive:**

- `AGENTs.md` - Describes old supervisor architecture
- `.claude/settings.local.json` - No longer needed (plugin uses hooks.json)
- `scripts/install-hooks.sh` - No longer needed (plugin auto-installs)
- `scripts/compile-mcp-to-skills.sh` - Skills are part of plugin

## Implementation Plan

### Phase 1: Restructure (No Functionality Changes)

1. Create plugin structure:
   - `.claude-plugin/plugin.json`
   - `hooks/hooks.json`
   - Folder-based hook organization

2. Move existing hooks to folders

3. Update documentation:
   - Create `docs/README.md`, `docs/INSTALL.md`
   - Update main `README.md`
   - Archive `AGENTs.md`

4. Commit: "refactor: convert to Claude Code plugin structure"

### Phase 2: Install & Verify

1. Clean up old installations
2. Create symlink: `~/.claude/plugins/hekate`
3. Enable plugin
4. Test basic functionality:
   - Hooks load correctly
   - Epic decomposition works
   - Agent spawning works

### Phase 3: Documentation & Publishing

1. Write comprehensive docs
2. Add examples
3. Create CHANGELOG.md
4. Tag v1.0.0
5. (Future) Publish to plugin registry

## Success Criteria

- [ ] Plugin recognized by `claude plugin list`
- [ ] Hooks execute without errors
- [ ] Epic creation works: `create epic: test`
- [ ] Skills load on-demand
- [ ] Scripts accessible via `${CLAUDE_PLUGIN_ROOT}/scripts/`
- [ ] Development changes immediately active (symlink)
- [ ] Documentation complete and accurate

## Open Questions

1. **Who coordinates the work without a supervisor?**
   - Answer: Claude Code hooks + Redis + Beads CLI
   - Hooks trigger on events → read/write Redis state → spawn agents
   - No central coordinator needed

2. **How do multiple agents coordinate?**
   - Redis provides shared state (tasks, quota, patterns)
   - Beads CLI provides task queue
   - Hooks inject cross-agent memories
   - Each agent is independent Claude Code session

3. **What if hooks fail?**
   - Async hooks don't block main flow
   - Sync hooks (router, complete_task) have fallbacks
   - Redis cleanup script handles orphaned state

## References

- [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks)
- [Plugin Structure Guide](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/plugin-dev/skills/plugin-structure/README.md)
- [Superpowers Plugin](https://github.com/obra/superpowers) - Reference implementation
