#!/usr/bin/env python3
"""隔离验收「表情包」工具：临时 HERMES_HOME、合成素材、不碰生产库、不调模型。

覆盖：空库隐藏、索引校验（越界/带空格/缺失/超限被忽略）、枚举与说明、正常发送、
8 秒冷却、未知 id、以及网关 MEDIA 提取与投递路径校验。

用法：venv/bin/python test-stickers.py   （HERMES_HOME 由脚本自己指向临时目录）
"""

import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
TMP = Path(tempfile.mkdtemp(prefix="sticker-test-"))
os.environ["HERMES_HOME"] = str(TMP)
sys.path.insert(0, str(SRC))

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
GIF_1PX = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
MEDIA_RE = re.compile(r"MEDIA:(/\S+\.(?:png|jpe?g|gif|webp|mp4|ogg|mp3|pdf))", re.IGNORECASE)

failures = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def write_manifest(items) -> None:
    (TMP / "stickers").mkdir(parents=True, exist_ok=True)
    (TMP / "stickers" / "manifest.json").write_text(
        json.dumps({"version": 1, "stickers": items}, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    from tools import sticker_tool as st

    check("empty home: stickers_dir under temp HERMES_HOME", st.stickers_dir() == TMP / "stickers")
    check("empty home: check_fn False", st.stickers_available() is False)
    check("empty home: schema has no enum",
          "enum" not in st._schema_overrides()["parameters"]["properties"]["sticker_id"])
    empty = json.loads(st.send_sticker("x"))
    check("empty home: send refuses", empty.get("success") is False and "空" in empty.get("error", ""))

    lib = TMP / "stickers"
    (lib / "packs" / "doro").mkdir(parents=True, exist_ok=True)
    (lib / "packs" / "doro" / "hello.png").write_bytes(PNG_1PX)
    (lib / "packs" / "doro" / "sleep.gif").write_bytes(GIF_1PX)
    (lib / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * (3 * 1024 * 1024))
    write_manifest([
        {"id": "doro_hello", "file": "packs/doro/hello.png", "scene": "打招呼、卖萌"},
        {"id": "doro_sleep", "file": "packs/doro/sleep.gif", "scene": "晚安"},
        {"id": "escape", "file": "../config.yaml", "scene": "越界"},
        {"id": "spaced", "file": "packs/doro/hello copy.png", "scene": "带空格"},
        {"id": "missing", "file": "packs/doro/nope.png", "scene": "不存在"},
        {"id": "huge", "file": "big.png", "scene": "超限"},
        {"id": "wrong_ext", "file": "packs/doro/sleep.gif.bak", "scene": "坏扩展名"},
    ])

    loaded = {i["id"] for i in st.load_manifest()}
    check("manifest keeps only valid entries", loaded == {"doro_hello", "doro_sleep"}, str(loaded))
    check("available after adding stickers", st.stickers_available() is True)

    schema = st._schema_overrides()
    enum = schema["parameters"]["properties"]["sticker_id"].get("enum")
    check("enum exposes both ids", sorted(enum or []) == ["doro_hello", "doro_sleep"], str(enum))
    check("description carries catalog", "doro_hello（打招呼、卖萌）" in schema["description"], schema["description"])
    check("base description has usage rule", "一轮最多一张" in st.SCHEMA["description"])

    st._last_sent_at = 0.0
    out = st.send_sticker("doro_hello")
    lines = out.strip().splitlines()
    payload = json.loads(lines[0])
    check("send returns success payload", payload == {"success": True, "sticker": "doro_hello"}, out)
    check("second line is MEDIA tag", lines[-1].startswith("MEDIA:"), lines[-1])
    media_path = Path(lines[-1][len("MEDIA:"):])
    check("MEDIA path exists and is the sticker",
          media_path.is_file() and media_path.name == "hello.png", str(media_path))
    check("MEDIA regex matches (gateway parser shape)", bool(MEDIA_RE.fullmatch(lines[-1])), lines[-1])

    st._last_sent_at = __import__("time").monotonic()
    throttled = json.loads(st.send_sticker("doro_sleep"))
    check("8s throttle blocks immediate resend", throttled.get("success") is False, throttled)

    st._last_sent_at = 0.0
    gif_out = st.send_sticker("doro_sleep")
    check("gif sticker accepted after cooldown", gif_out.strip().endswith("sleep.gif"), gif_out)

    st._last_sent_at = 0.0
    unknown = json.loads(st.send_sticker("escape"))
    check("unknown/traversal id refused", unknown.get("success") is False and "doro_hello" in unknown.get("error", ""), unknown)

    # 网关侧：MEDIA 标签能否被解析、是否通过投递路径校验（生产默认非 strict）。
    from gateway.platforms.base import BasePlatformAdapter

    text = "好呀，抱抱~\n" + out.strip().splitlines()[-1]
    media_files, cleaned = BasePlatformAdapter.extract_media(text)
    check("gateway extract_media finds 1 file", len(media_files) == 1, str(media_files))
    check("gateway strips tag from visible text", "MEDIA:" not in cleaned and "抱抱" in cleaned, cleaned)
    kept = BasePlatformAdapter.filter_media_delivery_paths(media_files)
    check("delivery policy accepts sticker path", len(kept) == 1 and Path(kept[0][0]).name == "hello.png", str(kept))

    print("\ntemp home:", TMP)
    print("failures:", len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
