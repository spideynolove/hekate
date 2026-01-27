import pytest
from unittest.mock import patch, Mock
from hekate.beads import BeadsClient
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
        mock_run.assert_called_with(["bd", "ready", "--json"], capture_output=True, text=True, check=True, cwd=None)

def test_beads_client_claims_task():
    client = BeadsClient()

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0)

        success = client.claim_task("bd-abc123", "agent-001")

        assert success is True
        mock_run.assert_called_with(
            ["bd", "update", "bd-abc123", "--metadata", "owner=agent-001"],
            capture_output=True,
            text=True,
            cwd=None
        )

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