from typing import Dict, Optional
from .quota import QuotaTracker

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
            if self._can_use_provider("claude"):
                claude_usage = self._get_quota_percentage("claude")
                if claude_usage < self.thresholds["claude_conservative"]:
                    return "claude"

            if self._can_use_provider("glm"):
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