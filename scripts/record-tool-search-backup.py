#!/usr/bin/env python3
"""把 tool_search.py 的改动前副本补进 stickers 备份目录，并登记 sha256。"""

import hashlib
import os
import shutil
from pathlib import Path

BAK = Path("/var/lib/hermes/.hermes/backups/stickers-20261020T063643Z")
SRC = Path("/tmp/tool_search_pre.py")

dest = BAK / "tools__tool_search.py"
shutil.copy2(SRC, dest)
os.chmod(dest, 0o600)
digest = hashlib.sha256(dest.read_bytes()).hexdigest()
with (BAK / "manifest.txt").open("a", encoding="utf-8") as fh:
    fh.write(f"tools__tool_search.py\tsha256={digest}\n")
print("backed up:", dest, digest)
print(sorted(p.name for p in BAK.iterdir()))
