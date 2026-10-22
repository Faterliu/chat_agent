"""DeepSeek Search API provider — search only, one direct request per search.

Env: ``DEEPSEEK_SEARCH_API_KEY`` (required) and optional
``DEEPSEEK_SEARCH_API_BASE`` (default ``https://api.deepseek.com/v1/tools``).
``/search`` is POSTed with ``{query, count, need_content: false}``; the response
``results[]`` carries ``title`` / ``url`` / ``summary`` (plus ``site_name``,
``date``, ``rerank_score``, which this provider ignores).

Search only: the companion ``/fetch`` endpoint is intentionally not wired up. Enable
the ``search`` toolset (not ``web``) so ``web_extract`` stays unavailable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from plugins.web._common import (
    SEARCH_LIMIT_CAP, BaseWebSearchProvider, provider_env, search_fail, search_ok, setup_schema, title_hit,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.deepseek.com/v1/tools"
_SUMMARY_CHARS = 1500
_TIMEOUT = 30


class DeepSeekSearchProvider(BaseWebSearchProvider):
    """Search-only provider over the DeepSeek Search API."""

    NAME = "deepseek"
    DISPLAY_NAME = "DeepSeek Search"
    KEY_ENV = "DEEPSEEK_SEARCH_API_KEY"

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        api_key = provider_env(self.KEY_ENV)
        if not api_key:
            return search_fail(
                f"{self.KEY_ENV} is not set. Add it to the restricted .env to enable DeepSeek search."
            )
        base = (provider_env("DEEPSEEK_SEARCH_API_BASE") or _DEFAULT_BASE).rstrip("/")
        try:
            count = max(1, min(int(limit or 5), SEARCH_LIMIT_CAP))
        except (TypeError, ValueError):
            count = 5
        payload = {"query": query, "count": count, "need_content": False}
        try:
            response = httpx.post(
                f"{base}/search",
                json=payload,
                timeout=_TIMEOUT,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            logger.warning("DeepSeek search HTTP error: %s", code)
            if code == 401:
                return search_fail("DeepSeek search rejected the credential (HTTP 401).")
            return search_fail(f"DeepSeek search returned HTTP {code}")
        except httpx.RequestError as exc:
            logger.warning("DeepSeek search request error: %s", exc)
            return search_fail(f"Could not reach DeepSeek search: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek search response parse error: %s", exc)
            return search_fail("Could not parse DeepSeek search response as JSON")

        raw = data.get("results") or []
        rows: List[Dict[str, Any]] = []
        for i, item in enumerate(raw[:count]):
            summary = item.get("summary") or item.get("snippet") or ""
            rows.append(
                title_hit(
                    str(item.get("title", "")),
                    str(item.get("url", "")),
                    str(summary)[:_SUMMARY_CHARS],
                    i + 1,
                )
            )
        logger.info("DeepSeek search: %d results (limit %d)", len(rows), count)
        return search_ok(rows)

    def get_setup_schema(self) -> Dict[str, Any]:
        return setup_schema(
            "DeepSeek Search",
            "paid",
            "Official DeepSeek Search API — one direct request per search.",
            "DEEPSEEK_SEARCH_API_KEY",
            "DeepSeek API key",
            "https://platform.deepseek.com/api_keys",
        )
