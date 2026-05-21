"""画像查询匹配器逻辑测试

测试 matchers.py 中的核心逻辑（resolve_target 解析、条件判断路径）。
不依赖 NoneBot 完整运行环境，通过直接构造 Message 对象和调用 analyzer 函数来验证。
"""

from datetime import datetime
from unittest.mock import MagicMock, PropertyMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.message import GroupMessage
from src.plugins.profile.analyzer import compute_stats, generate_profile_report
from src.plugins.profile.matchers import extract_command_text, resolve_target
from src.plugins.profile.models import UserProfile, UserStats
from src.services.database import get_db_session, init_db

GROUP_ID = 1001


# ── resolve_target 单元测试 ────────────────────────────────────

class MockMessageSegment:
    """模拟 MessageSegment 用于构造测试消息。"""

    def __init__(self, seg_type: str, data: dict):
        self.type = seg_type
        self.data = data


def _make_mock_event(
    segments: list[tuple[str, dict]],
    self_id: int = 12345,
) -> MagicMock:
    """构造模拟 GroupMessageEvent。"""
    mock = MagicMock()
    mock.self_id = self_id
    mock.group_id = GROUP_ID

    msg_segments = [MockMessageSegment(t, d) for t, d in segments]

    async def get_message():
        return msg_segments

    mock.get_message = get_message
    # 同步访问也返回 segments
    type(mock).get_message = PropertyMock(return_value=msg_segments)
    return mock


def _make_sync_mock_event(
    segments: list[tuple[str, dict]],
    self_id: int = 12345,
) -> MagicMock:
    """构造同步模拟 GroupMessageEvent（供 resolve_target 使用）。"""
    mock = MagicMock()
    mock.self_id = self_id
    mock.group_id = GROUP_ID

    msg_segments = [MockMessageSegment(t, d) for t, d in segments]

    # resolve_target 用 event.get_message() 遍历，需要返回可迭代对象
    mock.get_message.return_value = msg_segments
    return mock


class TestResolveTarget:
    """resolve_target 函数测试"""

    def test_normal_at(self):
        """正常 @ 其他用户应返回目标 QQ。"""
        event = _make_sync_mock_event([
            ("at", {"qq": "12345"}),  # bot 自身
            ("text", {"text": " 看看"}),
            ("at", {"qq": "67890"}),  # 目标用户
            ("text", {"text": " 的画像"}),
        ])
        assert resolve_target(event) == 67890

    def test_only_self_at(self):
        """仅 @bot 自身时应返回 None。"""
        event = _make_sync_mock_event([
            ("at", {"qq": "12345"}),  # 只有 bot 自身
            ("text", {"text": " 看看画像"}),
        ])
        assert resolve_target(event) is None

    def test_no_at(self):
        """没有 @ 任何人时应返回 None。"""
        event = _make_sync_mock_event([
            ("text", {"text": "看看画像"}),
        ])
        assert resolve_target(event) is None

    def test_multiple_targets(self):
        """多个 @ 时取第一个非 bot 的 @。"""
        event = _make_sync_mock_event([
            ("at", {"qq": "12345"}),  # bot
            ("at", {"qq": "11111"}),  # 目标 1
            ("at", {"qq": "22222"}),  # 目标 2
        ])
        assert resolve_target(event) == 11111


class TestExtractCommandText:
    """extract_command_text 函数测试"""

    def test_simple_text(self):
        event = _make_sync_mock_event([
            ("at", {"qq": "12345"}),
            ("text", {"text": " 看看 画像 "}),
        ])
        assert extract_command_text(event) == "看看 画像"

    def test_no_text(self):
        event = _make_sync_mock_event([
            ("at", {"qq": "12345"}),
        ])
        assert extract_command_text(event) == ""

    def test_multiple_text_segments(self):
        event = _make_sync_mock_event([
            ("text", {"text": " 看看 "}),
            ("at", {"qq": "67890"}),
            ("text", {"text": " 的 画像 "}),
        ])
        assert extract_command_text(event) == "看看 的 画像"


# ── 查询条件逻辑测试 ───────────────────────────────────────────

@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    yield e
    await e.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


class TestMatcherConditions:
    """模拟 matcher 的条件判断路径"""

    async def test_user_not_found(self, engine, session_maker):
        """查询不存在的用户 → stats.total_messages == 0 → "未找到该群友" """
        await init_db(engine)
        async with get_db_session(session_maker) as session:
            stats = await compute_stats(99999, GROUP_ID, session)

        assert stats.total_messages == 0
        # 这是 matcher 中的条件：
        # if stats.total_messages == 0: matcher.finish("未找到该群友")

    async def test_cold_start(self, engine, session_maker):
        """插入 5 条消息 → stats.total_messages < 10 → 冷启动"""
        await init_db(engine)
        messages = [
            GroupMessage(
                group_id=GROUP_ID, user_id=2001,
                plain_text=f"msg {i}", raw_message="",
                timestamp=int(datetime.now().timestamp()) + i,
                message_id=50000 + i,
            )
            for i in range(5)
        ]
        async with get_db_session(session_maker) as session:
            session.add_all(messages)

        async with get_db_session(session_maker) as session:
            stats = await compute_stats(2001, GROUP_ID, session)

        assert stats.total_messages == 5
        assert stats.total_messages < 10
        # 这是 matcher 中的条件：
        # if stats.total_messages < 10: matcher.finish("该群友发言较少，暂时无法生成画像")

    async def test_normal_query(self, engine, session_maker):
        """插入 50 条消息 → stats.total_messages >= 10 → 正常生成报告"""
        await init_db(engine)
        messages = [
            GroupMessage(
                group_id=GROUP_ID, user_id=2002,
                plain_text=f"消息内容 {i}", raw_message="",
                timestamp=int(datetime.now().timestamp()) + i,
                message_id=60000 + i,
            )
            for i in range(50)
        ]
        async with get_db_session(session_maker) as session:
            session.add_all(messages)

        async with get_db_session(session_maker) as session:
            stats = await compute_stats(2002, GROUP_ID, session)

        assert stats.total_messages >= 10

        profile = UserProfile(
            user_id=2002,
            group_id=GROUP_ID,
            stats=stats,
            tags=[],
            relations={},
        )
        report = generate_profile_report(profile)
        assert "用户 2002" in report
        assert "50" in report

    async def test_query_no_at(self):
        """没有 @ 任何人 → resolve_target 返回 None → "请 @ 你要查询的群友" """
        event = _make_sync_mock_event([
            ("text", {"text": "看看画像"}),
        ])
        target = resolve_target(event)
        assert target is None
        # matcher 中的逻辑：
        # if target_id is None: await matcher.finish("请 @ 你要查询的群友")
