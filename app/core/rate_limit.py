from collections import defaultdict
from threading import Lock
from time import time


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time()
        cutoff = now - window_seconds
        with self._lock:
            recent = [stamp for stamp in self._hits[key] if stamp > cutoff]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = MemoryRateLimiter()
