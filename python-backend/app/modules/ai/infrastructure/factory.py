"""Chọn cài đặt AIClient theo AI_PROVIDER, tương ứng AiConfig.java."""

from __future__ import annotations

from app.modules.ai.domain.contracts import AIClient
from app.modules.ai.infrastructure.llm_client import LlmAIClient
from app.modules.ai.infrastructure.mock_client import MockAIClient
from app.shared.config.settings import Settings


def build_ai_client(settings: Settings) -> AIClient:
    provider = (settings.ai_provider or "mock").strip().lower()
    if provider == "mock":
        return MockAIClient()
    if provider == "llm":
        return LlmAIClient(
            base_url=settings.ai_base_url,
            model=settings.ai_model,
            api_key=settings.ai_api_key,
            timeout_seconds=settings.ai_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
        )
    raise RuntimeError(
        "AI_PROVIDER phải là 'mock' hoặc 'llm', đang là: " + str(settings.ai_provider)
    )
