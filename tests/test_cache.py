"""TTLCache 单元测试"""

import time

from src.services.cache import TTLCache


def test_get_set():
    """基础 get/set 功能"""
    cache = TTLCache(ttl=60)
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_get_missing():
    """不存在的 key 返回 None"""
    cache = TTLCache(ttl=60)
    assert cache.get("nonexistent") is None


def test_expiry():
    """过期后返回 None"""
    cache = TTLCache(ttl=0.1)
    cache.set("key", "value")
    assert cache.get("key") == "value"
    time.sleep(0.15)
    assert cache.get("key") is None


def test_eviction():
    """超过 max_size 时淘汰最旧条目"""
    cache = TTLCache(ttl=60, max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # 应淘汰 "a"（最旧）
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_delete():
    """手动删除缓存项"""
    cache = TTLCache(ttl=60)
    cache.set("key", "value")
    cache.delete("key")
    assert cache.get("key") is None


def test_update_existing_no_eviction():
    """更新已有 key 不应触发淘汰"""
    cache = TTLCache(ttl=60, max_size=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("a", 3)  # 更新已有 key，而非新增
    assert cache.get("a") == 3
    assert cache.get("b") == 2


def test_delete_nonexistent():
    """删除不存在的 key 不报错"""
    cache = TTLCache(ttl=60)
    cache.delete("nonexistent")  # 不应抛出异常


def test_expired_entry_removed_on_get():
    """过期条目在 get 时自动清理"""
    cache = TTLCache(ttl=0.1)
    cache.set("key", "value")
    time.sleep(0.15)
    assert cache.get("key") is None
    # 验证内部数据也被清理
    assert "key" not in cache._data
    assert "key" not in cache._expires
