"""Offline tests for the DeepSeek search provider — mocked HTTP, no network.

Run: venv/bin/python /tmp/test_deepseek_provider.py [--real]
The mock is installed on a private shim, never on the shared httpx module, so the
--real smoke test always uses the real transport.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

import httpx  # noqa: E402

from plugins.web.deepseek import provider as mod  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + name + ((" :: " + detail) if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


class Shim:
    """Private stand-in for the ``httpx`` module inside the provider module."""

    HTTPStatusError = httpx.HTTPStatusError
    RequestError = httpx.RequestError

    def __init__(self) -> None:
        self.post = httpx.post


SHIM = Shim()
mod.httpx = SHIM  # type: ignore[assignment]

CAPTURED: dict = {}


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, url: str = "https://x/search"):
        self.status_code = status_code
        self._payload = payload or {}
        self.request = httpx.Request("POST", url)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=self.request, response=self)

    def json(self) -> dict:
        return self._payload


def install_fake(status: int, payload: dict | None, exc: Exception | None = None) -> None:
    def fake_post(url, json=None, timeout=None, headers=None):
        CAPTURED["url"] = url
        CAPTURED["json"] = json
        CAPTURED["headers"] = dict(headers or {})
        if exc is not None:
            raise exc
        return FakeResponse(status, payload, url)

    SHIM.post = fake_post


def main() -> int:
    os.environ["DEEPSEEK_SEARCH_API_KEY"] = "test-key"
    os.environ.pop("DEEPSEEK_SEARCH_API_BASE", None)
    provider = mod.DeepSeekSearchProvider()

    # 1) happy path mapping
    install_fake(200, {"results": [
        {"title": "T1", "url": "https://a/1", "summary": "S1", "site_name": "x", "date": None},
        {"title": "T2", "url": "https://a/2", "snippet": "S2"},
    ]})
    out = provider.search("hello world", limit=2)
    check("happy: success", out.get("success") is True, json.dumps(out, ensure_ascii=False)[:200])
    rows = (out.get("data") or {}).get("web") or []
    check("happy: two rows", len(rows) == 2, str(len(rows)))
    check("happy: row shape", bool(rows) and set(rows[0]) == {"title", "url", "description", "position"}, str(rows[:1]))
    check("happy: summary mapped", bool(rows) and rows[0]["description"] == "S1")
    check("happy: snippet fallback", len(rows) > 1 and rows[1]["description"] == "S2")
    check("happy: positions 1-based", [r["position"] for r in rows] == [1, 2], str([r["position"] for r in rows]))
    check("happy: endpoint", CAPTURED["url"].endswith("/v1/tools/search"), CAPTURED["url"])
    check("happy: payload", CAPTURED["json"] == {"query": "hello world", "count": 2, "need_content": False}, str(CAPTURED["json"]))
    check("happy: bearer auth", CAPTURED["headers"].get("Authorization") == "Bearer test-key")
    check("happy: no key in payload", "test-key" not in json.dumps(CAPTURED["json"]))

    # 2) limit clamping
    install_fake(200, {"results": []})
    provider.search("clamp", limit=999)
    check("clamp: count capped at 20", CAPTURED["json"]["count"] == 20, str(CAPTURED["json"]["count"]))

    # 3) empty results are success
    out = provider.search("nothing", limit=3)
    check("empty: success", out.get("success") is True and out["data"]["web"] == [])

    # 4) HTTP errors
    install_fake(500, {})
    out = provider.search("boom", limit=3)
    check("http500: failure", out.get("success") is False and "500" in out.get("error", ""), str(out))

    install_fake(401, {})
    out = provider.search("auth", limit=3)
    check("http401: credential wording", out.get("success") is False and "credential" in out.get("error", ""), str(out))

    # 5) transport error
    install_fake(0, None, exc=httpx.ConnectError("no route"))
    out = provider.search("offline", limit=3)
    check("transport: failure", out.get("success") is False and "Could not reach" in out.get("error", ""), str(out))

    # 6) key/base resolve from the restricted .env
    os.environ.pop("DEEPSEEK_SEARCH_API_KEY", None)
    check("env wiring: key readable from .env", bool(mod.provider_env("DEEPSEEK_SEARCH_API_KEY")))
    check("env wiring: base readable from .env",
          mod.provider_env("DEEPSEEK_SEARCH_API_BASE") == "https://api.deepseek.com/v1/tools",
          str(mod.provider_env("DEEPSEEK_SEARCH_API_BASE")))
    os.environ["DEEPSEEK_SEARCH_API_KEY"] = "test-key"

    # 7) missing key
    original_env = mod.provider_env
    mod.provider_env = lambda name: "" if name == "DEEPSEEK_SEARCH_API_KEY" else original_env(name)
    out = provider.search("no key", limit=3)
    mod.provider_env = original_env
    check("missing key: failure", out.get("success") is False and "not set" in out.get("error", ""), str(out))

    # 8) capability flags
    check("extract disabled", provider.supports_extract() is False)
    check("search enabled", provider.supports_search() is True)

    print()
    print("OFFLINE RESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAILED -> {FAILS}")

    if "--real" in sys.argv:
        print()
        print("=== REAL API SMOKE (real httpx transport) ===")
        mod.httpx = httpx  # type: ignore[assignment]
        for k in ("DEEPSEEK_SEARCH_API_KEY", "DEEPSEEK_SEARCH_API_BASE"):
            os.environ.pop(k, None)
        out = provider.search("DeepSeek API pricing", limit=3)
        ok = out.get("success") is True and len(out["data"]["web"]) > 0
        print("real:", "OK" if ok else "FAILED")
        for row in (out.get("data") or {}).get("web", [])[:3]:
            print("  -", row["position"], row["title"][:60], "|", row["url"][:60])
            print("    ", row["description"][:90].replace("\n", " "))
        if not ok:
            print("  error:", out.get("error"))
            FAILS.append("real api")

    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
