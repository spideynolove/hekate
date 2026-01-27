import pytest
import redis
from unittest.mock import Mock, patch, MagicMock
from hekate.agent import AgentManager
import subprocess
import os

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

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

def test_agent_manager_spawns_deepseek_with_env_override(redis_client):
    manager = AgentManager(home_dir="/home/hung", redis_client=redis_client)

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
        assert "deepseek" in " ".join(call_args[0][0][2:])

def test_agent_registers_heartbeat(redis_client):
    manager = AgentManager(home_dir="/home/hung", redis_client=redis_client)

    with patch('subprocess.Popen') as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process

        agent_id = manager.spawn_agent("claude", "bd-test", "/home/hung/test")

        heartbeat_key = f"agent:{agent_id}:heartbeat"
        task_key = f"agent:{agent_id}:task"

        assert redis_client.exists(heartbeat_key)
        assert redis_client.exists(task_key)

        ttl = redis_client.ttl(heartbeat_key)
        assert ttl > 0 and ttl <= 90