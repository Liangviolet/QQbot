"""U6 每日群聊总结生成器 — 单元测试"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models.message import GroupMessage
from src.models.summary import SummaryRecord
from src.services.database import get_db_session, init_db
from src.plugins.summary.generator import (
    get_hot_words,
    get_active_speakers,
    get_lurkers,
    generate_summary,
    get_last_summary_date,
    set_last_summary_date,
    _DEFAULT_STOPWORDS,
)


@pytest.fixture
async def engine():
    e = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    await init_db(e)
    yield e
    await e.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def seed_data(engine, session_maker):
    """插入测试用的消息数据。

    群组 1：
      - user 100: 6 条消息（5 条文本 + 1 条空文本），高频词"原神""抽卡"等
      - user 200: 3 条文本消息
      - user 300: 3 条消息（2 条文本 + 1 条空文本），含纯停用词消息
      - user 400: 过去 7 天有 1 条发言，今天 0 条（潜水）
      - user 500: 过去 7 天有 1 条发言，今天 0 条（潜水）
    群组 2：
      - user 999: 无关消息
    群组 3：无消息
    群组 4：只有空文本消息（表情包/sticker）
    """
    today = datetime.now()
    base_ts = int(datetime(today.year, today.month, today.day).timestamp())

    messages = [
        # --- 群组 1：主测试数据 ---
        # user 100 - 发言最多（5 条文本 + 1 条空）
        GroupMessage(group_id=1, user_id=100, plain_text="原神新版本终于来了", timestamp=base_ts + 100, message_id=1),
        GroupMessage(group_id=1, user_id=100, plain_text="抽卡抽到角色了", timestamp=base_ts + 200, message_id=2),
        GroupMessage(group_id=1, user_id=100, plain_text="剧情也太棒了吧", timestamp=base_ts + 300, message_id=3),
        GroupMessage(group_id=1, user_id=100, plain_text="新角色好强", timestamp=base_ts + 400, message_id=4),
        GroupMessage(group_id=1, user_id=100, plain_text="继续肝", timestamp=base_ts + 500, message_id=5),
        GroupMessage(group_id=1, user_id=100, plain_text="", timestamp=base_ts + 600, message_id=13),  # 表情包
        # user 200 - 发言第二（3 条文本）
        GroupMessage(group_id=1, user_id=200, plain_text="原神原神", timestamp=base_ts + 150, message_id=6),
        GroupMessage(group_id=1, user_id=200, plain_text="抽卡歪了难受", timestamp=base_ts + 250, message_id=7),
        GroupMessage(group_id=1, user_id=200, plain_text="新地图探索中", timestamp=base_ts + 350, message_id=8),
        # user 300 - 发言第三（2 条文本 + 1 条空）
        GroupMessage(group_id=1, user_id=300, plain_text="角色", timestamp=base_ts + 180, message_id=9),
        GroupMessage(group_id=1, user_id=300, plain_text="的的的", timestamp=base_ts + 280, message_id=10),  # 纯停用词
        GroupMessage(group_id=1, user_id=300, plain_text="", timestamp=base_ts + 700, message_id=14),  # 表情包
        # user 400 - 潜水（过去 7 天有发言，今天没有）
        GroupMessage(group_id=1, user_id=400, plain_text="昨天说了一句", timestamp=base_ts - 86400, message_id=11),
        # user 500 - 潜水（过去 7 天有发言，今天没有）
        GroupMessage(group_id=1, user_id=500, plain_text="前天也在聊", timestamp=base_ts - 172800, message_id=12),

        # --- 群组 2：无关数据 ---
        GroupMessage(group_id=2, user_id=999, plain_text="其他群消息", timestamp=base_ts + 100, message_id=100),

        # --- 群组 4：只有空文本 ---
        GroupMessage(group_id=4, user_id=777, plain_text="", timestamp=base_ts + 50, message_id=200),
        GroupMessage(group_id=4, user_id=777, plain_text="", timestamp=base_ts + 100, message_id=201),
        GroupMessage(group_id=4, user_id=888, plain_text="", timestamp=base_ts + 150, message_id=202),
    ]

    async with get_db_session(session_maker) as session:
        session.add_all(messages)

    return {
        "date": today,
        "base_ts": base_ts,
    }


class TestHotWords:
    """热词提取功能测试"""

    async def test_hot_words_basic(self, seed_data, session_maker):
        """Happy path: 正确提取热词并按频次排序"""
        result = await get_hot_words(1, seed_data["date"], session_maker=session_maker)
        words = [w for w, _ in result]
        counts = dict(result)

        assert "原神" in words, "原神应出现在热词中"
        assert "抽卡" in words, "抽卡应出现在热词中"
        assert "角色" in words, "角色应出现在热词中"
        assert counts["原神"] >= counts["抽卡"], "原神频次应 >= 抽卡"

    async def test_stopwords_filtered(self, seed_data, session_maker):
        """停用词过滤：'的'、'了' 等停用词不应出现在热词中"""
        result = await get_hot_words(1, seed_data["date"], session_maker=session_maker)
        words = {w for w, _ in result}
        assert "的" not in words
        assert "了" not in words
        assert "是" not in words

    async def test_short_words_filtered(self, seed_data, session_maker):
        """长度 < 2 的词应被过滤"""
        result = await get_hot_words(1, seed_data["date"], session_maker=session_maker)
        words = {w for w, _ in result}
        for w in words:
            assert len(w) >= 2, f"热词 '{w}' 长度不应小于 2"

    async def test_custom_stopwords(self, seed_data, session_maker):
        """自定义停用词集可以覆盖默认停用词"""
        custom_stopwords = {"原神", "抽卡"}
        result = await get_hot_words(1, seed_data["date"], stopwords=custom_stopwords, session_maker=session_maker)
        words = {w for w, _ in result}
        assert "原神" not in words
        assert "抽卡" not in words

    async def test_empty_text_not_counted(self, seed_data, session_maker):
        """空文本消息不计入热词"""
        result = await get_hot_words(4, seed_data["date"], session_maker=session_maker)
        assert result == [], "所有消息为空文本时热词应为空列表"

    async def test_no_messages_in_group(self, seed_data, session_maker):
        """无消息群组返回空列表"""
        result = await get_hot_words(3, seed_data["date"], session_maker=session_maker)
        assert result == []


class TestActiveSpeakers:
    """活跃用户排行测试"""

    async def test_active_speakers_ranking(self, seed_data, session_maker):
        """Happy path: 正确统计发言数并排序"""
        result = await get_active_speakers(1, seed_data["date"], session_maker=session_maker)
        assert len(result) == 3
        # user 100 发言最多（5 条文本 + 1 条表情包 = 6）
        assert result[0][0] == 100
        assert result[0][1] == 6
        # user 200 和 user 300 各有 3 条消息，顺序可能任意
        top_users = {uid for uid, _ in result}
        assert 200 in top_users
        assert 300 in top_users
        # 确认 user 200/300 的发言数
        counts = dict(result)
        assert counts[200] == 3
        assert counts[300] == 3

    async def test_top_n_limits(self, seed_data, session_maker):
        """top_n 参数应限制返回数量"""
        result = await get_active_speakers(1, seed_data["date"], top_n=1, session_maker=session_maker)
        assert len(result) == 1
        assert result[0][0] == 100

    async def test_no_messages_in_group(self, seed_data, session_maker):
        """无消息群组返回空列表"""
        result = await get_active_speakers(3, seed_data["date"], session_maker=session_maker)
        assert result == []


class TestLurkers:
    """潜水用户检测测试"""

    async def test_lurkers_detected(self, seed_data, session_maker):
        """Happy path: 正确识别今天未发言但过去 7 天有发言的用户"""
        lurkers = await get_lurkers(1, seed_data["date"], session_maker=session_maker)
        assert 400 in lurkers, "user 400 应被识别为潜水"
        assert 500 in lurkers, "user 500 应被识别为潜水"
        # 今天有发言的用户不应出现在潜水中
        assert 100 not in lurkers
        assert 200 not in lurkers
        assert 300 not in lurkers

    async def test_no_lurkers_when_all_speak_today(self, seed_data, session_maker):
        """今日所有人都发言时无潜水用户"""
        lurkers = await get_lurkers(2, seed_data["date"], session_maker=session_maker)
        # 群组 2 只有 user 999，且今天有发言
        assert lurkers == []

    async def test_no_messages_in_group(self, seed_data, session_maker):
        """无消息群组返回空列表"""
        lurkers = await get_lurkers(3, seed_data["date"], session_maker=session_maker)
        assert lurkers == []


class TestGenerateSummary:
    """总结生成完整流程测试"""

    async def test_happy_path(self, seed_data, session_maker):
        """Happy path: 生成包含热词、排行、潜水提醒的总结"""
        summary = await generate_summary(1, seed_data["date"], session_maker=session_maker)
        assert "📊 今日群聊总结" in summary
        assert "热词 TOP" in summary
        assert "原神" in summary  # top 热词
        assert "发言 TOP" in summary
        assert "用户100" in summary  # top 发言者
        assert "用户400" in summary  # 潜水提醒

    async def test_no_messages(self, seed_data, session_maker):
        """Edge case: 当日 0 条消息"""
        summary = await generate_summary(3, seed_data["date"], session_maker=session_maker)
        assert summary == "今天群里还没有消息哦～"

    async def test_stickers_only(self, seed_data, session_maker):
        """Edge case: 仅表情包/sticker 计入发言数但热词为空"""
        summary = await generate_summary(4, seed_data["date"], session_maker=session_maker)
        assert "📊 今日群聊总结" in summary
        assert "热词 TOP" in summary
        assert "暂无数据" in summary
        assert "发言 TOP" in summary
        assert "用户777" in summary

    async def test_llm_fallback_template(self, seed_data, session_maker):
        """Edge case: LLM 不可用时回退纯统计模板"""
        # 不传 llm_client 和 persona_config，强制使用模板
        summary = await generate_summary(1, seed_data["date"], session_maker=session_maker)
        assert "📊 今日群聊总结" in summary
        assert summary.startswith("📊")

    async def test_different_group_isolation(self, seed_data, session_maker):
        """不同群组的数据不应相互影响"""
        summary_1 = await generate_summary(1, seed_data["date"], session_maker=session_maker)
        summary_2 = await generate_summary(2, seed_data["date"], session_maker=session_maker)

        # 群组 1 有数据，群组 2 只有一条"其他群消息"
        assert "今天群里还没有消息哦～" not in summary_1
        assert "其他群消息" not in summary_1  # 群组 2 的数据不应影响群组 1
        # 群组 2 的消息不足以产生热词，但应为模板
        assert "📊" in summary_2


class TestLastSummaryDate:
    """总结日期记录功能测试"""

    async def test_get_none_when_not_set(self, session_maker):
        """未设置时 get 返回 None"""
        result = await get_last_summary_date(9999, session_maker=session_maker)
        assert result is None

    async def test_set_and_get(self, session_maker):
        """设置后可以正确读取"""
        await set_last_summary_date(1, "2026-05-21", session_maker=session_maker)
        result = await get_last_summary_date(1, session_maker=session_maker)
        assert result == "2026-05-21"

    async def test_multiple_groups(self, session_maker):
        """不同群组的日期记录互不干扰"""
        await set_last_summary_date(1, "2026-05-21", session_maker=session_maker)
        await set_last_summary_date(2, "2026-05-20", session_maker=session_maker)

        assert await get_last_summary_date(1, session_maker=session_maker) == "2026-05-21"
        assert await get_last_summary_date(2, session_maker=session_maker) == "2026-05-20"

    async def test_idempotent_set(self, session_maker):
        """重复设置同一天不会报错"""
        await set_last_summary_date(1, "2026-05-21", session_maker=session_maker)
        await set_last_summary_date(1, "2026-05-21", session_maker=session_maker)  # 不应抛异常
        result = await get_last_summary_date(1, session_maker=session_maker)
        assert result == "2026-05-21"

    async def test_latest_date_returned(self, session_maker):
        """多条记录时返回最新日期"""
        await set_last_summary_date(1, "2026-05-20", session_maker=session_maker)
        await set_last_summary_date(1, "2026-05-22", session_maker=session_maker)
        await set_last_summary_date(1, "2026-05-21", session_maker=session_maker)
        result = await get_last_summary_date(1, session_maker=session_maker)
        assert result == "2026-05-22"
