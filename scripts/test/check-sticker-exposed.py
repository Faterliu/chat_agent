#!/usr/bin/env python3
"""临时 HERMES_HOME + 合成素材，确认 send_sticker 在有素材时会带枚举暴露给模型。"""

import base64
import json
import os
import sys
from pathlib import Path

HOME = Path("/tmp/sticker-exposed")
os.environ["HERMES_HOME"] = str(HOME)
sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

lib = HOME / "stickers"
lib.mkdir(parents=True, exist_ok=True)
(lib / "a.png").write_bytes(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
(lib / "b.gif").write_bytes(base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"))
(lib / "manifest.json").write_text(json.dumps(
    {"version": 1, "stickers": [
        {"id": "doro_hello", "file": "a.png", "scene": "打招呼、卖萌"},
        {"id": "doro_sleep", "file": "b.gif", "scene": "晚安"},
    ]}, ensure_ascii=False), encoding="utf-8")

import tools.sticker_tool as st
from tools.registry import registry

defs = registry.get_definitions({"send_sticker"})
print("available:", st.stickers_available(), "count:", len(st.load_manifest()))
print("exposed:", bool(defs))
if defs:
    fn = defs[0].get("function", defs[0])
    print("name:", fn.get("name"))
    print("enum:", fn["parameters"]["properties"]["sticker_id"].get("enum"))
    print("description:", fn.get("description"))

from tools.tool_search import classify_tools

visible, deferred = classify_tools(defs)
print("visible:", [d.get("function", d).get("name") for d in visible])
print("deferred:", [d.get("function", d).get("name") for d in deferred])
