import redis
import yaml
import time
import logging
from pathlib import Path
from typing import Dict, List
from .quota import QuotaTracker
from .router import ProviderRouter
from .agent import AgentManager
from .beads import BeadsClient

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
        self.agent_manager = AgentManager(home_dir=str(Path.home()), redis_client=self.redis)
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

        # Filter out already claimed tasks
        unclaimed_tasks = [t for t in tasks if not self._is_task_claimed(t["id"])]

        if not unclaimed_tasks:
            logger.info("No unclaimed tasks")
            return

        for task in unclaimed_tasks:
            if self._can_assign_task():
                self._assign_task(task)
                break  # Only assign one task per iteration for stability

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

        # Claim in Beads as well for atomicity
        beads_claimed = self.beads.claim_task(task["id"], f"supervisor-{provider}")
        if not beads_claimed:
            logger.warning(f"Failed to claim task {task['id']} in Beads")
            self._unclaim_task_in_redis(task["id"])
            return

        project_dir = f"{Path.home()}/hekate-projects/{task.get('epic_id', 'default')}"

        agent_id = self.agent_manager.spawn_agent(
            provider=provider,
            task_id=task["id"],
            project_dir=project_dir
        )

        self.agent_pools[provider]["active"].append(agent_id)

        logger.info(f"Spawned {agent_id} for task {task['id']}")

    def _claim_task_in_redis(self, task_id: str, provider: str) -> bool:
        key = f"task:{task_id}:owner"
        claimed = self.redis.set(key, provider, nx=True, ex=3600)

        return claimed is not None

    def _unclaim_task_in_redis(self, task_id: str):
        key = f"task:{task_id}:owner"
        self.redis.delete(key)

    def _is_task_claimed(self, task_id: str) -> bool:
        key = f"task:{task_id}:owner"
        return self.redis.exists(key)

    def cleanup_completed_agents(self):
        for provider, pool in self.agent_pools.items():
            for agent_id in list(pool["active"]):
                status = self.agent_manager.get_agent_status(agent_id)

                if status in ["completed", "failed", "stale"]:
                    pool["active"].remove(agent_id)
                    logger.info(f"Agent {agent_id} {status}, removed from pool")

    def run(self):
        logger.info("Supervisor starting")

        try:
            while True:
                self.run_iteration()
                self.cleanup_completed_agents()
                time.sleep(10)

        except KeyboardInterrupt:
            logger.info("Supervisor stopping")
            self._shutdown()

    def _shutdown(self):
        logger.info("Shutting down all agents")

        for pool in self.agent_pools.values():
            for agent_id in pool["active"]:
                self.agent_manager.kill_agent(agent_id)

def main():
    # Try to find config in various locations
    config_paths = [
        Path.home() / ".hekate" / "config.yaml",  # User config
        Path.home() / ".config" / "hekate" / "config.yaml",  # System config
        Path(__file__).parent / "config.yaml",  # Package default
    ]

    config_path = None
    for path in config_paths:
        if path.exists():
            config_path = path
            break

    if not config_path:
        logger.error("Could not find config.yaml in any of the expected locations:")
        logger.error("\n".join(str(p) for p in config_paths))
        return

    logger.info(f"Loading config from: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    supervisor = Supervisor(config)
    supervisor.run()

if __name__ == "__main__":
    main()