"""
LLM client abstraction supporting Ollama (local), OpenAI, and Anthropic.

Provides a unified async interface for text generation and streaming,
used by the graph extraction, schema generation, and RAG synthesis pipelines.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens one by one."""
        ...


class OllamaClient(BaseLLMClient):
    """Client for locally-hosted Ollama models (ideal for M4 Apple Silicon)."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model or settings.LLM_MODEL
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> str:
        import aiohttp

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature or settings.LLM_TEMPERATURE,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("response", "")

    async def stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        import aiohttp
        import json

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature or settings.LLM_TEMPERATURE,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as response:
                response.raise_for_status()
                async for line in response.content:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI-compatible APIs (OpenAI, Azure, local vLLM)."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.LLM_MODEL
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature or settings.LLM_TEMPERATURE,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature or settings.LLM_TEMPERATURE,
            stream=True,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str | None = None):
        self.model = model or settings.LLM_MODEL
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    async def stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text


_llm_client_instance: BaseLLMClient | None = None


def get_llm_client() -> BaseLLMClient:
    """Get the configured LLM client (singleton per process)."""
    global _llm_client_instance
    if _llm_client_instance is not None:
        return _llm_client_instance

    provider = settings.LLM_PROVIDER
    if provider == "openai":
        _llm_client_instance = OpenAIClient()
    elif provider == "anthropic":
        _llm_client_instance = AnthropicClient()
    else:
        # Default to Ollama (local)
        _llm_client_instance = OllamaClient()

    return _llm_client_instance
