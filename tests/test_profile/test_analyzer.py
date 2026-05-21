"""群友画像分析器单元测试"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.base import Base
from src.models.message import GroupMessage
from src.plugins.profile.analyzer import (
    TOPIC_TAG_MAP,
    build_relation_graph,
    compute_stats,
    generate_profile_report,
    infer_tags,
    parse_cq_ats,
)
from src.plugins.profile.models import UserProfile, UserStats
from src.services.database import get_db_session, init_db

GROUP_ID = 1001
USER_ID_A = 2001
USER_ID_B = 2002
USER_ID_C = 2003


@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    yield e
    await e.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def populated_db(engine, session_maker):
    """插入 100 条模拟消息供统计测试使用。"""
    await init_db(engine)

    base_ts = 1_716_000_000  # 2024-05-18 附近
    messages = []
    for i in range(100):
        hour = (i // 4) % 24  # 每 4 条切换一小时，覆盖完整一天
        ts = base_ts + i * 300  # 每条间隔 5 分钟
        texts = [
            "今天天气真不错",
            "有人一起打原神吗",
            "Python 代码好难写",
            "晚上看番剧去",
            "股票又跌了",
            "去跑步锻炼身体",
            "这个电影好看",
            "吃饭了吗大家",
        ]
        msg = GroupMessage(
            group_id=GROUP_ID,
            user_id=USER_ID_A,
            plain_text=texts[i % len(texts)],
            raw_message=texts[i % len(texts)],
            timestamp=ts,
            message_id=10000 + i,
        )
        messages.append(msg)

    async with get_db_session(session_maker) as session:
        session.add_all(messages)

    return session_maker


@pytest.fixture
async def keyword_db(engine, session_maker):
    """含特定关键词的消息：5 次 "原神" + 5 次 "Python"。"""
    await init_db(engine)

    messages = []
    base_ts = 1_716_000_000

    for i in range(10):
        text = "原神" if i < 5 else "Python"
        msg = GroupMessage(
            group_id=GROUP_ID,
            user_id=USER_ID_B,
            plain_text=f"今天玩{text}真开心",
            raw_message=f"今天玩{text}真开心",
            timestamp=base_ts + i * 100,
            message_id=20000 + i,
        )
        messages.append(msg)

    async with get_db_session(session_maker) as session:
        session.add_all(messages)

    return session_maker


@pytest.fixture
async def relation_db(engine, session_maker):
    """含 CQ at 码的消息用于关系图测试。"""
    await init_db(engine)

    messages = []
    base_ts = 1_716_000_000

    # A → B 3 次, A → C 2 次
    raw_patterns: list[tuple[int, str]] = [
        (USER_ID_A, f"[CQ:at,qq={USER_ID_B}] 你好"),
        (USER_ID_A, f"[CQ:at,qq={USER_ID_B}] 在吗"),
        (USER_ID_A, f"[CQ:at,qq={USER_ID_B}] 好的"),
        (USER_ID_A, f"[CQ:at,qq={USER_ID_C}] 早上好"),
        (USER_ID_A, f"[CQ:at,qq={USER_ID_C}] 晚上好"),
        # B → A 1 次, B → C 1 次
        (USER_ID_B, f"[CQ:at,qq={USER_ID_A}] 收到"),
        (USER_ID_B, f"[CQ:at,qq={USER_ID_C}] 一起玩"),
    ]

    for i, (uid, raw) in enumerate(raw_patterns):
        msg = GroupMessage(
            group_id=GROUP_ID,
            user_id=uid,
            plain_text=raw,
            raw_message=raw,
            timestamp=base_ts + i * 100,
            message_id=30000 + i,
        )
        messages.append(msg)

    async with get_db_session(session_maker) as session:
        session.add_all(messages)

    return session_maker


@pytest.fixture
async def sparse_db(engine, session_maker):
    """仅含几条消息（<10），用于冷启动场景测试。"""
    await init_db(engine)

    messages = []
    base_ts = 1_716_000_000

    for i in range(5):
        msg = GroupMessage(
            group_id=GROUP_ID,
            user_id=USER_ID_C,
            plain_text=f"消息 {i}",
            raw_message=f"消息 {i}",
            timestamp=base_ts + i * 100,
            message_id=40000 + i,
        )
        messages.append(msg)

    async with get_db_session(session_maker) as session:
        session.add_all(messages)

    return session_maker


# ── 测试用例 ───────────────────────────────────────────────────

class TestComputeStats:
    """发言统计计算"""

    async def test_happy_path(self, populated_db, session_maker):
        """100 条消息的发言计数、热词、活跃时段应与实际数据一致。"""
        async with get_db_session(session_maker) as session:
            stats = await compute_stats(USER_ID_A, GROUP_ID, session)

        assert stats.total_messages == 100
        assert stats.avg_daily > 0
        assert len(stats.hourly_distribution) > 0
        # 至少有一些高频词
        assert len(stats.top_words) > 0
        # 检查一些预期词汇
        top_word_texts = [w for w, _ in stats.top_words]
        assert any("原神" in w or "天气" in w or "Python" in w for w in top_word_texts)

    async def test_hourly_distribution(self, populated_db, session_maker):
        """验证活跃时段分布是否正确。"""
        async with get_db_session(session_maker) as session:
            stats = await compute_stats(USER_ID_A, GROUP_ID, session)

        # 100 条数据分布在 24 小时中
        total_from_hours = sum(stats.hourly_distribution.values())
        assert total_from_hours == 100
        # 每个小时应该有约 4 条（100/24）
        assert all(0 <= k <= 23 for k in stats.hourly_distribution)

    async def test_cold_start(self, sparse_db, session_maker):
        """冷启动：只有几条消息时 stats 正确但总量少。"""
        async with get_db_session(session_maker) as session:
            stats = await compute_stats(USER_ID_C, GROUP_ID, session)

        assert stats.total_messages == 5
        assert stats.total_messages < 10

    async def test_empty_data(self, engine, session_maker):
        """无消息时返回空数据。"""
        await init_db(engine)
        async with get_db_session(session_maker) as session:
            stats = await compute_stats(9999, GROUP_ID, session)

        assert stats.total_messages == 0
        assert stats.avg_daily == 0.0
        assert stats.hourly_distribution == {}
        assert stats.top_words == []


class TestInferTags:
    """兴趣标签推断"""

    async def test_keyword_matching(self, keyword_db, session_maker):
        """含特定关键词的消息应正确推断出兴趣标签。"""
        async with get_db_session(session_maker) as session:
            tags = await infer_tags(USER_ID_B, GROUP_ID, session, min_occurrences=3)

        assert "游戏" in tags  # 原神 5 次
        assert "编程" in tags  # Python 5 次

    async def test_insufficient_occurrences(self, keyword_db, session_maker):
        """min_occurrences 设为高于实际次数时不应返回标签。"""
        async with get_db_session(session_maker) as session:
            tags = await infer_tags(USER_ID_B, GROUP_ID, session, min_occurrences=10)

        assert tags == []

    async def test_no_keywords(self, sparse_db, session_maker):
        """没有关键词匹配时返回空列表。"""
        async with get_db_session(session_maker) as session:
            tags = await infer_tags(USER_ID_C, GROUP_ID, session)

        assert tags == []

    async def test_empty_user(self, engine, session_maker):
        """不存在的用户返回空。"""
        await init_db(engine)
        async with get_db_session(session_maker) as session:
            tags = await infer_tags(9999, GROUP_ID, session)

        assert tags == []


class TestBuildRelationGraph:
    """关系图构建"""

    async def test_relation_counts(self, relation_db, session_maker):
        """CQ at 码关系图应正确反映互动频率。"""
        async with get_db_session(session_maker) as session:
            graph = await build_relation_graph(GROUP_ID, session)

        # A → B 3 次
        assert graph[USER_ID_A][USER_ID_B] == 3
        # A → C 2 次
        assert graph[USER_ID_A][USER_ID_C] == 2
        # B → A 1 次
        assert graph[USER_ID_B][USER_ID_A] == 1
        # B → C 1 次
        assert graph[USER_ID_B][USER_ID_C] == 1

    async def test_no_mentions(self, populated_db, session_maker):
        """不包含 @ 的消息群组应返回空关系图（或空的 user dict）。"""
        async with get_db_session(session_maker) as session:
            graph = await build_relation_graph(GROUP_ID, session)

        assert graph == {}


class TestParseCqAts:
    """CQ at 码解析"""

    def test_single_at(self):
        result = parse_cq_ats("[CQ:at,qq=123456] 你好")
        assert result == [123456]

    def test_multiple_ats(self):
        result = parse_cq_ats("[CQ:at,qq=111][CQ:at,qq=222] 大家好")
        assert result == [111, 222]

    def test_no_at(self):
        result = parse_cq_ats("没有 at 的消息")
        assert result == []

    def test_empty_string(self):
        result = parse_cq_ats("")
        assert result == []

    def test_invalid_format(self):
        result = parse_cq_ats("[CQ:at,qq=abc] 乱码")
        assert result == []


class TestGenerateProfileReport:
    """画像报告生成"""

    def test_basic_report(self):
        profile = UserProfile(
            user_id=2001,
            group_id=1001,
            stats=UserStats(
                total_messages=156,
                avg_daily=5.2,
                hourly_distribution={20: 30, 21: 25, 22: 20},
                top_words=[("原神", 10), ("Python", 8)],
            ),
            tags=["游戏", "编程"],
            relations={3001: 23, 3002: 12},
        )
        report = generate_profile_report(profile)
        assert "用户 2001" in report
        assert "156" in report
        assert "5.2" in report
        assert "#游戏" in report
        assert "#编程" in report
        assert "互动 23 次" in report
        assert "互动 12 次" in report

    def test_no_tags(self):
        profile = UserProfile(
            user_id=2001,
            group_id=1001,
            stats=UserStats(total_messages=50, avg_daily=2.0),
            tags=[],
            relations={},
        )
        report = generate_profile_report(profile)
        assert "暂无标签信息" in report

    def test_no_relations(self):
        profile = UserProfile(
            user_id=2001,
            group_id=1001,
            stats=UserStats(total_messages=50, avg_daily=2.0),
            tags=["游戏"],
            relations={},
        )
        report = generate_profile_report(profile)
        assert "暂无互动数据" not in report  # 无关系时不显示"暂无互动数据"章节
        assert "暂无标签信息" not in report  # 有标签时不显示"暂无标签信息"
