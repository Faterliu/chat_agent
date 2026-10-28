"""Deploy the persona into the LIVE config (agent.personalities.xiaoyun.system_prompt).

The persona source keeps the prompt as three English content fields — persona_core,
natural_communication, speaking_style — plus operational_rules (tool/group/privacy plumbing that
is not personality). The gateway only reads a single system_prompt string, so the fields are
composed here. The legacy `description` key is removed from the config dict: nothing at runtime
reads it and it duplicated the persona in prose.
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
FIELDS = ("persona_core", "natural_communication", "speaking_style", "operational_rules")
BLOCKS = ("【联网搜索】", "【对话检索】", "【记住对方】", "【定时提醒文案】", "安全边界：", "群聊默认收敛")

data = json.load(open(SRC, encoding="utf-8"))
assert data["version"] == "1.4.0", data["version"]
assert "description" not in data, "persona source must not carry a description field"
missing = [f for f in FIELDS if not str(data.get(f, "")).strip()]
assert not missing, "empty persona fields: " + ", ".join(missing)
sp = "\n\n".join(str(data[f]).strip() for f in FIELDS)
for block in BLOCKS:
    assert block in sp, "missing block: " + block

raw_before = open(CFG, encoding="utf-8").read()
before = yaml.safe_load(raw_before)
old = before["agent"]["personalities"]["xiaoyun"]
old_sp = old["system_prompt"]
print("config_before_chars", len(raw_before), "prompt_chars", len(old_sp))
print("before_keys", sorted(old.keys()))
print("before_blocks", [b for b in BLOCKS if b in old_sp])
assert old_sp != sp, "already deployed"

atomic_roundtrip_yaml_update(CFG, "agent.personalities.xiaoyun.system_prompt", sp)
atomic_roundtrip_yaml_update(CFG, "agent.personalities.xiaoyun.description", None)

raw_after = open(CFG, encoding="utf-8").read()
after = yaml.safe_load(raw_after)
new = after["agent"]["personalities"]["xiaoyun"]
new_sp = new["system_prompt"]
assert new_sp == sp, "roundtrip mismatch"
assert "description" not in new, "description key survived"
assert new.get("tone", "") == old.get("tone", "") and new.get("style", "") == old.get("style", "")

# Nothing else may change: blank the whole personality on both sides and compare documents.
a = json.loads(json.dumps(before, default=str))
b = json.loads(json.dumps(after, default=str))
a["agent"]["personalities"]["xiaoyun"] = {}
b["agent"]["personalities"]["xiaoyun"] = {}
assert a == b, "collateral change in config.yaml"

print("config_after_chars", len(raw_after), "prompt_chars", len(new_sp))
print("after_keys", sorted(new.keys()))
print("after_blocks", [x for x in BLOCKS if x in new_sp])
print("md5_config", hashlib.md5(raw_after.encode("utf-8")).hexdigest())
print("prompt_md5", hashlib.md5(new_sp.encode("utf-8")).hexdigest())
print("stat_mode", oct(os.stat(CFG).st_mode & 0o777))
# Loader check: the file-signature cache must reload on the new mtime/size.
from hermes_cli.config import load_config  # noqa: E402

live = load_config()["agent"]["personalities"]["xiaoyun"]["system_prompt"]
print("loader_sees_new", live == sp, "loader_chars", len(live))
print("display.personality", load_config()["display"]["personality"])
