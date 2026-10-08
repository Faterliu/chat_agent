from pathlib import Path
import difflib
import hashlib

root=Path(__file__).resolve().parent.parent
work=root/"staging/social-work"
chunks=[]
for p in sorted((work/"deployed-309").rglob("*.py")):
    name=p.relative_to(work/"deployed-309").as_posix()
    chunks.append(f"diff --git a/{name} b/{name}\n")
    chunks.extend(difflib.unified_diff(p.read_text(encoding="utf-8").splitlines(keepends=True),
                  (work/"updated"/name).read_text(encoding="utf-8").splitlines(keepends=True),
                  fromfile=f"a/{name}",tofile=f"b/{name}"))
out=root/"patches/hermes-v0.21.5-social-clock-fix.patch"
out.write_text("".join(chunks),encoding="utf-8",newline="\n")
print("clock_fix_sha256="+hashlib.sha256(out.read_bytes()).hexdigest())
