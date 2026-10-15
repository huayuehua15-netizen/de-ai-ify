"""进程内滑动窗口限流（lite 模式实现；Redis 令牌桶在 M4 以同一接口接入）。"""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    """按 key 统计最近 60 秒命中数，超过 per_min 拒绝。"""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_prune: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window = self._hits[key]
        # 惰性清理：每 10 秒对该 key 做一次完整裁剪
        if now - self._last_prune.get(key, 0.0) > 10.0:
            cutoff = now - 60.0
            while window and window[0] <= cutoff:
                window.popleft()
            self._last_prune[key] = now
        if len(window) >= self.per_minute:
            return False
        window.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()
        self._last_prune.clear()
