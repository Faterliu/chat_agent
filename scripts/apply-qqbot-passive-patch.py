#!/usr/bin/env python3
"""Patch the QQ Bot adapter so GROUP sends are passive replies.

Problem
-------
QQ rejects unsolicited ("proactive") group messages:

    HTTP 400 /v2/groups/<group_openid>/messages: 主动消息失败, 无权限

A group reply must be *passive* — it has to carry the inbound message's `msg_id`.
The adapter already attaches it whenever it is handed a `reply_to`
(`_send_text_to`, adapter.py:1414-1421), and it already caches the last inbound id
per chat in `self._last_msg_id` (`handle_message`, adapter.py:571-575), but nothing
ever populates `reply_to` for QQ: `gateway/run_turn.py:3181-3187` computes
`_progress_reply_to` only for FEISHU / MATTERMOST / Buzz / relay routes, and
`Platform.QQBOT` is absent from that list.

Deliberately narrow
-------------------
* Group chats only. `c2c` is left alone — QQ tolerates proactive DMs and that path is
  verified working. `guild` is left alone too.
* Does not touch `gateway/run_turn.py`. Editing the platform list there would widen
  `reply_to` to every outbound message of the turn (progress, interim, final), each of
  which counts against QQ's per-message passive-reply ceiling.
* Idempotent: re-running is a no-op.
* Syntax-checked before writing, and the anchor must appear exactly once.

Provenance: applied by explicit operator decision (option "打一行核心补丁"). This is a
core-file modification and therefore a documented deviation from AGENTS.md §24.5-24.6;
see documents/DEPLOYMENT_NOTES.md §11.17 / documents/TASK.md UNRESOLVED-1.
"""

from __future__ import annotations

import pathlib
import sys

ADAPTER = pathlib.Path("/var/lib/hermes/.hermes/hermes-agent/gateway/platforms/qqbot/adapter.py")

ANCHOR = """        if not content or not content.strip():
            return SendResult(success=True)

        chunks = self.truncate_message(self.format_message(content), self.MAX_MESSAGE_LENGTH)"""

PATCHED = """        if not content or not content.strip():
            return SendResult(success=True)

        # [LOCAL PATCH] QQ group messages must be PASSIVE replies carrying the inbound message
        # id, or QQ rejects them as unauthorised proactive messages
        # (HTTP 400 "主动消息失败, 无权限"). reply_to is never populated for QQBOT upstream
        # (gateway/run_turn.py computes _progress_reply_to only for Feishu/Mattermost/Buzz/relay),
        # but the last inbound id per chat is already cached by handle_message(). Groups only:
        # proactive c2c DMs are accepted by QQ, so that path is deliberately untouched.
        if reply_to is None and self._guess_chat_type(chat_id) == "group":
            reply_to = self._last_msg_id.get(chat_id)

        chunks = self.truncate_message(self.format_message(content), self.MAX_MESSAGE_LENGTH)"""

MARKER = "[LOCAL PATCH] QQ group messages must be PASSIVE"


def main() -> int:
    src = ADAPTER.read_text(encoding="utf-8")

    if MARKER in src:
        print("[patch] already applied — nothing to do")
        return 0

    if src.count(ANCHOR) != 1:
        print(f"[patch] anchor matched {src.count(ANCHOR)} times, expected exactly 1 — aborting")
        return 1

    patched = src.replace(ANCHOR, PATCHED, 1)

    try:
        compile(patched, str(ADAPTER), "exec")
    except SyntaxError as exc:
        print(f"[patch] refusing to write: patched source does not compile: {exc}")
        return 2

    backup = ADAPTER.with_suffix(".py.orig-qqbot-passive")
    if not backup.exists():
        backup.write_text(src, encoding="utf-8")
        print(f"[patch] original preserved at {backup.name}")

    ADAPTER.write_text(patched, encoding="utf-8")

    # verify by re-reading what landed on disk
    written = ADAPTER.read_text(encoding="utf-8")
    if MARKER not in written:
        print("[patch] VERIFY FAILED — marker absent after write")
        return 3
    compile(written, str(ADAPTER), "exec")

    print("[patch] applied to gateway/platforms/qqbot/adapter.py")
    print("[patch]   scope: group chats only; c2c and guild unchanged")
    print("[patch]   effect: group sends carry the cached inbound msg_id as a passive reply")
    print("[patch]   syntax: verified after write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
