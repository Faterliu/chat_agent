#!/usr/bin/env python3
"""部署「强情绪 emoji → 表情包补图」：新模块 + 出口挂点 + 配置块。

改动：
1. 新增 `gateway/emoji_stickers.py`（本地源 `source/emoji_stickers.py`）；
2. 更新 `tools/sticker_tool.py`（导出 `try_acquire()`，与映射补图共用冷却）；
3. 改 `gateway/platforms/base.py` 的 `send_final_ledgered`：先把可映射 emoji 摘出正文，
   文字发送成功后补一张图；
4. `config.yaml` 增加 `display.emoji_stickers`（默认开、仅 qqbot、5 个映射、300 秒冷却）。

幂等：重复运行只补缺；备份 `HERMES_HOME/backups/emoji-stickers-<ts>/`。不重启网关。
"""

import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
CFG = HOME / "config.yaml"
PINNED = "f97608f178d1ffeca59860195ab7da295f7c8e5f"
HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(SRC))

ANCHOR_HEAD = (
    "        delivery_adapter = self._final_delivery_adapter(event.source)\n"
)
HEAD_INSERT = '''        # [LOCAL PATCH] 强情绪 emoji → 表情包：先把可映射的 emoji 摘出正文，等文字发完再补一张图。
        _emoji_sticker_ids: list = []
        if not is_ephemeral_response:
            try:
                from gateway import emoji_stickers as _emoji_stickers

                text_content, _emoji_sticker_ids = _emoji_stickers.prepare(text_content, self.platform)
            except Exception:
                _emoji_sticker_ids = []
        delivery_adapter = self._final_delivery_adapter(event.source)
'''

ANCHOR_TAIL = (
    "        if obligation_id is not None:\n"
    "            await self._finalize_delivery_obligation(obligation_id, result, event, delivery_adapter)\n"
    "        return result, delivery_adapter\n"
)
TAIL_INSERT = (
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

CONFIG_BLOCK = {
    "enabled": True,
    "platforms": ["qqbot"],
    "mapping": {"😭": "doro_3", "😎": "doro_2", "🙄": "doro_6", "👀": "doro_9", "🥺": "doro_14"},
    "max_per_turn": 1,
    "cooldown_seconds": 300,
    "delay_ms": 1200,
    "max_lines": 3,
    "max_chars": 200,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(path: Path, old: str, new: str, label: str, *, marker: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"  skip (already applied): {label}")
        return False
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ABORT: anchor for {label} appears {count} times in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  patched: {label}")
    return True


def main() -> int:
    import subprocess

    head = subprocess.run(["git", "-C", str(SRC), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != PINNED:
        raise SystemExit(f"ABORT: source HEAD {head} != pinned {PINNED}")

    for name in ("emoji_stickers.py", "sticker_tool.py"):
        src = HERE.parent / "source" / name
        if not src.is_file():
            raise SystemExit(f"ABORT: missing {src}")

    base_py = SRC / "gateway" / "platforms" / "base.py"
    target_tool = SRC / "tools" / "sticker_tool.py"
    target_mod = SRC / "gateway" / "emoji_stickers.py"

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"emoji-stickers-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    lines = ["purpose: emoji -> sticker mapping at the final-response funnel\n", f"source_head: {head}\n"]
    for name, path in (("base.py", base_py), ("sticker_tool.py", target_tool), ("config.yaml", CFG)):
        if path.is_file():
            shutil.copy2(path, backup / name)
            os.chmod(backup / name, 0o600)
            lines.append(f"{name}\tsha256={sha256(path)}\n")
    (backup / "manifest.txt").write_text("".join(lines), encoding="utf-8")
    os.chmod(backup / "manifest.txt", 0o600)
    print("backup:", backup)

    print("1) tools/sticker_tool.py + gateway/emoji_stickers.py")
    shutil.copy2(HERE.parent / "source" / "sticker_tool.py", target_tool)
    os.chmod(target_tool, 0o644)
    shutil.copy2(HERE.parent / "source" / "emoji_stickers.py", target_mod)
    os.chmod(target_mod, 0o644)

    print("2) base.py send_final_ledgered")
    replace_once(base_py, ANCHOR_HEAD, HEAD_INSERT, "prepare()", marker="_emoji_sticker_ids: list = []")
    replace_once(base_py, ANCHOR_TAIL, TAIL_INSERT, "deliver()", marker="_emoji_stickers.deliver(")

    print("3) config.yaml display.emoji_stickers")
    import yaml
    from utils import atomic_roundtrip_yaml_update

    before_raw = CFG.read_text(encoding="utf-8")
    before = yaml.safe_load(before_raw) or {}
    existing = ((before.get("display") or {}).get("emoji_stickers"))
    if isinstance(existing, dict) and existing.get("mapping") == CONFIG_BLOCK["mapping"]:
        print("  skip (already applied)")
    else:
        if existing is not None:
            raise SystemExit(f"ABORT: display.emoji_stickers already exists: {existing}")
        atomic_roundtrip_yaml_update(CFG, "display.emoji_stickers", json.loads(json.dumps(CONFIG_BLOCK)))
        after_raw = CFG.read_text(encoding="utf-8")
        after = yaml.safe_load(after_raw) or {}
        got = (after.get("display") or {}).get("emoji_stickers") or {}
        if got.get("mapping") != CONFIG_BLOCK["mapping"] or got.get("enabled") is not True:
            shutil.copy2(backup / "config.yaml", CFG)
            raise SystemExit(f"ABORT: config round-trip mismatch: {got}")
        a, b = json.loads(json.dumps(before, default=str)), json.loads(json.dumps(after, default=str))
        a["display"].pop("emoji_stickers", None)
        b["display"].pop("emoji_stickers", None)
        if a != b:
            shutil.copy2(backup / "config.yaml", CFG)
            raise SystemExit("ABORT: collateral config change, restored backup")
        print("  keys:", sorted(got))

    print("4) syntax check")
    for path in (target_tool, target_mod, base_py):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        print("  ok:", path.relative_to(SRC))

    print("done. restart with /var/lib/hermes/start-chat-agent.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
