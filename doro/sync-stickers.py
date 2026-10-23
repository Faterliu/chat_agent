#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 doro 目录的表情包与映射一次性推到网关：上传图片、重建 manifest.json、写 emoji 映射。

布局：图片都放在 `doro/doro/`，脚本与总表 `doro/manifest.txt` 在上一层。
唯一要编辑的是总表：`id | 画面 | 适用场景 | 已映射`。
前两列进 manifest.json（模型挑图看的说明），第四列写进 config.yaml 的
display.emoji_stickers.mapping；第四列写 `--` 表示这张图还没有 emoji 指向。

用法（在本项目根目录）：
    python doro\\sync-stickers.py                 # 预览：图片差异 + 映射差异，不写任何东西
    python doro\\sync-stickers.py --apply         # 真正执行（图片 → manifest → 映射）
    python doro\\sync-stickers.py --apply --only mapping   # 只改映射，不碰图片
    python doro\\sync-stickers.py --apply --only images    # 只管图片与 manifest
    python doro\\sync-stickers.py --apply --prune          # 顺带删掉线上本地已不收录的图
    python doro\\sync-stickers.py --list          # 只读：线上现状 + 谁还没映射

顺序不能反：先上传图片、重建 manifest.json，再写映射——映射会拿 id 去核 manifest，
图没上线就写不进去。

写入前必备份（manifest 备份在 HOME/backups/stickers-manifest-*，
映射备份在 HOME/backups/emoji-mapping-*），写后逐条自检，失败自动回滚。
图片与 manifest 是幂等的，重跑无副作用；映射写失败只回滚 config，图片和 manifest 保留。

不需要重启网关：配置按文件签名缓存，下一轮聊天就生效；
只有工具枚举（素材库）变了、老会话还在用旧 schema 时才发 /new。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGES_DIR = HERE / "doro"          # 原图都放这个子目录
TABLE_FILE = HERE / "manifest.txt"  # 总表与脚本同层
DEFAULT_HOST = "hermes@8.148.73.94"

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
STICKERS = HOME / "stickers"
CFG = HOME / "config.yaml"
PACK = "packs/doro"
IMAGE_EXT = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
MAX_BYTES = 2 * 1024 * 1024
ID_RE = re.compile(r"^doro_(\d+)$")
# 第四列「已映射」写成这些就算留空（没有 emoji 指向这张图）
NONE_MARKS = {"", "-", "--", "---", "—", "——", "无", "空", "none", "null"}
SEP_RE = re.compile(r"[,\u3001\s]+")

# 远端命令必须用 POSIX 字符串（Windows 的 Path 会给出反斜杠，被远端 shell 吃掉）
R_HOME = os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes")
R_SRC = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
R_PY = R_SRC + "/venv/bin/python"
REMOTE_PLAN = "/tmp/doro-sync-plan.json"
REMOTE_TABLE = "/tmp/doro-manifest.txt"
REMOTE_PY = "/tmp/doro-sync-stickers.py"


def setup_console() -> None:
    """Windows 控制台默认 GBK，打印 emoji 会崩；尽量切到 UTF-8，失败就替换字符。"""
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


def disp_width(text: str) -> int:
    """终端显示宽度：emoji／CJK 算两格，方便把表格对齐。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


# ── 解析与校验 manifest.txt（本机／服务器共用） ──────────────────────
def parse_table(path: Path) -> tuple[list[dict], list[str]]:
    """解析四列总表：返回 [{id, scene, keys, lineno}] 与问题列表。

    scene＝「画面：适用场景」（适用场景留空就只用画面），就是 manifest.json 的 scene 字面。
    """
    rows: list[dict] = []
    problems: list[str] = []
    if not path.is_file():
        return rows, [f"找不到 {path}"]
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4:
            problems.append(
                f"manifest.txt 第 {lineno} 行要有四列（id | 画面 | 适用场景 | 已映射）：{line}")
            continue
        sid, look, when, mapped = parts
        if not ID_RE.match(sid):
            problems.append(f"manifest.txt 第 {lineno} 行 id 不合法（要 doro_3 这样）：{sid!r}")
            continue
        if not look:
            problems.append(f"manifest.txt 第 {lineno} 行「画面」是空的：{sid}")
            continue
        keys = [k for k in SEP_RE.split(mapped) if k and k.lower() not in NONE_MARKS]
        rows.append({"id": sid, "scene": f"{look}：{when}" if when else look,
                     "keys": keys, "lineno": lineno})
    return rows, problems


def base_char_count(key: str) -> int:
    """数一个键里有几个「基字」emoji：ZWJ 连字／肤色修饰／国旗对／VS16 都算同一个。"""
    if "\u200d" in key:
        return 1
    n, prev_flag = 0, False
    for ch in key:
        o = ord(ch)
        if ch in "\ufe0e\ufe0f\u20e3" or 0x1F3FB <= o <= 0x1F3FF:
            continue
        if 0x1F1E6 <= o <= 0x1F1FF:
            if prev_flag:
                prev_flag = False
                continue
            prev_flag = True
            n += 1
            continue
        prev_flag = False
        if o >= 0x2000:
            n += 1
    return n


def build_mapping(rows: list[dict]) -> tuple[list[str], list[str], dict[str, str]]:
    """把第四列摊成 {emoji: id}，行序即优先级；返回问题、提示与目标映射。"""
    problems: list[str] = []
    warnings: list[str] = []
    seen: dict[str, tuple[str, int]] = {}
    for row in rows:
        sid, lineno = row["id"], row["lineno"]
        for key in row["keys"]:
            if any(ord(c) < 0x2000 for c in key):
                problems.append(
                    f"manifest.txt 第 {lineno} 行（{sid}）第四列 {key!r} 不是 emoji"
                    "（不允许 ASCII 字母数字）")
                continue
            if base_char_count(key) > 1:
                problems.append(
                    f"manifest.txt 第 {lineno} 行（{sid}）第四列 {key!r} 像是几个 emoji"
                    f" 粘在一起了（中间缺空格）：要写成 {' '.join(key)} 才是每个各自生效")
                continue
            prev = seen.get(key)
            if prev and prev[0] != sid:
                problems.append(
                    f"{key} 同时映射到 {prev[0]}（第 {prev[1]} 行）和 {sid}（第 {lineno} 行）")
                continue
            seen.setdefault(key, (sid, lineno))
    keys = list(seen)
    for a in keys:
        for b in keys:
            if a != b and a in b:
                problems.append(f"{a} 是 {b} 的一部分，会互相破坏，只保留完整那个")
    for k in keys:
        if len(k) == 1 and 0x2600 <= ord(k) <= 0x27BF:
            warnings.append(f"{k}（U+{ord(k):04X}）可能被客户端补成 ♥️ 这类组合，确认后再用")
    return problems, warnings, {k: seen[k][0] for k in keys}


def diff_mapping(local: dict[str, str], live: dict[str, str]) -> dict:
    return {
        "added": [k for k in local if k not in live],
        "removed": [k for k in live if k not in local],
        "changed": [k for k in local if k in live and live[k] != local[k]],
        "reordered": [k for k in live if k in local] != [k for k in local if k in live],
        "same": local == live and list(local) == list(live),
    }


# ── 服务器端：素材与 manifest ──────────────────────────────────────
def server_remote_info() -> int:
    """输出线上文件清单、manifest.json 与当前映射，供本机算差异。"""
    root = STICKERS / PACK
    for d in (STICKERS, STICKERS / "packs", root):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    files = {}
    for p in sorted(root.iterdir(), key=lambda x: natural_key(x.name)):
        if p.is_file():
            files[p.name] = {"sha256": sha256_of(p), "size": p.stat().st_size}
    manifest = []
    mpath = STICKERS / "manifest.json"
    if mpath.is_file():
        manifest = json.loads(mpath.read_text(encoding="utf-8")).get("stickers") or []
    mapping = {}
    if CFG.is_file():
        sys.path.insert(0, str(SRC))
        import yaml  # noqa: E402
        cfg = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
        block = ((cfg.get("display") or {}).get("emoji_stickers")) or {}
        mapping = dict(block.get("mapping") or {})
    print(json.dumps({"files": files, "manifest": manifest, "mapping": mapping},
                     ensure_ascii=False))
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
    return 0


# ── 服务器端：emoji 映射 ──────────────────────────────────────────
def server_apply_mapping(table_path: Path) -> int:
    sys.path.insert(0, str(SRC))
    import yaml  # noqa: E402
    from utils import atomic_roundtrip_yaml_update  # noqa: E402

    rows, parse_problems = parse_table(table_path)
    problems, warnings, target = build_mapping(rows)
    problems = parse_problems + problems
    for w in warnings:
        print(f"提示：{w}")
    if problems:
        print(f"manifest.txt 第四列有 {len(problems)} 个问题，未做任何改动：")
        for p in problems:
            print("  -", p)
        return 2

    stickers = json.loads((STICKERS / "manifest.json").read_text(encoding="utf-8"))["stickers"]
    known = {s["id"] for s in stickers}
    missing = sorted({sid for sid in target.values() if sid not in known})
    if missing:
        print(f"错误：这些 id 线上 manifest 里没有：{', '.join(missing)}")
        print("可先跑一次 sync-stickers.py --apply --only images 把图推上去。")
        return 3

    raw = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    before = yaml.safe_load(raw) or {}
    block = ((before.get("display") or {}).get("emoji_stickers")) or {}
    if not block:
        print("错误：配置里没有 display.emoji_stickers")
        return 4
    current = dict(block.get("mapping") or {})
    d = diff_mapping(target, current)

    print(f"第四列 {len(target)} 条；线上现有 {len(current)} 条")
    for k in d["added"]:
        print(f"  + {k} -> {target[k]}")
    for k in d["removed"]:
        print(f"  - {k}（原来是 {current[k]}）")
    for k in d["changed"]:
        print(f"  ~ {k}: {current[k]} -> {target[k]}")
    if d["reordered"]:
        print("  顺序有调整（影响一回合只补一张时的优先级）")
    if d["same"]:
        print("映射与线上完全一致，不用改。")
        return 0

    import datetime
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"emoji-mapping-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    shutil.copy2(CFG, backup / "config.yaml")
    os.chmod(backup / "config.yaml", 0o600)
    shutil.copy2(table_path, backup / "manifest.txt")
    os.chmod(backup / "manifest.txt", 0o600)
    (backup / "note.txt").write_text(
        "purpose: sync doro/manifest.txt 第四列 into display.emoji_stickers.mapping\n"
        f"original_sha256: {before_sha}\n"
        f"added: {len(d['added'])} removed: {len(d['removed'])} "
        f"changed: {len(d['changed'])} reordered: {d['reordered']}\n"
        "rollback: copy config.yaml back into HERMES_HOME (loads next turn, no restart)\n",
        encoding="utf-8")
    os.chmod(backup / "note.txt", 0o600)

    new_block = dict(block)
    new_block["mapping"] = dict(target)
    atomic_roundtrip_yaml_update(CFG, "display.emoji_stickers", json.loads(json.dumps(new_block)))

    after_raw = CFG.read_text(encoding="utf-8")
    after = yaml.safe_load(after_raw) or {}
    got = dict((((after.get("display") or {}).get("emoji_stickers")) or {}).get("mapping") or {})
    if got != target:
        shutil.copy2(backup / "config.yaml", CFG)
        print("错误：写回后 mapping 与预期不一致，已恢复备份。")
        return 5
    a = json.loads(json.dumps(before, default=str))
    b = json.loads(json.dumps(after, default=str))
    a["display"]["emoji_stickers"].pop("mapping", None)
    b["display"]["emoji_stickers"].pop("mapping", None)
    if a != b:
        shutil.copy2(backup / "config.yaml", CFG)
        print("错误：mapping 之外的配置也被改了，已恢复备份。")
        return 6

    from gateway import emoji_stickers  # noqa: E402
    bad = []
    for key, sid in target.items():
        cleaned, ids = emoji_stickers.prepare("测试" + key, "qqbot")
        if cleaned != "测试" or list(ids) != [sid]:
            bad.append(f"{key} -> {sid}：得到 {cleaned!r} {list(ids)}")
    if bad:
        shutil.copy2(backup / "config.yaml", CFG)
        print("自检失败，已恢复备份：")
        for x in bad:
            print("  -", x)
        return 7

    print(f"已写入 {len(target)} 条，自检 {len(target)}/{len(target)} 通过。")
    print("备份：", f"backups/{backup.name}")
    print("config sha256：", before_sha[:8], "->",
          hashlib.sha256(after_raw.encode("utf-8")).hexdigest()[:8],
          "权限", oct(os.stat(CFG).st_mode & 0o777))
    print("下一轮聊天生效，无需重启。")
    return 0


def server_main(args) -> int:
    if args.remote_info:
        return server_remote_info()
    if args.install_plan:
        return server_install(Path(args.install_plan))
    if args.apply_mapping:
        return server_apply_mapping(Path(args.apply_mapping))
    print("服务器模式需要 --remote-info、--install-plan 或 --apply-mapping")
    return 2


# ── 本机端 ──────────────────────────────────────────────────────
def ssh(host: str, remote: str) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", host, remote], capture_output=True,
                          encoding="utf-8", errors="replace")


def scp(host: str, names: list[str], cwd: Path, dest: str) -> None:
    subprocess.run(["scp", "-q"] + names + [f"{host}:{dest}"], cwd=str(cwd), check=True)


def resolve_file(folder: Path, sid: str) -> tuple[Path | None, str]:
    hits = sorted([p for p in folder.iterdir()
                   if p.is_file() and p.stem == sid and p.suffix.lower() in IMAGE_EXT],
                  key=lambda p: p.name)
    if not hits:
        return None, f"{sid}：目录里找不到 {sid}.gif 之类的图片"
    if len(hits) > 1:
        return None, f"{sid}：目录里有多个同 id 的图（{', '.join(h.name for h in hits)}），只留一个"
    return hits[0], ""


def build_plan(folder: Path, rows: list[dict], remote_files: dict, prune: bool):
    """图片差异：谁要上传、谁没变、谁没收录、线上多出来的。"""
    entries, upload, unchanged = [], [], []
    problems: list[str] = []
    seen_ids, seen_files = {}, {}
    for row in rows:
        sid = row["id"]
        if sid in seen_ids:
            problems.append(f"{sid} 在 manifest.txt 里出现了两次")
            continue
        seen_ids[sid] = True
        path, err = resolve_file(folder, sid)
        if path is None:
            problems.append(err)
            continue
        if path.name in seen_files:
            problems.append(f"{path.name} 被 {seen_files[path.name]} 和 {sid} 同时引用")
            continue
        seen_files[path.name] = sid
        size = path.stat().st_size
        if not 0 < size <= MAX_BYTES:
            problems.append(f"{path.name}：{size} 字节，超出 1 B–2 MiB，先压缩")
            continue
        digest = sha256_of(path)
        entries.append({"id": sid, "name": path.name, "scene": row["scene"],
                        "size": size, "sha256": digest})
        old = remote_files.get(path.name)
        if old is None or old.get("sha256") != digest:
            upload.append(path.name)
        else:
            unchanged.append(path.name)

    listed = set(seen_files)
    all_images = sorted([p.name for p in folder.iterdir()
                         if p.is_file() and p.suffix.lower() in IMAGE_EXT], key=natural_key)
    unlisted = [n for n in all_images if n not in listed]
    extra = sorted([n for n in remote_files if n not in listed], key=natural_key)
    entries.sort(key=lambda e: int(ID_RE.match(e["id"]).group(1)))
    plan = {"pack": PACK, "stickers": entries, "prune": extra if prune else []}
    info = {"upload": upload, "unchanged": unchanged, "extra": extra, "unlisted": unlisted}
    return plan, problems, info


def render_status(rows: list[dict], remote: dict) -> int:
    """--list：线上素材＋总表并排打印，谁没映射一眼可见。只读。"""
    by_id: dict[str, list[str]] = {r["id"]: r["keys"] for r in rows}
    live_manifest = {s["id"]: s for s in remote.get("manifest") or []}
    live_map = dict(remote.get("mapping") or {})
    ids = sorted(set(by_id) | set(live_manifest),
                 key=lambda x: int(x.split("_")[-1]) if x.split("_")[-1].isdigit() else 0)

    print(f"{'id':9} {'已映射':<16} 画面：适用场景")
    print("-" * 78)
    unmapped = [i for i in ids if not by_id.get(i)]
    for sid in ids:
        keys = by_id.get(sid) or []
        cell = " ".join(keys) if keys else "— 未映射"
        scene = (live_manifest.get(sid) or {}).get("scene", "（线上没有这张图）")
        pad = max(2, 16 - disp_width(cell))
        print(f"{sid:9} {cell}{' ' * pad} {scene}")
    print("-" * 78)
    print(f"总表 {len(by_id)} 张里 {len(by_id) - len(unmapped)} 张已映射，"
          f"未映射 {len(unmapped)} 张：{' '.join(unmapped) if unmapped else '无'}")

    notes = []
    local_map = {}
    for r in rows:
        for k in r["keys"]:
            local_map[k] = r["id"]
    d = diff_mapping(local_map, live_map)
    if d["same"]:
        notes.append("映射与线上完全一致")
    else:
        bits = []
        if d["added"]:
            bits.append(f"待新增 {len(d['added'])}")
        if d["removed"]:
            bits.append(f"待删除 {len(d['removed'])}")
        if d["changed"]:
            bits.append(f"待改指向 {len(d['changed'])}")
        if d["reordered"]:
            bits.append("顺序不同（优先级会变）")
        notes.append("本地与线上不一致：" + "、".join(bits) + "，跑一次 --apply 同步")
    missing_live = [i for i in by_id if i not in live_manifest]
    if missing_live:
        notes.append(f"总表里有、线上还没有的图：{' '.join(missing_live)}")
    for n in notes:
        print("提示：", n)
    return 0


def local_main(args) -> int:
    folder = Path(args.dir).resolve()
    table_path = Path(args.manifest).resolve() if args.manifest else TABLE_FILE
    if not folder.is_dir():
        print(f"错误：目录不存在 {folder}")
        return 2
    if not table_path.is_file():
        print(f"错误：找不到 {table_path}")
        return 2

    rows, problems = parse_table(table_path)
    map_problems, warnings, target = build_mapping(rows)
    problems = problems + map_problems
    for w in warnings:
        print(f"提示：{w}")

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
        print("错误：读不到服务器状态：")
        print((info.stderr or "").strip())
        return 8
    try:
        remote = json.loads((info.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        print("错误：服务器返回无法解析：", (info.stdout or "")[:300])
        return 8

    if args.do_list:
        return render_status(rows, remote)

    do_images = args.only in ("all", "images")
    do_mapping = args.only in ("all", "mapping")
    plan, image_problems, summary = build_plan(folder, rows, remote.get("files") or {}, args.prune)
    problems = problems + image_problems
    if problems:
        print()
        print(f"manifest.txt 有 {len(problems)} 个问题，未做任何改动：")
        for x in problems:
            print("  -", x)
        return 2

    entries = plan["stickers"]
    desired = [{"id": e["id"], "file": f"{PACK}/{e['name']}", "scene": e["scene"]}
               for e in entries]
    manifest_same = desired == [{"id": s["id"], "file": s["file"], "scene": s["scene"]}
                                for s in remote.get("manifest") or []]
    mapping_diff = diff_mapping(target, dict(remote.get("mapping") or {}))
    unmapped = [r["id"] for r in rows if not r["keys"]]

    if do_images:
        print("【素材】")
        print(f"manifest.txt 收录 {len(entries)} 张，服务器现有 {len(remote.get('files') or {})} 个文件")
        if summary["upload"]:
            print(f"  要上传／更新 {len(summary['upload'])} 个 → " + "、".join(summary["upload"]))
        if summary["unchanged"]:
            print(f"  已是线上最新 {len(summary['unchanged'])} 个")
        if summary["unlisted"]:
            print(f"  目录里没收录（不会上传）：{'、'.join(summary['unlisted'])}")
        if summary["extra"]:
            tail = "（加 --prune 才会删）" if not args.prune else "（本次会删除）"
            print(f"  服务器多出来的文件：{'、'.join(summary['extra'])} {tail}")
        state = "无需重建" if manifest_same else "需要重建"
        print(f"  manifest.json：{state}；场景说明合计 "
              f"{sum(len(e['scene']) for e in entries)} 字符")
        if unmapped:
            print(f"  第四列还没写 emoji：{len(unmapped)} 张 → " + " ".join(unmapped))
    if do_mapping:
        if do_images:
            print()
        print(f"【映射】第四列 {len(target)} 条；线上现有 {len(remote.get('mapping') or {})} 条")
        if mapping_diff["same"]:
            print("  与线上完全一致，不用改。")
        else:
            if mapping_diff["added"]:
                print(f"  新增 {len(mapping_diff['added'])}：" + " ".join(mapping_diff["added"]))
            if mapping_diff["removed"]:
                print(f"  删除 {len(mapping_diff['removed'])}：" + " ".join(mapping_diff["removed"]))
            if mapping_diff["changed"]:
                print(f"  改指向 {len(mapping_diff['changed'])}："
                      + " ".join(mapping_diff["changed"]))
            if mapping_diff["reordered"]:
                print("  顺序有调整（影响一回合只补一张时的优先级）")

    nothing_to_do = (not summary["upload"] and manifest_same and not plan["prune"]
                     and mapping_diff["same"])
    if nothing_to_do:
        print()
        print("线上与本地完全一致，什么都不用做。")
        return 0
    if not args.apply:
        print()
        print("这是预览。确认后加 --apply 真正执行"
              + ("（--only images／mapping 可只做一半）。" if args.only == "all" else "。"))
        return 0

    # ── 执行 ───────────────────────────────────────────────────
    if do_images and (summary["upload"] or not manifest_same or plan["prune"]):
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
        if res.returncode != 0:
            print("素材这一步失败，映射没有动。")
            return res.returncode
    elif do_images:
        print()
        print("图片与 manifest.json 都已是最新，跳过。")

    if do_mapping:
        if mapping_diff["same"]:
            print()
            print("映射与线上一致，跳过。")
            return 0
        try:
            scp(args.host, [table_path.name], table_path.parent, REMOTE_TABLE)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            print(f"错误：上传 manifest.txt 失败：{exc}")
            return 8
        print()
        print("【映射】")
        res = ssh(args.host, f"HERMES_HOME={R_HOME} {R_PY} {REMOTE_PY} "
                             f"--on-server --apply-mapping {REMOTE_TABLE}")
        sys.stdout.write(res.stdout or "")
        sys.stderr.write(res.stderr or "")
        if res.returncode != 0:
            print("映射写入失败；图片与 manifest 已生效，config 未改动或已回滚。")
            return res.returncode

    if do_images and not manifest_same:
        print()
        print("新素材已进入 send_sticker 的枚举；老会话若还看不到新 id，发 /new 即可。")
    return 0


def main() -> int:
    setup_console()
    ap = argparse.ArgumentParser(
        description="把 doro/manifest.txt 推到网关：上传图片、重建 manifest.json、写 emoji 映射")
    ap.add_argument("--dir", default=str(IMAGES_DIR), help="本地图片目录，默认脚本目录下的 doro/")
    ap.add_argument("--manifest", default="", help="本地总表，默认脚本目录下的 manifest.txt")
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只预览，不写任何东西）")
    ap.add_argument("--only", choices=("all", "images", "mapping"), default="all",
                    help="只做一半：images＝图片与 manifest，mapping＝只写映射")
    ap.add_argument("--prune", action="store_true", help="删掉服务器上本地已不收录的图")
    ap.add_argument("--list", "--status", dest="do_list", action="store_true",
                    help="只读：看线上现状与谁还没映射")
    ap.add_argument("--host", default=DEFAULT_HOST, help="服务器地址")
    ap.add_argument("--on-server", action="store_true", help="（内部）在服务器上直接执行")
    ap.add_argument("--remote-info", action="store_true", help="（内部）输出线上状态 JSON")
    ap.add_argument("--install-plan", default="", help="（内部）按计划重建 manifest")
    ap.add_argument("--apply-mapping", default="", help="（内部）写入 emoji 映射")
    args = ap.parse_args()

    on_server = args.on_server or (CFG.is_file() and (SRC / "venv" / "bin" / "python").is_file())
    if on_server:
        return server_main(args)
    return local_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
