"""泛型 TTL 缓存"""

from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar
import time

T = TypeVar("T")


@dataclass
class TTLCache(Generic[T]):
    """带 TTL 的泛型内存缓存

    Args:
        ttl: 生存时间（秒）
        max_size: 最大缓存条目数，超限时淘汰最旧条目
    """

    ttl: float
    max_size: int = 1000
    _data: dict = field(default_factory=dict)
    _expires: dict = field(default_factory=dict)

    def get(self, key: str) -> Optional[T]:
        """获取缓存项，已过期返回 None"""
        if key not in self._data:
            return None
        if time.monotonic() > self._expires[key]:
            self.delete(key)
            return None
        return self._data[key]

    def set(self, key: str, value: T) -> None:
        """设置缓存项，超限时淘汰最旧条目"""
        if len(self._data) >= self.max_size and key not in self._data:
            oldest = min(self._expires, key=self._expires.get)
            self.delete(oldest)
        self._data[key] = value
        self._expires[key] = time.monotonic() + self.ttl

    def delete(self, key: str) -> None:
        """删除缓存项"""
        self._data.pop(key, None)
        self._expires.pop(key, None)
