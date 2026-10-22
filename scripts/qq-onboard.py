#!/usr/bin/env python3
"""Phase 7 runner — execute the QQ Bot QR onboarding without the interactive wizard.

Why this exists: `hermes gateway setup` is a TTY-only arrow-key wizard, but the
underlying `qr_register()` is a plain function. This runner calls it directly so the
flow can be driven over SSH.

Secret handling: `qr_register()` returns {"app_id", "client_secret", "user_openid"}.
The client_secret is a real credential, so this runner NEVER prints the returned dict.
It writes the dict to a mode-600 JSON file and prints only the non-secret identifiers.
The flow's own stdout (the connect URL, the App ID, the scanner's OpenID) is left intact
because that is what the operator needs to see.

Usage (as the hermes user):
    cd /var/lib/hermes/.hermes/hermes-agent
    PYTHONPATH=. venv/bin/python -u /var/lib/hermes/qq-onboard.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

RESULT = pathlib.Path("/var/lib/hermes/qq-onboard-result.json")


def main() -> int:
    try:
        from gateway.platforms.qqbot import qr_register
    except Exception as exc:  # noqa: BLE001
        print(f"[runner] import failed: {type(exc).__name__}: {exc}", flush=True)
        return 2

    print("[runner] starting QQ Bot QR onboarding (600 s window)", flush=True)
    try:
        creds = qr_register(timeout_seconds=600)
    except KeyboardInterrupt:
        print("[runner] interrupted", flush=True)
        return 130

    if not creds:
        print("[runner] onboarding did not complete (no credentials returned)", flush=True)
        return 1

    # Persist without exposing. mode 600, owned by the invoking user.
    RESULT.write_text(json.dumps(creds, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(RESULT, 0o600)

    app_id = str(creds.get("app_id") or "")
    openid = str(creds.get("user_openid") or "")
    has_secret = bool(str(creds.get("client_secret") or ""))
    print("", flush=True)
    print("[runner] SUCCESS", flush=True)
    print(f"[runner]   app_id            = {app_id}", flush=True)
    print(f"[runner]   scanner openid    = {openid or '(not returned)'}", flush=True)
    print(f"[runner]   client_secret     = {'captured' if has_secret else 'MISSING'}"
          " (never printed)", flush=True)
    print(f"[runner]   stored at         = {RESULT} (mode 600)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
