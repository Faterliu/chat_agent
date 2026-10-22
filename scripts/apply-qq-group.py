#!/usr/bin/env python3
"""Rewrite the top-level `platforms:` block for QQ Bot — with mandatory self-verification.

BUG THIS FIXES: a previous version of this script built the replacement as
`["platforms:"] + body.splitlines()` and forgot to indent `body` by two spaces. The
result was a syntactically valid but structurally wrong file:

    platforms:
    qqbot:            # <- became a TOP-LEVEL key
      enabled: true

`platforms:` parsed as null and every policy silently reverted to its built-in default
(`pairing` for both dm and group), which is an access-control regression that no error
surfaces. `hermes config get platforms.qqbot.extra.group_policy` returning
"Config key not set" is what exposed it.

Hence the post-write assertion below: the script re-reads the file it just wrote and
refuses to report success unless the values are actually reachable at the expected paths.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

CFG = pathlib.Path("/var/lib/hermes/.hermes/config.yaml")
KEY = "platforms:"
INDENT = "  "

OPERATOR_OPENID = "A729C39060FB65742B0C808249E36326"
GROUP_OPENID = "56B2E66590BD2ED9A098C5D8B0123D68"

BLOCK = {
    "qqbot": {
        "enabled": True,
        "extra": {
            "dm_policy": "allowlist",
            "allow_from": [OPERATOR_OPENID],
            "group_policy": "allowlist",
            "group_allow_from": [GROUP_OPENID],
        },
    },
}


def main() -> int:
    text = CFG.read_text(encoding="utf-8")
    lines = text.split("\n")

    hits = [i for i, ln in enumerate(lines) if ln.startswith(KEY)]
    if len(hits) != 1:
        print(f"[qq-group] expected exactly one '{KEY}' line, found {len(hits)}")
        return 1
    start = hits[0]

    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end].startswith(INDENT)):
        end += 1
    while end - 1 > start and lines[end - 1].strip() == "":
        end -= 1

    body = yaml.safe_dump(BLOCK, allow_unicode=True, default_flow_style=False,
                          sort_keys=False, width=10 ** 6).rstrip("\n")
    # THE FIX: every line of the child mapping must be indented under the parent key.
    block = [KEY] + [INDENT + ln if ln.strip() else ln for ln in body.splitlines()]

    CFG.write_text("\n".join(lines[:start] + block + lines[end:]), encoding="utf-8")

    # ---- mandatory self-verification ----
    parsed = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    try:
        extra = parsed["platforms"]["qqbot"]["extra"]
    except (KeyError, TypeError) as exc:
        print(f"[qq-group] VERIFY FAILED — platforms.qqbot.extra is not reachable: {exc!r}")
        return 2

    expected = BLOCK["qqbot"]["extra"]
    problems = [k for k, v in expected.items() if extra.get(k) != v]
    if problems:
        print(f"[qq-group] VERIFY FAILED — mismatched keys: {problems}")
        print(f"[qq-group]   got: {extra}")
        return 2

    print(f"[qq-group] rewrote the platforms block ({len(lines[start:end])} lines -> {len(block)})")
    print("[qq-group] verified by re-parsing the written file:")
    for k, v in expected.items():
        print(f"[qq-group]   platforms.qqbot.extra.{k} = {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
