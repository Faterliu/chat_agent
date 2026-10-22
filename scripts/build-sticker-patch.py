#!/usr/bin/env python3
"""生成表情包补丁（4 个源文件），并做反向 dry-run 前的自检。

差异基线：三个已部署文件取 stickers 备份目录里的原始副本；tool_search.py 的基线是
“已含 social、尚未含 sticker”的中间态（social 属于更早的补丁，不能混进本次记录）。
"""

import subprocess
from pathlib import Path

SRC = Path("/var/lib/hermes/.hermes/hermes-agent")
BAK = Path("/var/lib/hermes/.hermes/backups/stickers-20261020T063643Z")
OUT = Path("/tmp/stickers-src.patch")

cur = (SRC / "tools/tool_search.py").read_text(encoding="utf-8")
pre = cur.replace('frozenset({"social", "sticker", ', 'frozenset({"social", ', 1)
assert pre != cur, "tool_search baseline replace failed"
pre_path = Path("/tmp/tool_search_pre.py")
pre_path.write_text(pre, encoding="utf-8")

pairs = [
    ("toolsets.py", BAK / "toolsets.py", SRC / "toolsets.py"),
    ("gateway/run.py", BAK / "gateway__run.py", SRC / "gateway/run.py"),
    ("gateway/platforms/qqbot/adapter.py", BAK / "qqbot__adapter.py", SRC / "gateway/platforms/qqbot/adapter.py"),
    ("tools/tool_search.py", pre_path, SRC / "tools/tool_search.py"),
]

chunks = []
for label, old, new in pairs:
    res = subprocess.run(
        ["diff", "-u", "--label", f"a/{label}", "--label", f"b/{label}", str(old), str(new)],
        capture_output=True, text=True)
    assert res.returncode == 1, f"unexpected diff rc={res.returncode} for {label}: {res.stderr}"
    chunks.append(res.stdout)

OUT.write_text("".join(chunks), encoding="utf-8")
print(OUT, len(OUT.read_text(encoding='utf-8').splitlines()), "lines")
print("".join(chunks))
