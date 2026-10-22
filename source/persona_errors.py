"""云白 voice for user-facing gateway failure notices.

These are the messages a chat user sees when the model provider rate-limits,
rejects auth, drops the connection, times out, or the turn crashes. The stock
Hermes copy is operator-facing ("The AI model service is rate-limiting
requests…"); this module rewrites the same information in the bot persona's
voice while keeping it short and actionable.

Enabled with ``display.persona_error_voice: true``. When disabled (default) or
when config cannot be read, callers fall back to the stock wording, so the code
path stays reversible without a code revert.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# kinds: rate_limit, auth, policy, connection_interrupted, endpoint_unreachable,
#        connection_error, generic, failed_turn, timeout, no_model, storage
_COPY = {
    "rate_limit": "呜…模型那边现在排队排满了，我挤不进去 😣 缓一会儿再喊我，我马上到。",
    "rate_limit_window": "我这边模型额度被卡住了，大约 {window} 后才回血 ⏳ 到时候你喊我一声就行。",
    "auth": "我登录模型的口令过期了…这不是你的问题，得让管我的人重新登录一下，我才能继续说话。",
    "policy": "模型那边把这条请求拦下来了，不是我故意不答…你换个说法，或者让我换个模型试试？",
    "connection_interrupted": "刚聊到一半连接抖了一下就断了…你再说一遍，我接着刚才的讲。",
    "endpoint_unreachable": "我连不上自己的大脑了，模型服务好像没在跑…等会儿再试；要是一直这样，得让管我的人看看。",
    "connection_error": "我和模型服务突然失联了，连原因都没拿到…你再说一次，我重试给你看。",
    "generic": "模型服务一直不回我话，我有点没辙…稍后再试，或者让我换个模型？",
    "failed_turn": "呜，我刚刚脚滑了一下，这条没答完 😣 你再说一遍，我马上补上。",
    "timeout": "我走神太久被掐断了（{minutes} 分钟没动静）…你再说一遍，我这次抓紧。",
    "no_model": "我这边还没连上大脑，模型没登录…得让管我的人先登录一下，我才能开口。",
    "storage": "我这边存对话的柜子临时打不开了，这条先没往下走，免得把你的记录弄丢…等会儿再发一次。",
}

_KINDS = frozenset(_COPY)


def enabled() -> bool:
    """True when ``display.persona_error_voice`` is set for this profile."""
    try:
        from hermes_cli.config import cfg_get, load_config

        return bool(cfg_get(load_config(), "display", "persona_error_voice", default=False))
    except Exception:
        logger.debug("persona_errors: config read failed; using stock copy", exc_info=True)
        return False


def copy(kind: str, **fmt) -> str:
    """Persona copy for *kind*; falls back to generic wording for unknown kinds."""
    template = _COPY.get(kind) or _COPY["generic"]
    try:
        return template.format(**fmt) if fmt else template
    except (KeyError, IndexError, ValueError):
        return template


def rate_limit(seconds: int = 0, window: str = "") -> str:
    if seconds and seconds >= 120:
        return copy("rate_limit_window", window=window or f"{max(1, seconds // 60)} 分钟")
    return copy("rate_limit")


def provider(kind: str) -> str:
    return copy(kind if kind in _KINDS else "generic")


def failed_turn(status_code=None, hint: str = "") -> str:
    """Map an HTTP status / hint to persona copy: 429 → rate limit, 401 → auth, 400 → policy."""
    try:
        code = int(status_code) if status_code is not None else 0
    except (TypeError, ValueError):
        code = 0
    low = (hint or "").lower()
    if code == 429 or "rate-limit" in low or "rate limit" in low or "usage limit" in low:
        return copy("rate_limit")
    if code == 401 or "auth" in low or "sign in" in low or "login" in low:
        return copy("auth")
    if code == 400 or "rejected" in low or "policy" in low:
        return copy("policy")
    return copy("failed_turn")


def timeout(minutes: int) -> str:
    return copy("timeout", minutes=max(1, int(minutes or 1)))


def no_model() -> str:
    return copy("no_model")


def storage() -> str:
    return copy("storage")
