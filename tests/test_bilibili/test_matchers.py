"""Bilibili 匹配器集成测试（使用 mock）"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugins.bilibili.parser import VideoInfo
from src.plugins.bilibili.matchers import (
    handle_bv,
    handle_summary,
    bv_matcher,
    summary_matcher,
    _group_bv,
    _video_cache,
)
from src.services.llm_client import LLMUnavailableException

SAMPLE_VIDEO = VideoInfo(
    bvid="BV1xx411c7mD",
    title="测试视频标题",
    author="测试UP主",
    views=12345,
    cover_url="http://example.com/cover.jpg",
    duration=360,
)


def make_event(
    text: str,
    user_id: int = 123456,
    self_id: int = 999999,
    group_id: int = 111111,
) -> MagicMock:
    """创建模拟的 GroupMessageEvent"""
    event = MagicMock()
    event.get_plaintext.return_value = text
    event.user_id = user_id
    event.self_id = self_id
    event.group_id = group_id
    return event


@pytest.fixture(autouse=True)
def clear_context():
    """每个测试前清理 BV 上下文和视频缓存"""
    _group_bv.clear()
    _video_cache._data.clear()
    _video_cache._expires.clear()


@pytest.mark.asyncio
class TestHandleBv:
    """handle_bv 集成测试"""

    async def test_bv_video_card(self):
        """单个 BV 号应返回视频卡片"""
        event = make_event("看看这个视频 BV1xx411c7mD")

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=SAMPLE_VIDEO),
        ):
            with patch.object(bv_matcher, "finish", AsyncMock()) as mock_finish:
                await handle_bv(event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "测试视频标题" in msg
        assert "测试UP主" in msg
        assert "12,345" in msg

    async def test_multiple_bv_merged(self):
        """多个 BV 号应合并回复"""
        event = make_event("视频1 BV1xx411c7mD 视频2 BV1xx411c7mE")

        info2 = VideoInfo(
            bvid="BV1xx411c7mE",
            title="第二个视频",
            author="UP主2",
            views=500,
            cover_url="http://example.com/cover2.jpg",
            duration=60,
        )

        async def mock_fetch(bvid: str, _client):
            if bvid == "BV1xx411c7mD":
                return SAMPLE_VIDEO
            if bvid == "BV1xx411c7mE":
                return info2
            return None

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            mock_fetch,
        ):
            with patch.object(bv_matcher, "finish", AsyncMock()) as mock_finish:
                await handle_bv(event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "测试视频标题" in msg
        assert "第二个视频" in msg

    async def test_invalid_bv_no_error(self):
        """无效 BV 号不应报错（使用与其他测试不同的 BV ID 避免缓存命中）"""
        event = make_event("无效BV号 BV1zzzzzzzzz")

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=None),
        ):
            with patch.object(bv_matcher, "finish", AsyncMock()) as mock_finish:
                await handle_bv(event)

        mock_finish.assert_not_called()

    async def test_self_message_filtered(self):
        """自消息应被过滤，不触发 API 调用和回复"""
        event = make_event("BV1xx411c7mD", user_id=999999, self_id=999999)

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
        ) as mock_fetch:
            with patch.object(bv_matcher, "finish", AsyncMock()) as mock_finish:
                await handle_bv(event)

        mock_fetch.assert_not_called()
        mock_finish.assert_not_called()

    async def test_no_bv_text_no_reply(self):
        """不含 BV 号的消息不应触发回复"""
        event = make_event("今天天气真好")

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
        ) as mock_fetch:
            with patch.object(bv_matcher, "finish", AsyncMock()) as mock_finish:
                await handle_bv(event)

        mock_fetch.assert_not_called()
        mock_finish.assert_not_called()

    async def test_context_stored_on_bv(self):
        """处理 BV 号后应存储上下文"""
        event = make_event("BV1xx411c7mD")

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=SAMPLE_VIDEO),
        ):
            with patch.object(bv_matcher, "finish", AsyncMock()):
                await handle_bv(event)

        assert "111111" in _group_bv
        _, bvid = _group_bv["111111"]
        assert bvid == "BV1xx411c7mD"


@pytest.mark.asyncio
class TestHandleSummary:
    """handle_summary 集成测试"""

    async def _setup_context(self, bvid: str = "BV1xx411c7mD"):
        """辅助方法：通过 handle_bv 建立上下文"""
        event = make_event(bvid)
        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=SAMPLE_VIDEO),
        ):
            with patch.object(bv_matcher, "finish", AsyncMock()):
                await handle_bv(event)

    async def test_summary_with_context(self):
        """有上下文时 @bot 总结应返回摘要"""
        await self._setup_context()
        assert "111111" in _group_bv

        summary_event = make_event("总结")

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "这是一个测试视频的摘要内容。"
        mock_llm.chat = AsyncMock(return_value=mock_response)

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=SAMPLE_VIDEO),
        ):
            with patch(
                "src.plugins.bilibili.matchers.create_llm_client",
                return_value=mock_llm,
            ):
                with patch.object(
                    summary_matcher, "finish", AsyncMock()
                ) as mock_finish:
                    await handle_summary(summary_event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "测试视频标题" in msg
        assert "这是一个测试视频的摘要内容" in msg

    async def test_summary_context_expired(self):
        """上下文过期时 @bot 总结应提示"""
        await self._setup_context()

        # 模拟上下文过期（config 中 summary_context_ttl = 300）
        _group_bv["111111"] = (time.time() - 600, "BV1xx411c7mD")

        summary_event = make_event("总结")
        with patch.object(
            summary_matcher, "finish", AsyncMock()
        ) as mock_finish:
            await handle_summary(summary_event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "请发送或引用BV号" in msg

    async def test_summary_no_context(self):
        """无上下文时 @bot 总结应提示"""
        assert "111111" not in _group_bv

        summary_event = make_event("总结")
        with patch.object(
            summary_matcher, "finish", AsyncMock()
        ) as mock_finish:
            await handle_summary(summary_event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "请发送或引用BV号" in msg

    async def test_summary_video_not_found(self):
        """视频不存在时 @bot 总结应提示（手动设置 context 避免缓存干扰）"""
        _group_bv["111111"] = (time.time(), "BV1xx411c7mD")

        summary_event = make_event("总结")

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=None),
        ):
            with patch.object(
                summary_matcher, "finish", AsyncMock()
            ) as mock_finish:
                await handle_summary(summary_event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "无法获取视频信息" in msg

    async def test_summary_llm_unavailable(self):
        """LLM 不可用时应返回降级提示"""
        await self._setup_context()
        assert "111111" in _group_bv

        summary_event = make_event("总结")

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(
            side_effect=LLMUnavailableException("API error")
        )

        with patch(
            "src.plugins.bilibili.matchers.fetch_video_info",
            AsyncMock(return_value=SAMPLE_VIDEO),
        ):
            with patch(
                "src.plugins.bilibili.matchers.create_llm_client",
                return_value=mock_llm,
            ):
                with patch.object(
                    summary_matcher, "finish", AsyncMock()
                ) as mock_finish:
                    await handle_summary(summary_event)

        mock_finish.assert_called_once()
        msg = str(mock_finish.call_args[0][0])
        assert "AI 摘要暂时不可用" in msg
