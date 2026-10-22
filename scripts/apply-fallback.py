#!/usr/bin/env python3
"""Swap the fallback chain so the relay becomes the fallback.

Replace-in-place for the top-level `fallback_providers` key. A top-level block is
delimited by scanning from its key line forward over blank lines and lines indented by
two or more spaces, stopping at the first line that is neither. Text-only, so comments
elsewhere in config.yaml and every other section are preserved.

`hermes config set` cannot express a list of mappings, which is why this is a script.

Entry shape (hermes_cli/fallback_config.py `_iter_fallback_entries`):
    provider  required
    model     required
    base_url  optional
    api_key / key_env / api_key_env  optional credential source

`provider: kldai` names the entry defined under `providers:` in config.yaml, so the
endpoint AND its `transport: codex_responses` wire setting come from there. Putting a
bare `base_url` here instead would risk resolving the endpoint without the Responses
wire, which this relay requires.
"""

from __future__ import annotations

import pathlib
import sys

import yaml

CFG = pathlib.Path("/var/lib/hermes/.hermes/config.yaml")
KEY = "fallback_providers:"

CHAIN = [
    {
        # The OpenAI-compatible relay, demoted from primary: measured 25-45 s per trivial
        # prompt with intermittent 45 s timeouts and a misfiring anti-abuse 400.
        "provider": "kldai",
        "model": "gpt-6-sol",
        "key_env": "KLDAI_API_KEY",
    },
]


def main() -> int:
    text = CFG.read_text(encoding="utf-8")
    lines = text.split("\n")

    hits = [i for i, ln in enumerate(lines) if ln.startswith(KEY)]
    if len(hits) != 1:
        print(f"[fallback] expected exactly one '{KEY}' line, found {len(hits)}")
        return 1
    start = hits[0]

    end = start + 1
    while end < len(lines) and (lines[end].strip() == "" or lines[end].startswith("  ")):
        end += 1
    while end - 1 > start and lines[end - 1].strip() == "":
        end -= 1

    old = lines[start:end]

    body = yaml.safe_dump(CHAIN, allow_unicode=True, default_flow_style=False,
                          sort_keys=False, width=10 ** 6).rstrip("\n")
    block = [KEY] + ["  " + ln for ln in body.splitlines()]

    CFG.write_text("\n".join(lines[:start] + block + lines[end:]), encoding="utf-8")

    print(f"[fallback] replaced {len(old)} lines with {len(block)}")
    for entry in CHAIN:
        print(f"[fallback]   -> provider={entry['provider']} model={entry['model']} "
              f"key_env={entry.get('key_env', '-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
