---
name: beads-tools
description: Task management via Beads CLI with complexity tracking and epic decomposition
---

# Beads Task Management

## Available Operations

### List Tasks
```bash
bd list --json
bd ready --json
bd list --status pending --json
```

### Get Task Details
```bash
bd show <task-id> --json
```

### Create Task
```bash
bd create "Task title" --parent <epic-id> --priority 1
```

### Update Task
```bash
bd update <task-id> --status in_progress
bd update <task-id> --status complete --reason "Implementation done"
```

### Block/Unblock Tasks
```bash
bd update <task-id> --block <blocking-task-id>
bd update <task-id> --unblock <blocking-task-id>
```

### Epic Management
```bash
bd create "Epic title" --kind epic
bd list --kind epic --json
```

## Hekate Integration

Tasks are stored in Redis with complexity mapping:
- Low complexity (1-4) → DeepSeek
- Medium complexity (5-7) → GLM
- High complexity (8-10) → Claude

Use `bd ready` to see pending tasks with no blockers.
