"""Atomically deploy the updated persona and report the result (no secrets involved)."""
from __future__ import annotations

import hashlib
import json
import os

SRC = "/tmp/xiaoyun.json"
DST = "/var/lib/hermes/xiaoyun.json"

data = json.load(open(SRC, encoding="utf-8"))
assert data["version"] == "1.2.4", data["version"]
assert "【联网搜索】" in data["system_prompt"], "new block missing"

old = open(DST, encoding="utf-8").read()
tmp = DST + ".tmp"
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
os.chmod(tmp, 0o600)
os.replace(tmp, DST)

new = open(DST, encoding="utf-8").read()
print("old_chars", len(old), "-> new_chars", len(new))
print("version", json.loads(new)["version"])
print("md5", hashlib.md5(new.encode("utf-8")).hexdigest())
print("stat_mode", oct(os.stat(DST).st_mode & 0o777))
print()
print("=== deployed block ===")
sp = json.loads(new)["system_prompt"]
i = sp.find("【联网搜索】")
print(sp[i:i + 400])
