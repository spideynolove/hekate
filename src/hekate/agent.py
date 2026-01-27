import subprocess
import time
import os
from typing import Dict, Optional
from pathlib import Path
import redis
import threading

class AgentManager:
    def __init__(self, home_dir: str, redis_client: Optional[redis.Redis] = None):
        self.home_dir = Path(home_dir)
        self.agents: Dict[str, subprocess.Popen] = {}
        self.redis = redis_client or redis.Redis(host='localhost', port=6379, decode_responses=True)
        self._start_heartbeat_thread()

    def spawn_agent(self, provider: str, task_id: str, project_dir: str) -> str:
        agent_id = f"agent-{provider}-{int(time.time())}"

        if provider == "claude":
            cmd = ["claude", "--dangerously-skip-permissions"]
        else:
            # Use bash to source ~/.bashrc and call provider function
            bashrc = self.home_dir / ".bashrc"
            cmd = [
                "bash", "-c",
                f"source {bashrc} && {provider} --dangerously-skip-permissions"
            ]

        # Change to project directory
        process = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(os.environ, TASK_ID=task_id, AGENT_ID=agent_id)
        )

        self.agents[agent_id] = process

        # Register in Redis
        heartbeat_key = f"agent:{agent_id}:heartbeat"
        task_key = f"agent:{agent_id}:task"
        self.redis.setex(heartbeat_key, 90, int(time.time()))
        self.redis.set(task_key, task_id)

        return agent_id

    def get_agent_status(self, agent_id: str) -> Optional[str]:
        process = self.agents.get(agent_id)

        if not process:
            return None

        poll = process.poll()

        if poll is None:
            # Still running, check heartbeat
            heartbeat_key = f"agent:{agent_id}:heartbeat"
            heartbeat = self.redis.get(heartbeat_key)
            if heartbeat and int(time.time()) - int(heartbeat) < 120:
                return "running"
            else:
                return "stale"
        elif poll == 0:
            return "completed"
        else:
            return "failed"

    def kill_agent(self, agent_id: str) -> bool:
        process = self.agents.get(agent_id)

        if not process:
            return False

        try:
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # Clean up Redis keys
        heartbeat_key = f"agent:{agent_id}:heartbeat"
        task_key = f"agent:{agent_id}:task"
        self.redis.delete(heartbeat_key, task_key)

        del self.agents[agent_id]
        return True

    def update_heartbeat(self, agent_id: str):
        """Update the agent's heartbeat timestamp"""
        heartbeat_key = f"agent:{agent_id}:heartbeat"
        self.redis.setex(heartbeat_key, 90, int(time.time()))

    def _start_heartbeat_thread(self):
        """Background thread to update heartbeats for running agents"""
        def heartbeat_worker():
            while True:
                for agent_id, process in list(self.agents.items()):
                    if process.poll() is None:  # Still running
                        self.update_heartbeat(agent_id)
                time.sleep(30)  # Update every 30 seconds

        thread = threading.Thread(target=heartbeat_worker, daemon=True)
        thread.start()

    def get_active_agents(self) -> Dict[str, str]:
        """Get all active agents and their status"""
        active = {}
        for agent_id in list(self.agents.keys()):
            status = self.get_agent_status(agent_id)
            if status in ["running", "stale"]:
                active[agent_id] = status
            elif status in ["completed", "failed", None]:
                # Clean up completed/failed agents
                if agent_id in self.agents:
                    del self.agents[agent_id]

        return active