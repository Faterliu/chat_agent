#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 doro/mapping.txt 的映射写进网关配置 display.emoji_stickers.mapping。

用法（在本项目根目录）：
    python doro\\apply-mapping.py            # 校验 → 备份 → 写入 → 自检
    python doro\\apply-mapping.py --dry-run  # 只校验并显示与线上的差异
    python doro\\apply-mapping.py --list     # 列出线上可用的表情包 id 与场景

它有两副面孔：
  · 在 Windows 本机运行时，会把 mapping.txt 和本脚本一起传到服务器，
    再用生产 venv 执行（ruamel 往返改配置，保留注释与其余键）；
  · 在服务器上直接运行时，就地改本机配置。
写入前必备份，写入后核验“只有 mapping 变了”，再用线上模块逐条跑
emoji_stickers.prepare() 自检；自检不过自动回滚。

不需要重启网关：配置按文件签名缓存，下一轮聊天就生效。
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
DEFAULT_MAPPING = HERE / "mapping.txt"
DEFAULT_HOST = "hermes@8.148.73.94"

HOME = Path(os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes"))
SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
CFG = HOME / "config.yaml"
MANIFEST = HOME / "stickers" / "manifest.json"
VENV_PY = SRC / "venv" / "bin" / "python"

# 远端命令里必须用 POSIX 字符串：Windows 的 Path 会转成反斜杠，被远端 shell 吃掉
R_HOME = os.environ.get("HERMES_HOME", "/var/lib/hermes/.hermes")
R_SRC = os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent")
R_PY = R_SRC + "/venv/bin/python"

ID_RE = re.compile(r"^doro_\d+$")
ARROW_RE = re.compile(r"->|→|=>")
SEP_RE = re.compile(r"[,\u3001\s]+")
REMOTE_TXT = "/tmp/doro-mapping.txt"
REMOTE_PY = "/tmp/doro-apply-mapping.py"


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


# ── 解析与静态校验（本地／服务器共用） ──────────────────────────────
def parse_entries(text: str) -> tuple[list[tuple[str, str, int]], list[str]]:
    entries: list[tuple[str, str, int]] = []
    problems: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = ARROW_RE.split(line, maxsplit=1)
        if len(parts) == 2:
            left, right = parts
        elif "," in line:  # 宽容：也接受 "emoji, id"
            left, right = line.rsplit(",", 1)
        else:
            problems.append(f"第 {lineno} 行没有 ->：{raw.strip()}")
            continue
        sid = right.strip().strip("\"'")
        if not ID_RE.match(sid):
            problems.append(f"第 {lineno} 行右侧不是合法 id（要形如 doro_3）：{sid!r}")
            continue
        keys = [k for k in SEP_RE.split(left.strip()) if k]
        if not keys:
            problems.append(f"第 {lineno} 行左侧没有 emoji")
            continue
        for k in keys:
            entries.append((k, sid, lineno))
    return entries, problems


def validate(entries: list[tuple[str, str, int]]) -> tuple[list[str], list[str], dict[str, str]]:
    problems: list[str] = []
    warnings: list[str] = []
    seen: dict[str, tuple[str, int]] = {}
    for key, sid, lineno in entries:
        if any(ord(c) < 0x2000 for c in key):
            problems.append(f"第 {lineno} 行左侧 {key!r} 不是 emoji（不允许 ASCII 字母数字）")
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


def report(problems: list[str], warnings: list[str]) -> None:
    for w in warnings:
        print(f"提示：{w}")
    if problems:
        print()
        print(f"mapping.txt 有 {len(problems)} 个问题，未做任何改动：")
        for p in problems:
            print("  -", p)


# ── 服务器端：真正写配置 ──────────────────────────────────────────
def server_main(mapping_path: Path, dry_run: bool, do_list: bool) -> int:
    sys.path.insert(0, str(SRC))
    import yaml  # noqa: E402
    from utils import atomic_roundtrip_yaml_update  # noqa: E402

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stickers = manifest.get("stickers", [])
    if do_list:
        print(f"{'id':10} {'大小':>8}  场景")
        for s in stickers:
            p = HOME / "stickers" / s["file"]
            size = p.stat().st_size if p.is_file() else -1
            print(f"{s['id']:10} {size:>8}  {s.get('scene', '')}")
        return 0

    entries, parse_problems = parse_entries(mapping_path.read_text(encoding="utf-8"))
    problems, warnings, target = validate(entries)
    problems = parse_problems + problems
    report(problems, warnings)
    if problems:
        return 2

    known = {s["id"] for s in stickers}
    missing = sorted({sid for sid in target.values() if sid not in known})
    if missing:
        print(f"错误：这些 id 在线上 manifest 里不存在：{', '.join(missing)}")
        print("可用 id：", " ".join(sorted(known, key=lambda x: int(x.split('_')[1]))))
        print("新图要先传到 HERMES_HOME/stickers/packs/doro/ 并写进 manifest.json。")
        return 3

    raw = CFG.read_text(encoding="utf-8")
    before_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    before = yaml.safe_load(raw) or {}
    block = ((before.get("display") or {}).get("emoji_stickers")) or {}
    if not block:
        print("错误：配置里没有 display.emoji_stickers")
        return 4
    current = dict(block.get("mapping") or {})

    added = [k for k in target if k not in current]
    removed = [k for k in current if k not in target]
    changed = [k for k in target if k in current and current[k] != target[k]]
    kept_order = [k for k in current if k in target]
    reordered = kept_order != [k for k in target if k in current]

    print(f"mapping.txt：{len(target)} 条；线上现有：{len(current)} 条")
    if not (added or removed or changed or reordered):
        print("与线上完全一致，不用改。")
    else:
        for k in added:
            print(f"  + {k} -> {target[k]}")
        for k in removed:
            print(f"  - {k}（原来是 {current[k]}）")
        for k in changed:
            print(f"  ~ {k}: {current[k]} -> {target[k]}")
        if reordered:
            print("  顺序有调整（影响一回合只补一张时的优先级）")

    if dry_run:
        print()
        print("dry-run：没有写入。")
        return 0
    if not (added or removed or changed or reordered):
        return 0

    import datetime  # noqa: E402
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / f"emoji-mapping-file-{ts}"
    backup.mkdir(parents=True, exist_ok=False)
    os.chmod(backup, 0o700)
    shutil.copy2(CFG, backup / "config.yaml")
    os.chmod(backup / "config.yaml", 0o600)
    shutil.copy2(mapping_path, backup / "mapping.txt")
    os.chmod(backup / "mapping.txt", 0o600)
    (backup / "manifest.txt").write_text(
        "purpose: apply doro/mapping.txt to display.emoji_stickers.mapping\n"
        f"original_sha256: {before_sha}\n"
        f"added: {len(added)} removed: {len(removed)} changed: {len(changed)}\n"
        "rollback: copy config.yaml back into HERMES_HOME (loads next turn, no restart)\n",
        encoding="utf-8")
    os.chmod(backup / "manifest.txt", 0o600)

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

    # 用线上模块逐条自检
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

    print()
    print(f"已写入 {len(target)} 条，自检 {len(target)}/{len(target)} 通过。")
    print("备份：", backup)
    print("config sha256：", before_sha[:8], "->",
          hashlib.sha256(after_raw.encode("utf-8")).hexdigest()[:8],
          "权限", oct(os.stat(CFG).st_mode & 0o777))
    print("下一轮聊天生效，无需重启。")
    return 0


# ── 本机：上传后在服务器执行 ──────────────────────────────────────
def local_main(mapping_path: Path, host: str, dry_run: bool, do_list: bool) -> int:
    if do_list:
        print(f"（--list 只看线上素材库，不读 {mapping_path.name}）")
    else:
        if not mapping_path.is_file():
            print(f"错误：找不到 {mapping_path}")
            return 2
        entries, parse_problems = parse_entries(mapping_path.read_text(encoding="utf-8"))
        problems, warnings, target = validate(entries)
        problems = parse_problems + problems
        print(f"本地校验 {mapping_path.name}：{len(target)} 条")
        report(problems, warnings)
        if problems:
            return 2

    try:
        if mapping_path.is_file():
            subprocess.run(["scp", "-q", mapping_path.name, f"{host}:{REMOTE_TXT}"],
                           cwd=str(mapping_path.parent), check=True)
        subprocess.run(["scp", "-q", Path(__file__).name, f"{host}:{REMOTE_PY}"],
                       cwd=str(HERE), check=True)
    except FileNotFoundError:
        print("错误：找不到 scp/ssh 客户端。")
        return 8
    except subprocess.CalledProcessError as exc:
        print(f"错误：上传失败（{exc.returncode}），检查到 {host} 的 ssh 是否可用。")
        return 8

    remote = (f"HERMES_HOME={R_HOME} {R_PY} {REMOTE_PY} --mapping-file {REMOTE_TXT}"
              + (" --dry-run" if dry_run else "")
              + (" --list" if do_list else ""))
    proc = subprocess.run(["ssh", host, remote], capture_output=True,
                          encoding="utf-8", errors="replace")
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return proc.returncode


def main() -> int:
    setup_console()
    ap = argparse.ArgumentParser(description="把 doro/mapping.txt 写进网关的表情包映射")
    ap.add_argument("--mapping-file", default=str(DEFAULT_MAPPING))
    ap.add_argument("--dry-run", action="store_true", help="只校验和预览，不写入")
    ap.add_argument("--list", dest="do_list", action="store_true", help="列出线上可用 id 与场景")
    ap.add_argument("--host", default=DEFAULT_HOST, help="服务器地址，默认 hermes@8.148.73.94")
    args = ap.parse_args()

    mapping_path = Path(args.mapping_file).resolve()
    on_server = CFG.is_file() and VENV_PY.is_file()
    if on_server:
        return server_main(mapping_path, args.dry_run, args.do_list)
    return local_main(mapping_path, args.host, args.dry_run, args.do_list)


if __name__ == "__main__":
    raise SystemExit(main())
