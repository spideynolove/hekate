# Architecture Details

## System Overview

The Multi-Layer AI Agent System orchestrates 14 specialized AI agents across 4 providers (Claude, GLM, DeepSeek, OpenRouter) to autonomously execute development tasks. The system uses Beads for task orchestration, Redis for state management, and implements quality gates through staged verification.

## Core Components

### Supervisor (`supervisor.py`)
**Central orchestrator** that continuously polls for available tasks and manages the complete agent lifecycle.

- **Task Discovery**: Queries Beads for ready tasks
- **Atomic Claiming**: Uses Redis SETNX to prevent double assignment
- **Provider Routing**: Applies complexity/quota algorithms to select optimal provider
- **Process Management**: Spawns agent subprocesses with isolated environments
- **Lifecycle Cleanup**: Monitors agent health and reclaims resources
- **Continuous Loop**: 10-second iteration cycles with graceful shutdown

### Agent Manager (`agent.py`)
**Process lifecycle manager** that handles spawning, monitoring, and cleanup of individual AI agents.

- **Environment Setup**: Uses bash functions to configure provider-specific ANTHROPIC_* variables
- **Isolated Worktrees**: Each agent gets dedicated Git worktree for clean state
- **Heartbeat Monitoring**: Redis-based health tracking with 30-second updates
- **Graceful Termination**: SIGTERM → SIGKILL cascade with timeout
- **Provider Functions**: Leverages ~/.bashrc functions (deepseek, glm, opr) for environment switching

### Provider Router (`router.py`)
**Intelligent routing engine** that selects optimal AI providers based on task complexity and current quotas.

- **Complexity Assessment**: Simple (DeepSeek), Medium (GLM/Claude), Complex (Claude)
- **Quota Awareness**: Monitors 5-hour rolling windows, reserves buffer for emergencies
- **Cascade Chains**: DeepSeek → GLM → OpenRouter → Claude for fallbacks
- **Conservative Buffers**: 20% (Claude), 3% (GLM) emergency reserves

### Quota Tracker (`quota.py`)
**Sliding window quota management** that prevents provider rate limit violations.

- **Time Windowed**: 5-hour rolling windows for subscription providers
- **Buffer Protection**: Reserves 20% of Claude, 3% of GLM quotas for emergencies
- **Automatic Reset**: Window rotation after expiry (no lost quota)
- **Usage Tracking**: Count, percentage, remaining calculations

### Beads Client (`beads.py`)
**Task orchestration interface** that manages development tasks through Beads workflow system.

- **JSON Parsing**: `bd ready --json` for task discovery
- **Atomic Updates**: `bd update` with metadata for status/ownership
- **Task Lifecycle**: Creation, claiming, status updates, completion marking
- **Epic Management**: Parent-child relationships for complex projects

### Verification Agent (`verifier.py`)
**Quality gate implementation** with staged AI review cascade for code validation.

- **Test Execution**: Runs pytest suite in agent worktrees
- **AI Code Review**: Uses provider functions for automated code assessment
- **Major Issue Detection**: Keywords: security, critical, dangerous, exploit
- **Cascade Escalation**: GLM reviews → Claude fixes for failures

## Data Flow Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User/Cron     │────│    Beads Tasks   │────│   Supervisor    │
│  Epic Request   │    │  Ready Queue     │    │   Main Loop     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                       │
┌─────────────────┐    ┌──────────────────┐           │
│   Redis Store   │    │    Router        │◄──────────┘
│  Task Claims    │    │  Provider Select │
│  Agent Health   │    │  Complexity      │
│  Quota Windows  │    └──┬───────────────┘
└─────────────────┘       │
               ┌─────────▼─────────────────┐
               │    Agent Manager          │
               │  Process Spawning         │
               │  Environment Setup        │
               │  Heartbeat Monitoring     │
               └─────────┬─────────────────┘
                         │
            ┌────────────▼────────────────────┐
            │         Provider Pools          │
            │    2 Claude + 4 GLM             │
            │    6 DeepSeek + 2 OpenRouter    │
            └────────────┬────────────────────┘
                         │
            ┌────────────▼────────────────────┐
            │        Agent Execution          │
            │    TDD with Superpowers         │
            │    Git Worktree Isolation       │
            └────────────┬────────────────────┘
                         │
            ┌────────────▼────────────────────┐
            │     Verification Cascade        │
            │    DeepSeek → GLM → Claude      │
            └────────────┬────────────────────┘
                         │
            ┌────────────▼────────────────────┐
            │       Integration Branch        │
            │    Claude Epic Review → Main    │
            └─────────────────────────────────┘
```

## Quality Assurance

### Static Analysis
- **Pyright**: Type checking for all Python modules
- **Black**: Code formatting consistency
- **isort**: Import organization
- **Flake8**: Style and complexity rules

### Testing Strategy
- **Unit Tests**: Individual module functionality (16 test cases)
- **Integration Tests**: End-to-end workflow validation
- **Mock-Based**: Provider calls mocked to avoid API costs
- **Test Data Isolation**: Redis test DB usage

### Verification Stages
- **Phase 1**: DeepSeek basic validation (fast, cheap)
- **Phase 2**: GLM code quality + acceptance criteria (thorough)
- **Phase 3**: Claude major issue resolution (expensive, high quality)

## Performance Characteristics

### Resource Requirements
| Component | CPU | RAM | I/O |
|-----------|-----|-----|-----|
| Supervisor | 1 core | 100MB | Low |
| Agent Process | 2-4 cores | 1-2GB | Medium |
| Redis | 1 core | 256MB | High |
| Total (14 agents) | 12+ cores | 16-32GB | High |

### Scaling Limits
- **Agent Pools**: 14 concurrent agents (2 Claude, 4 GLM, 6 DeepSeek, 2 OpenRouter)
- **Task Throughput**: ~50-100 tasks/day depending on complexity
- **Cost Optimization**: Automatic downgrades save ~70% vs full Claude

### Reliability Features
- **Atomic Task Claiming**: Redis prevents double execution
- **Agent Heartbeats**: 90-second TTL detection
- **Graceful Degradation**: Provider cascades for fallback
- **Error Recovery**: Failed tasks re-queued for retry

## Deployment Architecture

### Directory Structure
```
/home/hung/ai-agents/
├── supervisor/                 # Core system
│   ├── supervisor.py          # Main orchestrator
│   ├── config.yaml            # Provider/quota config
│   ├── agent.py              # Process management
│   ├── quota.py              # Usage tracking
│   ├── router.py             # Provider selection
│   ├── beads.py              # Task integration
│   ├── verifier.py           # Quality gates
│   └── tests/                # Unit tests
├── projects/                  # Workspaces
├── logs/                      # Monitoring
│   ├── supervisor.log
│   └── agents/
├── scripts/                   # Management
│   └── health-check.sh
├── backuos/                   # Data safety
└── venv/                      # Isolated environment
```

### Production Deployment
1. **Automated Setup**: Virtual environment + dependency installation
2. **Systemd Service**: Auto-restart + logging integration
3. **Resource Limits**: CPU/RAM constraints per component
4. **Backup Strategy**: Redis snapshots + log rotation

### Monitoring Stack
- **Health Checks**: Script-based service verification
- **Metrics Export**: Prometheus-compatible counters/rates
- **Log Aggregation**: File-based with rotation
- **Alert Rules**: Quota exhaustion, agent failures