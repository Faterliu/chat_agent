"""DeepSeek Search API plugin — bundled, auto-loaded."""
from __future__ import annotations

from plugins.web.deepseek.provider import DeepSeekSearchProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(DeepSeekSearchProvider())
