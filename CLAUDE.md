# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hekate is an autonomous multi-agent development system that orchestrates AI coding agents across multiple LLM providers (Claude, GLM, DeepSeek, OpenRouter) with intelligent routing, quota management, and 24/7 autonomous development capabilities.

## Architecture

The system follows a layered architecture:
- **User Layer**: Epic creation via Beads CLI
- **Supervisor Layer**: Python orchestrator managing agent pools and routing
- **Agent Layer**: 14 concurrent agents (2 Claude, 4 GLM, 6 DeepSeek, 2 OpenRouter)
- **Execution Layer**: Isolated Git worktrees with TDD enforcement via Superpowers
- **Verification Layer**: Staged cascade from cheap to expensive providers

Key components in `supervisor/`:
- `supervisor.py` - Main orchestrator
- `quota.py` - Quota tracking with Redis persistence
- `router.py` - Provider-aware routing based on complexity/quota
- `agent.py` - Process management for agent pools
- `beads.py` - Beads task graph client
- `verifier.py` - Multi-stage verification cascade
- `mcporter_helper.py` - Token optimization via MCPorter

## Development Commands

# Install dependencies
cd supervisor && pip install -r requirements.txt

# Run all unit tests
cd supervisor && pytest tests/ -v

# Run integration tests
cd supervisor && pytest tests/test_integration.py -v -m integration

# Start supervisor
cd supervisor && python supervisor.py

# Health check
hekate --health-check  # or ~/.local/bin/hekate-health-check

## Environment Setup

Requires Python 3.11+, Redis 7+, Beads CLI, MCPorter, and Superpowers plugin.

Virtual environment setup: Use UV with `uv venv` and `uv pip install -e .`

API keys configured via `~/.bashrc` functions (deepseek, glm, opr) and supervisor/.env