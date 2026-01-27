import pytest
from pathlib import Path
import yaml

def test_config_loads_yaml():
    # Path from tests/ to hekate/ package
    config_path = Path(__file__).parent.parent / "hekate" / "config.yaml"
    assert config_path.exists()

    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert "providers" in config
    assert "agent_pools" in config
    assert "iteration_budgets" in config