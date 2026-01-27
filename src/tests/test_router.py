import pytest
import redis
from hekate.router import ProviderRouter
from hekate.quota import QuotaTracker

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

@pytest.fixture
def mock_quotas(redis_client):
    claude_quota = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="claude")
    glm_quota = QuotaTracker(redis_client, limit=180, window_hours=5, buffer_percent=3, provider="glm")

    return {
        "claude": claude_quota,
        "glm": glm_quota,
        "deepseek": None,
        "openrouter": None
    }

def test_router_selects_cheapest_for_simple_task(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "simple", "type": "implementation"}
    provider = router.route_task(task)

    assert provider == "deepseek"

def test_router_routes_planning_to_claude(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "medium", "type": "planning"}
    provider = router.route_task(task)

    assert provider == "claude"

def test_router_downgrades_when_quota_low(mock_quotas):
    # Initialize window and set high usage count
    mock_quotas["claude"].increment()  # This ensures window exists
    for _ in range(37):  # Set count to 38 (above buffer limit of 36)
        mock_quotas["claude"].increment()

    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    task = {"complexity": "medium", "type": "implementation"}
    provider = router.route_task(task)

    assert provider == "glm"

def test_router_cascades_to_higher_provider(mock_quotas):
    router = ProviderRouter(mock_quotas, thresholds={
        "claude_conservative": 40,
        "glm_conservative": 50
    })

    # First route should prefer claude for medium tasks with 0% usage
    task = {"complexity": "medium", "type": "implementation", "attempt": 1}
    first_provider = router.route_task(task)
    assert first_provider == "claude"

    task["attempt"] = 2
    task["previous_provider"] = "claude"
    cascade_provider = router.cascade(task)
    assert cascade_provider == "claude"  # End of chain returns claude