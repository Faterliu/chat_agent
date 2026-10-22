"""表情包：从受限素材库给当前聊天发一张图片（QQ / 微信）。

素材库固定在 ``HERMES_HOME/stickers/``，索引为同目录 ``manifest.json``：

    {"version": 1,
     "stickers": [
       {"id": "doro_hello", "file": "packs/doro/hello.png", "scene": "打招呼、卖萌"}
     ]}

约束（全部在读取时校验，来源不可信也不越界）：

* ``file`` 必须解析到 ``stickers/`` 目录内部（防 ``../`` 穿越），符号链接按真实路径判断；
* 扩展名限 png / jpg / jpeg / gif / webp，单文件 1 字节～2 MiB；
* 路径含空白字符的条目跳过——``MEDIA:`` 协议的路径以空白分隔，带空格会被截断；
* 库为空或索引损坏时 ``check_fn`` 返回 False，工具对模型完全不可见（零 token 开销）。

投递方式：handler 返回 ``MEDIA:<绝对路径>``，由网关既有的出站媒体管线发送。网关只会
为白名单里的工具自动附加媒体标签，因此 ``gateway/run.py`` 的
``_AUTO_APPEND_MEDIA_TOOL_NAMES`` 必须包含 ``send_sticker``。

限流：进程内全局 8 秒冷却，防止模型在单轮里连续调用刷屏；不区分用户（工具层拿不到
可信的 QQ／微信身份，按用户限流需要网关侧另行接线）。
"""

import json
import logging
import threading
import time
from pathlib import Path

from hermes_constants import get_hermes_home
from tools.registry import registry

logger = logging.getLogger("tools.sticker_tool")

_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_BYTES = 2 * 1024 * 1024
_MIN_INTERVAL_SECONDS = 8.0

_throttle_lock = threading.Lock()
_last_sent_at = 0.0


def try_acquire(interval_seconds: float) -> bool:
    """共用冷却：直接点单（本工具）与 emoji 映射补图共用一个计时器，间隔内只允许发一次。"""
    global _last_sent_at
    now = time.monotonic()
    with _throttle_lock:
        if now - _last_sent_at < interval_seconds:
            return False
        _last_sent_at = now
        return True


def stickers_dir() -> Path:
    """素材库目录；每次现算，HERMES_HOME 在网关进程内可能切换 profile。"""
    return get_hermes_home() / "stickers"


def _safe_relative(root: Path, rel: str) -> Path | None:
    """把 manifest 里的相对路径解析成 root 内的真实文件路径，越界/非法返回 None。"""
    rel = rel.strip()
    if not rel or any(ch.isspace() for ch in rel):
        return None
    try:
        candidate = (root / rel).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def load_manifest() -> list[dict]:
    """已校验的可用表情包列表 ``[{id, path, scene}]``；任何异常都退化为空列表。"""
    root = stickers_dir()
    try:
        data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("stickers") if isinstance(data, dict) else None
    result: list[dict] = []
    seen: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        path = _safe_relative(root, str(item.get("file") or ""))
        if not sid or sid in seen or path is None:
            continue
        if path.suffix.lower() not in _ALLOWED_EXTS or not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if not 0 < size <= _MAX_BYTES:
            continue
        seen.add(sid)
        result.append({"id": sid, "path": path, "scene": str(item.get("scene") or "").strip()})
    return result


def stickers_available() -> bool:
    """check_fn：库里一张可用的图都没有时隐藏工具。"""
    return bool(load_manifest())


def _catalog(items: list[dict]) -> str:
    return "；".join(f"{i['id']}（{i['scene']}）" if i["scene"] else i["id"] for i in items)


_BASE_DESCRIPTION = (
    "从表情包素材库给当前聊天发一张图片。只在对方情绪明显、适合点缀时使用："
    "一轮最多一张，不连发；严肃话题、故障提示、长回答里不要用；"
    "发了图正文照常写完，不要描述图片内容，也不要说“我发了个表情包”。"
)


def _schema_overrides() -> dict:
    """每次 get_definitions() 重建枚举与说明，新增素材后无需重启进程。"""
    items = load_manifest()
    params = {
        "type": "object",
        "properties": {
            "sticker_id": {
                "type": "string",
                "description": "要发送的表情包 id，只能从枚举里选。",
            }
        },
        "required": ["sticker_id"],
    }
    description = _BASE_DESCRIPTION
    if items:
        params["properties"]["sticker_id"]["enum"] = [i["id"] for i in items]
        description += " 当前可用：" + _catalog(items)
    return {"parameters": params, "description": description}


SCHEMA = {
    "name": "send_sticker",
    "description": _BASE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "sticker_id": {"type": "string", "description": "要发送的表情包 id，只能从枚举里选。"}
        },
        "required": ["sticker_id"],
    },
}


def send_sticker(sticker_id: str) -> str:
    """校验 id 并返回 ``MEDIA:<path>``，由网关媒体管线投递。"""
    items = {i["id"]: i for i in load_manifest()}
    wanted = str(sticker_id or "").strip()
    if not items:
        return json.dumps(
            {"success": False, "error": "表情包库是空的，先用文字回复。"}, ensure_ascii=False)
    item = items.get(wanted)
    if item is None:
        return json.dumps(
            {"success": False,
             "error": "没有这个表情包 id；可用：" + "、".join(sorted(items))},
            ensure_ascii=False)

    if not try_acquire(_MIN_INTERVAL_SECONDS):
        return json.dumps(
            {"success": False, "error": "刚发过表情包，这一轮不要再发，直接用文字接话。"},
            ensure_ascii=False)

    logger.info("sticker: id=%s file=%s size=%d", item["id"], item["path"].name,
                item["path"].stat().st_size)
    payload = json.dumps({"success": True, "sticker": item["id"]}, ensure_ascii=False)
    return f"{payload}\nMEDIA:{item['path']}"


registry.register(
    name="send_sticker",
    toolset="sticker",
    schema=SCHEMA,
    handler=lambda args, **kw: send_sticker(str(args.get("sticker_id") or "")),
    check_fn=stickers_available,
    description=_BASE_DESCRIPTION,
    emoji="🖼️",
    dynamic_schema_overrides=_schema_overrides,
)
