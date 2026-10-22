#!/usr/bin/env python3
"""修复 send_final_ledgered 的挂点：补回被顶掉的 delivery_adapter 赋值，并插入补图调用。

首版部署脚本的锚点把 `delivery_adapter = self._final_delivery_adapter(event.source)` 一并替换
掉了（日志里 skipped 的 deliver 块也因此没插入）。本脚本按精确片段修复，幂等。
"""

from pathlib import Path

BASE = Path("/var/lib/hermes/.hermes/hermes-agent/gateway/platforms/base.py")

HEAD_BLOCK = (
    "        # [LOCAL PATCH] 强情绪 emoji → 表情包：先把可映射的 emoji 摘出正文，等文字发完再补一张图。\n"
    "        _emoji_sticker_ids: list = []\n"
    "        if not is_ephemeral_response:\n"
    "            try:\n"
    "                from gateway import emoji_stickers as _emoji_stickers\n"
    "\n"
    "                text_content, _emoji_sticker_ids = _emoji_stickers.prepare(text_content, self.platform)\n"
    "            except Exception:\n"
    "                _emoji_sticker_ids = []\n"
)

TAIL_ANCHOR = (
    "        if obligation_id is not None:\n"
    "            await self._finalize_delivery_obligation(obligation_id, result, event, delivery_adapter)\n"
    "        return result, delivery_adapter\n"
)

TAIL_BLOCK = (
    "        if obligation_id is not None:\n"
    "            await self._finalize_delivery_obligation(obligation_id, result, event, delivery_adapter)\n"
    "        if _emoji_sticker_ids:\n"
    "            try:\n"
    "                from gateway import emoji_stickers as _emoji_stickers\n"
    "\n"
    "                await _emoji_stickers.deliver(\n"
    "                    delivery_adapter, event, _emoji_sticker_ids, metadata, reply_to=reply_to)\n"
    "            except Exception:\n"
    "                logger.warning(\"[%s] emoji sticker delivery failed\", delivery_adapter.name, exc_info=True)\n"
    "        return result, delivery_adapter\n"
)

text = BASE.read_text(encoding="utf-8")

if HEAD_BLOCK not in text:
    raise SystemExit("ABORT: patch head block not found — 先跑 apply-emoji-stickers.py")

assign = "        delivery_adapter = self._final_delivery_adapter(event.source)\n"
if assign not in text:
    text = text.replace(HEAD_BLOCK, HEAD_BLOCK + assign, 1)
    print("restored: delivery_adapter assignment")
else:
    print("skip: delivery_adapter assignment present")

if "_emoji_stickers.deliver(" in text:
    print("skip: deliver() call present")
else:
    if text.count(TAIL_ANCHOR) != 1:
        raise SystemExit(f"ABORT: tail anchor count {text.count(TAIL_ANCHOR)}")
    text = text.replace(TAIL_ANCHOR, TAIL_BLOCK, 1)
    print("inserted: deliver() call")

BASE.write_text(text, encoding="utf-8")
compile(BASE.read_text(encoding="utf-8"), str(BASE), "exec")
print("compiled ok")
