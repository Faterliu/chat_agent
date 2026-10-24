"""Deploy persona v1.3.1 into the LIVE config (agent.personalities.xiaoyun.system_prompt).

Root cause fixed here: the earlier deploy only wrote /var/lib/hermes/xiaoyun.json, which nothing
reads. The gateway resolves the persona from config.yaml on every turn, so that file is the target.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

import yaml  # noqa: E402
from utils import atomic_roundtrip_yaml_update  # noqa: E402

CFG = "/var/lib/hermes/.hermes/config.yaml"
SRC = "/tmp/xiaoyun.json"
BLOCKS = ("【联网搜索】", "【对话检索】", "【记住对方】")

data = json.load(open(SRC, encoding="utf-8"))
sp = data["system_prompt"]
assert data["version"] == "1.3.1", data["version"]
for block in BLOCKS:
    assert block in sp, "missing block: " + block

raw_before = open(CFG, encoding="utf-8").read()
before = yaml.safe_load(raw_before)
old_sp = before["agent"]["personalities"]["xiaoyun"]["system_prompt"]
print("config_before_chars", len(raw_before), "prompt_chars", len(old_sp))
print("before_blocks", [b for b in BLOCKS if b in old_sp])
assert old_sp != sp, "already deployed"

atomic_roundtrip_yaml_update(CFG, "agent.personalities.xiaoyun.system_prompt", sp)

raw_after = open(CFG, encoding="utf-8").read()
after = yaml.safe_load(raw_after)
new_sp = after["agent"]["personalities"]["xiaoyun"]["system_prompt"]
assert new_sp == sp, "roundtrip mismatch"

# Nothing else may change: blank the edited key on both sides and compare whole documents.
a = json.loads(json.dumps(before, default=str))
b = json.loads(json.dumps(after, default=str))
a["agent"]["personalities"]["xiaoyun"]["system_prompt"] = ""
b["agent"]["personalities"]["xiaoyun"]["system_prompt"] = ""
assert a == b, "collateral change in config.yaml"

print("config_after_chars", len(raw_after), "prompt_chars", len(new_sp))
print("after_blocks", [x for x in BLOCKS if x in new_sp])
print("md5_config", hashlib.md5(raw_after.encode("utf-8")).hexdigest())
print("prompt_md5", hashlib.md5(new_sp.encode("utf-8")).hexdigest())
print("stat_mode", oct(os.stat(CFG).st_mode & 0o777))
# Loader check: the file-signature cache must reload on the new mtime/size.
from hermes_cli.config import load_config  # noqa: E402

live = load_config()["agent"]["personalities"]["xiaoyun"]["system_prompt"]
print("loader_sees_new", live == sp, "loader_chars", len(live))
print("display.personality", load_config()["display"]["personality"])
