#!/usr/bin/env python3
"""Verify that the 小云 persona actually reaches the effective system prompt.

Why not just use `hermes -z`: the one-shot path (hermes_cli/oneshot.py:588) passes
`ephemeral_system_prompt=skills_prompt` and therefore deliberately bypasses the
personality overlay. Only the interactive CLI (cli_init_mixin.py:249) and the gateway
(gateway/run_config_loaders.py:93) resolve `display.personality`. A `-z` smoke test can
never prove this either way, so this script calls Hermes' own resolvers instead.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

from hermes_cli.config_effective import load_user_config_effective  # noqa: E402
from hermes_cli.personality import (  # noqa: E402
    active_personality_name,
    available_personalities,
    render_personality_prompt,
    resolve_ephemeral_system_prompt,
)


def flat(text: str, n: int) -> str:
    return text[:n].replace("\n", " / ")


def main() -> int:
    cfg = load_user_config_effective(fail_closed=True)

    name = active_personality_name(cfg)
    print(f"active personality name : {name!r}")

    definitions = available_personalities(cfg)
    print(f"personalities available : {len(definitions)} (built-ins + user)")
    print(f"xiaoyun is defined      : {'xiaoyun' in definitions}")

    definition = definitions.get(name) if name else None
    if definition is None:
        print("VERDICT: no active personality overlay")
        return 1

    rendered = render_personality_prompt(definition)
    print(f"rendered overlay        : {len(rendered)} chars")
    print(f"  head : {flat(rendered, 70)}")
    print(f"  tail : {flat(rendered[-70:], 70)}")

    effective = resolve_ephemeral_system_prompt(cfg)
    print(f"effective system overlay: {len(effective)} chars")
    for probe in ("云白", "小云", "本云", "昵称"):
        print(f"  contains {probe:<6}        : {probe in effective}")

    ok = "云白" in effective and "小云" in effective
    print("VERDICT: overlay is active (云白 + 小云 present)" if ok
          else "VERDICT: overlay NOT active")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
