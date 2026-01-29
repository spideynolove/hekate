# Changelog

All notable changes to Hekate will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-30

### Added

- Plugin structure with `.claude-plugin/plugin.json` manifest
- Folder-based hook organization (PreToolUse/, PostToolUse/, etc.)
- Plugin-format `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` support
- Comprehensive documentation (docs/README.md, docs/INSTALL.md)
- Skills integration (beads-tools, redis-cli, hekate-monitoring, hekate-agent-workflow)

### Changed

- **BREAKING**: Converted from standalone hooks to Claude Code plugin
- Reorganized hooks from flat structure with prefixes to folder-based organization
- Updated all documentation to reflect plugin architecture
- Simplified installation to symlink-based development workflow

### Removed

- `.claude/settings.local.json` (replaced by hooks/hooks.json)
- `scripts/install-hooks.sh` (plugins auto-install)
- `scripts/compile-mcp-to-skills.sh` (skills bundled with plugin)
- `AGENTs.md` (outdated supervisor architecture docs, moved to docs/archive/)

### Migration Guide

1. Remove old hook registrations from `~/.claude/settings.json`
2. Create symlink: `ln -s /path/to/hekate ~/.claude/plugins/hekate`
3. Enable plugin: `claude plugin enable hekate`
4. Initialize: `cd ~/.claude/plugins/hekate && ./scripts/init-redis.sh`

## [0.5.0] - 2026-01-29

### Added

- Phase 5: Observability with real-time monitoring
- Phase 4: Verification cascade with prefetch
- Phase 3: Semantic memory for cross-agent learning

### Changed

- Refactored from supervisor-based to hooks-based architecture

## Earlier Versions

See git history for earlier development.
