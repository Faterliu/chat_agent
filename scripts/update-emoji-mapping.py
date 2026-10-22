#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""追加 emoji → 表情包 映射（幂等；按批次把新的追加到末尾）。

批次：
- 第二批（2026-10-22）：😤→doro_4、😊→doro_5、😪→doro_7、😡/😠→doro_8、
  🤔/🤨→doro_10、🤗→doro_12、😌→doro_11、🥹→doro_13。
- 第三批（2026-10-22）：😄→doro_12。

做法：只改 `display.emoji_stickers.mapping` 这一个键，ruamel 往返保留注释与顺序；
已有条目保持原顺序，新条目追加到末尾（映射表顺序＝一回合多 emoji 时的优先级）。
断言：mapping 之外的 emoji_stickers 子键、以及整份配置其他键都不许变。
"""

import copy
import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

SRC = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
sys.path.insert(0, SRC)

import yaml  # noqa: E402
from utils import atomic_roundtrip_yaml_update  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
CFG = HOME / "config.yaml"
MANIFEST = HOME / "stickers" / "manifest.json"

# (emoji, sticker_id, 说明)；emoji 用转义写，避免任何传输编码问题
NEW: list[tuple[str, str, str]] = [
    ("\U0001F624", "doro_4", "😤 气鼓鼓（轻锤一下）"),
    ("\U0001F60A", "doro_5", "😊 满足（弹吉他）"),
    ("\U0001F62A", "doro_7", "😪 困乏（趴桌敲键盘）"),
    ("\U0001F621", "doro_8", "😡 愤怒（举手要打）"),
    ("\U0001F620", "doro_8", "😠 生气（举手要打）"),
    ("\U0001F914", "doro_10", "🤔 思考（托腮苦想）"),
    ("\U0001F928", "doro_10", "🤨 怀疑（托腮苦想）"),
    ("\U0001F917", "doro_12", "🤗 抱抱（转圈撒娇）"),
    ("\U0001F60C", "doro_11", "😌 放松（骑小黄鸭晃悠）"),
    ("\U0001F979", "doro_13", "🥹 忍住眼泪（车站重逢）"),
    ("\U0001F604", "doro_12", "😄 笑（转圈撒娇）"),
]


def guard_keys(keys: list[str]) -> None:
    """子串匹配是 `emoji in line`：键不能是 ASCII 词字符，也不能互为子串。"""
    for k in keys:
        if len(k) != len(k.strip()) or not k:
            raise SystemExit(f"ABORT: bad key repr {k!r}")
        if all(ord(c) < 0x2000 for c in k):
            raise SystemExit(f"ABORT: key {k!r} is not an emoji")
    for a in keys:
        for b in keys:
            if a != b and a in b:
                raise SystemExit(f"ABORT: key {a!r} is a substring of {b!r} (U+%04X)" % ord(b[0]))


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    known = {s["id"] for s in manifest.get("stickers", [])}
    unknown = sorted({sid for _, sid, _ in NEW if sid not in known})
    if unknown:
        raise SystemExit(f"ABORT: sticker ids not in manifest: {unknown}")

    before_raw = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(before_raw.encode("utf-8")).hexdigest()
    before = yaml.safe_load(before_raw) or {}
    block = ((before.get("display") or {}).get("emoji_stickers")) or {}
    if not block:
        raise SystemExit("ABORT: display.emoji_stickers missing")
    current = dict(block.get("mapping") or {})
    print("current mapping:", len(current), "entries")

    target = dict(current)
    added = []
    for emoji, sid, label in NEW:
        if target.get(emoji) == sid:
            continue
        if emoji in target and target[emoji] != sid:
            print(f"note: overriding {label}: {target[emoji]} -> {sid}")
        target[emoji] = sid
        added.append(label)
    if not added:
        print("no-op: mapping already up to date")
        return 0

    guard_keys(list(target.keys()))

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"emoji-mapping-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    shutil.copy2(CFG, backup / "config.yaml")
    os.chmod(backup / "config.yaml", 0o600)
    (backup / "manifest.txt").write_text(
        "purpose: append emoji -> sticker mappings (2026-10-22)\n"
        f"original_sha256: {before_sha}\n"
        f"added: {', '.join(added)}\n"
        "change: display.emoji_stickers.mapping only\n"
        "rollback: restore config.yaml into HERMES_HOME (no restart needed for this key)\n",
        encoding="utf-8")
    os.chmod(backup / "manifest.txt", 0o600)

    new_block = copy.deepcopy(block)
    new_block["mapping"] = target
    atomic_roundtrip_yaml_update(CFG, "display.emoji_stickers", copy.deepcopy(new_block))

    after_raw = CFG.read_text(encoding="utf-8")
    after = yaml.safe_load(after_raw) or {}
    got_block = ((after.get("display") or {}).get("emoji_stickers")) or {}
    if dict(got_block.get("mapping") or {}) != target:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: mapping round-trip mismatch, restored backup")
        return 3

    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a["display"]["emoji_stickers"].pop("mapping", None)
    b["display"]["emoji_stickers"].pop("mapping", None)
    if a != b:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: collateral config change outside mapping, restored backup")
        return 4

    print("backup:", backup)
    print("added:", len(added))
    for label in added:
        print("  +", label)
    print("before_sha256:", before_sha)
    print("after_sha256:", hashlib.sha256(after_raw.encode("utf-8")).hexdigest())
    print("mapping entries:", len(target))
    print("mode:", oct(os.stat(CFG).st_mode & 0o777))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
