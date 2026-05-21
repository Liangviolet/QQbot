"""Token bucket 限流器"""

import time


class TokenBucket:
    """基于 token bucket 算法的 API 限流器

    每个 key 维护独立的 token bucket，在 period 秒内最多允许 capacity 次请求。
    """

    def __init__(self, capacity: int, period: float):
        self.capacity = capacity
        self.period = period
        self._buckets: dict[str, tuple[int, float]] = {}

    def check(self, key: str) -> bool:
        """检查是否允许请求，消耗一个 token

        Returns:
            True 表示允许请求，False 表示限流
        """
        now = time.monotonic()
        tokens, refill = self._buckets.get(key, (self.capacity, now))

        # 到达周期则重置 token
        elapsed = now - refill
        if elapsed >= self.period:
            tokens = self.capacity
            refill = now

        if tokens > 0:
            self._buckets[key] = (tokens - 1, refill)
            return True
        return False
