import pytest
import redis
from unittest.mock import Mock, patch
from hekate.supervisor import Supervisor

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

@pytest.fixture
def config():
    return {
        "providers": {
            "claude": {"quota_limit": 45, "window_hours": 5, "buffer_percent": 20, "pool_size": 2},
            "glm": {"quota_limit": 180, "window_hours": 5, "buffer_percent": 3, "pool_size": 4},
            "deepseek": {"pool_size": 6},
            "openrouter": {"pool_size": 2}
        },
        "agent_pools": {"total_agents": 14},
        "iteration_budgets": {"simple": 5, "medium": 15, "complex": 30},
        "quota_thresholds": {"claude_conservative": 40, "glm_conservative": 50},
        "redis": {"host": "localhost", "port": 6379, "db": 15}
    }

def test_supervisor_initializes(config):
    with patch('redis.Redis'):
        supervisor = Supervisor(config)

        assert supervisor.config == config
        assert len(supervisor.agent_pools) == 4
        assert supervisor.redis is not None

def test_supervisor_selects_task_and_routes(config):
    with patch('redis.Redis') as mock_redis:
        supervisor = Supervisor(config)

        with patch.object(supervisor.beads, 'list_ready_tasks') as mock_list:
            mock_list.return_value = [
                {"id": "bd-abc123", "complexity": "simple", "type": "implementation"}
            ]

            with patch.object(supervisor, '_assign_task') as mock_assign, \
                 patch.object(supervisor, '_claim_task_in_redis', return_value=True), \
                 patch.object(supervisor, '_is_task_claimed', return_value=False):

                supervisor.run_iteration()

                mock_assign.assert_called_once()
                task = mock_assign.call_args[0][0]
                assert task["id"] == "bd-abc123"

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