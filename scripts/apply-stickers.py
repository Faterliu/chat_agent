#!/usr/bin/env python3
"""部署「表情包」能力（空素材库阶段）：工具 + 工具集 + MEDIA 白名单 + QQ 群富媒体补丁 + 配置。

改动清单（全部幂等，重复运行只补缺）：
1. 新增 ``tools/sticker_tool.py``（来源：本脚本同目录 sticker_tool.py）；
2. ``toolsets.py`` 增加 ``sticker`` 工具集；
3. ``gateway/run.py`` 的 ``_AUTO_APPEND_MEDIA_TOOL_NAMES`` 加入 ``send_sticker``，
   否则工具返回的 MEDIA 标签不会被自动附加到回复里；
4. ``gateway/platforms/qqbot/adapter.py`` 的 ``_send_media`` 在群聊回填被动回复
   ``msg_id``（与既有文本补丁一致，否则 QQ 以「主动消息失败, 无权限」拒绝图片）；
5. ``config.yaml`` 的 ``platform_toolsets.qqbot`` 增加 ``sticker``（微信本阶段不加）；
6. 建 ``HERMES_HOME/stickers/``（0700）与空 ``manifest.json``（0600，已存在则不动）。

备份：``HERMES_HOME/backups/stickers-<UTC>/``（0700，内含 4 个文件的副本 + sha256 清单）。
不重启网关；由调用者用低内存启动器单独重启。

用法：
    HERMES_HOME=/var/lib/hermes/.hermes \\
      /var/lib/hermes/.hermes/hermes-agent/venv/bin/python apply-stickers.py
"""

import datetime
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
CFG = HOME / "config.yaml"
PINNED = "f97608f178d1ffeca59860195ab7da295f7c8e5f"
HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(SRC))

TOOLSET_ANCHOR = '    "social": _ts("本人私聊主动关心与生日订阅", ["social_manage"]),\n'
TOOLSET_LINE = '    "sticker": _ts("表情包：从受限素材库挑一张图片发到当前聊天", ["send_sticker"]),\n'

MEDIA_ANCHOR = '_AUTO_APPEND_MEDIA_TOOL_NAMES = {"text_to_speech", "text_to_speech_tool", "image_generate"}'
MEDIA_NEW = '_AUTO_APPEND_MEDIA_TOOL_NAMES = {"text_to_speech", "text_to_speech_tool", "image_generate", "send_sticker"}'

QQ_ANCHOR = (
    '        chat_type = self._guess_chat_type(chat_id)\n'
    '        if chat_type == "guild":\n'
    '            return SendResult(success=False, error="Guild media send not supported via this path")\n'
)
QQ_BLOCK = '''
        # [LOCAL PATCH] 群聊富媒体同样必须带被动回复 msg_id，否则 QQ 按主动消息拒绝
        # （HTTP 400 "主动消息失败, 无权限"）；语义与 send() 里的文本补丁一致。
        if reply_to is None and chat_type == "group":
            reply_to = self._last_msg_id.get(chat_id)
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(path: Path, old: str, new: str, label: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if new in text:
        print(f"  skip (already applied): {label}")
        return False
    if text.count(old) != 1:
        raise SystemExit(f"ABORT: anchor for {label} found {text.count(old)} times in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"  patched: {label}")
    return True


def main() -> int:
    import subprocess

    head = subprocess.run(["git", "-C", str(SRC), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != PINNED:
        raise SystemExit(f"ABORT: source HEAD {head} != pinned {PINNED}")

    tool_src = HERE.parent / "source" / "sticker_tool.py"
    if not tool_src.is_file():
        raise SystemExit(f"ABORT: missing {tool_src}")

    targets = {
        "toolsets.py": SRC / "toolsets.py",
        "gateway__run.py": SRC / "gateway" / "run.py",
        "qqbot__adapter.py": SRC / "gateway" / "platforms" / "qqbot" / "adapter.py",
        "config.yaml": CFG,
        "tools__sticker_tool.py": SRC / "tools" / "sticker_tool.py",
    }
    for name, path in targets.items():
        if name == "tools__sticker_tool.py" and not path.exists():
            continue
        if not path.is_file():
            raise SystemExit(f"ABORT: missing {path}")

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"stickers-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    lines = [f"purpose: 部署表情包工具（空素材库阶段）\n", f"source_head: {head}\n"]
    for name, path in targets.items():
        if path.is_file():
            shutil.copy2(path, backup / name)
            os.chmod(backup / name, 0o600)
            lines.append(f"{name}\tsha256={sha256(path)}\n")
    (backup / "manifest.txt").write_text("".join(lines), encoding="utf-8")
    os.chmod(backup / "manifest.txt", 0o600)
    print("backup:", backup)

    print("1) tools/sticker_tool.py")
    dest_tool = SRC / "tools" / "sticker_tool.py"
    shutil.copy2(tool_src, dest_tool)
    os.chmod(dest_tool, 0o644)

    print("2) toolsets.py: sticker toolset")
    replace_once(targets["toolsets.py"], TOOLSET_ANCHOR, TOOLSET_ANCHOR + TOOLSET_LINE, "toolsets sticker")

    print("3) gateway/run.py: MEDIA auto-append allowlist")
    replace_once(targets["gateway__run.py"], MEDIA_ANCHOR, MEDIA_NEW, "media allowlist")

    print("4) qqbot adapter: passive msg_id for group rich media")
    replace_once(targets["qqbot__adapter.py"], QQ_ANCHOR, QQ_ANCHOR + QQ_BLOCK, "qqbot group media")

    print("5) config.yaml: platform_toolsets.qqbot += sticker")
    import yaml
    from utils import atomic_roundtrip_yaml_update

    before_raw = CFG.read_text(encoding="utf-8")
    before = yaml.safe_load(before_raw) or {}
    qq = list((before.get("platform_toolsets") or {}).get("qqbot") or [])
    if "sticker" in qq:
        print("  skip (already applied): qqbot toolset list")
    else:
        if "social" in qq:
            qq.insert(qq.index("social") + 1, "sticker")
        else:
            qq.append("sticker")
        atomic_roundtrip_yaml_update(CFG, "platform_toolsets.qqbot", qq)
        after_raw = CFG.read_text(encoding="utf-8")
        after = yaml.safe_load(after_raw) or {}
        a, b = json.loads(json.dumps(before, default=str)), json.loads(json.dumps(after, default=str))
        a_qq = (a.get("platform_toolsets") or {}).get("qqbot")
        b_qq = (b.get("platform_toolsets") or {}).get("qqbot")
        for doc in (a, b):
            ps = doc.get("platform_toolsets") or {}
            ps.pop("qqbot", None)
            if not ps:
                doc.pop("platform_toolsets", None)
        if a != b:
            shutil.copy2(backup / "config.yaml", CFG)
            raise SystemExit("ABORT: collateral config change, restored backup")
        if b_qq != qq:
            shutil.copy2(backup / "config.yaml", CFG)
            raise SystemExit(f"ABORT: qq list mismatch after write: {b_qq}")
        print("  after list:", b_qq)

    print("6) sticker library scaffold")
    lib = HOME / "stickers"
    lib.mkdir(parents=True, exist_ok=True)
    os.chmod(lib, 0o700)
    manifest = lib / "manifest.json"
    if manifest.exists():
        print("  keep existing manifest.json")
    else:
        manifest.write_text(json.dumps({"version": 1, "stickers": []}, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        os.chmod(manifest, 0o600)
        print("  wrote empty manifest.json (0600)")
    readme = lib / "README.md"
    if not readme.exists():
        readme.write_text((HERE.parent / "source" / "stickers-README.md").read_text(encoding="utf-8"), encoding="utf-8")
        os.chmod(readme, 0o600)

    print("7) syntax check")
    for path in (SRC / "tools" / "sticker_tool.py", SRC / "toolsets.py",
                 SRC / "gateway" / "run.py", SRC / "gateway" / "platforms" / "qqbot" / "adapter.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        print("  ok:", path.relative_to(SRC))

    print("done. restart with /var/lib/hermes/start-chat-agent.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
