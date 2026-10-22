#!/usr/bin/env python3
"""隔离验收「emoji → 表情包补图」：临时 HERMES_HOME、合成素材、假适配器，不连模型。

覆盖：正常摘除与映射、未映射 emoji 保留、长回复不处理、代码块不处理、平台过滤、开关关闭、
一条消息多个 emoji 只取一个、纯 emoji 不产生空消息、补图限频。
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
import types
from pathlib import Path

SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
TMP = Path(tempfile.mkdtemp(prefix="emoji-test-"))
os.environ["HERMES_HOME"] = str(TMP)
sys.path.insert(0, str(SRC))

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
MAPPING = {"😭": "doro_3", "😎": "doro_2", "🙄": "doro_6", "👀": "doro_9", "🥺": "doro_14"}

failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def write_config(enabled=True, delay_ms=0):
    (TMP / "config.yaml").write_text(
        "display:\n"
        "  emoji_stickers:\n"
        f"    enabled: {str(enabled).lower()}\n"
        "    platforms: [qqbot]\n"
        f"    mapping: {json.dumps(MAPPING, ensure_ascii=False)}\n"
        "    max_per_turn: 1\n"
        "    cooldown_seconds: 300\n"
        f"    delay_ms: {delay_ms}\n"
        "    max_lines: 3\n"
        "    max_chars: 200\n",
        encoding="utf-8")


def write_library():
    lib = TMP / "stickers" / "packs" / "doro"
    lib.mkdir(parents=True, exist_ok=True)
    items = []
    for sid in ("doro_2", "doro_3", "doro_6", "doro_9", "doro_14"):
        (lib / f"{sid}.png").write_bytes(PNG)
        items.append({"id": sid, "file": f"packs/doro/{sid}.png", "scene": "测试"})
    (TMP / "stickers" / "manifest.json").write_text(
        json.dumps({"version": 1, "stickers": items}, ensure_ascii=False), encoding="utf-8")


class FakeAdapter:
    def __init__(self):
        self.calls = []

    async def send_image_file(self, chat_id, image_path, caption=None, metadata=None, reply_to=None, **kw):
        self.calls.append({"chat_id": chat_id, "path": image_path, "reply_to": reply_to})
        return types.SimpleNamespace(success=True)


def main() -> int:
    write_library()
    write_config()

    from tools import sticker_tool
    from gateway import emoji_stickers

    text, ids = emoji_stickers.prepare("今天好累😭 早点睡吧👍", "qqbot")
    check("映射 emoji 被摘除", "😭" not in text and ids == ["doro_3"], f"{text!r} {ids}")
    check("未映射 emoji 保留", "👍" in text, text)
    check("多余空格被清理", "  " not in text, text)

    text, ids = emoji_stickers.prepare("行1\n行2\n行3\n行4 😭", "qqbot")
    check("长回复不处理", text.endswith("😭") and ids == [], f"{text!r} {ids}")

    fenced = "看这个：\n```\nprint('😭')\n```"
    text, ids = emoji_stickers.prepare(fenced, "qqbot")
    check("代码块不处理", ids == [] and "😭" in text, f"{ids}")

    text, ids = emoji_stickers.prepare("好累😭", "weixin")
    check("平台过滤（微信未开）", ids == [] and "😭" in text, f"{ids}")

    text, ids = emoji_stickers.prepare("又累又得意😭😎", "qqbot")
    check("多个映射只取一个", len(ids) == 1 and ids == ["doro_3"], f"{ids} {text!r}")

    text, ids = emoji_stickers.prepare("😭", "qqbot")
    check("纯 emoji 不产生空消息", ids == [] and text == "😭", f"{ids} {text!r}")

    write_config(enabled=False)
    text, ids = emoji_stickers.prepare("好累😭", "qqbot")
    check("开关关闭时不处理", ids == [] and "😭" in text, f"{ids}")
    write_config()

    adapter = FakeAdapter()
    event = types.SimpleNamespace(source=types.SimpleNamespace(chat_id="CHAT1"))
    sticker_tool._last_sent_at = 0.0
    asyncio.run(emoji_stickers.deliver(adapter, event, ["doro_3"], None, reply_to="MSG1"))
    check("补图发出一次", len(adapter.calls) == 1, str(adapter.calls))
    if adapter.calls:
        sent = Path(adapter.calls[0]["path"])
        check("补的是映射到的那张图", sent.name == "doro_3.png", sent.name)
    check("补图带上 reply_to", adapter.calls and adapter.calls[0]["reply_to"] == "MSG1", str(adapter.calls))

    asyncio.run(emoji_stickers.deliver(adapter, event, ["doro_2"], None, reply_to="MSG1"))
    check("冷却内不再补图", len(adapter.calls) == 1, str(adapter.calls))

    sticker_tool._last_sent_at = 0.0
    out = sticker_tool.send_sticker("doro_9")
    check("工具与补图共用冷却（工具仍可用）", "MEDIA:" in out, out)
    asyncio.run(emoji_stickers.deliver(adapter, event, ["doro_2"], None, reply_to="MSG1"))
    check("工具刚发过则补图跳过", len(adapter.calls) == 1, str(adapter.calls))

    print("\ntemp home:", TMP)
    print("failures:", len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
