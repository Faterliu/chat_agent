#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 doro 目录里的表情包和 manifest.txt 同步到网关素材库：上传新图 + 重建 manifest.json。

用法（在本项目根目录）：
    python doro\\sync-stickers.py                   # 预览：谁要上传、谁没变、谁没收录
    python doro\\sync-stickers.py --apply           # 真正上传并重建 manifest
    python doro\\sync-stickers.py --apply --prune   # 顺便删掉线上多出来的图

本地两个来源：
  · `manifest.txt`（id | 文件名 | 场景说明）——要改就改它；
  · 目录里的图片本身。
服务器 `HERMES_HOME/stickers/manifest.json` 由本脚本整份重建，不要手改。

与 apply-mapping.py 同样是双模式：在 Windows 本机跑时自动 scp 到服务器、用生产 venv
执行；在服务器上跑就地执行。上传后校验 sha256、大小 1 B–2 MiB、权限 0600，
再用线上 tools.sticker_tool.load_manifest() 复核每条都能读出来。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_HOST = "hermes@8.148.73.94"

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
STICKERS = HOME / "stickers"
PACK = "packs/doro"
IMAGE_EXT = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024
ID_RE = re.compile(r"^doro_(\d+)$")

# 远端命令必须用 POSIX 字符串（Windows 的 Path 会给出反斜杠）
R_HOME = os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes")
R_SRC = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
R_PY = R_SRC + "/venv/bin/python"
REMOTE_PLAN = "/tmp/doro-sync-plan.json"
REMOTE_PY = "/tmp/doro-sync-stickers.py"


def setup_console() -> None:
    utf8_ok = False
    if os.name == "nt":
        try:
            import ctypes
            utf8_ok = bool(ctypes.windll.kernel32.SetConsoleOutputCP(65001))
        except Exception:
            utf8_ok = False
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace") if utf8_ok \
                else stream.reconfigure(errors="replace")
        except Exception:
            pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def natural_key(name: str) -> list:
    parts = re.split(r"(\d+)", name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def looks_like_image(text: str) -> bool:
    return Path(text).suffix.lower() in IMAGE_EXT


def read_manifest_txt(path: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """解析 manifest.txt：返回 [(id, 文件名或"", 场景)] 与问题列表。"""
    rows: list[tuple[str, str, str]] = []
    problems: list[str] = []
    if not path.is_file():
        return rows, [f"找不到 {path}"]
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 3:
                problems.append(f"manifest.txt 第 {lineno} 行要用三列（id | 文件名 | 场景）：{line}")
                continue
            sid, fname, scene = parts
        elif "=" in line:  # 宽容：id = 场景
            sid, scene = line.split("=", 1)
            sid, fname, scene = sid.strip(), "", scene.strip()
        else:
            problems.append(f"manifest.txt 第 {lineno} 行看不懂（要 id | 文件名 | 场景）：{line}")
            continue
        if not ID_RE.match(sid):
            problems.append(f"manifest.txt 第 {lineno} 行 id 不合法（要 doro_3 这样）：{sid!r}")
            continue
        if not scene:
            problems.append(f"manifest.txt 第 {lineno} 行场景说明是空的：{sid}")
            continue
        if fname and not looks_like_image(fname):
            problems.append(f"manifest.txt 第 {lineno} 行文件名不像图片：{fname!r}")
            continue
        rows.append((sid, fname, scene))
    return rows, problems


def resolve_file(folder: Path, sid: str, fname: str) -> tuple[Path | None, str]:
    if fname:
        p = folder / fname
        return (p, "") if p.is_file() else (None, f"{sid}：manifest.txt 写的文件 {fname} 不存在")
    hits = sorted([p for p in folder.iterdir()
                   if p.is_file() and p.stem == sid and p.suffix.lower() in IMAGE_EXT],
                  key=lambda p: p.name)
    if not hits:
        return None, f"{sid}：目录里找不到 {sid}.gif 之类的图片"
    if len(hits) > 1:
        return None, f"{sid}：目录里有多个同 id 的图（{', '.join(h.name for h in hits)}），在 manifest.txt 里指定一个"
    return hits[0], ""


def build_plan(folder: Path, manifest_path: Path, remote: dict, prune: bool):
    rows, problems = read_manifest_txt(manifest_path)
    entries, upload, unchanged = [], [], []
    seen_ids, seen_files = {}, {}

    for sid, fname, scene in rows:
        if sid in seen_ids:
            problems.append(f"{sid} 在 manifest.txt 里出现了两次")
            continue
        seen_ids[sid] = True
        path, err = resolve_file(folder, sid, fname)
        if path is None:
            problems.append(err)
            continue
        if path.name in seen_files:
            problems.append(f"{path.name} 被 {seen_files[path.name]} 和 {sid} 同时引用")
            continue
        seen_files[path.name] = sid
        if path.suffix.lower() not in IMAGE_EXT:
            problems.append(f"{path.name}：扩展名不支持")
            continue
        size = path.stat().st_size
        if not 0 < size <= MAX_BYTES:
            problems.append(f"{path.name}：{size} 字节，超出 1 B–2 MiB，先压缩")
            continue
        if path.stem != sid:
            print(f"提示：{sid} 用的是文件 {path.name}（文件名和 id 不一致，也能用）")
        digest = sha256_of(path)
        entries.append({"id": sid, "name": path.name, "scene": scene,
                        "size": size, "sha256": digest})
        old = remote.get(path.name)
        if old is None or old.get("sha256") != digest:
            upload.append(path.name)
        else:
            unchanged.append(path.name)

    listed = set(seen_files)
    all_images = sorted([p.name for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() in IMAGE_EXT], key=natural_key)
    unlisted = [n for n in all_images if n not in listed]
    extra = sorted([n for n in remote if n not in listed], key=natural_key)

    entries.sort(key=lambda e: int(ID_RE.match(e["id"]).group(1)))
    plan = {"pack": PACK, "stickers": entries, "prune": extra if prune else []}
    info = {"upload": upload, "unchanged": unchanged, "extra": extra, "unlisted": unlisted}
    return plan, problems, info


# ── 服务器端 ────────────────────────────────────────────────────
def server_remote_info() -> int:
    root = STICKERS / PACK
    for d in (STICKERS, STICKERS / "packs", root):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    out = {}
    for p in sorted(root.iterdir(), key=lambda x: natural_key(x.name)):
        if p.is_file():
            out[p.name] = {"sha256": sha256_of(p), "size": p.stat().st_size}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def server_install(plan_path: Path) -> int:
    sys.path.insert(0, str(SRC))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    root = STICKERS / PACK
    entries = plan.get("stickers") or []
    if not entries:
        print("错误：计划里没有条目")
        return 2

    problems = []
    for e in entries:
        p = root / e["name"]
        if not p.is_file():
            problems.append(f"{e['name']}：服务器上没有这个文件（上传失败？）")
            continue
        if p.stat().st_size != e["size"]:
            problems.append(f"{e['name']}：大小不符 {p.stat().st_size} != {e['size']}")
            continue
        if sha256_of(p) != e["sha256"]:
            problems.append(f"{e['name']}：sha256 不符，重传一次")
            continue
        if not 0 < p.stat().st_size <= MAX_BYTES:
            problems.append(f"{e['name']}：超出 1 B–2 MiB")
            continue
        os.chmod(p, 0o600)
    if problems:
        print("上传校验失败，manifest 未改动：")
        for x in problems:
            print("  -", x)
        return 3

    manifest = {"version": 1, "stickers": [
        {"id": e["id"], "file": f"{PACK}/{e['name']}", "scene": e["scene"]} for e in entries]}

    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"stickers-manifest-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    current = STICKERS / "manifest.json"
    if current.is_file():
        shutil.copy2(current, backup / "manifest.json")
        os.chmod(backup / "manifest.json", 0o600)
    (backup / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    os.chmod(backup / "plan.json", 0o600)

    tmp = STICKERS / ".manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, current)

    for name in plan.get("prune") or []:
        p = root / name
        if p.is_file() and ID_RE.match(p.stem):
            p.unlink()

    from tools import sticker_tool
    loaded = {i["id"]: i for i in sticker_tool.load_manifest()}
    expected = {e["id"]: e for e in entries}
    missing = sorted(set(expected) - set(loaded))
    if missing:
        print(f"错误：重建后这些 id 读不出来：{', '.join(missing)}（备份 {backup}）")
        return 4
    for sid, e in expected.items():
        if loaded[sid]["scene"] != e["scene"]:
            print(f"错误：{sid} 场景读回不一致（备份 {backup}）")
            return 4

    catalog = "；".join(f"{i['id']}（{i['scene']}）" for i in sticker_tool.load_manifest())
    print(f"manifest 已重建：{len(expected)} 条，备份 backups/{backup.name}")
    print(f"工具说明长度：{len(catalog)} 字符（每轮随 schema 发给模型，条目越多越贵）")
    print("id：" + " ".join(sorted(expected, key=lambda x: int(x.split("_")[1]))))
    return 0


def server_main(args) -> int:
    if args.remote_info:
        return server_remote_info()
    if not args.install_plan:
        print("服务器模式需要 --remote-info 或 --install-plan")
        return 2
    return server_install(Path(args.install_plan))


# ── 本机端 ──────────────────────────────────────────────────────
def ssh(host: str, remote: str) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", host, remote], capture_output=True,
                          encoding="utf-8", errors="replace")


def scp(host: str, names: list[str], cwd: Path, dest: str) -> None:
    subprocess.run(["scp", "-q"] + names + [f"{host}:{dest}"], cwd=str(cwd), check=True)


def local_main(args) -> int:
    folder = Path(args.dir).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else folder / "manifest.txt"
    if not folder.is_dir():
        print(f"错误：目录不存在 {folder}")
        return 2

    try:
        scp(args.host, [Path(__file__).name], HERE, REMOTE_PY)
    except FileNotFoundError:
        print("错误：找不到 scp/ssh 客户端。")
        return 8
    except subprocess.CalledProcessError as exc:
        print(f"错误：上传脚本失败（{exc.returncode}），检查到 {args.host} 的 ssh 是否可用。")
        return 8

    info = ssh(args.host, f"HERMES_HOME={R_HOME} {R_PY} {REMOTE_PY} --on-server --remote-info")
    if info.returncode != 0:
        print("错误：读不到服务器素材库：")
        print((info.stderr or "").strip())
        return 8
    try:
        remote = json.loads((info.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print("错误：服务器返回无法解析：", (info.stdout or "")[:300])
        return 8

    plan, problems, summary = build_plan(folder, manifest_path, remote, args.prune)
    entries = plan["stickers"]
    print(f"manifest.txt 收录 {len(entries)} 张，服务器现有 {len(remote)} 个文件")
    if summary["upload"]:
        print(f"要上传／更新：{len(summary['upload'])} 个 → " + "、".join(summary["upload"]))
    if summary["unchanged"]:
        print(f"已是最新：{len(summary['unchanged'])} 个")
    if summary["unlisted"]:
        print(f"目录里没收录（不会上传）：{'、'.join(summary['unlisted'])}")
    if summary["extra"]:
        tail = "（加 --prune 才会删）" if not args.prune else "（本次会删除）"
        print(f"服务器多出来的文件：{'、'.join(summary['extra'])} {tail}")
    if problems:
        print()
        print(f"有 {len(problems)} 个问题，未做任何改动：")
        for x in problems:
            print("  -", x)
        return 2

    total = sum(len(e["scene"]) for e in entries)
    print(f"场景说明合计 {total} 字符；manifest 将重建为 {len(entries)} 条")

    if not args.apply:
        print()
        print("这是预览。确认后加 --apply 真正上传并重建 manifest。")
        return 0

    try:
        if summary["upload"]:
            scp(args.host, summary["upload"], folder, f"{R_HOME}/stickers/{PACK}/")
        plan_file = HERE / ".doro-sync-plan.json"
        plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            scp(args.host, [plan_file.name], HERE, REMOTE_PLAN)
        finally:
            plan_file.unlink(missing_ok=True)
    except FileNotFoundError:
        print("错误：找不到 scp/ssh 客户端。")
        return 8
    except subprocess.CalledProcessError as exc:
        print(f"错误：上传失败（{exc.returncode}），检查到 {args.host} 的 ssh 是否可用。")
        return 8

    res = ssh(args.host, f"HERMES_HOME={R_HOME} {R_PY} {REMOTE_PY} "
                         f"--on-server --install-plan {REMOTE_PLAN}")
    sys.stdout.write(res.stdout or "")
    sys.stderr.write(res.stderr or "")
    if res.returncode == 0:
        print()
        print("新表情包立刻出现在 send_sticker 的枚举里；")
        print("如果聊天中模型还没看到新 id，发 /new 开个新会话即可。")
    return res.returncode


def main() -> int:
    setup_console()
    ap = argparse.ArgumentParser(description="上传表情包并重建 manifest.json")
    ap.add_argument("--dir", default=str(HERE), help="本地表情包目录，默认脚本所在目录")
    ap.add_argument("--manifest", default="", help="本地索引，默认 <dir>/manifest.txt")
    ap.add_argument("--apply", action="store_true", help="真正上传并重建（默认只预览）")
    ap.add_argument("--prune", action="store_true", help="删掉服务器上本地已不收录的图")
    ap.add_argument("--host", default=DEFAULT_HOST, help="服务器地址")
    ap.add_argument("--on-server", action="store_true", help="（内部）在服务器上直接执行")
    ap.add_argument("--remote-info", action="store_true", help="（内部）输出线上文件清单 JSON")
    ap.add_argument("--install-plan", default="", help="（内部）按计划重建 manifest")
    args = ap.parse_args()

    on_server = args.on_server or (HOME.is_dir() and (SRC / "venv" / "bin" / "python").is_file())
    if on_server:
        return server_main(args)
    return local_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
