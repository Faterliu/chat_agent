# server-mirror/

A local, reviewable copy of the Hermes deployment artefacts that live on the target
server (`hermes@8.148.73.94`). It exists so the server-side configuration can be
diffed, reviewed, and restored without logging in.

## Connecting as `hermes`, not `admin`

The sync connects as the **`hermes` service account**, because `HERMES_HOME`
(`/var/lib/hermes/.hermes`) is mode `700` and owned by `hermes`. Connecting as `admin`
cannot even traverse into it, and the tool would silently report every Hermes artefact
as `[absent]` — which is exactly what happened on its first real run.

The `/etc` and `/usr/local` paths in the manifest are world-readable (`644`/`755`), so
`hermes` can read them without `sudo`.

## What is mirrored

| Remote path | Why |
| --- | --- |
| `/var/lib/hermes/.hermes/config.yaml` | the real Hermes configuration (121 KB in v0.21.5) |
| `/var/lib/hermes/.hermes/SOUL.md` | agent personality |
| `/var/lib/hermes/.hermes/hermes-agent/.env.example` | credential-free env template |
| `/etc/sysctl.conf` | we changed `vm.swappiness` here |
| `/etc/fstab` | we added the `/swapfile` entry here |
| `/etc/systemd/system/hermes*.service`, `hermes-media-cleanup.*` | once Phase 16 writes them |
| `/etc/tmpfiles.d/hermes.conf`, `/etc/logrotate.d/hermes` | once Phases 14/15 write them |
| `/usr/local/bin/hermes-media-cleanup.sh` | once Phase 14 writes it |

The local layout mirrors the remote absolute path, so
`/var/lib/hermes/.hermes/config.yaml` lands at
`server-mirror/var/lib/hermes/.hermes/config.yaml`.

## What is deliberately NOT mirrored

- `/var/lib/hermes/.hermes/.env` — the credential file. Harmless today (`hermes setup`
  was skipped, so it holds only timeout/debug switches), but it is where API keys will
  land. Mirrored is the template, not the file.
- `{sessions,logs,memories,image_cache,audio_cache,cache}/` — runtime state and user
  conversation content.
- `node/`, `hermes-agent/`, `bin/uv` — ~2 GB of upstream code and runtimes, fully
  reproducible from the pinned commit plus the checksummed installer.

A mirrored file that turns out to contain a secret is a finding to fix **on the
server**, not a file to keep. See AGENTS.md §6 and §11.

## How to use it

```bash
# from the repository root
python tools/sync_from_server.py              # pull / update the mirror
python tools/sync_from_server.py --dry-run    # show what would be pulled
python tools/sync_from_server.py --prune      # also drop local files gone from the server
```

The sync is strictly read-only against the server: it never writes or deletes anything
on the remote host, so it cannot leave residue there.

`--host` or the `HERMES_TARGET_HOST` environment variable overrides the default target.

## Status

Verified working against the live install: 5 artefacts mirrored, 0 failures. The
remaining manifest entries are `[absent]` because the systemd units, cleanup timer, and
log rotation config do not exist yet — they arrive in Phases 14–16.
