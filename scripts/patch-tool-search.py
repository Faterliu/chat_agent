#!/usr/bin/env python3
"""把 sticker 工具集加入 tool_search 的“直接可见”名单，避免表情包工具被降级成目录存根。

理由：_DIRECT_SURFACE_TOOLSETS 之外的非 core 工具默认 deferred，模型必须先 tool_search
才能拿到 enum；表情包需要“情绪到了就发”，多一次往返就失去意义。
工具本身仍由 check_fn 控制：库里没有素材时不可见，不占 token。
"""

from pathlib import Path

p = Path("/var/lib/hermes/.hermes/hermes-agent/tools/tool_search.py")
s = p.read_text(encoding="utf-8")
old = '_DIRECT_SURFACE_TOOLSETS = frozenset({"social", "desktop_ui", "project", "setup"})'
new = '_DIRECT_SURFACE_TOOLSETS = frozenset({"social", "sticker", "desktop_ui", "project", "setup"})'
if new in s:
    print("no-op: already patched")
    raise SystemExit(0)
if s.count(old) != 1:
    raise SystemExit(f"ABORT: anchor count {s.count(old)}")
p.write_text(s.replace(old, new, 1), encoding="utf-8")
compile(p.read_text(encoding="utf-8"), str(p), "exec")
print("patched:", new)
