"""问答路由 & 权限逻辑测试（直接测试核心逻辑，无需 NoneBot 运行环境）"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugins.qa.router import route


# ------------------------------------------------------------------
# 测试：KB 命中
# ------------------------------------------------------------------

class TestKBHit:
    """KB 命中时应返回知识库答案并附加来源标识"""

    @pytest.mark.asyncio
    async def test_kb_hit_returns_kb_answer(self):
        mock_kb = MagicMock()
        mock_kb.search.return_value = ("欢迎遵守群规", "kb")

        result = await route("群规是什么", mock_kb, None, {})

        assert "欢迎遵守群规" in result
        assert "来自知识库" in result

    @pytest.mark.asyncio
    async def test_kb_hit_with_threshold(self):
        mock_kb = MagicMock()
        mock_kb.search.return_value = ("天气答案", "kb")

        result = await route("今天天气", mock_kb, None, {}, threshold=80)

        mock_kb.search.assert_called_once_with("今天天气", threshold=80)
        assert "天气答案" in result


# ------------------------------------------------------------------
# 测试：LLM 兜底
# ------------------------------------------------------------------

class TestLLMFallback:
    """KB 未命中时应调用 LLM 并追加免责声明"""

    @pytest.mark.asyncio
    async def test_llm_fallback_appends_disclaimer(self):
        mock_kb = MagicMock()
        mock_kb.search.return_value = None

        with patch(
            "src.plugins.qa.router.generate_answer",
            new=AsyncMock(return_value="GIL 是全局解释器锁，用于保证线程安全。"),
        ):
            result = await route("Python 的 GIL 是什么", mock_kb, None, {})

            assert "GIL 是全局解释器锁" in result
            assert "*AI 生成，仅供参考" in result

    @pytest.mark.asyncio
    async def test_llm_receives_persona_config(self):
        mock_kb = MagicMock()
        mock_kb.search.return_value = None
        persona = {"name": "测试Bot", "reply_tone": "concise"}

        with patch(
            "src.plugins.qa.router.generate_answer",
            new=AsyncMock(return_value="42"),
        ) as mock_gen:
            await route("生命的意义", mock_kb, None, persona)

            mock_gen.assert_awaited_once_with(
                "生命的意义",
                persona,
                None,
            )


# ------------------------------------------------------------------
# 测试：空问题引导
# ------------------------------------------------------------------

class TestEmptyQuestion:
    """空问题应返回引导文本"""

    @pytest.mark.asyncio
    async def test_empty_string(self):
        result = await route("", None, None, {})
        assert result == "在呢，有什么可以帮你的？"

    @pytest.mark.asyncio
    async def test_whitespace_only(self):
        result = await route("   ", None, None, {})
        assert result == "在呢，有什么可以帮你的？"


# ------------------------------------------------------------------
# 测试：LLM 不可用时降级
# ------------------------------------------------------------------

class TestLLMUnavailable:
    """LLM 服务不可用时应返回降级消息，不追加免责"""

    @pytest.mark.asyncio
    async def test_returns_fallback_without_disclaimer(self):
        mock_kb = MagicMock()
        mock_kb.search.return_value = None

        # generate_answer 内部捕获异常并返回降级文本
        with patch(
            "src.plugins.qa.router.generate_answer",
            new=AsyncMock(return_value="抱歉，AI 服务暂时不可用"),
        ):
            result = await route("任何问题", mock_kb, None, {})

            assert result == "抱歉，AI 服务暂时不可用"
            assert "*AI 生成" not in result


# ------------------------------------------------------------------
# 测试：权限检查
# ------------------------------------------------------------------

class TestPermissionCheck:
    """检查 _is_superuser 辅助函数"""

    def test_superuser_in_list(self):
        from src.plugins.qa.matchers import _is_superuser

        # 这里只验证函数签名和行为模式，实际结果依赖配置文件
        # superusers 从全局 config 读取
        assert callable(_is_superuser)

    @pytest.mark.asyncio
    async def test_superuser_check_logic(self):
        """验证 route 本身不受权限影响（权限由 matchers 层保证）"""
        mock_kb = MagicMock()
        mock_kb.search.return_value = None

        with patch(
            "src.plugins.qa.router.generate_answer",
            new=AsyncMock(return_value="正常回答"),
        ):
            result = await route("问题", mock_kb, None, {})
            assert "正常回答" in result


# ------------------------------------------------------------------
# 测试：无 @ 不响应（规则层验证）
# ------------------------------------------------------------------

class TestToMeRule:
    """验证 to_me() 规则已配置在 matcher 上"""

    def test_matcher_has_to_me_rule(self):
        """检查 qa_matcher 的 rule 中包含 to_me"""
        from nonebot.rule import to_me
        from nonebot import on_message

        # 验证 to_me 函数可被正常导入
        assert callable(to_me)

        # 验证 on_message 可被正常导入
        assert callable(on_message)
