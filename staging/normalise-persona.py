#!/usr/bin/env python3
"""Normalise the operator's persona JSON before it is applied to Hermes.

Two transforms, both deliberate and both reported rather than silent:

1. NEWLINE UNESCAPING
   The operator's file stores `system_prompt` with DOUBLE-escaped newlines: the raw JSON
   contains the two characters `\\n`, which `json.loads` decodes to a literal backslash
   followed by `n` — not a line break. Measured on the incoming file: 1541 chars,
   0 real newlines, 70 literal `\\n` sequences. Applied verbatim the prompt would reach
   the model as a single line containing visible `\n` text. This converts those back to
   real line breaks.

2. PLATFORM WORDING
   The incoming `system_prompt` reverted to "运行在用户本地微信机器人里". The operator
   explicitly instructed platform-agnostic wording earlier the same day, after the bot's own
   reasoning flagged the mismatch while running on QQ. That instruction is preserved here.
   Flagged to the operator so it can be reverted if the regression was intentional.

Also bumps `version`, because the incoming content differs materially from the previously
applied file that carried the same version string (1.1.0).

Output: staging/personas/xiaoyun.json
"""

from __future__ import annotations

import json
import pathlib

SRC = pathlib.Path(r"C:\Users\liuzhuo\Downloads\xiaoyun.json")
DST = pathlib.Path(r"C:\file\HermesAgent\staging\personas\xiaoyun.json")

OLD_WORDING = "运行在用户本地微信机器人里"
NEW_WORDING = "运行在用户的聊天机器人里"


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))

    sp = data["system_prompt"]
    before_chars = len(sp)
    before_newlines = sp.count("\n")
    before_literal = sp.count("\\n")

    sp = sp.replace("\\n", "\n")

    wording_changed = 0
    if OLD_WORDING in sp:
        sp = sp.replace(OLD_WORDING, NEW_WORDING)
        wording_changed = 1

    data["system_prompt"] = sp
    data["version"] = "1.2.0"
    data["_local_normalisation"] = {
        "note": "normalised locally before applying to Hermes; see staging/apply-persona.py",
        "unescaped_literal_newlines": before_literal,
        "platform_wording_changed": bool(wording_changed),
        "source_file": str(SRC),
    }

    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"source : {SRC}")
    print(f"written: {DST}")
    print(f"  version          : {data['version']}")
    print(f"  system_prompt     : {before_chars} -> {len(sp)} chars")
    print(f"  real newlines     : {before_newlines} -> {sp.count(chr(10))}")
    print(f"  literal \\n left   : {sp.count(chr(92) + 'n')}")
    print(f"  wording replaced  : {bool(wording_changed)} ({OLD_WORDING!r} -> {NEW_WORDING!r})")
    print(f"  first line        : {sp.splitlines()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
