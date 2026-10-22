#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 doro 目录里的表情包按顺序重命名成 doro_1、doro_2 …… doro_N。

默认只预览（dry-run），确认无误后加 --apply 真正改名。

排序规则（--order）：
  number （默认）先按已有的 doro_N 数字排，其余没编号的按文件名排在后面
  name           全部按文件名自然排序（tmp2 < tmp10）
  mtime          按修改时间从早到晚

安全性：
  · 两阶段改名（先改成临时名再改成目标名），不会因为目标名被占用而丢文件；
  · 每次真正改名都写一份 rename-log-<时间>.txt，里面有反向改名清单；
  · 若数字发生变化，同目录的 mapping.txt（emoji → id）和 manifest.txt（id | 文件名 | 场景）
    会自动跟着改引用，保持“哪个 emoji／说明对应哪张图”不变，并各留一份 .bak-<时间> 备份。
    不想动就加 --no-txt-rewrite。按 token 精确匹配，doro_1 不会误伤 doro_14。

注意：这里只改本地文件。要让新编号在线上生效，接着跑 sync-stickers.py --apply，
      再跑 apply-mapping.py（顺序反了会因为 id 不存在被拦下）。
"""

import argparse
import datetime
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE_EXT = {".gif", ".png", ".jpg", ".jpeg", ".webp"}
NUM_RE = re.compile(r"^doro[_-]?(\d+)$", re.IGNORECASE)


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


def natural_key(name: str) -> list:
    """自然排序键：tmp2 排在 tmp10 前面。"""
    parts = re.split(r"(\d+)", name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def scan(folder: Path) -> list[Path]:
    items = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    return sorted(items, key=lambda p: natural_key(p.name))


def order_files(files: list[Path], mode: str) -> list[Path]:
    if mode == "name":
        return sorted(files, key=lambda p: natural_key(p.name))
    if mode == "mtime":
        return sorted(files, key=lambda p: (p.stat().st_mtime, natural_key(p.name)))
    numbered, others = [], []
    for p in files:
        m = NUM_RE.match(p.stem)
        if m:
            numbered.append((int(m.group(1)), natural_key(p.name), p))
        else:
            others.append(p)
    numbered.sort(key=lambda t: (t[0], t[1]))
    return [p for _, _, p in numbered] + sorted(others, key=lambda p: natural_key(p.name))


def plan(files: list[Path], start: int) -> list[tuple[Path, Path]]:
    out = []
    for i, src in enumerate(files, start=start):
        dst = src.with_name(f"doro_{i}{src.suffix.lower()}")
        if src != dst:
            out.append((src, dst))
    return out


def id_tokens(head: str) -> tuple[list[str], list[tuple[int, str]]]:
    """把 txt 一行（去掉注释后）切成 token，返回 token 列表和每个非空 token 的位置。

    按 token 精确比对，避免 "doro_1" 误伤 "doro_14"。
    """
    tokens = re.split(r"(\s+|,|\u3001|\|)", head)
    hits = [(i, t.strip()) for i, t in enumerate(tokens) if t.strip()]
    return tokens, hits


def token_new_name(tok: str, renames: dict[str, str]) -> str | None:
    """token 若是 doro_N 或 doro_N.gif，返回改名后的写法，否则 None。"""
    suffix = Path(tok).suffix.lower()
    if suffix in IMAGE_EXT:
        stem, ext = tok[: -len(suffix)], suffix
    else:
        stem, ext = tok, ""
    if stem in renames:
        return renames[stem] + ext
    return None


def preview_txt_changes(path: Path, renames: dict[str, str]) -> list[str]:
    changes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        head = line.split("#", 1)[0]
        _, hits = id_tokens(head)
        for _, tok in hits:
            new = token_new_name(tok, renames)
            if new:
                changes.append(f"{tok} → {new}")
    return sorted(set(changes))


def rewrite_txt(path: Path, renames: dict[str, str]) -> list[str]:
    """把 txt 里的 doro_N / doro_N.gif 换成新编号，保留注释与排版，返回改动说明。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    changed: list[str] = []
    out: list[str] = []
    for line in lines:
        head, sep, comment = line.partition("#")
        tokens, hits = id_tokens(head)
        for idx, tok in hits:
            new = token_new_name(tok, renames)
            if new:
                tokens[idx] = new
                changed.append(f"{tok} → {new}")
        out.append("".join(tokens) + sep + comment)
    if changed:
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{ts}"))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return sorted(set(changed))


def main() -> int:
    setup_console()
    ap = argparse.ArgumentParser(description="把 doro 目录里的表情包重命名成 doro_1..doro_N")
    ap.add_argument("--dir", default=str(HERE), help="表情包目录，默认脚本所在目录")
    ap.add_argument("--apply", "-a", action="store_true", help="真正改名（默认只预览）")
    ap.add_argument("cmd", nargs="?", choices=("apply", "preview"), default=None,
                    help="也可以直接写 apply（等价于 --apply）或 preview")
    ap.add_argument("--start", type=int, default=1, help="起始编号，默认 1")
    ap.add_argument("--order", choices=("number", "name", "mtime"), default="number")
    ap.add_argument("--no-txt-rewrite", "--no-mapping-rewrite", dest="no_txt_rewrite",
                    action="store_true",
                    help="不要自动改 mapping.txt / manifest.txt 里的 id 与文件名")
    args = ap.parse_args()

    folder = Path(args.dir).resolve()
    if not folder.is_dir():
        print(f"错误：目录不存在 {folder}")
        return 2

    files = scan(folder)
    if not files:
        print(f"{folder} 里没有表情包（支持 {', '.join(sorted(IMAGE_EXT))}）")
        return 0

    ordered = order_files(files, args.order)
    pairs = plan(ordered, args.start)
    width = max(len(p.name) for p in files)

    print(f"目录：{folder}")
    print(f"共 {len(files)} 个文件，排序方式：{args.order}")
    print()
    if not pairs:
        print("已经是从 doro_%d 开始的连续编号，不需要改名。" % args.start)
        return 0

    print(f"{'原名'.ljust(width)}  →  新名")
    for src, dst in pairs:
        print(f"{src.name.ljust(width)}  →  {dst.name}")
    print()

    # 目标名冲突检查：不能撞上“本目录里存在但不在本次列表里”的文件
    sources = {p for p in files}
    clash = [dst for _, dst in pairs if dst.exists() and dst not in sources]
    if clash:
        print("错误：以下目标名已被别的文件占用，先手动处理：")
        for c in clash:
            print("  -", c.name)
        return 3

    renames = {src.stem: dst.stem for src, dst in pairs}
    txt_files = [p for p in (folder / "mapping.txt", folder / "manifest.txt") if p.is_file()]
    previews: dict[Path, list[str]] = {}
    if not args.no_txt_rewrite:
        for p in txt_files:
            changes = preview_txt_changes(p, renames)
            if changes:
                previews[p] = changes
    for p, changes in previews.items():
        print(f"{p.name} 里需要跟着改的引用：{len(changes)} 处")
        for line in changes:
            print("  ", line)
        print()

    apply_now = bool(args.apply or args.cmd == "apply")
    if not apply_now:
        print("这是预览。确认无误后真正改名：")
        print(f"  python {Path(__file__).name} apply" if folder == HERE
              else f"  python {Path(__file__).name} --dir \"{folder}\" apply")
        return 0

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp_pairs = []
    for i, (src, dst) in enumerate(pairs):
        tmp = src.with_name(f".renaming-{ts}-{i}{src.suffix.lower()}")
        src.rename(tmp)
        tmp_pairs.append((tmp, dst))
    for tmp, dst in tmp_pairs:
        tmp.rename(dst)

    log = folder / f"rename-log-{ts}.txt"
    body = [f"# {ts} 重命名记录（排序：{args.order}）", "", "## 正向", ""]
    body += [f"{src.name} -> {dst.name}" for src, dst in pairs]
    body += ["", "## 反向（按此顺序执行即可还原）", ""]
    body += [f"{dst.name} -> {src.name}" for src, dst in reversed(pairs)]
    log.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"已改名 {len(pairs)} 个文件，记录：{log.name}")

    if not args.no_txt_rewrite:
        for p in txt_files:
            changed = rewrite_txt(p, renames)
            if changed:
                print(f"{p.name} 已跟着改 {len(changed)} 处（备份 {p.name}.bak-*）")
            else:
                print(f"{p.name} 无需改动")

    print()
    print("提醒：这只是本地文件。要让新编号在线上生效，接着跑")
    print("      python doro\\sync-stickers.py --apply   （上传新图 + 重建 manifest）")
    print("      再跑 python doro\\apply-mapping.py      （把映射写进配置）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
