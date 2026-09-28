"""
OpenAI runtime — parallel path to Google ADK / Gemini.

Default model is gpt-4o-mini. Stretch harder target: gpt-5.6-luna (OPENAI_MODEL).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from core.config import (
    OPENROUTER_BASE_URL,
    PROVIDER_OPENROUTER,
    get_blue_runtime_model,
    get_model_name,
)


@dataclass
class OpenAIAgent:
    name: str
    instruction: str
    provider: str = "openai"


@dataclass
class _MockInvocationContext:
    user_id: str = "student"


@dataclass
class OpenAIRunner:
    """OpenAI-compatible runner for OpenAI or OpenRouter endpoints."""

    app_name: str
    model: str = field(default_factory=get_model_name)
    plugins: list = field(default_factory=list)
    provider: str = "openai"
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.4
    input_hooks: list[Callable[[str], str | None]] = field(default_factory=list)
    output_hooks: list[Callable[[str], str]] = field(default_factory=list)

    def _client(self):
        from openai import OpenAI

        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"Missing required API key: {self.api_key_env}")
        kwargs = {"api_key": api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    async def chat(self, agent: OpenAIAgent, user_message: str) -> str:
        for hook in self.input_hooks:
            blocked = hook(user_message)
            if blocked:
                return blocked

        block_msg = await self._run_input_plugins(user_message)
        if block_msg is not None:
            return block_msg

        client = self._client()
        completion = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": agent.instruction},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
        )
        text = (completion.choices[0].message.content or "").strip()

        for hook in self.output_hooks:
            text = hook(text)

        text = await self._run_output_plugins(text)
        return text

    async def _run_input_plugins(self, user_message: str) -> str | None:
        if not self.plugins:
            return None
        try:
            from google.genai import types
        except ImportError:
            return None

        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
        ctx = _MockInvocationContext()
        for plugin in self.plugins:
            cb = getattr(plugin, "on_user_message_callback", None)
            if cb is None:
                continue
            try:
                result = await cb(
                    invocation_context=ctx, user_message=user_content
                )
            except TypeError:
                # Some plugins may be sync
                result = cb(invocation_context=ctx, user_message=user_content)
            if result is None:
                continue
            return _content_to_text(result)
        return None

    async def _run_output_plugins(self, text: str) -> str:
        if not self.plugins or not text:
            return text
        try:
            from google.genai import types
        except ImportError:
            return text

        # Build a duck-typed llm_response for after_model_callback
        content = types.Content(
            role="model", parts=[types.Part.from_text(text=text)]
        )

        class _Resp:
            pass

        llm_response = _Resp()
        llm_response.content = content

        class _Ctx:
            pass

        for plugin in self.plugins:
            cb = getattr(plugin, "after_model_callback", None)
            if cb is None:
                continue
            try:
                out = await cb(callback_context=_Ctx(), llm_response=llm_response)
            except TypeError:
                out = cb(callback_context=_Ctx(), llm_response=llm_response)
            if out is not None and getattr(out, "content", None) is not None:
                llm_response = out
        return _content_to_text(llm_response.content) or text


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = getattr(content, "parts", None) or []
    chunks = []
    for part in parts:
        t = getattr(part, "text", None)
        if t:
            chunks.append(t)
    return "".join(chunks)


def create_openai_pair(
    *,
    name: str,
    instruction: str,
    app_name: str,
    plugins: list | None = None,
    input_hooks: list | None = None,
    output_hooks: list | None = None,
    temperature: float = 0.4,
    model: str | None = None,
    provider: str = "openai",
    base_url: str | None = None,
    api_key_env: str = "OPENAI_API_KEY",
) -> tuple[OpenAIAgent, OpenAIRunner]:
    agent = OpenAIAgent(name=name, instruction=instruction, provider=provider)
    runner = OpenAIRunner(
        app_name=app_name,
        model=model or get_model_name(),
        plugins=list(plugins or []),
        provider=provider,
        base_url=base_url,
        api_key_env=api_key_env,
        input_hooks=list(input_hooks or []),
        output_hooks=list(output_hooks or []),
        temperature=temperature,
    )
    return agent, runner


def create_openrouter_pair(
    *,
    name: str,
    instruction: str,
    app_name: str,
    plugins: list | None = None,
    temperature: float = 0.4,
) -> tuple[OpenAIAgent, OpenAIRunner]:
    """Create the assignment-locked Blue agent through OpenRouter."""
    return create_openai_pair(
        name=name,
        instruction=instruction,
        app_name=app_name,
        plugins=plugins,
        temperature=temperature,
        model=get_blue_runtime_model(),
        provider=PROVIDER_OPENROUTER,
        base_url=OPENROUTER_BASE_URL,
        api_key_env="OPENROUTER_API_KEY",
    )
