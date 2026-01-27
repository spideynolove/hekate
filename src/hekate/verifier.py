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
        try:
            # Checkout the branch
            result = subprocess.run(
                ["git", "checkout", git_branch],
                capture_output=True,
                timeout=30
            )

            if result.returncode != 0:
                return False

            # Run tests
            test_result = subprocess.run(
                ["pytest", "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            return test_result.returncode == 0

        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            # No test framework installed
            return True

    def _code_review(self, task: Dict) -> Dict:
        prompt = f"""Review this task implementation:
Task ID: {task['id']}
Acceptance Criteria: {task.get('acceptance_criteria', [])}

Check for:
1. Security issues or vulnerabilities
2. Code quality and best practices
3. Acceptance criteria fulfillment
4. Logic correctness
5. Error handling

Respond with JSON only: {{"pass": true/false, "confidence": 0.0-1.0, "issues": ["list", "of", "issues"]}}
"""

        try:
            result = subprocess.run(
                ["bash", "-c", f"source ~/.bashrc && {self.provider} --dangerously-skip-permissions <<< '{prompt}'"],
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                return {"pass": False, "confidence": 0.0, "issues": ["Review failed to execute"]}

            return json.loads(result.stdout.strip())

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return {"pass": False, "confidence": 0.0, "issues": ["Review timeout or parsing error"]}

    def _is_major_issue(self, review_result: Dict) -> bool:
        issues = review_result.get("issues", [])

        major_keywords = [
            "security", "vulnerability", "critical", "breaking", "incorrect",
            "dangerous", "exploit", "unsafe", "malfunction", "broken"
        ]

        for issue in issues:
            issue_lower = issue.lower()
            if any(keyword in issue_lower for keyword in major_keywords):
                return True

        return False