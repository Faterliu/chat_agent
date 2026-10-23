#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产配置下核对 QQ／微信共用的 emoji → 表情包映射。

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
    ("收到\U0001F44D\u2705", "qqbot", "收到\U0001F44D\u2705", []),
    # 长回复 / 多行不动
    ("第一行\U0001F624\n第二行\n第三行\n第四行", "qqbot",
     "第一行\U0001F624\n第二行\n第三行\n第四行", []),
    # 未开放平台仍不生效
    ("气死了\U0001F624", "cli", "气死了\U0001F624", []),
    # 纯 emoji 不发空消息
    ("\U0001F624", "qqbot", "\U0001F624", []),
    # 代码块不动
    ("看这段\n```\nprint('\U0001F624')\n```", "qqbot",
     "看这段\n```\nprint('\U0001F624')\n```", []),
]

# 微信与 QQ 使用同一套映射、优先级和短回复规则。
CASES += [(text, "weixin", want_text, want_ids)
          for text, platform, want_text, want_ids in list(CASES) if platform == "qqbot"]


def main() -> int:
    cfg = emoji_stickers._config()
    mapping = dict(cfg.get("mapping") or {})
    failures: list[str] = []

    print("enabled:", cfg.get("enabled"), "platforms:", cfg.get("platforms"),
          "max_per_turn:", cfg.get("max_per_turn"), "cooldown:", cfg.get("cooldown_seconds"))
    print("mapping:", len(mapping), "entries")
    for k, v in mapping.items():
        print("  U+%04X %s -> %s" % (ord(k[0]) if k else 0, k, v))
    # 完整 emoji 可以由 VS16 / ZWJ 等多个码点组成，不能按 len(key)==1 拒绝。
    # 配置写入端负责完整序列校验；这里查残缺边界、键间包含及实际摘除结果。
    for key in mapping:
        if not key or key[0] in "\u200d\ufe0e\ufe0f" or key.endswith("\u200d"):
            failures.append(f"incomplete emoji key: {key!r}")
        for other in mapping:
            if key != other and key in other:
                failures.append(f"emoji key is a substring of another: {key!r} in {other!r}")
    # 每个线上键都要在双平台正确摘除，含组合 emoji，且不能残留连接符／变体符。
    mapping_cases = [("映射核对" + key, platform, "映射核对", [sid])
                     for key, sid in mapping.items() for platform in ("qqbot", "weixin")]
    cases = CASES + mapping_cases

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

    for text, platform, want_text, want_ids in cases:
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
    print(f"ALL PASS ({len(cases)} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
