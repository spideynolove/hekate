# Multi-Layer AI Agent System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an autonomous multi-agent development system on GPU server with Beads task orchestration, MCPorter token optimization, provider-aware routing (Claude/GLM/DeepSeek/OpenRouter), and Superpowers quality enforcement.

**Architecture:** Python supervisor manages agent pools (2 Claude, 4 GLM, 6 DeepSeek agents) that claim tasks from Beads, spawn `claude` CLI with provider-specific environment overrides, implement with TDD, verify through staged cascade (cheap→expensive), and merge via epic integration branches.

**Tech Stack:** Python 3.11+, Redis 7+, Beads CLI, MCPorter, Superpowers plugin, systemd, Prometheus/Grafana

---

## Task 1: Project Scaffolding

**Files:**
- Create: `/home/hung/ai-agents/supervisor/supervisor.py`
- Create: `/home/hung/ai-agents/supervisor/config.yaml`
- Create: `/home/hung/ai-agents/supervisor/requirements.txt`
- Create: `/home/hung/ai-agents/supervisor/.env.example`
- Create: `/home/hung/ai-agents/supervisor/tests/test_config.py`

**Step 1: Create directory structure**

Run:
```bash
mkdir -p /home/hung/ai-agents/supervisor
mkdir -p /home/hung/ai-agents/supervisor/tests
mkdir -p /home/hung/ai-agents/projects
mkdir -p /home/hung/ai-agents/logs/agents
mkdir -p /home/hung/ai-agents/backups/{beads-daily,redis-snapshots}
cd /home/hung/ai-agents/supervisor
```

**Step 2: Write test for config loading**

Create: `tests/test_config.py`
```python
import pytest
from pathlib import Path
import yaml

def test_config_loads_yaml():
    config_path = Path(__file__).parent.parent / "config.yaml"
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert "providers" in config
    assert "agent_pools" in config
    assert "iteration_budgets" in config
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_config_loads_yaml -v`
Expected: FAIL with "config.yaml does not exist"

**Step 4: Create config.yaml**

Create: `config.yaml`
```yaml
providers:
  claude:
    type: web_subscription
    quota_limit: 45
    window_hours: 5
    buffer_percent: 20
    pool_size: 2

  glm:
    type: web_subscription
    quota_limit: 180
    window_hours: 5
    buffer_percent: 3
    pool_size: 4

  deepseek:
    type: api
    pool_size: 6

  openrouter:
    type: api
    pool_size: 2

agent_pools:
  total_agents: 14

iteration_budgets:
  simple: 5
  medium: 15
  complex: 30

routing:
  planning_providers: ["claude", "openrouter"]
  review_providers: ["claude"]
  verification_providers: ["glm", "openrouter"]
  implementation_providers: ["glm", "deepseek"]

quota_thresholds:
  claude_conservative: 40
  claude_emergency: 20
  glm_conservative: 50
  glm_critical: 3

redis:
  host: localhost
  port: 6379
  db: 0

monitoring:
  metrics_port: 8000
  log_level: INFO
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_config_loads_yaml -v`
Expected: PASS

**Step 6: Create requirements.txt**

Create: `requirements.txt`
```
redis==5.0.1
pyyaml==6.0.1
prometheus-client==0.19.0
pytest==7.4.3
```

**Step 7: Create .env.example**

Create: `.env.example`
```bash
DEEPSEEK_API_KEY=sk-...
Z_AI_API_KEY=...
OPENROUTER_API_KEY=sk-or-...
REDIS_HOST=localhost
REDIS_PORT=6379
ALERT_EMAIL=your@email.com
ALERT_WEBHOOK=https://hooks.slack.com/services/...
```

**Step 8: Initialize Python virtual environment**

Run:
```bash
python3 -m venv /home/hung/ai-agents/venv
source /home/hung/ai-agents/venv/bin/activate
pip install -r requirements.txt
```

Expected: All packages installed successfully

**Step 9: Commit**

Run:
```bash
git init
git add .
git commit -m "feat: initialize project scaffold with config and tests"
```

---

## Task 2: Quota Tracking Module

**Files:**
- Create: `/home/hung/ai-agents/supervisor/quota.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_quota.py`

**Step 1: Write test for quota initialization**

Create: `tests/test_quota.py`
```python
import pytest
import redis
from datetime import datetime
from quota import QuotaTracker

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

def test_quota_tracker_initializes_windows(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20)

    assert tracker.limit == 45
    assert tracker.window_hours == 5
    assert tracker.buffer_limit == 36
    assert tracker.emergency_limit == 9

def test_quota_tracker_tracks_usage(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="claude")

    tracker.increment()
    tracker.increment()

    usage = tracker.get_usage()
    assert usage["count"] == 2
    assert usage["limit"] == 45
    assert usage["percentage"] == pytest.approx(4.4, rel=0.1)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quota.py -v`
Expected: FAIL with "No module named 'quota'"

**Step 3: Implement QuotaTracker class**

Create: `quota.py`
```python
import redis
from datetime import datetime, timedelta
from typing import Dict

class QuotaTracker:
    def __init__(self, redis_client: redis.Redis, limit: int, window_hours: int,
                 buffer_percent: int, provider: str = "default"):
        self.redis = redis_client
        self.limit = limit
        self.window_hours = window_hours
        self.buffer_percent = buffer_percent
        self.provider = provider

        self.buffer_limit = int(limit * (1 - buffer_percent / 100))
        self.emergency_limit = int(limit * (buffer_percent / 100))

    def _get_window_key(self) -> str:
        return f"quota:{self.provider}:window_start"

    def _get_count_key(self) -> str:
        return f"quota:{self.provider}:count"

    def _ensure_window(self):
        window_key = self._get_window_key()
        count_key = self._get_count_key()

        window_start = self.redis.get(window_key)
        now = datetime.now()

        if not window_start:
            self.redis.set(window_key, now.isoformat())
            self.redis.set(count_key, 0)
            return

        window_start_dt = datetime.fromisoformat(window_start)
        if now - window_start_dt > timedelta(hours=self.window_hours):
            self.redis.set(window_key, now.isoformat())
            self.redis.set(count_key, 0)

    def increment(self) -> int:
        self._ensure_window()
        count_key = self._get_count_key()
        return self.redis.incr(count_key)

    def get_usage(self) -> Dict:
        self._ensure_window()
        count = int(self.redis.get(self._get_count_key()) or 0)

        return {
            "count": count,
            "limit": self.limit,
            "percentage": (count / self.limit) * 100,
            "remaining": self.limit - count,
            "buffer_limit": self.buffer_limit,
            "emergency_limit": self.emergency_limit,
            "below_buffer": count <= self.buffer_limit,
            "is_emergency": count >= self.buffer_limit
        }

    def can_use(self, reserve_for_emergency: bool = False) -> bool:
        usage = self.get_usage()

        if reserve_for_emergency:
            return usage["count"] < self.buffer_limit

        return usage["count"] < self.limit
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_quota.py -v`
Expected: PASS (2 tests)

**Step 5: Add test for window reset**

Add to `tests/test_quota.py`:
```python
from unittest.mock import patch

def test_quota_window_resets_after_expiry(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="test")

    tracker.increment()
    tracker.increment()
    assert tracker.get_usage()["count"] == 2

    past_time = datetime.now() - timedelta(hours=6)
    redis_client.set("quota:test:window_start", past_time.isoformat())

    tracker.increment()
    usage = tracker.get_usage()
    assert usage["count"] == 1
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_quota.py::test_quota_window_resets_after_expiry -v`
Expected: PASS

**Step 7: Commit**

Run:
```bash
git add quota.py tests/test_quota.py
git commit -m "feat: add quota tracking with time window management"
```

---

## Task 3: Provider Routing Module

**Files:**
- Create: `/home/hung/ai-agents/supervisor/router.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_router.py`

**Step 1: Write test for provider selection**

Create: `tests/test_router.py`
```python
import pytest
from router import ProviderRouter
from quota import QuotaTracker

@pytest.fixture
def mock_quotas(redis_client):
    claude_quota = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="claude")
    glm_quota = QuotaTracker(redis_client, limit=180, window_hours=5, buffer_percent=3, provider="glm")

    return {
        "claude": claude_quota,
        "glm": glm_quota,
        "deepseek": None,
        "openrouter": None
    }

def test_router_selects_cheapest_for_simple_task(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "simple", "type": "implementation"}
    provider = router.route_task(task)

    assert provider == "deepseek"

def test_router_routes_planning_to_claude(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "medium", "type": "planning"}
    provider = router.route_task(task)

    assert provider == "claude"

def test_router_downgrades_when_quota_low(mock_quotas):
    mock_quotas["claude"].redis.set("quota:claude:count", 20)

    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "medium", "type": "implementation"}
    provider = router.route_task(task)

    assert provider == "glm"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_router.py -v`
Expected: FAIL with "No module named 'router'"

**Step 3: Implement ProviderRouter**

Create: `router.py`
```python
from typing import Dict, Optional
from quota import QuotaTracker

class ProviderRouter:
    def __init__(self, quotas: Dict[str, Optional[QuotaTracker]], thresholds: Dict[str, int]):
        self.quotas = quotas
        self.thresholds = thresholds

    def route_task(self, task: Dict) -> str:
        complexity = task.get("complexity", "simple")
        task_type = task.get("type", "implementation")

        if task_type == "planning":
            return self._route_planning()
        elif task_type == "review":
            return self._route_review()
        elif task_type == "verification":
            return self._route_verification()
        else:
            return self._route_implementation(complexity)

    def _route_planning(self) -> str:
        if self._can_use_provider("claude"):
            return "claude"
        elif self._can_use_provider("openrouter"):
            return "openrouter"
        else:
            return "glm"

    def _route_review(self) -> str:
        if self._can_use_provider("claude", emergency=True):
            return "claude"
        else:
            return "glm"

    def _route_verification(self) -> str:
        if self._can_use_provider("glm"):
            return "glm"
        else:
            return "openrouter"

    def _route_implementation(self, complexity: str) -> str:
        if complexity == "complex":
            if self._can_use_provider("claude"):
                return "claude"
            else:
                return "glm"

        elif complexity == "medium":
            claude_usage = self._get_quota_percentage("claude")

            if claude_usage < self.thresholds["claude_conservative"] and self._can_use_provider("claude"):
                return "claude"
            elif self._can_use_provider("glm"):
                return "glm"
            else:
                return "deepseek"

        else:
            return "deepseek"

    def _can_use_provider(self, provider: str, emergency: bool = False) -> bool:
        quota = self.quotas.get(provider)

        if quota is None:
            return True

        return quota.can_use(reserve_for_emergency=emergency)

    def _get_quota_percentage(self, provider: str) -> float:
        quota = self.quotas.get(provider)

        if quota is None:
            return 0.0

        usage = quota.get_usage()
        return usage["percentage"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_router.py -v`
Expected: PASS (3 tests)

**Step 5: Add cascade routing test**

Add to `tests/test_router.py`:
```python
def test_router_cascades_to_higher_provider(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "medium", "type": "implementation", "attempt": 1}
    first_provider = router.route_task(task)
    assert first_provider == "glm"

    task["attempt"] = 2
    task["previous_provider"] = "glm"
    cascade_provider = router.cascade(task)
    assert cascade_provider == "claude"
```

**Step 6: Implement cascade method**

Add to `router.py`:
```python
    def cascade(self, task: Dict) -> str:
        previous_provider = task.get("previous_provider", "deepseek")

        cascade_chain = ["deepseek", "glm", "openrouter", "claude"]

        try:
            current_index = cascade_chain.index(previous_provider)
            next_index = current_index + 1

            if next_index < len(cascade_chain):
                return cascade_chain[next_index]
            else:
                return "claude"

        except ValueError:
            return "claude"
```

**Step 7: Run test to verify it passes**

Run: `pytest tests/test_router.py::test_router_cascades_to_higher_provider -v`
Expected: PASS

**Step 8: Commit**

Run:
```bash
git add router.py tests/test_router.py
git commit -m "feat: add provider routing with quota-aware selection and cascade"
```

---

## Task 4: Agent Process Manager

**Files:**
- Create: `/home/hung/ai-agents/supervisor/agent.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_agent.py`

**Step 1: Write test for agent spawning**

Create: `tests/test_agent.py`
```python
import pytest
from unittest.mock import Mock, patch, MagicMock
from agent import AgentManager
import subprocess

def test_agent_manager_spawns_claude_agent():
    manager = AgentManager(home_dir="/home/hung")

    with patch('subprocess.Popen') as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        agent_id = manager.spawn_agent(
            provider="claude",
            task_id="bd-abc123",
            project_dir="/home/hung/ai-agents/projects/test-project"
        )

        assert agent_id.startswith("agent-claude-")
        mock_popen.assert_called_once()

        call_args = mock_popen.call_args
        assert call_args[0][0][0] == "claude"

def test_agent_manager_spawns_deepseek_with_env_override():
    manager = AgentManager(home_dir="/home/hung")

    with patch('subprocess.Popen') as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12346
        mock_popen.return_value = mock_process

        agent_id = manager.spawn_agent(
            provider="deepseek",
            task_id="bd-def456",
            project_dir="/home/hung/ai-agents/projects/test-project"
        )

        call_args = mock_popen.call_args
        assert "bash" in call_args[0][0]
        assert "deepseek" in call_args[0][0][2]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py -v`
Expected: FAIL with "No module named 'agent'"

**Step 3: Implement AgentManager**

Create: `agent.py`
```python
import subprocess
import time
from typing import Dict, Optional
from pathlib import Path

class AgentManager:
    def __init__(self, home_dir: str):
        self.home_dir = Path(home_dir)
        self.agents: Dict[str, subprocess.Popen] = {}

    def spawn_agent(self, provider: str, task_id: str, project_dir: str) -> str:
        agent_id = f"agent-{provider}-{int(time.time())}"

        if provider == "claude":
            cmd = ["claude", "--task", task_id]
        else:
            bashrc = self.home_dir / ".bashrc"
            cmd = ["bash", "-c", f"source {bashrc} && {provider} --task {task_id}"]

        process = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        self.agents[agent_id] = process
        return agent_id

    def get_agent_status(self, agent_id: str) -> Optional[str]:
        process = self.agents.get(agent_id)

        if not process:
            return None

        poll = process.poll()

        if poll is None:
            return "running"
        elif poll == 0:
            return "completed"
        else:
            return "failed"

    def kill_agent(self, agent_id: str) -> bool:
        process = self.agents.get(agent_id)

        if not process:
            return False

        process.terminate()

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

        del self.agents[agent_id]
        return True
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent.py -v`
Expected: PASS (2 tests)

**Step 5: Add heartbeat tracking test**

Add to `tests/test_agent.py`:
```python
import redis

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

def test_agent_registers_heartbeat(redis_client):
    manager = AgentManager(home_dir="/home/hung", redis_client=redis_client)

    with patch('subprocess.Popen') as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        agent_id = manager.spawn_agent("claude", "bd-test", "/home/hung/test")

        heartbeat_key = f"agent:{agent_id}:heartbeat"
        assert redis_client.exists(heartbeat_key)

        ttl = redis_client.ttl(heartbeat_key)
        assert ttl > 0 and ttl <= 90
```

**Step 6: Update AgentManager with Redis heartbeat**

Update `agent.py`:
```python
import redis

class AgentManager:
    def __init__(self, home_dir: str, redis_client: Optional[redis.Redis] = None):
        self.home_dir = Path(home_dir)
        self.agents: Dict[str, subprocess.Popen] = {}
        self.redis = redis_client or redis.Redis(host='localhost', port=6379, decode_responses=True)

    def spawn_agent(self, provider: str, task_id: str, project_dir: str) -> str:
        agent_id = f"agent-{provider}-{int(time.time())}"

        if provider == "claude":
            cmd = ["claude", "--task", task_id]
        else:
            bashrc = self.home_dir / ".bashrc"
            cmd = ["bash", "-c", f"source {bashrc} && {provider} --task {task_id}"]

        process = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        self.agents[agent_id] = process

        self.redis.setex(f"agent:{agent_id}:heartbeat", 90, int(time.time()))
        self.redis.set(f"agent:{agent_id}:task", task_id)

        return agent_id

    def update_heartbeat(self, agent_id: str):
        self.redis.setex(f"agent:{agent_id}:heartbeat", 90, int(time.time()))
```

**Step 7: Run test to verify it passes**

Run: `pytest tests/test_agent.py::test_agent_registers_heartbeat -v`
Expected: PASS

**Step 8: Commit**

Run:
```bash
git add agent.py tests/test_agent.py
git commit -m "feat: add agent process manager with heartbeat tracking"
```

---

## Task 5: Beads Integration Module

**Files:**
- Create: `/home/hung/ai-agents/supervisor/beads.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_beads.py`

**Step 1: Write test for Beads task listing**

Create: `tests/test_beads.py`
```python
import pytest
from unittest.mock import patch, Mock
from beads import BeadsClient
import json

def test_beads_client_lists_ready_tasks():
    client = BeadsClient()

    mock_output = json.dumps([
        {"id": "bd-abc123", "status": "open", "complexity": "simple", "phase": "phase1"},
        {"id": "bd-def456", "status": "open", "complexity": "medium", "phase": "phase1"}
    ])

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        tasks = client.list_ready_tasks()

        assert len(tasks) == 2
        assert tasks[0]["id"] == "bd-abc123"
        mock_run.assert_called_with(["bd", "ready", "--json"], capture_output=True, text=True, check=True)

def test_beads_client_claims_task():
    client = BeadsClient()

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)

        success = client.claim_task("bd-abc123", "agent-001")

        assert success is True
        mock_run.assert_called_with(
            ["bd", "update", "bd-abc123", "--metadata", "owner=agent-001"],
            capture_output=True,
            text=True
        )
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_beads.py -v`
Expected: FAIL with "No module named 'beads'"

**Step 3: Implement BeadsClient**

Create: `beads.py`
```python
import subprocess
import json
from typing import List, Dict, Optional

class BeadsClient:
    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd

    def list_ready_tasks(self, epic_id: Optional[str] = None) -> List[Dict]:
        cmd = ["bd", "ready", "--json"]

        if epic_id:
            cmd.extend(["--parent", epic_id])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            cwd=self.cwd
        )

        return json.loads(result.stdout)

    def get_task(self, task_id: str) -> Dict:
        result = subprocess.run(
            ["bd", "show", task_id, "--json"],
            capture_output=True,
            text=True,
            check=True,
            cwd=self.cwd
        )

        return json.loads(result.stdout)

    def claim_task(self, task_id: str, agent_id: str) -> bool:
        result = subprocess.run(
            ["bd", "update", task_id, "--metadata", f"owner={agent_id}"],
            capture_output=True,
            text=True,
            cwd=self.cwd
        )

        return result.returncode == 0

    def update_task_status(self, task_id: str, status: str, reason: Optional[str] = None) -> bool:
        cmd = ["bd", "update", task_id, "--status", status]

        if reason:
            cmd.extend(["--reason", reason])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.cwd
        )

        return result.returncode == 0

    def create_task(self, title: str, epic_id: str, complexity: str, phase: str,
                   files: List[str], acceptance_criteria: List[str]) -> str:
        metadata_json = json.dumps({
            "complexity": complexity,
            "phase": phase,
            "files": files,
            "acceptance_criteria": acceptance_criteria
        })

        result = subprocess.run(
            ["bd", "create", title, "--parent", epic_id, "--metadata", metadata_json],
            capture_output=True,
            text=True,
            cwd=self.cwd
        )

        if result.returncode == 0:
            return result.stdout.strip()

        return ""
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_beads.py -v`
Expected: PASS (2 tests)

**Step 5: Add test for task filtering by phase**

Add to `tests/test_beads.py`:
```python
def test_beads_client_filters_tasks_by_phase():
    client = BeadsClient()

    mock_output = json.dumps([
        {"id": "bd-abc123", "phase": "phase1", "status": "open"},
        {"id": "bd-def456", "phase": "phase2", "status": "open"}
    ])

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(stdout=mock_output, returncode=0)

        tasks = client.list_ready_tasks()
        phase1_tasks = [t for t in tasks if t["phase"] == "phase1"]

        assert len(phase1_tasks) == 1
        assert phase1_tasks[0]["id"] == "bd-abc123"
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_beads.py::test_beads_client_filters_tasks_by_phase -v`
Expected: PASS

**Step 7: Commit**

Run:
```bash
git add beads.py tests/test_beads.py
git commit -m "feat: add Beads integration for task management"
```

---

## Task 6: Supervisor Main Loop

**Files:**
- Create: `/home/hung/ai-agents/supervisor/supervisor.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_supervisor.py`

**Step 1: Write test for supervisor initialization**

Create: `tests/test_supervisor.py`
```python
import pytest
from unittest.mock import Mock, patch
from supervisor import Supervisor
import yaml

@pytest.fixture
def config():
    return {
        "providers": {
            "claude": {"quota_limit": 45, "window_hours": 5, "buffer_percent": 20, "pool_size": 2},
            "glm": {"quota_limit": 180, "window_hours": 5, "buffer_percent": 3, "pool_size": 4},
            "deepseek": {"pool_size": 6},
            "openrouter": {"pool_size": 2}
        },
        "iteration_budgets": {"simple": 5, "medium": 15, "complex": 30},
        "quota_thresholds": {"claude_conservative": 40, "glm_conservative": 50},
        "redis": {"host": "localhost", "port": 6379, "db": 15}
    }

def test_supervisor_initializes(config):
    with patch('redis.Redis'):
        supervisor = Supervisor(config)

        assert supervisor.config == config
        assert len(supervisor.agent_pools) == 4

def test_supervisor_selects_task_and_routes(config):
    with patch('redis.Redis') as mock_redis:
        supervisor = Supervisor(config)

        with patch.object(supervisor.beads, 'list_ready_tasks') as mock_list:
            mock_list.return_value = [
                {"id": "bd-abc123", "complexity": "simple", "type": "implementation"}
            ]

            with patch.object(supervisor, '_assign_task') as mock_assign:
                supervisor.run_iteration()

                mock_assign.assert_called_once()
                task = mock_assign.call_args[0][0]
                assert task["id"] == "bd-abc123"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_supervisor.py -v`
Expected: FAIL with "No module named 'supervisor'"

**Step 3: Implement Supervisor skeleton**

Create: `supervisor.py`
```python
import redis
import yaml
import time
import logging
from pathlib import Path
from typing import Dict, List
from quota import QuotaTracker
from router import ProviderRouter
from agent import AgentManager
from beads import BeadsClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Supervisor:
    def __init__(self, config: Dict):
        self.config = config

        redis_config = config.get("redis", {})
        self.redis = redis.Redis(
            host=redis_config.get("host", "localhost"),
            port=redis_config.get("port", 6379),
            db=redis_config.get("db", 0),
            decode_responses=True
        )

        self.quotas = self._initialize_quotas()
        self.router = ProviderRouter(self.quotas, config["quota_thresholds"])
        self.agent_manager = AgentManager(home_dir="/home/hung", redis_client=self.redis)
        self.beads = BeadsClient()

        self.agent_pools = {}
        for provider, settings in config["providers"].items():
            self.agent_pools[provider] = {
                "size": settings["pool_size"],
                "active": []
            }

    def _initialize_quotas(self) -> Dict:
        quotas = {}

        for provider, settings in self.config["providers"].items():
            if settings.get("type") == "web_subscription":
                quotas[provider] = QuotaTracker(
                    self.redis,
                    limit=settings["quota_limit"],
                    window_hours=settings["window_hours"],
                    buffer_percent=settings["buffer_percent"],
                    provider=provider
                )
            else:
                quotas[provider] = None

        return quotas

    def run_iteration(self):
        tasks = self.beads.list_ready_tasks()

        if not tasks:
            logger.info("No ready tasks")
            return

        for task in tasks:
            if self._can_assign_task():
                self._assign_task(task)

    def _can_assign_task(self) -> bool:
        total_active = sum(len(pool["active"]) for pool in self.agent_pools.values())
        total_capacity = sum(pool["size"] for pool in self.agent_pools.values())

        return total_active < total_capacity

    def _assign_task(self, task: Dict):
        provider = self.router.route_task(task)

        logger.info(f"Assigning task {task['id']} to {provider}")

        claimed = self._claim_task_in_redis(task["id"], provider)

        if not claimed:
            logger.warning(f"Failed to claim task {task['id']}")
            return

        agent_id = self.agent_manager.spawn_agent(
            provider=provider,
            task_id=task["id"],
            project_dir=f"/home/hung/ai-agents/projects/{task.get('epic_id', 'default')}"
        )

        self.agent_pools[provider]["active"].append(agent_id)

        logger.info(f"Spawned {agent_id} for task {task['id']}")

    def _claim_task_in_redis(self, task_id: str, provider: str) -> bool:
        key = f"task:{task_id}:owner"
        claimed = self.redis.set(key, provider, nx=True, ex=3600)

        return claimed is not None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_supervisor.py -v`
Expected: PASS (2 tests)

**Step 5: Add continuous loop test**

Add to `tests/test_supervisor.py`:
```python
def test_supervisor_runs_continuous_loop(config):
    with patch('redis.Redis'):
        supervisor = Supervisor(config)

        iteration_count = 0

        def mock_iteration():
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 3:
                raise KeyboardInterrupt()

        with patch.object(supervisor, 'run_iteration', side_effect=mock_iteration):
            with patch('time.sleep'):
                try:
                    supervisor.run()
                except KeyboardInterrupt:
                    pass

        assert iteration_count == 3
```

**Step 6: Implement continuous run method**

Add to `supervisor.py`:
```python
    def run(self):
        logger.info("Supervisor starting")

        try:
            while True:
                self.run_iteration()
                self._cleanup_completed_agents()
                time.sleep(10)

        except KeyboardInterrupt:
            logger.info("Supervisor stopping")
            self._shutdown()

    def _cleanup_completed_agents(self):
        for provider, pool in self.agent_pools.items():
            for agent_id in list(pool["active"]):
                status = self.agent_manager.get_agent_status(agent_id)

                if status in ["completed", "failed"]:
                    pool["active"].remove(agent_id)
                    logger.info(f"Agent {agent_id} {status}")

    def _shutdown(self):
        logger.info("Shutting down all agents")

        for pool in self.agent_pools.values():
            for agent_id in pool["active"]:
                self.agent_manager.kill_agent(agent_id)
```

**Step 7: Run test to verify it passes**

Run: `pytest tests/test_supervisor.py::test_supervisor_runs_continuous_loop -v`
Expected: PASS

**Step 8: Create main entry point**

Add to `supervisor.py`:
```python
def main():
    config_path = Path(__file__).parent / "config.yaml"

    with open(config_path) as f:
        config = yaml.safe_load(f)

    supervisor = Supervisor(config)
    supervisor.run()

if __name__ == "__main__":
    main()
```

**Step 9: Commit**

Run:
```bash
git add supervisor.py tests/test_supervisor.py
git commit -m "feat: add supervisor main loop with task assignment"
```

---

## Task 7: Verification Workflow

**Files:**
- Create: `/home/hung/ai-agents/supervisor/verifier.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_verifier.py`

**Step 1: Write test for verification agent**

Create: `tests/test_verifier.py`
```python
import pytest
from unittest.mock import Mock, patch
from verifier import VerificationAgent

def test_verification_agent_reviews_task():
    agent = VerificationAgent(provider="glm", redis_client=Mock())

    task = {
        "id": "bd-abc123",
        "acceptance_criteria": ["Tests pass", "No security issues"],
        "git_branch": "agent-001-bd-abc123"
    }

    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = [
            Mock(returncode=0, stdout="All tests passed"),
            Mock(returncode=0, stdout='{"pass": true, "confidence": 0.85, "issues": []}')
        ]

        result = agent.verify(task)

        assert result["status"] == "approved"
        assert result["confidence"] >= 0.85

def test_verification_fails_with_major_issues():
    agent = VerificationAgent(provider="glm", redis_client=Mock())

    task = {"id": "bd-abc123", "acceptance_criteria": [], "git_branch": "test"}

    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = [
            Mock(returncode=0),
            Mock(returncode=0, stdout='{"pass": false, "confidence": 0.4, "issues": ["security hole"]}')
        ]

        result = agent.verify(task)

        assert result["status"] == "needs_guidance"
        assert "security hole" in result["issues"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_verifier.py -v`
Expected: FAIL with "No module named 'verifier'"

**Step 3: Implement VerificationAgent**

Create: `verifier.py`
```python
import subprocess
import json
from typing import Dict
import redis

class VerificationAgent:
    def __init__(self, provider: str, redis_client: redis.Redis):
        self.provider = provider
        self.redis = redis_client

    def verify(self, task: Dict) -> Dict:
        task_id = task["id"]
        git_branch = task.get("git_branch")

        tests_passed = self._run_tests(git_branch)

        if not tests_passed:
            return {
                "status": "failed",
                "reason": "tests_failed"
            }

        review_result = self._code_review(task)

        if not review_result["pass"]:
            if self._is_major_issue(review_result):
                return {
                    "status": "needs_guidance",
                    "issues": review_result["issues"],
                    "confidence": review_result["confidence"]
                }
            else:
                return {
                    "status": "approved_with_minor_issues",
                    "issues": review_result["issues"]
                }

        return {
            "status": "approved",
            "confidence": review_result["confidence"]
        }

    def _run_tests(self, git_branch: str) -> bool:
        result = subprocess.run(
            ["git", "checkout", git_branch],
            capture_output=True
        )

        if result.returncode != 0:
            return False

        test_result = subprocess.run(
            ["pytest", "-v"],
            capture_output=True,
            text=True
        )

        return test_result.returncode == 0

    def _code_review(self, task: Dict) -> Dict:
        prompt = f"""Review this task implementation:
Task ID: {task['id']}
Acceptance Criteria: {task.get('acceptance_criteria', [])}

Check for:
1. Security issues
2. Code quality
3. Acceptance criteria met

Respond with JSON: {{"pass": true/false, "confidence": 0.0-1.0, "issues": []}}
"""

        result = subprocess.run(
            ["bash", "-c", f"source ~/.bashrc && {self.provider} <<< '{prompt}'"],
            capture_output=True,
            text=True
        )

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"pass": False, "confidence": 0.0, "issues": ["Review failed to parse"]}

    def _is_major_issue(self, review_result: Dict) -> bool:
        issues = review_result.get("issues", [])

        major_keywords = ["security", "critical", "broken", "incorrect"]

        for issue in issues:
            if any(keyword in issue.lower() for keyword in major_keywords):
                return True

        return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_verifier.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

Run:
```bash
git add verifier.py tests/test_verifier.py
git commit -m "feat: add verification agent with staged review"
```

---

## Task 8: MCPorter Integration

**Files:**
- Create: `/home/hung/ai-agents/supervisor/mcporter_helper.py`
- Create: `/home/hung/ai-agents/supervisor/tests/test_mcporter.py`
- Modify: `~/.mcporter/mcporter.json`

**Step 1: Write test for MCPorter invocation**

Create: `tests/test_mcporter.py`
```python
import pytest
from unittest.mock import patch, Mock
from mcporter_helper import MCPorterHelper

def test_mcporter_invokes_tool():
    helper = MCPorterHelper()

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"result": "success"}'
        )

        result = helper.invoke("repomix", "pack_codebase", path="src/")

        assert result["result"] == "success"
        mock_run.assert_called_once()

def test_mcporter_caches_result():
    helper = MCPorterHelper()

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout='{"cached": true}')

        result1 = helper.invoke("repomix", "pack_codebase", path="src/", cache_key="test")
        result2 = helper.invoke("repomix", "pack_codebase", path="src/", cache_key="test")

        assert mock_run.call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcporter.py -v`
Expected: FAIL with "No module named 'mcporter_helper'"

**Step 3: Implement MCPorterHelper**

Create: `mcporter_helper.py`
```python
import subprocess
import json
from typing import Dict, Any, Optional

class MCPorterHelper:
    def __init__(self):
        self.cache: Dict[str, Any] = {}

    def invoke(self, server: str, tool: str, cache_key: Optional[str] = None, **kwargs) -> Dict:
        if cache_key and cache_key in self.cache:
            return self.cache[cache_key]

        args = [f"--{k}={v}" for k, v in kwargs.items()]

        cmd = ["mcporter", "invoke", server, tool] + args

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {"error": result.stderr}

        try:
            parsed = json.loads(result.stdout)

            if cache_key:
                self.cache[cache_key] = parsed

            return parsed

        except json.JSONDecodeError:
            return {"raw_output": result.stdout}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcporter.py -v`
Expected: PASS (2 tests)

**Step 5: Verify MCPorter daemon configuration**

Run:
```bash
cat ~/.mcporter/mcporter.json
```

Expected output showing lifecycle: "keep-alive" for all MCPs

If not configured, create: `~/.mcporter/mcporter.json`
```json
{
  "mcpServers": {
    "sequential-thinking": {
      "command": "/home/hung/env/.venv/bin/python",
      "args": ["/home/hung/MCPs/sequential-thinking-mcp-v2/main.py"],
      "lifecycle": "keep-alive"
    },
    "repomix": {
      "command": "npx",
      "args": ["-y", "repomix", "--mcp"],
      "lifecycle": "keep-alive"
    },
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"],
      "lifecycle": "keep-alive",
      "env": {
        "CONTEXT7_API_KEY": "${CONTEXT7_API_KEY}"
      }
    }
  }
}
```

**Step 6: Start MCPorter daemon**

Run:
```bash
mcporter daemon start
```

Expected: "MCPorter daemon started"

**Step 7: Commit**

Run:
```bash
git add mcporter_helper.py tests/test_mcporter.py
git commit -m "feat: add MCPorter integration for token optimization"
```

---

## Task 9: Systemd Service Setup

**Files:**
- Create: `/etc/systemd/system/ai-agent-supervisor.service`
- Create: `/home/hung/ai-agents/scripts/health-check.sh`

**Step 1: Create systemd service file**

Create: `/etc/systemd/system/ai-agent-supervisor.service` (requires sudo)
```ini
[Unit]
Description=AI Agent Supervisor - Multi-Provider Orchestrator
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=hung
Group=hung
WorkingDirectory=/home/hung/ai-agents/supervisor

Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/home/hung/ai-agents/supervisor/.env

ExecStart=/home/hung/ai-agents/venv/bin/python supervisor.py

Restart=always
RestartSec=10

StandardOutput=append:/home/hung/ai-agents/logs/supervisor.log
StandardError=append:/home/hung/ai-agents/logs/supervisor.log

[Install]
WantedBy=multi-user.target
```

**Step 2: Create .env file from example**

Run:
```bash
cp /home/hung/ai-agents/supervisor/.env.example /home/hung/ai-agents/supervisor/.env
```

Edit `.env` and add your actual API keys

**Step 3: Create health check script**

Create: `/home/hung/ai-agents/scripts/health-check.sh`
```bash
#!/bin/bash

REDIS_HOST=localhost
REDIS_PORT=6379

check_redis() {
    redis-cli -h $REDIS_HOST -p $REDIS_PORT ping > /dev/null 2>&1
    return $?
}

check_supervisor() {
    systemctl is-active --quiet ai-agent-supervisor
    return $?
}

check_agent_count() {
    active_agents=$(redis-cli -h $REDIS_HOST KEYS "agent:*:heartbeat" | wc -l)
    echo "Active agents: $active_agents"

    if [ $active_agents -eq 0 ]; then
        return 1
    fi

    return 0
}

echo "=== AI Agent System Health Check ==="

if check_redis; then
    echo "✓ Redis running"
else
    echo "✗ Redis not responding"
    exit 1
fi

if check_supervisor; then
    echo "✓ Supervisor running"
else
    echo "✗ Supervisor not running"
    exit 1
fi

if check_agent_count; then
    echo "✓ Agents active"
else
    echo "⚠ No active agents"
fi

echo "=== Health check complete ==="
```

**Step 4: Make health check executable**

Run:
```bash
chmod +x /home/hung/ai-agents/scripts/health-check.sh
```

**Step 5: Enable and start service**

Run:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-agent-supervisor
sudo systemctl start ai-agent-supervisor
```

**Step 6: Verify service status**

Run:
```bash
sudo systemctl status ai-agent-supervisor
```

Expected: "active (running)"

**Step 7: Test health check**

Run:
```bash
/home/hung/ai-agents/scripts/health-check.sh
```

Expected: All checks pass

**Step 8: Commit**

Run:
```bash
git add scripts/health-check.sh
git commit -m "feat: add systemd service and health monitoring"
```

---

## Task 10: Documentation & Usage Guide

**Files:**
- Create: `/home/hung/ai-agents/README.md`
- Create: `/home/hung/ai-agents/docs/USAGE.md`
- Create: `/home/hung/ai-agents/docs/ARCHITECTURE.md`

**Step 1: Create README**

Create: `/home/hung/ai-agents/README.md`
```markdown
# Multi-Layer AI Agent System

Autonomous development system with Beads orchestration, provider routing, and quality enforcement.

## Quick Start

```bash
cd /home/hung/ai-agents/supervisor
source ../venv/bin/activate
python supervisor.py
```

## System Status

```bash
systemctl status ai-agent-supervisor
/home/hung/ai-agents/scripts/health-check.sh
```

## Provider Quota

```bash
redis-cli get quota:claude:count
redis-cli get quota:glm:count
```

## Active Agents

```bash
redis-cli keys "agent:*:heartbeat"
```

## Documentation

- [Usage Guide](docs/USAGE.md)
- [Architecture](docs/ARCHITECTURE.md)
```

**Step 2: Create usage guide**

Create: `/home/hung/ai-agents/docs/USAGE.md`
```markdown
# Usage Guide

## Creating an Epic

```bash
cd /home/hung/ai-agents/projects/my-project
bd init
bd create "OAuth 2.0 System" --type epic --priority 0
```

## System automatically:
1. Planning agent decomposes epic into tasks
2. Router assigns tasks to providers based on complexity + quota
3. Agents implement with TDD (Superpowers enforces)
4. Verification agents review (GLM → cascade to Claude if issues)
5. Merge to integration branch per epic
6. Claude reviews complete epic
7. Merge to main

## Monitoring

Supervisor logs: `/home/hung/ai-agents/logs/supervisor.log`
Agent logs: `/home/hung/ai-agents/logs/agents/`

## Manual Intervention

Stop specific agent:
```bash
redis-cli keys "agent:*:task" | xargs redis-cli del
```

Force quota reset:
```bash
redis-cli del quota:claude:count quota:claude:window_start
```
```

**Step 3: Create architecture doc**

Create: `/home/hung/ai-agents/docs/ARCHITECTURE.md`
```markdown
# Architecture

## Layers

1. **Orchestration**: Beads task graph + Redis coordination
2. **Routing**: Provider selection based on complexity + quota
3. **Execution**: Agent pools spawn `claude` with env overrides
4. **Verification**: Staged cascade (cheap → expensive)
5. **Quality**: Superpowers auto-triggering skills

## Components

- `supervisor.py`: Main loop
- `quota.py`: Time-windowed quota tracking
- `router.py`: Provider selection logic
- `agent.py`: Process spawning + heartbeat
- `beads.py`: Task management
- `verifier.py`: Review workflows
- `mcporter_helper.py`: Token optimization

## Data Flow

Epic created → Planning agent decomposes → Tasks in Beads → Supervisor routes → Agent spawned → Implementation → Verification → Cascade if needed → Merge to integration → Claude epic review → Merge to main
```

**Step 4: Commit**

Run:
```bash
git add README.md docs/
git commit -m "docs: add usage guide and architecture documentation"
```

**Step 5: Create final integration test**

Create: `tests/test_integration.py`
```python
import pytest
from supervisor import Supervisor
import yaml
import time

@pytest.mark.integration
def test_full_workflow_simple_task():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    supervisor = Supervisor(config)

    task_created = supervisor.beads.create_task(
        title="Add hello world function",
        epic_id="test-epic",
        complexity="simple",
        phase="phase1",
        files=["src/hello.py", "tests/test_hello.py"],
        acceptance_criteria=["Function returns 'Hello World'"]
    )

    assert task_created

    supervisor.run_iteration()

    time.sleep(5)

    active_agents = [a for pool in supervisor.agent_pools.values() for a in pool["active"]]
    assert len(active_agents) > 0
```

**Step 6: Run integration test**

Run:
```bash
pytest tests/test_integration.py -v -m integration
```

Expected: PASS

**Step 7: Final commit**

Run:
```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration test"
git tag v1.0.0
```

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-01-28-multi-layer-ai-agent-system.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
