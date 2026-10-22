#!/usr/bin/env python3
"""给网关放行表情包目录的 MEDIA 投递。

背景：生产网关按默认安全策略拒绝 `/var/lib` 下的 MEDIA 路径（`_MEDIA_DELIVERY_DENIED_PREFIXES`
含 `/var/lib`），表情包位于 `/var/lib/hermes/.hermes/stickers/packs/`，因此工具调用成功、
图却被投递层丢掉。放行方式是运维白名单 `gateway.media_delivery_allow_dirs`——它优先于
denylist，且只覆盖素材目录本身。

只增加一个键，ruamel 往返保留注释与缩进，断言 gateway 下其他键不变。
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
ALLOW_DIR = "/var/lib/hermes/.hermes/stickers/packs"


def main() -> int:
    before_raw = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(before_raw.encode("utf-8")).hexdigest()
    before = yaml.safe_load(before_raw) or {}
    gateway = before.get("gateway") or {}
    existing = gateway.get("media_delivery_allow_dirs")

    if existing == [ALLOW_DIR]:
        print("no-op: already allowlisted")
        return 0
    if existing and existing != [ALLOW_DIR]:
        print("refusing: media_delivery_allow_dirs already set:", json.dumps(existing, ensure_ascii=False))
        return 2

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"media-allow-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    shutil.copy2(CFG, backup / "config.yaml")
    os.chmod(backup / "config.yaml", 0o600)
    (backup / "manifest.txt").write_text(
        "purpose: allow MEDIA delivery from the sticker library\n"
        f"original_sha256: {before_sha}\n"
        f"change: gateway.media_delivery_allow_dirs = [{ALLOW_DIR!r}]\n"
        "rollback: restore config.yaml (or delete the key), restart the gateway\n",
        encoding="utf-8")
    os.chmod(backup / "manifest.txt", 0o600)

    atomic_roundtrip_yaml_update(CFG, "gateway.media_delivery_allow_dirs", [ALLOW_DIR])

    after_raw = CFG.read_text(encoding="utf-8")
    after = yaml.safe_load(after_raw) or {}
    got = (after.get("gateway") or {}).get("media_delivery_allow_dirs")
    if got != [ALLOW_DIR]:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: round-trip mismatch, restored backup; got:", got)
        return 3

    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a["gateway"].pop("media_delivery_allow_dirs", None)
    b["gateway"].pop("media_delivery_allow_dirs", None)
    if a != b:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: collateral config change, restored backup")
        return 4

    print("backup:", backup)
    print("before_sha256:", before_sha)
    print("after_sha256:", hashlib.sha256(after_raw.encode("utf-8")).hexdigest())
    print("gateway.media_delivery_allow_dirs:", got)
    print("mode:", oct(os.stat(CFG).st_mode & 0o777))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
