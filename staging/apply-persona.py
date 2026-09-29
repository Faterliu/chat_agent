#!/usr/bin/env python3
"""Phase 7b (v2) — write/refresh the 小云 persona under `agent.personalities`.

Where it goes and why:
  * `agent.personalities.<name>` — user-defined personalities, overlaying built-ins
    (hermes_cli/personality.py owns this state).
  * `display.personality` — the *selected* name. Set separately with
    `hermes config set display.personality xiaoyun`; it is what activates the overlay
    on both the interactive CLI and the messaging gateway.
  * `render_personality_prompt()` consumes exactly four fields:
    `description` (display only), `system_prompt`, `tone`, `style`.
    The remaining JSON fields have no slot in Hermes' schema.

v2 differs from v1 in that it REPLACES an existing entry instead of refusing to run.
The `agent.personalities` region is delimited by scanning from the `  personalities:`
line forward over blank and 4+-space-indented lines, stopping at the first line that is
neither. That is exactly the region between the key and the commented examples that
follow it. The operation is text-only, so every comment elsewhere in config.yaml —
and the rest of the `agent:` section — is preserved untouched.

Safety: the `  personalities:` anchor must appear EXACTLY once. Appending a second
top-level `agent:` block instead would let a duplicate YAML key discard the rest of
`agent:`, including `max_turns`.
"""

from __future__ import annotations

import json
import pathlib
import sys

import yaml

CFG = pathlib.Path("/var/lib/hermes/.hermes/config.yaml")
SRC = pathlib.Path("/var/lib/hermes/xiaoyun.json")
MARKER = "  personalities:"


def joined(items: object) -> str:
    if not isinstance(items, list):
        return ""
    return "；".join(str(i).strip() for i in items if str(i).strip())


def main() -> int:
    persona = json.loads(SRC.read_text(encoding="utf-8"))
    name = str(persona.get("id") or "").strip().lower()
    if not name:
        print("[persona] the JSON has no usable 'id'")
        return 1

    entry = {
        "description": str(persona.get("description") or "").strip(),
        "system_prompt": str(persona.get("system_prompt") or "").strip(),
        "tone": joined((persona.get("personality") or {}).get("core_traits")),
        "style": joined((persona.get("speech_style") or {}).get("general")),
    }
    if not entry["system_prompt"]:
        print("[persona] the JSON has no system_prompt — refusing to write")
        return 1

    text = CFG.read_text(encoding="utf-8")
    lines = text.split("\n")

    anchors = [i for i, ln in enumerate(lines) if ln.startswith(MARKER)]
    if len(anchors) != 1:
        print(f"[persona] expected exactly one '{MARKER}' line, found {len(anchors)}")
        return 1
    start = anchors[0]

    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end].startswith("    ")):
        end += 1
    # keep blank separator lines that follow the region
    while end - 1 > start and lines[end - 1].strip() == "":
        end -= 1

    old = lines[start:end]

    inner = yaml.safe_dump(
        {name: entry},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=10 ** 6,
    ).rstrip("\n")
    block = [MARKER] + ["    " + ln for ln in inner.splitlines()]

    CFG.write_text("\n".join(lines[:start] + block + lines[end:]), encoding="utf-8")

    print(f"[persona] rewrote agent.personalities.{name}")
    print(f"[persona]   region replaced : {len(old)} lines -> {len(block)} lines")
    print(f"[persona]   name/nickname   : {persona.get('name')} / {persona.get('nickname')}")
    print(f"[persona]   description     : {len(entry['description'])} chars")
    print(f"[persona]   system_prompt   : {len(entry['system_prompt'])} chars, "
          f"{entry['system_prompt'].count(chr(10)) + 1} lines")
    print(f"[persona]   tone            : {len(entry['tone'])} chars")
    print(f"[persona]   style           : {len(entry['style'])} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
