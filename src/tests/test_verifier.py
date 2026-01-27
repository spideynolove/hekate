import pytest
from unittest.mock import Mock, patch
from hekate.verifier import VerificationAgent

def test_verification_agent_reviews_task():
    agent = VerificationAgent(provider="glm", redis_client=Mock())

    task = {
        "id": "bd-abc123",
        "acceptance_criteria": ["Tests pass", "No security issues"],
        "git_branch": "agent-001-bd-abc123"
    }

    with patch.object(agent, '_run_tests', return_value=True), \
         patch.object(agent, '_code_review', return_value={"pass": True, "confidence": 0.85, "issues": []}):

        result = agent.verify(task)

        assert result["status"] == "approved"
        assert result["confidence"] >= 0.85

def test_verification_fails_with_major_issues():
    agent = VerificationAgent(provider="glm", redis_client=Mock())

    task = {"id": "bd-abc123", "acceptance_criteria": [], "git_branch": "test"}

    with patch.object(agent, '_run_tests', return_value=True), \
         patch.object(agent, '_code_review', return_value={"pass": False, "confidence": 0.4, "issues": ["security hole"]}):

        result = agent.verify(task)

        assert result["status"] == "needs_guidance"
        assert "security hole" in result["issues"]

def test_verification_detects_major_issues():
    agent = VerificationAgent(provider="glm", redis_client=Mock())

    # Test that major issues are correctly identified
    assert agent._is_major_issue({"issues": ["security vulnerability found"]}) == True
    assert agent._is_major_issue({"issues": ["minor style issue"]}) == False
    assert agent._is_major_issue({"issues": ["critical bug", "dangerous code"]}) == True