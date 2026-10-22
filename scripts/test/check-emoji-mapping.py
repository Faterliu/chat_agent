#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产配置下核对 emoji → 表情包 映射（第二批 9 条追加后共 15 条）。

只读：调用真实 `gateway.emoji_stickers.prepare()`，不发消息、不连平台。
运行（服务器上，hermes 用户）：
    HERMES_HOME=/var/lib/hermes/.hermes \
    /var/lib/hermes/.hermes/hermes-agent/venv/bin/python /tmp/check-emoji-mapping.py
"""

import json
import os
import sys
from pathlib import Path

SRC = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
sys.path.insert(0, SRC)

from gateway import emoji_stickers  # noqa: E402

# (输入, 平台, 期望文本, 期望 id 列表)
CASES = [
    ("气死了\U0001F624 不想干了", "qqbot", "气死了 不想干了", ["doro_4"]),
    ("今天还行\U0001F60A", "qqbot", "今天还行", ["doro_5"]),
    ("困死了\U0001F62A", "qqbot", "困死了", ["doro_7"]),
    ("你气我\U0001F621", "qqbot", "你气我", ["doro_8"]),
    ("真是\U0001F620", "qqbot", "真是", ["doro_8"]),
    ("这个怎么说\U0001F914", "qqbot", "这个怎么说", ["doro_10"]),
    ("真的假的\U0001F928", "qqbot", "真的假的", ["doro_10"]),
    ("抱一下\U0001F917", "qqbot", "抱一下", ["doro_12"]),
    ("终于松口气\U0001F60C", "qqbot", "终于松口气", ["doro_11"]),
    ("好久不见\U0001F979", "qqbot", "好久不见", ["doro_13"]),
    ("笑死\U0001F604", "qqbot", "笑死", ["doro_12"]),
    # 老映射不能丢
    ("今天好累\U0001F62D", "qqbot", "今天好累", ["doro_3"]),
    ("我厉害吧\U0001F60E", "qqbot", "我厉害吧", ["doro_2"]),
    ("不是这样\U0001F644", "qqbot", "不是这样", ["doro_6"]),
    ("看戏\U0001F440", "qqbot", "看戏", ["doro_9"]),
    ("求你了\U0001F97A", "qqbot", "求你了", ["doro_14"]),
    # 多个已映射 emoji：只补一张，取映射表里靠前的（😪 在 😡 之前）
    ("又困又气\U0001F62A\U0001F621", "qqbot", "又困又气", ["doro_7"]),
    # 未映射 emoji 原样保留
    ("好吃\U0001F44D\U0001F602", "qqbot", "好吃\U0001F44D\U0001F602", []),
    # 长回复 / 多行不动
    ("第一行\U0001F624\n第二行\n第三行\n第四行", "qqbot",
     "第一行\U0001F624\n第二行\n第三行\n第四行", []),
    # 微信不生效
    ("气死了\U0001F624", "weixin", "气死了\U0001F624", []),
    # 纯 emoji 不发空消息
    ("\U0001F624", "qqbot", "\U0001F624", []),
    # 代码块不动
    ("看这段\n```\nprint('\U0001F624')\n```", "qqbot",
     "看这段\n```\nprint('\U0001F624')\n```", []),
]


def main() -> int:
    cfg = emoji_stickers._config()
    mapping = dict(cfg.get("mapping") or {})
    failures: list[str] = []

    print("enabled:", cfg.get("enabled"), "platforms:", cfg.get("platforms"),
          "max_per_turn:", cfg.get("max_per_turn"), "cooldown:", cfg.get("cooldown_seconds"))
    print("mapping:", len(mapping), "entries")
    for k, v in mapping.items():
        print("  U+%04X %s -> %s" % (ord(k[0]) if k else 0, k, v))
    for k in mapping:
        if len(k) != 1:
            failures.append(f"key not single codepoint: {k!r}")

    manifest = json.loads((HOME / "stickers" / "manifest.json").read_text(encoding="utf-8"))
    files = {s["id"]: s["file"] for s in manifest.get("stickers", [])}
    for sid in sorted(set(mapping.values())):
        if sid not in files:
            failures.append(f"{sid} not in manifest")
            continue
        p = HOME / "stickers" / files[sid]
        if not p.is_file():
            failures.append(f"{sid} file missing: {p}")
        elif not (1 <= p.stat().st_size <= 2 * 1024 * 1024):
            failures.append(f"{sid} size out of range: {p.stat().st_size}")
    print("mapped sticker ids:", sorted(set(mapping.values())))

    for text, platform, want_text, want_ids in CASES:
        got_text, got_ids = emoji_stickers.prepare(text, platform)
        ok = (got_text == want_text and list(got_ids) == list(want_ids))
        tag = "PASS" if ok else "FAIL"
        print(f"{tag} [{platform}] {text!r} -> {got_text!r} {list(got_ids)}")
        if not ok:
            failures.append(f"{text!r}: want {want_text!r} {want_ids}, got {got_text!r} {list(got_ids)}")

    print()
    if failures:
        print("FAILURES:", len(failures))
        for f in failures:
            print(" -", f)
        return 1
    print(f"ALL PASS ({len(CASES)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
