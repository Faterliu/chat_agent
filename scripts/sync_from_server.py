#!/usr/bin/env python3
"""Mirror the Hermes deployment artefacts from the target server into ./documents/server-mirror.

Design constraints (see AGENTS.md / documents/TASK.md):
  * Read-only against the server. This script never writes to or deletes anything
    on the remote host, so it cannot leave residue there.
  * Only persistent, reviewable artefacts are mirrored: systemd units, tmpfiles
    rules, logrotate config, Hermes config, and helper scripts.
  * Transient data is deliberately excluded -- /var/lib/hermes/media holds live
    media and must never be mirrored or committed.
  * Secrets are never mirrored. If a mirrored file turns out to contain a
    credential, that is a finding to report, not a file to keep.

Usage:
    <python> scripts/sync_from_server.py            # update the local mirror
    <python> scripts/sync_from_server.py --dry-run  # report only, copy nothing
    <python> scripts/sync_from_server.py --prune    # also drop local files gone remote

Exit codes: 0 = ok (even if some paths are absent), 1 = transport/usage failure.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Connect as the `hermes` service account, not `admin`.
#   * HERMES_HOME (/var/lib/hermes/.hermes) is mode 700 and owned by hermes, so
#     `admin` cannot even traverse into it -- using admin silently reports every
#     Hermes artefact as [absent].
#   * The /etc and /usr/local paths in the manifest are world-readable (644/755),
#     so hermes can read them without sudo.
# Override with --host or HERMES_TARGET_HOST if the layout ever changes.
DEFAULT_HOST = "hermes@8.148.73.94"
REPO_ROOT = Path(__file__).resolve().parent.parent
MIRROR_ROOT = REPO_ROOT / "documents" / "server-mirror"

# Remote paths that make up "the program on the server".
# Absent paths are reported and skipped -- they simply are not deployed yet.
MANIFEST: list[str] = [
    # systemd units and timers (AGENTS.md 19, documents/TASK.md Phase 16 / 14.1)
    # NOTE: actual unit filenames are not known until Phase 16 writes them.
    "/etc/systemd/system/hermes.service",
    "/etc/systemd/system/hermes-media-cleanup.service",
    "/etc/systemd/system/hermes-media-cleanup.timer",
    # age-based media cleanup (AGENTS.md 15, documents/TASK.md Phase 14)
    "/etc/tmpfiles.d/hermes.conf",
    # bounded logs (AGENTS.md 20, documents/TASK.md Phase 15)
    "/etc/logrotate.d/hermes",
    # helper scripts installed on the host
    "/usr/local/bin/hermes-media-cleanup.sh",
    # --- real Hermes artefacts, confirmed on-host in Phase 3.3 (see documents/DEPLOYMENT_NOTES.md 10) ---
    # HERMES_HOME is /var/lib/hermes/.hermes for the unprivileged hermes account.
    "/var/lib/hermes/.hermes/config.yaml",
    "/var/lib/hermes/.hermes/SOUL.md",
    # the credential-free template, mirrored instead of .env
    "/var/lib/hermes/.hermes/hermes-agent/.env.example",
    # --- host files this deployment has modified, so the footprint is restorable ---
    # Both are non-secret: swappiness tuning and the /swapfile mount entry.
    "/etc/sysctl.conf",
    "/etc/fstab",
]

# Deliberately never mirrored, even though it lives under HERMES_HOME:
#   /var/lib/hermes/.hermes/.env          -> credential file (harmless today because
#                                            `hermes setup` was skipped, but it is
#                                            where API keys will land)
#   /var/lib/hermes/.hermes/{sessions,logs,memories,image_cache,audio_cache,cache}
#                                        -> runtime state and user conversation data
#   /var/lib/hermes/.hermes/node, hermes-agent/**, bin/uv
#                                        -> 2 GB of upstream code and runtimes that are
#                                            reproducible from the pinned commit + installer

EXCLUDED_NAMES = {".git", "__pycache__", "node_modules"}


def run(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def remote_exists(host: str, remote: str) -> bool:
    res = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host,
               f"test -e {shell_quote(remote)}"])
    return res.returncode == 0


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def remote_kind(host: str, remote: str) -> str:
    res = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host,
               f"if [ -d {shell_quote(remote)} ]; then echo dir; "
               f"elif [ -f {shell_quote(remote)} ]; then echo file; "
               f"else echo other; fi"])
    return res.stdout.strip() or "other"


def copy_remote(host: str, remote: str, local: Path, kind: str) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    if kind == "dir":
        local.mkdir(parents=True, exist_ok=True)
        src = f"{host}:{remote}/."
        res = run(["scp", "-r", "-p", "-q", src, str(local)])
    else:
        res = run(["scp", "-p", "-q", f"{host}:{remote}", str(local)])
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or f"scp failed for {remote}")


def prune_local(mirror_root: Path, needed: set[str]) -> list[str]:
    """Remove local files under etc/ usr/ home/ var/ that no longer exist remotely."""
    removed: list[str] = []
    if not mirror_root.exists():
        return removed
    for child in sorted(mirror_root.iterdir()):
        if child.name in {"README.md", ".gitignore"}:
            continue
        if child.is_dir():
            for path in sorted(child.rglob("*"), reverse=True):
                if any(part in EXCLUDED_NAMES for part in path.parts):
                    continue
                if path.is_file() and path.name not in needed:
                    path.unlink()
                    removed.append(str(path.relative_to(mirror_root)))
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("HERMES_TARGET_HOST", DEFAULT_HOST))
    ap.add_argument("--dry-run", action="store_true", help="report only, copy nothing")
    ap.add_argument("--prune", action="store_true",
                    help="delete local mirror files that no longer exist on the server")
    args = ap.parse_args()

    host = args.host
    print(f"target : {host}")
    print(f"mirror : {MIRROR_ROOT}")
    print(f"mode   : {'dry-run' if args.dry_run else 'sync'}"
          f"{' + prune' if args.prune else ''}")
    print()

    probe = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", host, "true"])
    if probe.returncode != 0:
        print(f"ERROR: cannot reach {host} over SSH: {probe.stderr.strip()}", file=sys.stderr)
        return 1

    copied, skipped, failed = [], [], []
    mirrored_names: set[str] = set()

    for remote in MANIFEST:
        local = MIRROR_ROOT / remote.lstrip("/")
        if not remote_exists(host, remote):
            skipped.append(remote)
            print(f"  [absent]  {remote}")
            continue
        kind = remote_kind(host, remote)
        print(f"  [{kind:^6}]  {remote}  ->  {local.relative_to(REPO_ROOT)}")
        if args.dry_run:
            copied.append(remote)
            mirrored_names.add(local.name)
            continue
        try:
            copy_remote(host, remote, local, kind)
            copied.append(remote)
            mirrored_names.add(local.name)
        except RuntimeError as exc:
            failed.append((remote, str(exc)))
            print(f"            FAILED: {exc}", file=sys.stderr)

    if args.prune and not args.dry_run:
        removed = prune_local(MIRROR_ROOT, mirrored_names)
        for rel in removed:
            print(f"  [pruned]  {rel}")

    print()
    print(f"mirrored : {len(copied)}")
    print(f"not yet  : {len(skipped)}")
    print(f"failed   : {len(failed)}")
    if skipped:
        print("\nAbsent paths are simply not deployed yet. The systemd units, cleanup")
        print("timer, tmpfiles rule, and logrotate config appear in Phases 14-16.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
