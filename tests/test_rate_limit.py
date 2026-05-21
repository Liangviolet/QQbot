"""TokenBucket 限流器单元测试"""

import time

from src.utils.rate_limit import TokenBucket


def test_allow_within_capacity():
    """在容量内应全部允许"""
    bucket = TokenBucket(capacity=3, period=10)
    assert bucket.check("key") is True
    assert bucket.check("key") is True
    assert bucket.check("key") is True
    assert bucket.check("key") is False  # 用尽


def test_independent_buckets():
    """不同 key 拥有独立的 bucket"""
    bucket = TokenBucket(capacity=2, period=10)
    assert bucket.check("a") is True
    assert bucket.check("b") is True  # 不同 key，重新计数
    assert bucket.check("a") is True
    assert bucket.check("a") is False  # "a" 已用尽


def test_refill_after_period():
    """超过 period 后 token 重置"""
    bucket = TokenBucket(capacity=1, period=0.1)
    assert bucket.check("key") is True
    assert bucket.check("key") is False
    time.sleep(0.15)
    assert bucket.check("key") is True  # 已重置


def test_zero_capacity():
    """容量为 0 时应全部拒绝"""
    bucket = TokenBucket(capacity=0, period=10)
    assert bucket.check("key") is False


def test_one_capacity():
    """容量为 1 时每次重置后只能放行一次"""
    bucket = TokenBucket(capacity=1, period=0.1)
    assert bucket.check("key") is True
    assert bucket.check("key") is False
    time.sleep(0.15)
    assert bucket.check("key") is True
    assert bucket.check("key") is False


def test_multiple_keys_independent_refill():
    """多个 key 各自独立重置"""
    bucket = TokenBucket(capacity=1, period=0.1)
    assert bucket.check("a") is True
    assert bucket.check("b") is True
    assert bucket.check("a") is False
    assert bucket.check("b") is False
    time.sleep(0.15)
    assert bucket.check("a") is True
    assert bucket.check("b") is True
