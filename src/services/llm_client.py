"""LLM 抽象客户端 — 多 provider 支持与重试"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


@dataclass
class LLMResponse:
    """LLM 响应封装"""

    content: str
    tokens_used: int
    model: str


class LLMUnavailableException(Exception):
    """LLM 服务不可用异常"""
    pass


def _is_transient_error(exc: BaseException) -> bool:
    """判断是否为可重试的临时错误"""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    return False


_llm_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception(_is_transient_error),
    reraise=True,
)


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client or httpx.AsyncClient(timeout=60.0)

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        ...


class OpenAIClient(LLMClient):
    """OpenAI 兼容 API 客户端（支持 OpenAI、DeepSeek 等兼容 API）"""

    @_llm_retry
    async def _do_chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        response = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
        )
        response.raise_for_status()
        return response.json()

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        try:
            data = await self._do_chat(system_prompt, user_message, max_tokens, temperature)
            return LLMResponse(
                content=data["choices"][0]["message"]["content"],
                tokens_used=data["usage"]["total_tokens"],
                model=data.get("model", self.model),
            )
        except Exception as e:
            raise LLMUnavailableException(str(e)) from e


class AnthropicClient(LLMClient):
    """Anthropic Claude API 客户端"""

    @_llm_retry
    async def _do_chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        response = await self._client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
        )
        response.raise_for_status()
        return response.json()

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        try:
            data = await self._do_chat(system_prompt, user_message, max_tokens, temperature)
            content = data["content"][0]["text"]
            tokens_used = data["usage"]["input_tokens"] + data["usage"]["output_tokens"]
            return LLMResponse(
                content=content,
                tokens_used=tokens_used,
                model=data.get("model", self.model),
            )
        except Exception as e:
            raise LLMUnavailableException(str(e)) from e


def create_llm_client(config: dict) -> LLMClient:
    """工厂方法：根据配置创建 LLM 客户端

    Args:
        config: 包含以下字段的字典
            - provider: "openai" | "anthropic"
            - api_key: API 密钥
            - base_url: API 端点地址（可选，默认使用 provider 的官方端点）
            - model: 模型名称（可选，默认使用 provider 的默认模型）

    Returns:
        LLMClient 实例
    """
    provider = config.get("provider", "openai")
    api_key = config.get("api_key") or ""
    base_url = config.get("base_url") or ""
    model = config.get("model") or ""

    if provider == "openai":
        return OpenAIClient(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            model=model or "gpt-4o-mini",
        )
    elif provider == "anthropic":
        return AnthropicClient(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com",
            model=model or "claude-3-haiku-20240307",
        )
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}")
