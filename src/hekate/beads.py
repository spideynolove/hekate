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

    def mark_task_completed(self, task_id: str, branch_name: str) -> bool:
        """Mark a task as completed with resulting branch"""
        metadata_json = json.dumps({
            "completed_branch": branch_name,
            "completed_at": self._get_timestamp()
        })

        result = subprocess.run(
            ["bd", "update", task_id, "--status", "completed", "--metadata", metadata_json],
            capture_output=True,
            text=True,
            cwd=self.cwd
        )

        return result.returncode == 0

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()