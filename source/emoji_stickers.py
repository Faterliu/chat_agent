"""把强情绪 emoji 从回复里摘出来，改在文字发送之后单独补一张表情包。

用户口径（2026-10-22）：没映射的 emoji 原样保留；有映射的从正文删掉，等文字回复发送完成后
再单独发一张图——比"把 emoji 换成图嵌在句子里"更像真人打字。

挂点：`gateway/platforms/base.py` 的 `send_final_ledgered`（所有最终文本的唯一出口）。
本模块只做两件事：
1. `prepare()`：判定要不要摘、摘哪几个、清理残留空白；
2. `deliver()`：文字发出去之后再发图，限频、尽力而为、失败只写日志。

约束：
- 只在短回复里生效（默认 ≤3 行、≤200 字），长解释/教程/严肃话题不动 emoji；
- 代码块里的 emoji 不摘；
- 一回合最多一张（`max_per_turn`），且与 `send_sticker` 工具共用同一个冷却计时器，
  工具刚发过就整轮跳过（工具优先）；
- 图片路径只从 `HERMES_HOME/stickers/manifest.json` 取，不认任意路径。
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("gateway.emoji_stickers")

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "platforms": ["qqbot"],
    "mapping": {
        "😭": "doro_3",
        "😎": "doro_2",
        "🙄": "doro_6",
        "👀": "doro_9",
        "🥺": "doro_14",
    },
    "max_per_turn": 1,
    "cooldown_seconds": 300,
    "delay_ms": 1200,
    "max_lines": 3,
    "max_chars": 200,
}

_WS_RE = re.compile(r"[ \t]{2,}")


def _config() -> dict[str, Any]:
    """读 display.emoji_stickers（配置按文件签名缓存，热改生效）。任何异常都返回默认值。"""
    cfg: dict[str, Any] = dict(DEFAULTS)
    try:
        from hermes_cli.config import load_config_readonly

        live = ((load_config_readonly() or {}).get("display") or {}).get("emoji_stickers")
        if isinstance(live, dict):
            for key, value in live.items():
                if key == "mapping" and isinstance(value, dict):
                    cfg["mapping"] = {str(k): str(v) for k, v in value.items() if str(v).strip()}
                elif key in cfg:
                    cfg[key] = value
    except Exception:  # noqa: BLE001 - 配置读不到就当关闭
        logger.debug("emoji_stickers: config load failed", exc_info=True)
        return dict(DEFAULTS, enabled=False)
    if not isinstance(cfg.get("mapping"), dict):
        cfg["mapping"] = dict(DEFAULTS["mapping"])
    return cfg


def _platform_name(platform: Any) -> str:
    raw = getattr(platform, "value", platform)
    text = str(raw or "").strip().lower()
    return text.rsplit(".", 1)[-1]


def _strip_marked(text: str, mapping: dict[str, str]) -> tuple[str, list[str]]:
    """摘掉映射内的 emoji（跳过代码围栏），返回清理后的文本与去重后的表情包 id。"""
    out_lines: list[str] = []
    found: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        line_found = False
        for emoji in mapping:
            if emoji in line:
                line = line.replace(emoji, "")
                found.append(mapping[emoji])
                line_found = True
        if line_found:
            line = _WS_RE.sub(" ", line).strip()
            # 删掉表情后只剩标点的行直接丢弃，避免留下孤零零的"。"或"~"
            if line and not re.search(r"[\w\u4e00-\u9fff]", line):
                line = ""
        out_lines.append(line)

    cleaned = "\n".join(out_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, found


def prepare(text: str, platform: Any) -> tuple[str, list[str]]:
    """按配置决定是否摘 emoji；返回 (要发送的文本, 待补发的表情包 id 列表)。"""
    if not text or not text.strip():
        return text, []
    cfg = _config()
    if not cfg.get("enabled"):
        return text, []
    if _platform_name(platform) not in {str(p).lower() for p in (cfg.get("platforms") or [])}:
        return text, []
    if len(text) > int(cfg.get("max_chars") or 0):
        return text, []
    if len(text.splitlines()) > int(cfg.get("max_lines") or 0):
        return text, []
    if "```" in text:
        return text, []  # 代码块场景一律不动

    cleaned, found = _strip_marked(text, dict(cfg.get("mapping") or {}))
    if not found:
        return text, []
    keep = max(0, int(cfg.get("max_per_turn") or 0))
    deduped = list(dict.fromkeys(found))[:keep]
    if not deduped:
        return text, []
    if not cleaned.strip():
        # 整条只剩一个 emoji：把原文还回去，宁可保留 emoji 也不发空消息
        return text, []
    return cleaned, deduped


def _resolve_paths(ids: Iterable[str]) -> list[Path]:
    try:
        from tools.sticker_tool import load_manifest

        library = {item["id"]: item["path"] for item in load_manifest()}
    except Exception:  # noqa: BLE001 - 素材库读不到就当没有
        logger.warning("emoji_stickers: sticker library unavailable", exc_info=True)
        return []
    return [library[i] for i in ids if i in library]


async def deliver(adapter: Any, event: Any, ids: list[str], metadata: Any, *, reply_to: str | None = None) -> None:
    """文字已经发出后的补图：限频 → 停顿 → 发一张 → 失败只记录。"""
    if not ids:
        return
    cfg = _config()
    paths = _resolve_paths(ids)
    if not paths:
        logger.info("emoji_stickers: no sticker to send (ids=%s)", ",".join(ids))
        return
    try:
        from tools.sticker_tool import try_acquire
    except Exception:  # noqa: BLE001
        return
    cooldown = float(cfg.get("cooldown_seconds") or 0)
    if not try_acquire(cooldown):
        logger.info("emoji_stickers: skipped by cooldown (%.0fs)", cooldown)
        return
    delay = max(0.0, float(cfg.get("delay_ms") or 0) / 1000.0)
    if delay:
        await asyncio.sleep(delay)
    chat_id = getattr(getattr(event, "source", None), "chat_id", None)
    try:
        result = await adapter.send_image_file(
            chat_id=chat_id, image_path=str(paths[0]), metadata=metadata, reply_to=reply_to)
        ok = bool(getattr(result, "success", False))
        logger.info("emoji_stickers: sent %s ok=%s", paths[0].name, ok)
    except Exception:  # noqa: BLE001 - 补图失败不影响已发出的文字
        logger.warning("emoji_stickers: send failed for %s", paths[0], exc_info=True)
