#!/usr/bin/env python3
"""Add ``auxiliary.vision`` (remote relay VLM) to the live Hermes config.

Uses the project's ``utils.atomic_roundtrip_yaml_update`` so comments, ordering,
quoting and indentation of the rest of config.yaml are preserved. Idempotent for
the exact target block; aborts on a different pre-existing ``auxiliary.vision``.
Backs the original up under ``HERMES_HOME/backups/vision-<ts>/`` (0600), asserts
that only the ``auxiliary`` key changed, then writes 0600 atomically.

Usage: HERMES_HOME=/var/lib/hermes/.hermes venv/bin/python deploy-vision.py
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

TARGET = {
    "provider": "custom",
    "model": "cn:deepseek-v4.1-flash",
    "base_url": "https://wb.yinxingye.space/v1",
    "key_env": "DEEPSEEK_API_KEY",
    "timeout": 60,
    "reasoning_effort": "none",
}

RUAMEL_VALUE = {
    "provider": "custom",
    "model": DoubleQuotedScalarString(TARGET["model"]),
    "base_url": DoubleQuotedScalarString(TARGET["base_url"]),
    "key_env": "DEEPSEEK_API_KEY",
    "timeout": 60,
    "reasoning_effort": "none",
}


def main() -> int:
    raw_before = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(raw_before.encode("utf-8")).hexdigest()
    before = yaml.safe_load(raw_before) or {}
    existing = (before.get("auxiliary") or {}).get("vision")
    if existing == TARGET:
        print("no-op: auxiliary.vision already set to target values")
        return 0
    if existing is not None:
        print("refusing: auxiliary.vision already exists with different values:")
        print(json.dumps(existing, ensure_ascii=False, indent=2))
        return 2

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = HOME / "backups" / f"vision-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    os.chmod(backup_dir, 0o700)
    shutil.copy2(CFG, backup_dir / "config.yaml")
    os.chmod(backup_dir / "config.yaml", 0o600)
    manifest = backup_dir / "manifest.txt"
    manifest.write_text(
        "purpose: enable auxiliary.vision via the wb relay (cn:deepseek-v4.1-flash)\n"
        f"original_sha256: {before_sha}\n"
        f"original_size: {len(raw_before.encode('utf-8'))}\n"
        "change: add auxiliary.vision {provider, model, base_url, key_env, timeout, reasoning_effort}\n"
        "rollback: cp config.yaml over HERMES_HOME/config.yaml, chmod 600, restart the gateway\n",
        encoding="utf-8",
    )
    os.chmod(manifest, 0o600)

    atomic_roundtrip_yaml_update(CFG, "auxiliary.vision", copy.deepcopy(RUAMEL_VALUE))

    raw_after = CFG.read_text(encoding="utf-8")
    after = yaml.safe_load(raw_after) or {}
    got = (after.get("auxiliary") or {}).get("vision")
    if got != TARGET:
        print("ERROR: round-trip mismatch, restoring backup")
        shutil.copy2(backup_dir / "config.yaml", CFG)
        print(json.dumps(got, ensure_ascii=False, indent=2))
        return 3

    # Nothing outside auxiliary may change (blank it out on both sides, compare whole docs).
    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a.pop("auxiliary", None)
    b.pop("auxiliary", None)
    if a != b:
        print("ERROR: collateral change in config.yaml, restoring backup")
        shutil.copy2(backup_dir / "config.yaml", CFG)
        return 4

    from hermes_cli.config import load_config  # noqa: E402

    live = (load_config().get("auxiliary") or {}).get("vision") or {}
    live_target = {key: live.get(key) for key in TARGET}
    print("backup:", backup_dir)
    print("config_before_chars:", len(raw_before), "after_chars:", len(raw_after))
    print("before_sha256:", before_sha)
    print("after_sha256:", hashlib.sha256(raw_after.encode("utf-8")).hexdigest())
    print("mode:", oct(os.stat(CFG).st_mode & 0o777))
    print("loader_sees_target:", live_target == TARGET)
    print("model.default:", load_config()["model"]["default"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
