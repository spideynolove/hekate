import pytest
import redis
from datetime import datetime, timedelta
from hekate.quota import QuotaTracker

@pytest.fixture
def redis_client():
    client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()

def test_quota_tracker_initializes_windows(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20)

    assert tracker.limit == 45
    assert tracker.window_hours == 5
    assert tracker.buffer_limit == 36
    assert tracker.emergency_limit == 9

def test_quota_tracker_tracks_usage(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="claude")

    tracker.increment()
    tracker.increment()

    usage = tracker.get_usage()
    assert usage["count"] == 2
    assert usage["limit"] == 45
    assert usage["percentage"] == pytest.approx(4.4, rel=0.1)

def test_quota_window_resets_after_expiry(redis_client):
    tracker = QuotaTracker(redis_client, limit=45, window_hours=5, buffer_percent=20, provider="test")

    tracker.increment()
    tracker.increment()
    assert tracker.get_usage()["count"] == 2

    past_time = datetime.now() - timedelta(hours=6)
    redis_client.set("quota:test:window_start", past_time.isoformat())

    tracker.increment()
    usage = tracker.get_usage()
    assert usage["count"] == 1