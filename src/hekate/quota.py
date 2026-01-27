import redis
from datetime import datetime, timedelta
from typing import Dict

class QuotaTracker:
    def __init__(self, redis_client: redis.Redis, limit: int, window_hours: int,
                 buffer_percent: int, provider: str = "default"):
        self.redis = redis_client
        self.limit = limit
        self.window_hours = window_hours
        self.buffer_percent = buffer_percent
        self.provider = provider

        self.buffer_limit = int(limit * (1 - buffer_percent / 100))
        self.emergency_limit = int(limit * (buffer_percent / 100))

    def _get_window_key(self) -> str:
        return f"quota:{self.provider}:window_start"

    def _get_count_key(self) -> str:
        return f"quota:{self.provider}:count"

    def _ensure_window(self):
        window_key = self._get_window_key()
        count_key = self._get_count_key()

        window_start = self.redis.get(window_key)
        now = datetime.now()

        if not window_start:
            self.redis.set(window_key, now.isoformat())
            self.redis.set(count_key, 0)
            return

        window_start_dt = datetime.fromisoformat(window_start)
        if now - window_start_dt > timedelta(hours=self.window_hours):
            self.redis.set(window_key, now.isoformat())
            self.redis.set(count_key, 0)

    def increment(self) -> int:
        self._ensure_window()
        count_key = self._get_count_key()
        return self.redis.incr(count_key)

    def get_usage(self) -> Dict:
        self._ensure_window()
        count = int(self.redis.get(self._get_count_key()) or 0)

        return {
            "count": count,
            "limit": self.limit,
            "percentage": (count / self.limit) * 100,
            "remaining": self.limit - count,
            "buffer_limit": self.buffer_limit,
            "emergency_limit": self.emergency_limit,
            "below_buffer": count <= self.buffer_limit,
            "is_emergency": count >= self.buffer_limit
        }

    def can_use(self, reserve_for_emergency: bool = False) -> bool:
        usage = self.get_usage()

        if reserve_for_emergency:
            return usage["count"] < self.buffer_limit

        return usage["count"] < self.limit