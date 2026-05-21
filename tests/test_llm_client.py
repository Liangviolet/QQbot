"""LLM 客户端单元测试（使用 httpx MockTransport）"""

import json

import httpx
import pytest

from src.services.llm_client import (
    LLMUnavailableException,
    OpenAIClient,
    AnthropicClient,
    create_llm_client,
)


# ── OpenAI ──


@pytest.mark.asyncio
async def test_openai_chat_success():
    """OpenAI 客户端成功解析响应"""

    def handler(request):
        data = json.loads(request.content)
        assert data["model"] == "gpt-4o-mini"
        assert data["messages"][0]["role"] == "system"
        assert data["messages"][1]["role"] == "user"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello!"}}],
                "usage": {"total_tokens": 42},
                "model": "gpt-4o-mini",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAIClient(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            client=client,
        )
        resp = await llm.chat("You are a helpful assistant.", "Hi")

    assert resp.content == "Hello!"
    assert resp.tokens_used == 42
    assert resp.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_openai_retry_then_success():
    """首次 503，重试后成功"""

    attempt_count = 0

    def handler(request):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count == 1:
            return httpx.Response(503, json={"error": "Service Unavailable"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "OK after retry"}}],
                "usage": {"total_tokens": 5},
                "model": "gpt-4o-mini",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAIClient(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            client=client,
        )
        resp = await llm.chat("system", "message")

    assert resp.content == "OK after retry"
    assert attempt_count == 2


@pytest.mark.asyncio
async def test_openai_retry_exhausted():
    """连续 503 最终抛出 LLMUnavailableException"""

    attempt_count = 0

    def handler(request):
        nonlocal attempt_count
        attempt_count += 1
        return httpx.Response(503, json={"error": "Service Unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAIClient(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            client=client,
        )
        with pytest.raises(LLMUnavailableException):
            await llm.chat("system", "message")

    assert attempt_count == 3


@pytest.mark.asyncio
async def test_openai_4xx_not_retried():
    """4xx 错误不应触发重试"""

    attempt_count = 0

    def handler(request):
        nonlocal attempt_count
        attempt_count += 1
        return httpx.Response(401, json={"error": "Unauthorized"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = OpenAIClient(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
            client=client,
        )
        with pytest.raises(LLMUnavailableException):
            await llm.chat("system", "message")

    assert attempt_count == 1  # 未重试


# ── Anthropic ──


@pytest.mark.asyncio
async def test_anthropic_chat_success():
    """Anthropic 客户端成功解析响应"""

    def handler(request):
        data = json.loads(request.content)
        assert data["model"] == "claude-3-haiku-20240307"
        assert data["system"] == "You are Claude."
        assert data["messages"][0]["role"] == "user"
        assert request.headers["x-api-key"] == "sk-ant-test"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello from Claude!"}],
                "model": "claude-3-haiku-20240307",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicClient(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            model="claude-3-haiku-20240307",
            client=client,
        )
        resp = await llm.chat("You are Claude.", "Hello")

    assert resp.content == "Hello from Claude!"
    assert resp.tokens_used == 30  # input + output
    assert resp.model == "claude-3-haiku-20240307"


@pytest.mark.asyncio
async def test_anthropic_retry_exhausted():
    """Anthropic 客户端重试耗尽后抛出异常"""

    def handler(request):
        return httpx.Response(503, json={"error": "Service Unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        llm = AnthropicClient(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            model="claude-3-haiku-20240307",
            client=client,
        )
        with pytest.raises(LLMUnavailableException):
            await llm.chat("system", "message")


# ── 工厂方法 ──


def test_create_openai_client():
    """create_llm_client 创建 OpenAI 客户端"""
    config = {
        "provider": "openai",
        "api_key": "sk-test",
        "base_url": "https://custom.api.com/v1",
        "model": "gpt-4",
    }
    client = create_llm_client(config)
    assert isinstance(client, OpenAIClient)
    assert client.model == "gpt-4"
    assert "custom.api.com" in client.base_url


def test_create_anthropic_client():
    """create_llm_client 创建 Anthropic 客户端"""
    config = {
        "provider": "anthropic",
        "api_key": "sk-ant-test",
        "model": "claude-3-opus-20240229",
    }
    client = create_llm_client(config)
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-3-opus-20240229"


def test_create_unknown_provider():
    """不支持的 provider 抛出 ValueError"""
    with pytest.raises(ValueError):
        create_llm_client({"provider": "unknown"})


def test_create_with_defaults():
    """不传 model 和 base_url 时使用默认值"""
    config = {"provider": "openai", "api_key": "sk-test"}
    client = create_llm_client(config)
    assert client.model == "gpt-4o-mini"
    assert client.base_url == "https://api.openai.com/v1"


def test_create_anthropic_defaults():
    """Anthropic 不传 model 和 base_url 时使用默认值"""
    config = {"provider": "anthropic", "api_key": "sk-ant-test"}
    client = create_llm_client(config)
    assert client.model == "claude-3-haiku-20240307"
    assert client.base_url == "https://api.anthropic.com"
