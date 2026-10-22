#!/usr/bin/env python3
"""Flip ``display.persona_error_voice`` (云白-voice failure copy) with a backup.

Usage: HERMES_HOME=/var/lib/hermes/.hermes venv/bin/python deploy-error-voice.py [true|false]
"""
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
from utils import atomic_roundtrip_yaml_update  # noqa: E402

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
CFG = HOME / "config.yaml"
WANT = (sys.argv[1] if len(sys.argv) > 1 else "true").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    raw = CFG.read_text(encoding="utf-8")
    before = yaml.safe_load(raw) or {}
    current = (before.get("display") or {}).get("persona_error_voice")
    if current is WANT:
        print(f"no-op: display.persona_error_voice already {WANT}")
        return 0

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"error-voice-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    shutil.copy2(CFG, backup / "config.yaml")
    os.chmod(backup / "config.yaml", 0o600)
    (backup / "manifest.txt").write_text(
        "purpose: toggle display.persona_error_voice (云白 failure copy)\n"
        f"before: {current!r}\n"
        f"after: {WANT}\n"
        f"original_sha256: {hashlib.sha256(raw.encode('utf-8')).hexdigest()}\n"
        "rollback: cp config.yaml over HERMES_HOME/config.yaml, chmod 600, restart gateway\n",
        encoding="utf-8",
    )
    os.chmod(backup / "manifest.txt", 0o600)

    atomic_roundtrip_yaml_update(CFG, "display.persona_error_voice", bool(WANT))

    after = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    if (after.get("display") or {}).get("persona_error_voice") is not WANT:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: not applied; restored")
        return 3
    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a.pop("display", None)
    b.pop("display", None)
    if a != b:
        shutil.copy2(backup / "config.yaml", CFG)
        print("ERROR: collateral change; restored")
        return 4

    from hermes_cli.config import load_config  # noqa: E402

    print("backup:", backup)
    print("loader persona_error_voice:",
          (load_config().get("display") or {}).get("persona_error_voice"))
    print("sha256:", hashlib.sha256(CFG.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
