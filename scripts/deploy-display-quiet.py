#!/usr/bin/env python3
"""Silence gateway chat "receipts" (busy ack, long-running heartbeat, interim chatter,
tool-progress bubbles, background-completion notices) for QQ/WeChat.

Only ``display.*`` changes; CLI display is left alone. Round-trips YAML with the
project helper, backs up first, asserts nothing outside ``display`` moved, keeps 0600.

Usage: HERMES_HOME=/var/lib/hermes/.hermes venv/bin/python deploy-display-quiet.py
"""
import copy
import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

SRC_ROOT = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
sys.path.insert(0, SRC_ROOT)

import yaml  # noqa: E402
from ruamel.yaml.scalarstring import DoubleQuotedScalarString  # noqa: E402
from utils import atomic_roundtrip_yaml_update  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
CFG = HOME / "config.yaml"

CHANGES = [
    ("display.busy_ack_detail", False),
    ("display.busy_ack_enabled", False),
    ("display.long_running_notifications", False),
    ("display.interim_assistant_messages", False),
    ("display.background_process_notifications", DoubleQuotedScalarString("off")),
    ("display.platforms.weixin.tool_progress", False),
]


def _lookup(doc, path):
    node = doc
    for part in path.split(".")[1:]:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def main() -> int:
    raw_before = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(raw_before.encode("utf-8")).hexdigest()
    before = yaml.safe_load(raw_before) or {}
    current = before.get("display") or {}

    backup_dir = None
    if all(_lookup(current, path) == value for path, value in CHANGES):
        print("no-op: display already quiet")
    else:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = HOME / "backups" / f"display-quiet-{ts}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        os.chmod(backup_dir, 0o700)
        shutil.copy2(CFG, backup_dir / "config.yaml")
        os.chmod(backup_dir / "config.yaml", 0o600)
        manifest = backup_dir / "manifest.txt"
        manifest.write_text(
            "purpose: silence gateway chat receipts\n"
            f"original_sha256: {before_sha}\n"
            + "".join(f"change: {path} -> {value!r}\n" for path, value in CHANGES)
            + "rollback: cp config.yaml over HERMES_HOME/config.yaml, chmod 600, restart gateway\n",
            encoding="utf-8",
        )
        os.chmod(manifest, 0o600)
        for path, value in CHANGES:
            atomic_roundtrip_yaml_update(CFG, path, value)
        print("backup:", backup_dir)

    raw_after = CFG.read_text(encoding="utf-8")
    after = yaml.safe_load(raw_after) or {}
    got_display = after.get("display") or {}

    def restore() -> int:
        if backup_dir is not None:
            shutil.copy2(backup_dir / "config.yaml", CFG)
        return 3

    for path, value in CHANGES:
        if _lookup(got_display, path) != value:
            print(f"ERROR: {path} not applied; restoring")
            return restore()

    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a.pop("display", None)
    b.pop("display", None)
    if a != b:
        print("ERROR: collateral change outside display; restoring")
        return restore()

    from hermes_cli.config import load_config  # noqa: E402

    live = load_config().get("display") or {}
    print("before_sha256:", before_sha)
    print("after_sha256:", hashlib.sha256(raw_after.encode("utf-8")).hexdigest())
    print("mode:", oct(os.stat(CFG).st_mode & 0o777))
    for path, value in CHANGES:
        print(f"loader {path} = {_lookup(live, path)!r}")
    print("note: busy_ack_enabled is bridged to env at gateway start -> restart required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
