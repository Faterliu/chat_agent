#!/usr/bin/env python3
"""Phase 7 — move QQ onboarding credentials into .env without ever exposing them.

Reads /var/lib/hermes/qq-onboard-result.json (mode 600) and upserts the three keys the
official wizard would have written. Prints only key names and yes/no, never a value.

Deliberately does NOT write QQ_ALLOWED_USERS: the allowlist lives in config.yaml under
platforms.qqbot.extra so there is exactly one authoritative source (the adapter reads
extra.allow_from first and the env var only seeds it when absent).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys

HERMES_HOME = pathlib.Path("/var/lib/hermes/.hermes")
SRC = pathlib.Path("/var/lib/hermes/qq-onboard-result.json")
ENV = HERMES_HOME / ".env"


def upsert(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(lambda _m: line, text, count=1)
    if not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def main() -> int:
    if not SRC.exists():
        print(f"[apply] {SRC} not found")
        return 1

    creds = json.loads(SRC.read_text(encoding="utf-8"))
    app_id = str(creds.get("app_id") or "").strip()
    secret = str(creds.get("client_secret") or "").strip()

    if not app_id or not secret:
        print("[apply] app_id or client_secret missing — refusing to write")
        return 1

    text = ENV.read_text(encoding="utf-8")
    text = upsert(text, "QQ_APP_ID", app_id)
    text = upsert(text, "QQ_CLIENT_SECRET", secret)
    text = upsert(text, "QQ_ALLOW_ALL_USERS", "false")
    ENV.write_text(text, encoding="utf-8")
    os.chmod(ENV, 0o600)

    current = ENV.read_text(encoding="utf-8").splitlines()
    for key in ("QQ_APP_ID", "QQ_CLIENT_SECRET", "QQ_ALLOW_ALL_USERS"):
        hit = [l for l in current if l.startswith(key + "=") and l.split("=", 1)[1].strip()]
        print(f"[apply] {key:<20} {'set' if hit else 'MISSING'}")

    print(f"[apply] app_id (non-secret) starts with {app_id[:4]}…, length {len(app_id)}")
    print(f"[apply] client_secret length {len(secret)} (value never printed)")
    print(f"[apply] .env mode {oct(ENV.stat().st_mode & 0o777)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
