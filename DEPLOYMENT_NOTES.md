# DEPLOYMENT_NOTES.md

Project: Hermes QQ + Weixin Lightweight Multimodal Agent
Scope of this file: verified facts, real commands, and deviations. No secrets.
Status: **Phases 0–7 complete** · QQ live (DM + group @ mention) · persona 云白/小云 v1.2.0 · one core patch applied (§11.17) · memory architecture audited, 4 new open items (§14) · next: Phase 8 (Weixin)
Last updated: 2026-09-29

---

## 1. Execution context

- Operator workstation: Windows (win32). All host-level work is performed **over SSH to the target host**. No package, swap, systemd, or `/var/lib` change is made on the local workstation.
- Remote entry point: `ssh admin@8.148.73.94`
  - Authentication: `publickey` (no password prompt; `BatchMode=yes` succeeds)
  - Client key: `C:\Users\liuzhuo\.ssh\id_ed25519` — ED25519, `SHA256:2Uf6Uz83hwbZVsxwG2aMcHAl3QNMkK+Pw3rynXNLXkc`
  - Client config: `C:\Users\liuzhuo\.ssh\config` contains a host entry for `8.148.73.94`
  - Server host key: ED25519 `SHA256:ITJw4b4dQxd0UIXekwdSzIoGBBnd+1j7bfsNwfVd8qw`
  - Remote `admin` = `uid=1000(admin) gid=1000(admin)`; passwordless sudo `(ALL) NOPASSWD: ALL`
- Local mirror of server artefacts: `server-mirror/`, driven by `tools/sync_from_server.py`. Read-only against the server; excludes live media and any secret-bearing file.

---

## 2. Target host baseline (Phase 0)

| Item | Observed | Acceptance |
| --- | --- | --- |
| Execution target confirmed | Commands ran on `8.148.73.94`, not the workstation | pass |
| Hostname | `iZn4aetqy7dj6wsl6t9c7hZ` (Aliyun ECS naming) | — |
| OS | Ubuntu 24.04.2 LTS (Noble Numbat) | pass |
| Kernel | `6.8.0-63-generic` x86_64 | — |
| CPU | 2 vCPU (`nproc` = 2) | pass |
| RAM | total 1.6 GiB visible; 481 MiB used; ~1.1 GiB available | **pass with caveat — see §3 and §7.1** |
| Disk | `/dev/vda3` 40 G; 29 G available after Phase 1 | pass |
| Time | `Asia/Shanghai` (CST +0800), NTP active | pass |
| DNS / egress | github 200, registry.npmjs.org 200, pypi.org 200 | pass (§7.3) |
| Hermes installed | not found | matches AGENTS.md §0 |

---

## 3. CRITICAL — the target host is a live, shared, multi-purpose server

This was **not** discoverable from `TASK.md` Phase 0's checklist and materially changes the deployment's risk profile. AGENTS.md §3 and §21 assume a host dedicated to Hermes. That assumption does not hold.

Confirmed running, in production, on this host:

| Service | Detail |
| --- | --- |
| `nginx.service` | listening on `0.0.0.0:80` and `0.0.0.0:443`, plus internal `127.0.0.1:8080/8081`; 2 workers as `www-data` |
| nginx sites enabled | `000-catchall`, `codex-relay`, `main-site.conf`, `site-a.conf`, `site-b.conf`, `updates.yinxingye.space.conf` |
| `main-site-editor.service` | `/usr/bin/python3 /opt/main-site-editor/server.py`, user `editorapi`, listening `127.0.0.1:8787`. Unit hardening notes state it invokes a root helper via `sudo`, and writes to `/var/www/main-site`, `/opt/leleo-home-page/public`, `/var/backups/main-site-editor`, `/var/lib/main-site-editor` |
| `prune-recorder-updates.timer` + `.service` | every 5 min, keeps the 3 newest APK versions under `/var/www/updates/apps`. Operator already uses the host-level systemd-timer pattern that AGENTS.md §5 permits |
| `frps.service` | reverse-proxy tunnel, unit file mode `600` — **not read, assumed to contain a credential** |
| Aliyun stack | `aegis.service`, `AssistDaemon.service`, `aliyun.service`, `cloudmonitor.service` (AliYunDun ~68 MB + argusagent ~14 MB) |
| Base system extras | `tuned`, `packagekitd`, `multipathd`, `udisks2`, `ModemManager` |

Supporting assets under `/opt`: `frp` (20 M), `imgtool` (21 M), `leleo-home-page` (165 M), `main-site-editor` (32 K).

### Consequences

1. **RAM is shared.** Hermes would compete with a live website, a write API, a tunnel, and the Aliyun monitoring stack for ~1.1 GiB of headroom. AGENTS.md §21's targets must be re-based against "headroom on a shared host", not "total RAM of a dedicated box".
2. **Blast radius.** A gateway that misbehaves can degrade or take down live sites. Phase 16's `Restart=always` and Phase 20's `sudo reboot` are no longer routine operations on this host.
3. **Phase 22 acceptance is not satisfiable as written.** "2C2G server remains stable" cannot be verified without an explicit statement that the pre-existing services keep working.
4. **Isolation is now a requirement, not a nicety.** A dedicated service user (matching the host's existing `editorapi` precedent) and explicit resource limits are advisable before anything is installed.

### Resolution

The operator chose to **deploy on this host with a dedicated service account**, not to relocate. See §8 for what was prepared.

---

## 4. Phase 1 — Base system: complete

### 1.1 System update — done

```bash
sudo -E apt-get update
sudo -E apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold upgrade
```

- 80 packages upgraded; `0` newly installed; `2` held back (`cloud-init`, `fwupd`).
- rc = 0. No web-facing service was restarted.
- `fwupd.service` and `fwupd-refresh.service` failed to restart. Expected on this virtualised host — no hardware firmware to manage. Not a functional concern.

### 1.2 Minimal dependencies — done

```bash
sudo -E apt-get -y install curl wget git unzip ffmpeg sqlite3 htop ca-certificates
```

Already present: `curl` 8.5.0, `wget` 1.21.4, `git` 2.43.0, `htop` 3.3.0, `ca-certificates` 20260601.
Newly installed: `unzip` 6.00, `ffmpeg` 6.1.1, `sqlite3` 3.45.1 — plus **127 dependency packages, 294 MB on disk**.

Acceptance:

- [x] `ffmpeg -version` works → `ffmpeg version 6.1.1-3ubuntu5`
- [x] `sqlite3 --version` works → `3.45.1`
- [x] no Chromium installed as part of this phase

Note for the record: Ubuntu's `ffmpeg` package pulls in GTK3, icon themes, and Mesa VA/VDPAU drivers — heavier than the "minimal dependencies" label suggests. It is still the correct and permitted choice per AGENTS.md §18, and none of it runs resident.

---

## 5. Phase 2 — Swap: complete

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

| Item | Value |
| --- | --- |
| File | `/swapfile`, `-rw-------`, `root:root`, 2147483648 bytes |
| UUID | `0a00fe58-ab98-4618-abda-e99d14036541` |
| Depth | 2 GiB active, 0 B used |
| fstab | `/swapfile none swap sw 0 0` appended (idempotent guarded) |

Persistence was **proven without a reboot**, which isolates the fstab wiring from Phase 20:

```bash
sudo swapoff /swapfile          # no swap active
sudo swapon --all               # re-reads /etc/fstab
swapon --show                   # /swapfile file 2G 0B -2
sudo systemctl daemon-reload
```

Acceptance:

- [x] swap appears in `free -h` → `Swap: 2.0Gi`
- [x] swap survives reboot — fstab entry present and verified to mount via `swapon --all`

Note: `/etc/sysctl.conf` line 1 sets `vm.swappiness = 0`. This pre-existed; it was not changed. See §7.4.

---

## 6. Residue audit and cleanup (requirement: leave nothing extra on the server)

### 6.1 Backups taken BEFORE any deletion

Nothing was deleted until a verified local copy existed. Byte-for-byte verification: remote 63 files / 364 147 bytes vs local 63 files / 364 147 bytes, with identical `.git` pack sizes.

| Local destination | Source | Size |
| --- | --- | --- |
| `backups/retired-chat_bot/` | `/home/admin/chat_bot` | 364 KB, 63 files, includes `.git` |
| `backups/tmp-scratch/` | 8 scratch files from `/tmp` | 37 KB |

`chat_bot` was additionally recoverable independently: its remote is `https://gitee.com/liuzhuo0312/chat_bot.git`, working tree clean, 2 commits (`fb9e53b 搭建框架`, `6454d8d Initial commit`).

### 6.2 Removed from the server (irreversible, operator-confirmed)

| Target | Note |
| --- | --- |
| `/home/admin/chat_bot/` | retired prior project — see §7.2 |
| `/tmp/.org.chromium.Chromium.*` (7 dirs) | stale headless-Chromium state |
| `/tmp/puppeteer_dev_chrome_profile-*` (4 dirs, ~21 MB) | stale Puppeteer state |
| `/tmp/pw/` (55 MB) | stale browser-automation workspace |
| `/tmp/node-compile-cache/` (2.6 MB), `/tmp/__pycache__/` (36 K) | regenerable caches |
| `/tmp/shot-*.png` (5 files, ~6 MB) | stale screenshots |
| `/tmp/cfg-live.json`, `/tmp/cfg-src.json`, `/tmp/_diag-footer.sh`, `/tmp/_diag-wrap-rule.sh`, `/tmp/_new-ProjectsSection.vue`, `/tmp/_patch-app-less.py`, `/tmp/updates-yinxingye-current.conf`, `/tmp/camera-sync-result.txt` | stale editor scratch — all copied to `backups/tmp-scratch/` first |
| `/var/cache/apt/archives/*` | `apt-get clean`; 177 M → 44 K, regenerable `.deb` cache only |

### 6.3 Deliberately NOT removed from `/tmp`

Held open by a running process, or system runtime state. Deleting these would break live services:

- `/tmp/aliyun_assist_service.sock` and `/tmp/AliyunAssistClientSingleLock.lock` — held open by `aliyun-service` (PID 781), confirmed via `lsof`
- `/tmp/systemd-private-*` (6 dirs) — per-unit `PrivateTmp` namespaces for chrony, main-site-editor, ModemManager, polkit, systemd-logind, systemd-resolved
- `/tmp/.X11-unix`, `/tmp/.ICE-unix`, `/tmp/.XIM-unix`, `/tmp/.font-unix` — live X sockets
- `/tmp/snap-private-tmp` — snap runtime state

Post-cleanup verification confirmed all of the above still present and `aliyun.service` still `active`.

### 6.4 Left alone on purpose, outside the requested scope

`/home/admin/my_images/` (2.1 M), `/home/admin/myweb/` (16 K), `/home/admin/.{claude,codex,copilot,dotnet,nvm,npm,cache,config,local,pki}`, `/opt/{frp,imgtool,leleo-home-page,main-site-editor}`. These belong to other projects and were not in scope. `/etc/systemd/system/frps.service` is mode `600` and was **never read**.

---

## 7. Findings and decisions

Operator decisions taken 2026-09-29 are recorded inline; the actions they produced are in §8.

### 7.1 RAM is 1.6 GiB and shared

Thresholds in AGENTS.md §21 and TASK.md Phase 17 were re-based to the measured host and are now: idle < 600 MB, normal chat < 900 MB, bursts < 1.1 GB, investigate above ~1.3 GB or on sustained swap-in.

**Decision: deploy on this host using a dedicated service account for isolation, rather than relocating to a clean machine.** Consequence carried forward: the AGENTS.md §21 numbers measure *total* host usage, which now includes the pre-existing `nginx`, `main-site-editor`, `frps`, and Aliyun agents. Hermes' own budget is therefore strictly smaller than the headroom those numbers imply. A per-unit `MemoryMax` will be set when the gateway unit is written in Phase 16.

### 7.2 A prior WeChat bot project existed at `/home/admin/chat_bot`

Contents: `wechat_bot_project_plan.md` (22.9 K), `agent.md`, `server_brain/`, `windows_client/`, `docs/`, `requirements.txt`, `readme.md`, `.git/` (branch activity as recent as 2026-09-01). Mtime of the plan itself is 2026-07-04.

This was an earlier attempt at the same objective.

**Decision: retire it.** Backed up to `backups/retired-chat_bot/` (verified, byte-for-byte) and to Gitee, then deleted from the server. It is not a component of this deployment and must not be resurrected by accident.

### 7.3 PyPI egress latency

`https://pypi.org` returned 200 but took 7.75 s (github 0.93 s, npm 0.73 s). Relevant when verifying the install method in Phase 3.1.

### 7.4 `vm.swappiness = 0`

Was set explicitly in `/etc/sysctl.conf` line 1. On a 1.6 GiB host shared with live services, `swappiness = 0` biased the kernel toward reclaiming page cache and eventually OOM-killing rather than swapping out — precisely the failure mode the Phase 2 swap file exists to soften.

**Decision: change to 10.** Applied and persisted; see §8.2. This is a host-wide parameter and therefore also affects the pre-existing projects — a small non-zero value is the conservative choice.

### 7.5 Ports

80 and 443 are held by nginx. Hermes inbound for QQ is long-poll/outbound; Weixin may require an inbound webhook reachability path. No port conflict was assumed or introduced. Confirm the Weixin adapter's actual inbound mechanism during Phase 4 before designing anything that needs a public port.

### 7.6 Existing host-level timer precedent

`prune-recorder-updates.timer` shows the operator already uses systemd timers for housekeeping under `/var/www`. Phase 14.1's cleanup will follow the same pattern — a dedicated timer, not Hermes Cron. Consistency is good; this also confirms the §5 scheduler boundary is workable here.

---

## 8. Host preparation applied (isolation)

### 8.1 Dedicated service account

Created so the gateway never runs as `admin` (uid 1000) on a host that also serves live sites.

```bash
sudo useradd --system --create-home --home-dir /var/lib/hermes \
  --shell /bin/bash --comment "Hermes QQ+Weixin gateway service account" hermes
sudo passwd -l hermes
sudo mkdir -p /var/lib/hermes/media
sudo chown -R hermes:hermes /var/lib/hermes
sudo chmod 750 /var/lib/hermes /var/lib/hermes/media
```

Verified state:

| Property | Value |
| --- | --- |
| Identity | `uid=993(hermes) gid=984(hermes)`, member of no group but its own |
| Home | `/var/lib/hermes`, mode `750`, owner `hermes:hermes` |
| Media cache | `/var/lib/hermes/media`, mode `750` — matches AGENTS.md §15's preferred path |
| Password | locked (`passwd -S` → `hermes L`) |
| SSH material | `.ssh` mode `700`, `authorized_keys` mode `600`, both `hermes:hermes`. Operator's `id_ed25519` public key (`SHA256:2Uf6Uz83hwbZVsxwG2aMcHAl3QNMkK+Pw3rynXNLXkc`) added 2026-09-29 at operator request — key-only login works, verified |
| Privileges | no sudo, no supplementary groups |

`/var/lib/hermes` doubles as the home directory and the AGENTS.md §15 media root, so there is a single obvious place for config, sessions, and media.

The account keeps `/bin/bash` as its shell and now accepts a **public key only** — the password stays locked, so key auth is the sole path in. `sudo -u hermes -s /bin/bash` also works for maintenance from `admin`.

Key login verified: `ssh hermes@8.148.73.94 'id'` → `uid=993(hermes)`, `HOME=/var/lib/hermes`.

### 8.2 `vm.swappiness`

```bash
sudo cp /etc/sysctl.conf /etc/sysctl.conf.bak-before-hermes
sudo sed -i "s/^vm\.swappiness.*/vm.swappiness = 10/" /etc/sysctl.conf
sudo sysctl -w vm.swappiness=10 && sudo sysctl -p
```

- Only `/etc/sysctl.conf` set this key; no `/etc/sysctl.d/*` override existed.
- Runtime and persisted value both verified as `10` (`sysctl vm.swappiness`, `/proc/sys/vm/swappiness`).
- Original file preserved at `/etc/sysctl.conf.bak-before-hermes`.

### 8.3 Impact check on the pre-existing workload

Performed because this is a live host, not a lab box.

| Check | Result |
| --- | --- |
| `nginx.service` | active |
| `main-site-editor.service` | active |
| `prune-recorder-updates.timer` | active |
| `ssh.service` | active |
| `aliyun.service` | active |
| Running service count | 24. The only difference from the pre-deployment count of 25 is `packagekit.service`, a D-Bus-activated transient that the `apt` run had started and which has since exited. No real service was lost |
| Memory | 484 MiB used of 1613 MiB; swap 2047 MiB / 0 B used |

### 8.4 Not yet applied

`MemoryMax` / `TasksMax` on the gateway unit, and a disk quota or size cap on the media cache. Both belong with the systemd unit in Phase 16, once the real gateway command is known. Recorded here so they are not forgotten — on a shared host they matter more than they would on a dedicated one.

---

## 9. Phase 3.1 — Hermes source, version, and verified installation method

### 9.1 Authoritative source — established

| Field | Value |
| --- | --- |
| Project | Hermes Agent, by Nous Research |
| Repository | `https://github.com/NousResearch/hermes-agent` |
| Official documentation | `https://hermes-agent.nousresearch.com/docs/` |
| Official installer endpoint | `https://hermes-agent.nousresearch.com/install.sh` |

Both AGENTS.md §3's illustrative URL and TASK.md's example turned out to point at real endpoints, but neither had been verified. They now have been.

### 9.2 Selected release — pinned to a tag

| Field | Value |
| --- | --- |
| Tag | `v2026.9.24` |
| Version | Hermes Agent **v0.21.5** |
| Annotated tag object | `e3dd27ee2d8b011737a4eea8e3eb3d711ab78690` |
| **Commit to pin (`--commit`)** | **`f97608f178d1ffeca59860195ab7da295f7c8e5f`** |
| Published | 2026-09-24 |
| Prerelease | no |
| Tag signature | unsigned |

Pinning rationale: the installer has **no `--tag` flag**; it pins via `--commit <SHA>` and accepts only a **full 40-character** SHA. `v2026.9.24` is an annotated tag object, so it must be dereferenced to the commit above. Deploying the tag rather than `main` gives a stable, reviewable target and matches the release note's own "measured at commit" value.

### 9.3 Installation method — verified against this exact revision

The installer was fetched from the pinned tag, stored locally with a checksum, and will be executed **from disk** rather than piped from `curl | bash`, so the installed revision and the reviewed script cannot drift apart.

| Field | Value |
| --- | --- |
| Source URL | `https://raw.githubusercontent.com/NousResearch/hermes-agent/v2026.9.24/scripts/install.sh` |
| Local copy | `installer/install-v2026.9.24.sh` |
| Size / lines | 175 101 bytes / 3 964 lines |
| **SHA-256** | **`2017ddf0cc7bc6cfb70d40dc9fba1d916f47dbcccf5fe73bdee2cf93a11262af`** |
| Documented one-liner | `curl -fsSL https://hermes-agent.nousresearch.com/install.sh \| bash` |

Flags confirmed present by grepping the downloaded file (not from documentation):

| Flag | Purpose |
| --- | --- |
| `--skip-browser` (alias `--no-playwright`) | **skip Playwright/Chromium install** — the flag TASK.md asked us to verify |
| `--skip-computer-use` | skip `cua-driver` (Computer Use toolset) |
| `--commit <SHA>` | pin to a commit; full 40-char SHA required, abbreviations rejected |
| `--force-commit` | apply `--commit` even if it rolls the install backwards |
| `--branch <NAME>` | branch to clone, default `main` |
| `--non-interactive` | suppress prompts |
| `--skip-setup` | skip the setup wizard |
| `--no-venv`, `--no-skills` | skip venv handling / skills install |
| `--hermes-home <DIR>`, `--dir <DIR>` | relocate `HERMES_HOME` / install dir |
| `--json` | machine-readable result |

Also present: `--include-desktop`, `--manifest`, `--stage`, `--ensure`, `-h`/`--help`.

**Planned invocation (not yet executed)** — run as the unprivileged `hermes` account:

```bash
bash installer/install-v2026.9.24.sh \
  --skip-browser \
  --skip-computer-use \
  --commit f97608f178d1ffeca59860195ab7da295f7c8e5f \
  --non-interactive
```

`git`, `curl`, and `xz` must be on the invoker's PATH — all three are (see §9.4).

### 9.4 Target-host compatibility — measured on the real machine

Prerequisites, all satisfied:

| Requirement | Host state |
| --- | --- |
| `git` | 2.43.0 ✅ |
| `curl` | 8.5.0 ✅ |
| `xz-utils` | 5.4.5 ✅ — required because the installer unpacks Node as a `.tar.xz` |
| `g++` / build-essential | 13.3.0 ✅ — only needed for the desktop app, present anyway |

What the installer will add: `uv`, Python 3.11 (uv-managed — the host's system Python is 3.12.3), **Node 26**, and `ripgrep`. `ffmpeg` is already installed.

**Node version gate — a managed Node download will be triggered.** The installer accepts an existing system Node only at 22.22+, 24.11+, or ≥26. The host has **v18.19.1**, which fails, so the installer downloads a Hermes-managed Node into `HERMES_HOME`. That is ~50 MB of disk and *not* a resident process — but it is a deviation from AGENTS.md §3's "extra Node.js … unless strictly required", since Node exists upstream for browser automation and the WhatsApp bridge, both of which we are disabling. It is dead weight, not a functional need.

### 9.5 Expected install layout (unprivileged user)

| Item | Path |
| --- | --- |
| Code | `/var/lib/hermes/.hermes/hermes-agent/` |
| Launcher | `/var/lib/hermes/.local/bin/hermes` |
| Data / config | `/var/lib/hermes/.hermes/` (`config.yaml`) |

This is the documented per-user layout, because the install runs as `hermes`, not root. It does **not** match AGENTS.md §15's suggested `/var/lib/hermes/media/`; the media path must be reconciled in Phase 14 once the real cache location is known.

### 9.6 Pre-flight gaps — must be closed before the installer runs

#### Gap 1 — BLOCKING: PyPI is effectively unusable from this host

`uv sync` has to pull a large dependency set from an index. Measured:

| Endpoint | Result |
| --- | --- |
| `pypi.org/simple/` | **connection timed out after 12 s** (46 MB index never completed) |
| `pypi.org/simple/requests/` | 200 but **8.9 KB/s** — 9.3 s for 82 KB |
| `files.pythonhosted.org` | reachable (404 on root, which is expected) |
| `mirrors.aliyun.com/pypi/simple/` | 200, 533 KB/s on the index — 6.4 MB in 12 s, would need ~85 s |
| **`pypi.tuna.tsinghua.edu.cn/simple/`** | **200, 20.7 MB/s** — full 45 MB index in 2.2 s |
| `mirrors.cloud.aliyuncs.com/pypi/simple/` | TLS certificate name mismatch — unusable |

At 8.9 KB/s the install cannot complete. **A PyPI mirror is required.** Recommendation: Tsinghua TUNA via `UV_DEFAULT_INDEX`, plus `PIP_INDEX_URL` for the pip fallback path. This changes the package source, so it needs a decision (see §9.8).

#### Gap 2 — `~/.local/bin` is not on the `hermes` account's PATH

Its login PATH is `/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin`, so the installer's launcher at `/var/lib/hermes/.local/bin/hermes` will not resolve. Two documented fixes; the symlink is better here because systemd never reads `.bashrc`:

```bash
sudo ln -s /var/lib/hermes/.hermes/hermes-agent/venv/bin/hermes /usr/local/bin/hermes
```

#### Gap 3 — boot persistence needs an explicit choice

`/var/lib/systemd/linger/` is empty and `hermes` has no user session. A user-level gateway service will **not** start at boot until `sudo loginctl enable-linger hermes` is run. The alternative is `sudo hermes gateway install --system` (boot-time system service). Decide in Phase 16; either way it is a one-liner.

#### Gap 4 — good news: no root is needed on the install path

Playwright's `--with-deps` is the only step in the installer that genuinely requires root. `--skip-browser` avoids it entirely, so the whole installation runs as the unprivileged `hermes` account. This is precisely the "Non-Sudo / System Service User Installs" pattern the official docs describe.

### 9.7 Expectations to verify on-host in Phase 3.3 / 4

Documentation-derived for v0.21.5. Per AGENTS.md §17 these are **expectations, not facts** until the installed CLI confirms them:

| Item | Expected |
| --- | --- |
| Weixin adapter / toolset | `hermes-weixin` |
| QQ adapter / toolset | `hermes-qqbot` (official QQ API v2) |
| Config file | `~/.hermes/config.yaml` |
| Platform enable/disable | `platforms.weixin.enabled: false` overrides env credentials |
| Gateway commands | `hermes gateway` / `install` / `setup` / `start` / `stop` / `status` |
| Diagnostics | `hermes doctor` |
| Built-in memory | `MEMORY.md` + `USER.md` — matches AGENTS.md §11 |
| Media cache path | **not yet confirmed** — resolve in Phase 14 before wiring the cleanup timer |
| Memory providers (V2 candidates) | Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, Supermemory |

### 9.8 Decision required before Phase 3.2

**Which PyPI index should `uv` use?** Recommendation: Tsinghua TUNA, `https://pypi.tuna.tsinghua.edu.cn/simple`. Rationale: 2300× the throughput of the official index from this host, it is a long-standing university-operated public mirror, and the alternative cloud-provider mirror fails TLS on the hostname. Final choice rests with the operator because it changes where Python packages are sourced from.

**Decision taken: Tsinghua TUNA.**

### 9.9 Phase 3.2 — installation executed

Run as the unprivileged `hermes` account, from the checksummed local copy, with the mirror injected via environment. Duration 6 m 5 s, **exit code 0**.

```bash
export UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn
bash install-v2026.9.24.sh --skip-browser --skip-computer-use \
  --commit f97608f178d1ffeca59860195ab7da295f7c8e5f --non-interactive
```

Pre-flight integrity check on the server confirmed the uploaded script's SHA-256 equalled `2017ddf0cc7bc6cfb70d40dc9fba1d916f47dbcccf5fe73bdee2cf93a11262af` — the reviewed script and the executed script are byte-identical.

What the installer did, verbatim from its output:

| Step | Result |
| --- | --- |
| managed `uv` | 0.12.20 → `/var/lib/hermes/.hermes/bin` |
| Python | **reused system 3.12.3** — `supported; reusing instead of downloading 3.11` (no 3.11 download) |
| Git | 2.43.0 found |
| Node | v18.19.1 unsupported → downloaded **v26.10.0** into `~/.hermes/node/` |
| C++ compiler | found (13.3.0) |
| ripgrep | **not installed** — non-interactive mode cannot apt-install; falls back to `grep` |
| ffmpeg | 6.1.1 found |
| clone | HTTPS → `/var/lib/hermes/.hermes/hermes-agent`, then **`HEAD is now at f97608f178 chore: release v0.21.5 (2026.9.24)`** |
| venv | created with Python 3.12.3 |
| dependencies | **`uv.lock` `--locked` sync FAILED** (`lockfile needs to be updated`) → fell back to the `all` tier resolve → `✓ All dependencies installed` |
| node deps | installed (`node_modules`, 403 MB) |
| `--skip-browser` | honoured twice: `Skipping Playwright/Chromium install` and `Skipping Browser Use CLI install` |
| `--skip-computer-use` | honoured: `Skipping Computer Use (cua-driver) install` |
| launchers | `hermes`, `hermes-agent`, `hermes-acp` → `~/.local/bin/` |
| PATH | installer appended `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` |
| config | created `~/.hermes/.env`, `config.yaml`, `SOUL.md` |
| skills | 58 bundled skills synced into `~/.hermes/skills/` |
| setup wizard | skipped (no terminal) — `hermes setup` still pending |

#### Observed issues (none fatal)

1. **`uv.lock --locked` verification did not run.** Upstream's lockfile is out of date relative to `pyproject.toml` at this tag, so the hash-verified tier was skipped and dependencies were resolved fresh from the TUNA mirror. Consequence: the dependency set is *not* hash-pinned for this deployment, and the mirror was load-bearing — without it this step could not have completed (§9.6 Gap 1). Recorded as a supply-chain caveat, not a failure.
2. **`sudo` attempt failed as designed.** The installer tried `sudo` to install build tools and got `a terminal is required to read the password`; it printed `✓ Build tools installed` regardless. Misleading message, but `g++` was already present so nothing was actually missing.
3. **Connectivity self-check warned.** `Could not reach https://duckduckgo.com/` → `Network checks failed`. Irrelevant here: web search is a V1-disabled capability, and package downloads worked via the mirror.
4. **`ripgrep` absent.** Deliberately not installed — see §9.10.

### 9.10 Phase 3.3 — installation identity and CLI validated

Pin verified independently of the installer's own claim:

| Check | Result |
| --- | --- |
| `git rev-parse HEAD` | `f97608f178d1ffeca59860195ab7da295f7c8e5f` — exact match to the pin |
| `git log -1` | `chore: release v0.21.5 (2026.9.24)`, Thu Sep 24 02:59:46 2026 -0700 |
| worktree | clean |
| `hermes --version` | `Hermes Agent v0.21.5 (2026.9.24) · upstream 666f313d · local f97608f1 (+41514 carried commits)` |
| install method | `git` |
| Python | 3.12.3 |
| OpenAI SDK | 2.24.0 |

`hermes --help` confirms the real subcommands; TASK.md's historical names are correct for this release:

| TASK.md assumption | Reality in v0.21.5 |
| --- | --- |
| `hermes gateway` | ✅ exists — "Messaging gateway management"; plus `gateway install/start/stop/status` |
| `hermes tools` | ✅ exists — "Configure which tools are enabled per platform" |
| `hermes doctor` | ✅ exists — "Check configuration and dependencies" |

**Warning recorded: do not run `hermes update`.** `--version` reports "Update available: 4534 commits behind — run 'hermes update'". Running it would move the checkout off the pinned release and silently invalidate every verification in this section. Updates must be deliberate and re-verified.

Acceptance (TASK.md Phase 3.3):

- [x] authoritative source identified
- [x] selected Hermes version/revision recorded
- [x] installation method verified before execution
- [x] Hermes CLI starts successfully
- [x] actual gateway command identified → `hermes gateway`
- [x] actual tool-inspection command identified → `hermes tools`
- [x] no Chromium/Playwright dependency was intentionally installed — no `ms-playwright` cache, no Chromium binary, no browser process. The only "chromium" hits are the `electron-to-chromium` npm data package, vite's `openChrome.js`, and test fixtures
- [x] no local model installed — the only model-like files are the repo's own tiny wakeword asset `tools/wakewords/hey_hermes.onnx` and a `.pt`-named contributor data file; no LLM/Vision/Whisper weights

Footprint:

| Item | Size |
| --- | --- |
| `HERMES_HOME` total | **2.0 GB** |
| `hermes-agent` (repo + venv) | 1.7 GB |
| `node_modules` | 403 MB |
| managed Node 26 | 229 MB |
| Root filesystem | 8.9 GB → 11 GB used; 27 GB free |

Residue: the standalone installer copy at `/var/lib/hermes/install-v2026.9.24.sh` was **removed** after the install — the cloned repo carries its own `scripts/install.sh`, so the copy was redundant. `/var/lib/hermes` now contains only `.bashrc`, `.cache`, `.hermes`, `.local`, `.npm`, `media`, `.profile`, `.ssh`, `.bash_logout`.

Not installed on purpose: **`ripgrep`**. The installer recommends `sudo apt install ripgrep` for file search, but the File tool is a V1-disabled capability (AGENTS.md §5) and Hermes falls back to `grep`. Installing it would add a dependency with no V1 consumer. Revisit only if Phase 4 shows Hermes needs `rg` for something we *do* enable.

### 9.11 New open item — the media cache path in AGENTS.md §15 does not match reality

Hermes creates its caches **inside `HERMES_HOME`**: `~/.hermes/image_cache/`, `~/.hermes/audio_cache/`, `~/.hermes/cache/`. It does **not** use `/var/lib/hermes/media/`, which we created earlier to satisfy AGENTS.md §15.

That directory is currently empty and unused. Either AGENTS.md §15 is re-pointed at the real cache directories, or Hermes is configured to use it — decide in Phase 14 before the cleanup timer is written. Leaving an unused empty directory also conflicts with the standing "no residue on the server" requirement.

---

## 10. Installed capability inventory (Phase 3.3 + Phase 4)

Everything below was read from the installed v0.21.5 — CLI output, the repo source at the
pinned commit, and `hermes doctor`. Nothing here is documentation-only.

### 10.0 Installed layout and verified commands

| Item | Actual value |
| --- | --- |
| Hermes executable | `/var/lib/hermes/.local/bin/hermes` (launcher written by the installer) |
| Login-shell resolution | resolves via the `.bashrc` PATH line the installer added |
| Version | `Hermes Agent v0.21.5 (2026.9.24)` |
| Local revision | `f97608f178d1ffeca59860195ab7da295f7c8e5f` |
| Install method | `git` |
| Code / repo | `/var/lib/hermes/.hermes/hermes-agent` |
| Python runtime | 3.12.3 (system, reused) |
| venv | `/var/lib/hermes/.hermes/hermes-agent/venv` |
| Gateway command | `hermes gateway` (+ `install`, `start`, `stop`, `status`) |
| Tool-inspection command | `hermes tools` |
| Diagnostics | `hermes doctor` |
| Config file | `/var/lib/hermes/.hermes/config.yaml` (121 KB) |
| Credentials file | `/var/lib/hermes/.hermes/.env` (mode `600`) — **never mirrored, never printed** |
| Personality | `/var/lib/hermes/.hermes/SOUL.md` |
| Managed uv | `/var/lib/hermes/.hermes/bin/uv` (0.12.20) |
| Managed Node | `/var/lib/hermes/.hermes/node` (v26.10.0) |
| Bundled skills | `/var/lib/hermes/.hermes/skills/` — 58 |
| Memory store | `/var/lib/hermes/.hermes/memories/` (matches AGENTS.md §11) |
| Sessions | `/var/lib/hermes/.hermes/sessions/` |
| Logs | `/var/lib/hermes/.hermes/logs/` |
| Image cache | `/var/lib/hermes/.hermes/image_cache/` |
| Audio cache | `/var/lib/hermes/.hermes/audio_cache/` |
| Other dirs created | `backups/`, `cache/`, `cron/`, `hooks/`, `pairing/` |

### 10.1 Platform registry — both target platforms confirmed

From `hermes_cli/platforms.py` at the pinned commit:

| Platform key | Label | `default_toolset` |
| --- | --- | --- |
| `weixin` | 💬 Weixin | `hermes-weixin` |
| `qqbot` | 💬 QQBot | `hermes-qqbot` |

Registry also contains telegram, discord, whatsapp, whatsapp_cloud, slack, signal,
bluebubbles, email, homeassistant, mattermost, matrix, dingtalk, feishu, wecom,
wecom_callback, yuanbao, webhook, api_server, cron. **None of these may be enabled**
(AGENTS.md §7) — leave them unconfigured, do not delete the adapters.

Adapter packages exist on disk: `gateway/platforms/weixin.py`, `gateway/platforms/qqbot/`.

### 10.2 Credential variables — exact names

| Platform | Required | Allowlist / policy knobs |
| --- | --- | --- |
| Weixin | `WEIXIN_TOKEN`, `WEIXIN_ACCOUNT_ID` (or `platforms.weixin.token` / `platforms.weixin.extra.account_id`) | `WEIXIN_ALLOWED_USERS`, `WEIXIN_GROUP_ALLOWED_USERS`, `WEIXIN_GROUP_POLICY`; per-key `WEIXIN_<KEY>` env fallback |
| QQ | `QQ_APP_ID` + `QQ_CLIENT_SECRET` (or `platforms.qq.extra.app_id` / `.client_secret`) | dm_policy + allow_from, group_policy + allow_from, markdown_support |

Two notes that matter for Phases 7 and 8:

- **Weixin authenticates by QR login**, connecting an *iLink bot identity* (e.g. `...@im.bot`). Media is fetched from an allowlisted CDN host `https://novac2c.cdn.weixin.qq.com/c2c`.
- **QQ has both paths.** TASK.md §7.1 assumes manual AppID/Secret entry, but the adapter ships a QR registration flow (`gateway/platforms/qqbot/onboard.py`, "QR scan complete! (App ID: …)"). Prefer the QR flow — it avoids handling `client_secret` by hand. Adapter version 1.1.0, official Bot API v2, token endpoint `https://bots.qq.com/app/getAppAccessToken`.
- **Config-path inconsistency to watch:** the platform key is `qqbot` in the registry, but the adapter's own docstring says config lives under `platforms.qq.extra`. Verify against `hermes gateway setup` in Phase 7 rather than trusting either alone.

### 10.3 Tool configuration — the real command and the TTY trap

| Item | Reality in v0.21.5 |
| --- | --- |
| Tool-inspection command | **`hermes tools list --platform <p>`** |
| Enable / disable | `hermes tools enable/disable --platform <p> NAME [NAME …]` |
| Interactive UI | bare `hermes tools` — **requires a real TTY** |
| Per-platform summary | `hermes tools --summary` — **requires a real TTY** |
| `hermes chat --list-toolsets` | **does not exist in this release** (the `config.yaml` comment referencing it is stale) |

**The TTY trap:** bare `hermes tools` and `--summary` fail over SSH with
`'hermes tools' requires an interactive terminal`. The `list`, `enable`, and `disable`
subcommands **do** work non-interactively when `--platform` is given. Phase 6 can
therefore be driven over SSH; the interactive UI cannot.

Documented alternative (from `config.yaml` itself): *"Use `hermes tools` to configure
interactively, or edit `platform_toolsets` directly."* The deprecated top-level
`toolsets:` key is ignored — tool config is **per-platform via `platform_toolsets`**.

### 10.4 CRITICAL — every messaging bundle is full-access by default

`hermes-weixin` and `hermes-qqbot` are both defined as
`_bundle(...) = _HERMES_CORE_TOOLS`, with no narrowing. `_HERMES_CORE_TOOLS` contains
**50+ tools**, including `terminal`, `process_manage`, `read_file`, `write_file`,
`patch`, `search_files`, all 16 `browser_*` tools, `execute_code`, `delegate_task`,
`cronjob_manage`, `computer_use`, and `web_search`/`web_extract`.

And `_DEFAULT_OFF_TOOLSETS` is only
`{homeassistant, spotify, discord, discord_admin, video, video_gen, x_search, a2a, kanban}` —
**terminal, file, browser, web, and code execution are all ON by default.**

Measured baseline, identical for `cli`, `qqbot`, and `weixin`:

```text
✓ enabled   web  browser  terminal  file  code_execution  image_gen
            vision  tts  skills  todo  memory  session_search
            connections  clarify  delegation  cronjob  computer_use
✗ disabled  video  video_gen  x_search  stt  kanban  context_engine
            homeassistant  spotify  yuanbao  a2a
```

So a freshly installed and configured bot would hand QQ and Weixin users a shell, file
writes, code execution, browser automation, and cron. This is exactly the escalation
AGENTS.md §5, §6 and §17 exist to prevent. **Phase 6 is the highest-risk step in the
plan and must complete before either platform is reachable** (AGENTS.md §8: "Do not
expose the bot publicly until rate limiting and access control are verified").

Phase 6 must disable, on both `qqbot` and `weixin`:
`web`, `browser`, `terminal`, `file`, `code_execution`, `image_gen`, `connections`,
`delegation`, `cronjob`, `computer_use`.

Still to be decided (not mandated by AGENTS.md either way): `skills` (note `skill_manage`
writes into `~/.hermes/skills/`), `session_search`, `clarify`, `todo`.

Keep enabled: `vision` (AGENTS.md §12), `tts` (AGENTS.md §14, optional), `memory` (§11).

### 10.5 Vision / STT / TTS / memory / LLM mechanisms

| Capability | Mechanism | V1 assessment |
| --- | --- | --- |
| LLM | `model.default: anthropic/claude-opus-4.6`, `provider: auto`, `base_url: https://openrouter.ai/api/v1` | remote API ✅ — needs `OPENROUTER_API_KEY`; Phase 5 |
| Vision | toolset `vision` (`vision_analyze`), **requires `OPENROUTER_API_KEY`**; no separate top-level `vision:` section | remote ✅ — same key as text; Phase 11 |
| STT | toolset name `stt` is **config-only** (`_CONFIG_ONLY_TOOLSETS`) — controlled by `stt.enabled`, never by `platform_toolsets` | see 10.6 — **two defaults violate AGENTS.md** |
| TTS | toolset `tts` (`text_to_speech`); no active top-level `tts:` section, so it uses the built-in default **Edge TTS (network, free)** | remote/lightweight ✅ — Phase 13 |
| Long-term memory | built-in: `memory_enabled: true`, `user_profile_enabled: true`, `memory_char_limit: 2200` (~800 tok), `user_char_limit: 1375` (~500 tok), `nudge_interval: 10` turns; files `~/.hermes/memories/MEMORY.md` + `USER.md`, created on first write | matches AGENTS.md §11 ✅ — `hermes memory` is the command that would add an external provider; stays unused in V1 |
| Sessions | `~/.hermes/state.db` (not yet created; appears on first session) + `~/.hermes/sessions/` | Phase 9 |
| Cache / scratch | `~/.hermes/cache/scratch/` is the **TMPDIR**, entries pruned after **24 h idle** | retention mismatch with AGENTS.md §15's ≤1 h — Phase 14 |

### 10.6 Two default-config values that conflict with AGENTS.md

1. **`stt.enabled: true` plus `stt.local.model: "base"`.** The default STT provider is
   **local faster-whisper** — AGENTS.md §13 explicitly forbids running local Whisper in
   V1. Phase 12 must switch to a remote provider (groq / openai / mistral) or leave STT
   off.
2. **`stt.language: "en"`** — a *global* language hint for every STT provider. This would
   force English recognition on Chinese voice messages, failing TASK.md Phases 12.3 and
   19.8/19.9. Must be set to `""` (auto-detect) or `"zh"`.

### 10.7 Settings with resource implications for a 1.6 GiB shared host

- `agent.max_turns: 500` — a single turn may run up to 500 tool iterations. On this host
  that is a long-running, memory-elastic loop. Consider lowering; record the chosen value
  when Phase 6 / 17 sets it.
- `agent.reasoning_effort: "medium"` — per-call cost, not RAM. Relevant to provider quota.
- `hermes doctor` reports **SQLite 3.45.1 carries the WAL-reset bug** (affected range
  includes 3.45.1; fixed in 3.44.6 / 3.50.7 / 3.51.3+). Hermes stores sessions in
  `state.db`. **Note carefully: doctor's advice is "run `hermes update`", but that would
  not help — the bug is in the system libsqlite3 that Ubuntu 24.04 ships, not in Hermes —
  and running it would break the pin (§9.10).** Needs a decision; options are to accept
  the risk, or supply a newer SQLite to the venv. See §11 deviations.

### 10.8 `hermes doctor` result

rc = 0. No security advisories; no suspicious MCP stdio commands; venv active; version
files consistent (0.21.5); config version v46 with no deprecated keys; all expected
directories present. Only warnings: the SQLite note above, and optional packages for
platforms we do not use (`python-telegram-bot`, `discord.py`) — those should stay
uninstalled. `MEMORY.md`, `USER.md`, and `state.db` correctly do not exist yet.

### 10.9 Health-check commands worth keeping

```bash
hermes --version          # pin + install method
hermes doctor             # full environment diagnostics (rc=0 when clean)
hermes tools list --platform weixin
hermes tools list --platform qqbot
hermes status             # status of all components
hermes logs               # agent.log tail; `hermes logs errors`, `--since 1h`
```

### 10.10 Phase 5 — provider configuration mechanism (resolved; awaiting operator values)

**Operator decision:** use an **OpenAI-compatible relay ("中转站")** serving a **DeepSeek** model,
rather than a first-party provider. This is a supported first-class path, not a workaround — the
`config.yaml` template documents `provider: "custom"` as *"Any other OpenAI-compatible endpoint"*, and
the source explicitly anticipates the relay case:

> `OPENAI_BASE_URL` (**a proxy/gateway the OPENAI_API_KEY was issued for**) wins over the public
> endpoint — sending the proxy key to api.openai.com 401s and then **quarantines a valid key**.
> — `hermes_cli/runtime_provider_custom.py:470`

Two mechanisms exist. **The named-provider form is preferred**, because it binds the credential to the
endpoint so the relay key can never be sent to `api.openai.com`:

```yaml
# config.yaml — preferred: credential bound to the endpoint
providers:
  <relay-slug>:
    base_url: "https://<relay-host>/v1"
    key_env: "<RELAY_KEY_ENV_NAME>"

model:
  provider: "<relay-slug>"
  default: "<model-name-as-the-relay-expects>"
```

```bash
# .env
<RELAY_KEY_ENV_NAME>=<key>
```

The simpler bare form (`model.provider: custom` + `model.base_url` + `OPENAI_BASE_URL`/
`OPENAI_API_KEY` in `.env`) also works, but leaves key routing to host-gated fallbacks. The template's
per-provider variant also supports `extra_headers` (values treated as secrets, never logged) and
`session_affinity_header` for session-aware proxies — available if the relay needs them.

Current state after the change (all verified by Hermes itself, not by eyeballing the file):

| Item | Before | After |
| --- | --- | --- |
| `model.default` | `anthropic/claude-opus-4.6` | **`GPT-6-Sol`** |
| `model.provider` | `auto` | **`kldai`** |
| `model.base_url` | `https://openrouter.ai/api/v1` | **`https://www.kldai.cc/v1`** |
| `providers:` | absent | **present** — `kldai` = base_url + `key_env: KLDAI_API_KEY` + `transport: codex_responses` |
| `fallback_providers:` | absent | **present** — `deepseek` / `deepseek-chat` / `key_env: DEEPSEEK_API_KEY` |

`hermes fallback list` now reports:

```text
Primary:   GPT-6-Sol  (via kldai)
Fallback chain (1 entry):
  1. deepseek-chat  (via deepseek)
```

Note: `hermes config set model.provider kldai` **automatically cleared the stale OpenRouter
`base_url`**, with the explanation *"that route belonged to auto, not kldai"*. Hermes reasons about
provider↔endpoint routing rather than blindly writing the value, which validates using the named
provider form.

#### Wire-protocol mapping — the trap that was avoided

The operator specified `wire_api = "responses"`. That is Codex CLI terminology; the Hermes equivalents
are not obvious:

- `hermes_cli/config_providers.py:47-49` maps `"responses"` → **`codex_responses`** (aliases:
  `openai_responses`, `openai-responses`).
- The current field name is **`transport`**; **`api_mode` is the legacy alias**. The source warns:
  *"v12 migration writes `transport`; hand-edited configs may still use `api_mode`. Accept both or
  migrated configs **silently downgrade to chat_completions**."* A wrong field name would have
  silently sent chat-completions traffic to a responses-only relay.
- `providers.<slug>.transport` was used, and the value read back correctly as `codex_responses`.

A DeepSeek relay has no vision capability, so Phase 11 still needs a separate vision provider.

### 10.11 Phase 5.3 — text chat test PASSED

The operator supplied both keys (`KLDAI_API_KEY` 67 chars, `DEEPSEEK_API_KEY` 35 chars; `.env` stays
`600 hermes:hermes`, no commented placeholders left). Two model-id errors in the operator's input were
found and corrected before the test could pass.

#### Correction 1 — the relay is case-sensitive and exposes a fixed catalogue

`GET /v1/models` on the relay (key valid, HTTP 200, 2.1 s) returns exactly **8** ids:

```text
codex-auto-review  gpt-5.5  gpt-5.6  gpt-5.6-sol
gpt-5.6-terra      gpt-6    gpt-6-astra  gpt-6-sol
```

`GPT-6-Sol` was rejected:

```json
{"error":{"message":"Model \"GPT-6-Sol\" is not supported by any configured account in this group",
          "type":"model_not_found"}}
```

The correct id is **`gpt-6-sol`** (lowercase). `model.default` was corrected accordingly.
**The relay exposes no DeepSeek models at all** — it is OpenAI-family only.

#### Correction 2 — DeepSeek's real model ids

`GET /v1/models` on `api.deepseek.com` (key valid, HTTP 200, 0.19 s) returns:

```text
deepseek-flash
deepseek-v4-pro
```

**`deepseek-chat` — the id originally configured — does not exist on this account.** The fallback entry
was corrected to **`deepseek-flash`**, which is also the model the operator identified as
vision-capable (relevant to Phase 11).

#### The relay accepts only the Responses wire — `transport: codex_responses` was necessary

| Request | Result |
| --- | --- |
| `POST /v1/chat/completions` with `gpt-6-sol` | **400** — `"Upstream rejected illegal short-input distillation or heartbeat probing."` |
| `POST /v1/responses` with `gpt-6-sol` | **200**, 10.9 s, a complete `response` object (`status: completed`) |

Chat-completions traffic is refused for this model, exactly as the source warned. Had the field name
been left as the legacy `api_mode` (or omitted), the request would have silently gone out as
chat-completions and failed.

#### Final evidence

```text
hermes -z "Reply with exactly this and nothing else: PHASE5-OK-PERSISTED" --usage-file /tmp/u.json
  → rc=0, elapsed 30 s
  → stdout: PHASE5-OK-PERSISTED
  → usage:  "model": "gpt-6-sol", "provider": "custom", "api_calls": 1,
            "completed": true, "failed": false,
            "turn_exit_reason": "text_response(finish_reason=stop)"
```

`"provider": "custom"` is expected, not a fault: `resolve_runtime_provider` returns the bare billing
class `custom` for every named `providers:` entry, and `effective_runtime_provider()` re-derives the
configured name only for display (`hermes_cli/fallback_config.py`).

Acceptance (TASK.md Phase 5.3):

- [x] remote LLM responds successfully
- [x] API key is not embedded in source code — it lives only in `.env`, mode `600`
- [x] API key does not appear in logs — verified by never printing it; probes read it into a shell
      variable and the value is never echoed
- [x] no local inference process starts

### 10.12 CRITICAL — Hermes performs runtime package installs, so the mirror must persist

This is the finding that cost the most time. The first three `hermes -z` attempts **hung** (killed by
`timeout`, rc=124, no output, no usage file) rather than erroring — the model id was only part of it.

Root cause, from `agent.log`:

```text
16:xx  INFO tools.lazy_deps: Lazy-installing boto3==1.42.89 for feature 'provider.bedrock'
```

and from `errors.log`:

```text
agent.bedrock_adapter: boto3 lazy install did not complete: pip install failed:
  error: Request failed after 3 retries in 84.2s
  cause: Failed to fetch: `https://pypi.org/simple/botocore/`   ← network-blocked
```

**Hermes lazily installs optional dependencies at runtime**, and `UV_DEFAULT_INDEX` was only set for the
Phase 3 installation — it was not present in the runtime environment. So every run tried `pypi.org`,
retried for ~84 s per attempt, and stalled the whole turn.

Fix applied — the mirror is now persisted in `.env`, which Hermes loads into the process environment
that `uv` inherits:

```text
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

| | Before | After |
| --- | --- | --- |
| `hermes -z` outcome | killed at 300 s, no output | **rc=0 in 30 s** |

The same variables must be supplied to the systemd gateway unit in Phase 16 (`Environment=` or
`EnvironmentFile=`), because a systemd service does not read `.bashrc`. **This is a Phase 16
prerequisite, not an optional nicety.**

### 10.13 `hermes config set` rewrites config.yaml and strips template comments

Observed and verified benign, but worth knowing before it causes alarm:

| Measure | Before | After | Interpretation |
| --- | --- | --- | --- |
| Comment lines | 1 999 | 1 736 | template documentation comments dropped by the rewrite |
| **Code lines** | 139 | **148** | +9 = exactly the intended edits; **no code line lost** |
| Bytes | 121 555 | 108 217 | the ~14 KB delta is comment text only |

Every section that matters is intact (`platform_toolsets`, `stt`, `memory`, `agent`, `model`,
`providers`, `fallback_providers`, `gateway`, `cron`), and the code-line diff shows only the intended
changes. `hermes doctor` reports rc=0, config version v46, no deprecated keys.

Consequence: the annotated template is progressively consumed by writes. The pre-change backups are
therefore the only remaining copy of Hermes' own documentation — **do not delete them**:

- `~/.hermes/backups/config.yaml.bak-before-max-turns`
- `~/.hermes/backups/config.yaml.bak-before-phase5` (still fully annotated, 121 555 bytes)

### 10.14 Phase 5 execution incident — heredocs do not survive the local shell

Recorded because it cost a rollback and will recur otherwise.

The first attempt appended config via a `cat >> file <<YAML` heredoc inside a single-quoted SSH command.
The **local** Git-Bash shim parsed the heredoc body and executed it locally
(`providers:: command not found`, `kldai:: command not found`, …), so only a mangled 6-line comment
fragment reached the server; the apostrophe and quotes inside the comment were altered in transit.

Recovery: config.yaml was restored from `backups/config.yaml.bak-before-phase5` (2 281 lines), then the
block was applied by **writing the fragment locally, `scp`-ing it, normalising CRLF, and `cat`-ing it
on the host**, then deleting the fragment. That path worked first time.

**Rule: never use heredocs in the remote command string.** Write a local file and transfer it.

### 10.15 多行内联脚本同样不可用

The local screen also mangles **multi-line inline scripts** (`python3 -c "…"` spanning lines): the
command aborts with rc=2 and no output, silently losing the rest of the batch. This bit twice.

Workarounds that work: keep remote one-liners single-line; use `hermes config get` / `hermes
fallback list` / `hermes doctor` as the authoritative validators instead of hand-rolled parsing; or
write a local script and `scp` it.

### 10.16 Phase 6 — execution-heavy toolsets removed, verified per platform

Operator decision: keep `session_search`; remove `skills`, `clarify`, and `todo` along with the
AGENTS.md §5 list.

Backup first: `~/.hermes/backups/config.yaml.bak-before-phase6`.

```bash
hermes tools disable --platform qqbot  web browser terminal file code_execution image_gen \
  connections delegation cronjob computer_use skills clarify todo
hermes tools disable --platform weixin <same list>
```

Both returned `✓ Disabled: <all 13>`.

**Verified by re-reading the per-platform state rather than trusting the command echo:**

```text
qqbot  →  ✓ vision   ✓ tts   ✓ memory   ✓ session_search      (everything else ✗)
weixin →  ✓ vision   ✓ tts   ✓ memory   ✓ session_search      (everything else ✗)
```

`platform_toolsets` in `config.yaml` now reads:

```yaml
  qqbot: [memory, session_search, tts, vision]
  weixin:
    - memory
    - session_search
    - tts
    - vision
```

Every other platform keeps its stock `hermes-<platform>` bundle — that is acceptable because those
adapters are **not configured, not loaded, not started** (AGENTS.md §7 explicitly prefers that over
deleting source).

Acceptance (TASK.md Phase 6):

- [x] bot cannot execute shell commands — `terminal` disabled on both exposed platforms
- [x] bot cannot browse the web through browser automation — `browser` disabled; no Chromium process, no `ms-playwright` cache
- [x] bot cannot arbitrarily read/write server files — `file` disabled
- [x] bot cannot execute arbitrary Python/shell code — `code_execution` disabled
- [x] MCP is disabled — no active `mcp_servers:` key; `hermes mcp list` → "No MCP servers configured."
- [x] no Chromium process appears after normal chat use
- [x] source files not deleted to save RAM

`hermes doctor` after the change: no security advisories, no suspicious MCP stdio commands, config
intact.

#### Two items Phase 6 could NOT fix, both requiring a decision

**1. STT is active and violates AGENTS.md §13.** `stt` is a **config-only** toolset
(`_CONFIG_ONLY_TOOLSETS`) — it renders as "✗ disabled" in `hermes tools list` but is *not* controlled
by `platform_toolsets`. Measured state:

```text
stt.enabled      = true
stt.local.model  = base     ← local faster-whisper, forbidden by AGENTS.md §13
stt.language     = en       ← would transcribe Chinese voice as English, failing 12.3 / 19.8 / 19.9
```

So the bot currently *would* run local Whisper on a voice message. Nothing has triggered it yet
(no platform is connected), but this is a genuine rule violation sitting one phase away from
exposure, because TASK.md orders platform setup (7, 8) **before** STT (12).

**2. The `cli` platform still has 17 toolsets enabled**, including `terminal`, `file`, `browser`,
`web`, `code_execution`, and `computer_use`. This is the operator's own interactive interface, not a
user-facing surface, so it is arguably out of scope for AGENTS.md §5 — but TASK.md Phase 22 lists
"Terminal/Shell tool is disabled" and "File tool is disabled" as blanket acceptance criteria, with no
platform qualifier. Needs an explicit decision.

### 10.17 Phase 6 closure — both open items resolved by operator decision

Backup: `~/.hermes/backups/config.yaml.bak-before-stt-cli`.

**1. STT disabled (was violating AGENTS.md §13).**

```bash
hermes config set stt.enabled false   →  ✓ Set stt.enabled = False
hermes config get stt.enabled         →  false
```

The local faster-whisper provider can no longer be invoked, and the English-only `stt.language` no
longer affects anything. STT is re-enabled in Phase 12 only after switching the provider to Groq and
setting the language to auto/`zh`. **Consequence accepted: voice messages are not transcribed in the
meantime.**

**2. `cli` converged to the same four toolsets.**

```bash
hermes tools disable --platform cli web browser terminal file code_execution image_gen \
  connections delegation cronjob computer_use skills clarify todo
```

**Final cross-platform state — all three platforms identical:**

| Platform | Enabled toolsets | Count |
| --- | --- | --- |
| `cli` | `memory`, `session_search`, `tts`, `vision` | 4 |
| `qqbot` | `memory`, `session_search`, `tts`, `vision` | 4 |
| `weixin` | `memory`, `session_search`, `tts`, `vision` | 4 |

```yaml
platform_toolsets:
  cli: [memory, session_search, tts, vision]
  qqbot: [memory, session_search, tts, vision]
  weixin:
    - memory
    - session_search
    - tts
    - vision
```

`hermes doctor` after the change: no security advisories, no suspicious MCP stdio commands, config
version v46, no deprecated keys.

TASK.md Phase 22's blanket criteria — "Terminal/Shell tool is disabled", "File tool is disabled",
"Code Execution is disabled", "MCP is disabled" — are now **unambiguous**: they hold for every
platform, with no qualifier needed.

### Mirror status

`server-mirror/` mirrors real artefacts. **Superseded text removed — the manifest was re-pointed in
Phase 3.3** at the real paths (`/var/lib/hermes/.hermes/config.yaml`, `SOUL.md`,
`hermes-agent/.env.example`, `/etc/sysctl.conf`, `/etc/fstab`) and the tool now connects as
`hermes@` because `admin` cannot traverse the `700` `HERMES_HOME`. Current result: 5 files mirrored, 0
failures, `.env` excluded by policy. See `server-mirror/README.md`.

---

## 11. Phase 7 — QQ Bot onboarding (IN PROGRESS)

### 11.1 Why a custom runner instead of `hermes gateway setup`

`hermes gateway setup` is a **TTY-only arrow-key wizard** (`--help` exposes no flags), so it cannot be
driven over SSH. Its QQ branch
(`hermes_cli/gateway_setup_wizard.py:519` `_setup_qqbot()`) does however call a plain function,
`gateway.platforms.qqbot.qr_register()`, which is drivable directly. `staging/qq-onboard.py` wraps it.

Secret handling: `qr_register()` returns `{"app_id", "client_secret", "user_openid"}`. The runner
**never prints that dict** — it writes it to `/var/lib/hermes/qq-onboard-result.json` at mode `600` and
prints only `app_id` and the scanner's openid. The flow's own output (the connect URL) is left intact
because the operator needs to see it.

### 11.2 Canonical credential persistence (read from the wizard, to be replicated exactly)

The wizard writes these to `.env` via `save_env_value`:

| Key | Source |
| --- | --- |
| `QQ_APP_ID` | `credentials["app_id"]` |
| `QQ_CLIENT_SECRET` | `credentials["client_secret"]` |
| `QQ_ALLOW_ALL_USERS` | `"false"` for pairing/allowlist modes, `"true"` for open |
| `QQ_ALLOWED_USERS` | comma-separated openids (or `""`) |
| `QQBOT_HOME_CHANNEL` | optional, set to the scanner's own openid |

The adapter reads `platforms.qq.extra.app_id` / `.client_secret` first and falls back to the scoped
secrets `QQ_APP_ID` / `QQ_CLIENT_SECRET` (`gateway/platforms/qqbot/adapter.py:148-149`). Because
`qr_register()` returns the **scanner's own openid**, the operator can be allowlisted automatically —
exactly the option the wizard offers.

TASK.md §7.2 requires an explicit allowlist during testing, so the target is
`QQ_ALLOW_ALL_USERS=false` + `QQ_ALLOWED_USERS=<operator openid>` (the wizard's "only allow listed
user OpenIDs" branch), not the default `pairing` mode.

### 11.3 Endpoint facts

- Connect URL template: `https://q.qq.com/qqbot/openclaw/connect.html?task_id={task_id}&_wv=2&source=hermes`
- Portal host `q.qq.com` reachable (HTTP 200, 0.36 s); `api.sgroup.qq.com` reachable
- Polling: every 2 s, 10 s API timeout, QR auto-refreshes up to **3** times before giving up; overall window 600 s
- The `qrcode` module is **not** installed, so the flow prints the URL instead of an ASCII QR — fine for a phone, and it avoids adding a dependency (AGENTS.md §18)

### 11.4 Phase 7.1/7.2 — DONE

Credentials applied without exposure:

| Key | Where | Note |
| --- | --- | --- |
| `QQ_APP_ID` | `.env` | App ID `1905696144` (non-secret) |
| `QQ_CLIENT_SECRET` | `.env` | 32 chars; written by script, **never printed** |
| `QQ_ALLOW_ALL_USERS` | `.env` | `false` — the startup guard against an `open` policy |
| `platforms.qqbot.enabled` | `config.yaml` | `true` |
| `platforms.qqbot.extra.dm_policy` | `config.yaml` | **`allowlist`** (not the `pairing` default) |
| `platforms.qqbot.extra.allow_from` | `config.yaml` | the operator's OpenID `A729C39060FB65742B0C808249E36326` |
| `platforms.qqbot.extra.group_policy` | `config.yaml` | `allowlist`, list intentionally empty |

Backups taken first: `~/.hermes/backups/env.bak-before-qq`, `~/.hermes/backups/config.yaml.bak-before-qq`.

All four values read back correctly through `hermes config get`.

#### Platform name resolved: `qqbot`, not `qq`

The adapter's own docstring says credentials live under `platforms.qq.extra` — **that is stale**. The
authoritative references are `gateway/config_env.py:627` (`Platform.QQBOT, (("QQ_APP_ID",
"QQ_CLIENT_SECRET"),)`) and `platform_toolsets`, both of which use **`qqbot`**. Using `qq` would have
silently produced an unconfigured adapter.

Also confirmed: **the platform auto-enables when both credentials are present** (the `_Cred` gate), so
`enabled: true` is documentation rather than a requirement.

#### Why `allowlist` instead of the `pairing` default

`gateway/platforms/qqbot/adapter.py:151-153` defaults both policies to `pairing`. `gateway/run.py:2242`
maps `Platform.QQBOT` to `(None, None, "QQ_ALLOW_ALL_USERS")` — meaning **QQ has no
`QQ_DM_POLICY`/`QQ_GROUP_POLICY` env vars**; policy is read only from `extra.*`. Accepted values are
`open | allowlist | disabled | pairing`.

`pairing` lets unknown senders *request* access, which does not satisfy TASK.md §7.2 (explicit allowlist
during testing) or §7.4 ("non-allowed users/groups are rejected or ignored"). `allowlist` hard-rejects.
`QQ_ALLOW_ALL_USERS=false` is kept solely because an `open` policy without it **aborts gateway startup**
(`_own_policy_open_startup_violation`).

The allowlist was placed in `config.yaml` rather than `QQ_ALLOWED_USERS` so there is exactly one
authoritative source; the env var only seeds `extra.allow_from` when it is absent.

### 11.5 Gateway connected — live proof

Temporary foreground run as the `hermes` user (`hermes gateway run`, backgrounded for the test). This is
**not** the permanent service; systemd is Phase 16.

```text
16:40:32,532 [QQBot:1905696144] Access token refreshed, expires in 6956s
16:40:32,882 [QQBot:1905696144] Gateway URL: wss://api.sgroup.qq.com/websocket
16:40:33,068 [QQBot:1905696144] WebSocket connected
16:40:33,076 gateway.run: ✓ qqbot connected
16:40:33,226 [QQBot:1905696144] Ready, session_id=fdc9670a-…
16:40:34,305 gateway.run: Gateway running with 1 platform(s)
```

Other confirmed-at-runtime facts:

| Log line | Meaning |
| --- | --- |
| `Agent budget: max_iterations=32 (agent.max_turns from config.yaml …)` | the §11.2 reduction is live |
| `Secret redaction: ENABLED (tool output, logs, and chat responses are scrubbed before delivery)` | satisfies AGENTS.md §6's "logs must never print secrets" |
| `Model context warmed: gpt-6-sol -> 272000 tokens (detected)` | relay model advertises a 272k context |
| `memory trim: rss_kib=182752->173292` | gateway RSS ≈ 173 MB — comfortable against §21's 900 MB chat target |

#### Two findings surfaced by the gateway itself

**1. Hermes auto-mitigates the SQLite bug — the accepted risk does not actually fire.**
On every database it opens it logs:

```text
linked SQLite 3.45.1 … is vulnerable to the WAL-reset corruption bug — using
journal_mode=DELETE instead of enabling WAL.
```

So Hermes **detects the vulnerable library and refuses to enable WAL**, which is precisely the condition
the bug requires. This is a stronger mitigation than §11.1 assumed. (The message still suggests
`hermes update`; that remains prohibited — and is unnecessary.)

**2. Hermes' own security audit flags the host.**

```text
[security 1/1] SSH password authentication is ENABLED. Password auth is brute-forceable
and dangerous on an internet-facing box. Set 'PasswordAuthentication no' in sshd_config.
```

This matches the hardening candidate noted in §7.5/§4.5 and remains **deliberately out of V1 scope** —
changing it would alter the operator's own access path. Recorded, not actioned.

### 11.6 Phase 7.3 / 7.4 — pending live tests

Require the operator to send messages: a private `你好` (§7.3), then `@机器人 你好` in an allowlisted
group (§7.4). **No group is authorised yet**, so the group test additionally needs the target group's ID
added to `group_allow_from`; the allowlist mechanism is already in place.

### 11.7 Personality injection — 小云 (Xiaoyun)

Operator supplied a rich persona JSON (`staging/personas/xiaoyun.json`, kept as the authoring source).
Backup first: `~/.hermes/backups/config.yaml.bak-before-persona`.

#### The mechanism, read from `hermes_cli/personality.py` ("single owner for personality overlays")

| Concept | Location |
| --- | --- |
| Personality **definition** | `agent.personalities.<name>` (user entries overlay built-ins by name) |
| Personality **selection** | **`display.personality`** — "the active selection is stored in `display.personality` (never here, and never in `agent.system_prompt`)" |
| Manual prompt (mutually exclusive) | `agent.system_prompt` — used only when `display.personality` does not name a known personality |

`render_personality_prompt()` consumes **exactly four fields**:

```python
parts = [value.get("system_prompt", "")]
if value.get("tone"):  parts.append(f'Tone: {value["tone"]}')
if value.get("style"): parts.append(f'Style: {value["style"]}')
```

`description` is used only for list/preview UIs (`describe_personality`).

#### Field mapping applied

| Hermes field | Source in the operator's JSON |
| --- | --- |
| `description` | `description` |
| `system_prompt` | `system_prompt` — **verbatim**, 763 chars / 46 lines |
| `tone` | `personality.core_traits` (8 traits, joined with `；`) |
| `style` | `speech_style.general` (10 rules, joined with `；`) |

Injected with a duplicate-key guard: the script asserted that the anchor
`  personalities: {}` appears **exactly once** before replacing it. Appending a second top-level
`agent:` block instead would have been actively harmful — a duplicate YAML key would have discarded the
rest of the `agent:` section, including `max_turns: 32`. Post-write verification confirmed
`agent.max_turns = 32` and `personalities keys = ['xiaoyun']` both survived.

#### Verification — and why `hermes -z` was the wrong test

A `hermes -z "你好"` smoke test returned a generic *"你好！有什么可以帮你？"* — **not** 小云's voice. That is
**not** a config failure: the one-shot path deliberately bypasses the overlay.

```python
# hermes_cli/oneshot.py:588
ephemeral_system_prompt=skills_prompt,
```

Only two surfaces resolve it:

| Surface | Code path |
| --- | --- |
| interactive CLI | `cli_init_mixin.py:249` → `resolve_ephemeral_system_prompt(CLI_CONFIG)` |
| **messaging gateway (QQ / Weixin)** | `gateway/run_config_loaders.py:93-99` → `resolve_ephemeral_system_prompt_from_config(...)`, consumed at `run_turn_runner.py:1112` |

So the persona **does** apply to QQ/Weixin. Confirmed by calling Hermes' own resolvers
(`staging/verify-persona.py`):

```text
active personality name : 'xiaoyun'
personalities available : 15 (built-ins + user)
xiaoyun is defined      : True
rendered overlay        : 920 chars
effective system overlay: 920 chars
  contains 小云          : True
  contains 本云          : True
VERDICT: overlay is active
```

920 = 763 (system_prompt) + the `Tone:` and `Style:` lines, confirming all four fields landed.

#### Fields in the operator's JSON that Hermes cannot consume

`identity`, `strengths`, `flaws`, **`catchphrases`** (10 phrases),
`private_chat_behavior`, `group_chat_behavior`, and `task_behavior` **have no slot** in the personality
schema. Most of their content is already restated inside the supplied `system_prompt`, so little is lost
— **except the catchphrases**, which are nowhere in the prompt. The authored JSON is preserved verbatim
at `staging/personas/xiaoyun.json` so they can be folded in later if wanted; that was not done
unilaterally because it would mean editing the operator's authored prompt.

#### `~/.hermes/SOUL.md` — checked for conflict, none found

The installer wrote a compact **style** directive, not a competing persona:

> "You are Hermes Agent, built by Nous Research. Be direct: match the length of your reply to the weight
> of the ask … No filler ("Great question," "I'd be happy to"), no restating the request back …"

It reinforces 小云's "简短自然 / 不写作文 / 不用客服腔" rather than fighting it, so the two coexist. Worth
knowing that it is injected **in addition to** the personality overlay.

#### Lifecycle

Activation is per-profile and switchable at runtime: `/personality xiaoyun` (and `/personality` with no
argument lists options) works from both the CLI and any connected chat, and the gateway re-reads it each
turn. Set `display.personality` to `""` or the neutral value to remove the overlay.

#### Verification still outstanding

The end-to-end proof (a QQ message answered in 小云's voice) doubles as TASK.md §7.3 and is pending an
operator message.

### 11.8 Persona revision — 本名 云白, 昵称 小云

Operator correction: the character's **name is 云白**, **小云 is the nickname**. Persona JSON bumped to
`1.1.0`; backup `~/.hermes/backups/config.yaml.bak-before-yunbai`.

#### The technical slug was deliberately left as `xiaoyun`

The personality **key** (`agent.personalities.xiaoyun`) and `display.personality: xiaoyun` were **not**
renamed. The operator's instruction was about the name/nickname, and the nickname is still 小云, so
`xiaoyun` remains an accurate slug. Renaming it would have meant rewriting three places
(`agent.personalities`, `display.personality`, and every reference in this document) for no functional
gain. Say the word if a `yunbai` slug is preferred — it is a mechanical change.

#### What changed

| Field | Before | After |
| --- | --- | --- |
| `name` | 小云 | **云白** |
| `nickname` | — | **小云** (new field, informational) |
| `description` | 小云是一个… | **云白（昵称小云）**是一个… (63 chars) |
| `system_prompt` | 763 chars / 46 lines | **869 chars / 52 lines** |
| first prompt line | 你是"小云"，一个运行在… | **你是"云白"，昵称"小云"，一个运行在…** |

A dedicated 名字 section was added to the prompt:

```text
名字：
- 你的本名是"云白"，昵称"小云"。
- 日常对话里通常用昵称"小云"自称。
- 需要正式自我介绍，或对方问起名字时，说本名"云白"。
- 不要主动纠正别人叫你小云，这个称呼就是对的。
```

`identity.self_awareness` gained "本名云白，昵称小云" as its first entry, and
`speech_style.self_reference` gained "本名云白，昵称小云" and "日常对话里通常用'小云'自称；需要正式自我介绍时说本名'云白'".
`catchphrases` were left untouched — they all use 小云, which the nickname still licenses.
`group_chat_behavior` was updated from "@ 小云" to "@ 云白".

#### Write method — region replacement, not append

The v1 script refused to run when the entry already existed. v2 **replaces** the
`agent.personalities` region instead. The region is found by scanning forward from the single
`  personalities:` line over blank and 4+-space-indented lines, stopping at the first line that is
neither — which is precisely the start of the commented examples that follow. Trailing blank separator
lines are preserved.

It is a purely textual splice: **every comment elsewhere in `config.yaml`, and the rest of the `agent:`
section, are untouched.** Result: 89 lines → 100 lines replaced, and post-write verification confirmed
`PARSE OK`, `agent.max_turns = 32`, `display.personality = xiaoyun`, `personalities = ['xiaoyun']`.

#### Verification

```text
active personality name : 'xiaoyun'
rendered overlay        : 1026 chars
  head : 你是“云白”，昵称“小云”，一个运行在用户本地微信机器人里的中文对话智能体。 /  / 人格设定： / …
effective system overlay: 1026 chars
  contains 云白 / 小云 / 本云 / 昵称 : all True
VERDICT: overlay is active (云白 + 小云 present)
```

1026 = 869 (system_prompt) + the `Tone:` and `Style:` lines.

#### Still outstanding

The end-to-end proof on QQ (a reply in 云白/小云's voice) doubles as TASK.md §7.3 and is pending an
operator message.

### 11.9 Chat display — reasoning hidden

The operator reported the bot's replies arriving with a `🧠 Reasoning:` block (rendered as a code block
in QQ) and asked for it to be removed.

The switch is **`display.show_reasoning`**, which was `true`:

```bash
hermes config set display.show_reasoning false   →  ✓ Set display.show_reasoning = False
```

Related settings noticed in the same block, **not changed** — worth a review if the chat feels noisy:

| Key | Current | Effect |
| --- | --- | --- |
| `display.tool_progress` | `all` | renders tool activity into the chat |
| `display.interim_assistant_messages` | `true` | sends mid-turn assistant text |
| `display.busy_ack_detail` | `true` | verbose "busy" acknowledgements |
| `display.suppress_warning_notifications` | `false` | lets the `⚠️ Model fallback:` banner through (see §11.10) |

The test gateway was restarted so the change takes effect; QQ reconnected cleanly at 17:00:41.

### 11.10 The relay is unreliable — the fallback is doing all the work

The bot's replies are arriving via the **fallback**, not the intended primary. From `agent.log`:

```text
agent.conversation_loop: API call failed (attempt 1/3, not retryable) error_type=BadRequestError
  provider=custom base_url=https://www.kldai.cc/v1 model=gpt-6-sol
  summary=HTTP 400: Upstream rejected illegal short-input distillation or heartbeat probing.
agent.chat_completion_helpers: Fallback activated: gpt-6-sol → deepseek-flash (deepseek)
```

**The Hermes side is configured correctly** — `agent.model_metadata` confirms the intended route is live:
`Using Codex OAuth context length 272,000 for model 'gpt-6-sol' (codex_responses route at https://www.kldai.cc/v1)`.

Direct probes of the relay's `/v1/responses` (bypassing Hermes) show the service itself is the problem:

| Probe | Result |
| --- | --- |
| minimal, non-streaming | **timeout at 45 s** |
| minimal, `stream: true` | 200, but 44.5 s |
| 4000-char `instructions` | 200, 26.2 s |
| `tools` | **timeout at 45 s** |
| `instructions` + `tools` | 200, 25.9 s |

So the same request shape succeeds and fails interchangeably, with **25–45 s latency on trivial prompts**
and frequent hard timeouts. The `400 "illegal short-input distillation or heartbeat probing"` is the
relay's own anti-abuse heuristic misfiring — not a malformed request from Hermes.

Consequences while the relay stays primary:

- every reply pays a failed primary attempt **plus** a fallback round trip;
- the `⚠️ Model fallback:` banner is shown to the user in chat;
- the actually-serving model (`deepseek-flash`) is fast and reliable by comparison — measured 0.19 s
  against the relay's 25–45 s.

**Recommendation (needs the operator's decision): swap the roles — make `deepseek-flash` the primary and
demote the relay to a fallback.** The operator stated DeepSeek V4.1 Flash has vision, so it can also carry
Phase 11. This is a two-line config change. Not done unilaterally because the relay was an explicit
operator choice.

### 11.11 Pitfall — the repo's `hermes` file is not the launcher

While bouncing the gateway, a helper script invoked `$REPO/hermes` (the source entry point) and the gateway
died immediately:

```text
ModuleNotFoundError: No module named 'dotenv'
```

That is the exact failure the official install guide warns about: the repo file picks up the **system**
interpreter, while the installer's launcher explicitly execs the venv:

```bash
# /var/lib/hermes/.local/bin/hermes
exec "/var/lib/hermes/.hermes/hermes-agent/venv/bin/python" \
     "/var/lib/hermes/.hermes/hermes-agent/hermes" "$@"
```

**Always start Hermes via `/var/lib/hermes/.local/bin/hermes`, never `$REPO/hermes`.** Recorded because
Hermes' own error message does not say this; only the docs do.

A reusable bounce script now exists at `staging/restart-gateway.sh` (stops the test instance, restarts it
with the mirror environment injected, and reports connection state).

### 11.12 Primary / fallback swapped — DeepSeek promoted

Operator decision, taken after §11.10's measurements. Backup: `~/.hermes/backups/config.yaml.bak-before-swap`.

| | Before | After |
| --- | --- | --- |
| `model.provider` | `kldai` | **`deepseek`** |
| `model.default` | `gpt-6-sol` | **`deepseek-flash`** |
| `model.base_url` | `https://www.kldai.cc/v1` | **`https://api.deepseek.com/v1`** |
| `fallback_providers[0]` | `deepseek` / `deepseek-chat`→`deepseek-flash` | **`kldai` / `gpt-6-sol`** |
| `providers.kldai` | unchanged | unchanged (still carries `transport: codex_responses`) |

`hermes fallback list` now reports:

```text
Primary:   deepseek-flash  (via deepseek)
Fallback chain (1 entry):
  1. gpt-6-sol  (via kldai)
```

The relay entry is written as `provider: kldai` — a **named** provider reference, so the endpoint *and*
its `transport: codex_responses` wire setting come from the `providers:` block. A bare `base_url` here
would risk resolving the relay without the Responses wire, which it requires (§10.11). `hermes config set`
also proactively warned that the stale kldai `base_url` still applied to `deepseek` and named the fix.

Verified end to end:

```text
hermes -z "Reply with exactly: SWAP-OK" --usage-file …
  → rc=0 in 4 s          (the relay took 25–45 s for the same kind of call)
  → stdout: SWAP-OK
  → usage: model=deepseek-flash  provider=deepseek  api_calls=1  failed=false
  → no fallback event logged since the restart
```

### 11.13 Persona — platform-agnostic wording

The bot's own reasoning had flagged the mismatch (§11.10 note): the prompt claimed a WeChat deployment
while the runtime was QQ. Operator instruction: describe it as *"运行在用户的聊天机器人里"*.

Changed in `system_prompt` only:

| | Text |
| --- | --- |
| before | 你是"云白"，昵称"小云"，一个运行在**用户本地微信机器人**里的中文对话智能体。 |
| after | 你是"云白"，昵称"小云"，一个运行在**用户的聊天机器人**里的中文对话智能体。 |

Also 住在**微信**里的自由小脑袋 → 住在**聊天软件**里的自由小脑袋. Verified in `config.yaml`: the new
phrase appears once, the old one zero times. Persona JSON bumped accordingly; `system_prompt` is now
870 chars / 52 lines.

**Left as authored, not changed** — `description` still reads "…是一个…**微信**智能体", and `identity.role`
/ `identity.self_awareness` still say 微信. These fields are **inert**: Hermes consumes only
`description` (list previews), `system_prompt`, `tone`, `style` (§11.7). So the only functional surface is
already platform-agnostic. Say the word if the `description` text should follow.

### 11.14 Error/notice routing — what Hermes can and cannot do

Operator requirement: *"对于其他人或群，不要发送任何报错，出现报错直接发送给我自己的账号"*.

Investigated the delivery policy rather than guessing. **`gateway/warning_notifications.py`** is the
decision point — its own docstring: *"Delivery policy for engine diagnostics, never assistant or command
responses."* The rule is:

```python
warning_notifications_enabled(platform, user_config) =
    not resolve_display_setting(user_config, platform_key,
                                "suppress_warning_notifications", False)
```

`resolve_display_setting(user_config, platform_key, key, default)` resolves
**`display.platforms.<platform>.<key>`** first and falls back to the global
`display.suppress_warning_notifications`.

**Conclusion: the granularity is the platform, not the chat.** There is no operator-only target and no
per-chat rule. Diagnostics are always emitted **into the originating chat** — which is why the
`⚠️ Model fallback:` banner appeared in the operator's DM.

What that means in practice:

1. **The requirement is already satisfied by construction today.** The QQ DM allowlist contains only the
   operator, and `group_policy: allowlist` with an empty `group_allow_from` means **no group and no other
   user can reach the bot at all**. Nothing can be sent to them, errors included. This is exactly "errors
   only reach my account".
2. **Once a group is allowlisted**, Hermes cannot mute diagnostics for that group while keeping them in the
   operator's DM — both are the same platform (`qqbot`). The available options then are:

| Option | Command | Trade-off |
| --- | --- | --- |
| Mute diagnostics **globally** | `hermes config set display.suppress_warning_notifications true` | nothing shown in any chat; operator reads `hermes logs errors` |
| Mute on **QQ only** | set `display.platforms.qqbot.suppress_warning_notifications: true` | same, but the CLI still shows them |
| Mute only the `notify` categories | `hermes config set display.suppress_warning_notifications true` | as above |
| Accept group-visible diagnostics | — | group members see engine warnings |

3. **Proactive push of error digests to the operator's DM** (rather than reactive, in the chat being used)
   would need a scheduled job plus `hermes send` — i.e. **Hermes Cron, which AGENTS.md §5 keeps disabled
   in V1**. Out of scope until the V5 deferred item.

**Standing rule recorded:** before adding any group to `group_allow_from`, decide between option 1 and the
"accept" row above. The choice cannot be made retroactively without the group having already seen output.

Practical note: the banner that prompted this was a *symptom* of the broken relay. With the primary fixed
(§11.12) it should no longer appear at all — the requirement's spirit is served without muting anything.

### 11.15 All engine diagnostics silenced

Operator instruction: *"报错全部静默"*.

```bash
hermes config set display.suppress_warning_notifications true   →  ✓ Set … = True
```

Gateway restarted; QQ reconnected at 17:15:14.

**Scope verified in code, not assumed.** The fallback banner travels as an `AgentNotice`, not as assistant
text:

- `run_turn_runner.py:1916-1950` stashes the pre-agent fallback notice and hands it to the agent as
  `agent._pending_fallback_notice` — "Reuse the in-agent one-shot notice so the pre-agent provider switch
  is user-visible too."
- The notice sink at `run_turn_runner.py:1177-1190` classifies it with
  `is_diagnostic_notice(notice)` — true when `level in {"warn", "error"}` — and only then calls
  `render_notification(..., diagnostic=diagnostic, user_config=…)`.
- `render_notification` itself: `if diagnostic and not warning_notifications_enabled(platform, user_config): return False`.
- `warning_notifications_enabled` = `not resolve_display_setting(user_config, platform_key, "suppress_warning_notifications", False)`.

So the flag does gate the banner. **Language matters here:** `gateway/warning_notifications.py` describes
itself as *"Delivery policy for engine diagnostics, never assistant or command responses"* — this is a
*presentation* switch.

**Logging is unaffected.** Every error still reaches `~/.hermes/logs/errors.log` and `agent.log`. The
operator's diagnostics move from chat to:

```bash
hermes logs errors            # errors.log tail
hermes logs --since 1h        # agent.log, last hour
hermes logs -f                # follow live
```

#### One error path the switch does NOT cover — worth knowing

`run_turn_runner.py:1930-1937` builds a *failure reply as assistant text* when model resolution fails
before the turn begins (both primary and fallback unusable):

```python
return {"final_response": (
    "⚠️ I couldn't connect to the AI model service, so this message wasn't processed. "
    "Use /login to sign in again, or /model to pick a different model. …"), …}
```

That is a `final_response`, **not a notice**, so `suppress_warning_notifications` does not gate it and it
would be delivered to whichever chat triggered it. There is no config for it.

This is not a practical exposure today — the QQ DM allowlist contains only the operator and no group is
authorised (§11.14), so no other chat can reach the bot. It is recorded because it means **the allowlist,
not this flag, is what actually guarantees "errors only reach me."** Keep the allowlist tight; the display
flag is cosmetic by comparison.

### 11.16 QQ group authorisation — the group number is NOT the group id

The operator added the bot to group **`1107720324`**. That value **cannot be used** as-is, and the reason is
worth recording.

**The allowlist matches `group_openid`, an opaque per-bot identifier — not the QQ group number.**
`gateway/platforms/qqbot/adapter.py:764-768`:

```python
group_openid = str(d.get("group_openid", ""))
member = str(author.get("member_openid", ""))
if not group_openid or not self._is_group_allowed(group_openid, member):
    return
```

and `gateway/platforms/access_policy_mixin.py:45-46,65-69`:

```python
def _entry_matches(self, entries, target):
    return target in entries            # exact membership — no wildcards, no prefixes

def _is_group_allowed(self, chat_id, sender_id=""):
    if self._group_policy == "allowlist":
        return self._entry_matches(self._group_allow_from, chat_id)
    return self._group_policy == "open"
```

Three consequences that shaped the approach:

1. ~~**Exact match only.** `_entry_matches` is a plain membership test, so there is no wildcard that could
   admit "the group" without knowing its openid.~~

   **CORRECTION (recorded because the wrong version drove a decision).** This was **wrong**. I read the
   *base* mixin's `_entry_matches` (`access_policy_mixin.py:45-46`, `return target in entries`) and missed
   that the **QQ adapter overrides it** with a wildcard-capable version
   (`gateway/platforms/qqbot/adapter.py:1669-1671`):

   ```python
   def _entry_matches(self, entries: List[str], target: str) -> bool:
       normalized_target = str(target).strip().lower()
       return any(str(e).strip().lower() in ("*", normalized_target) for e in entries)
   ```

   So `"*"` **is** supported, the match is case-insensitive, and **the temporary `group_policy: open`
   window was unnecessary** — `group_allow_from: ["*"]` would have admitted the group long enough to read
   its openid from the log, with no startup-guard involvement and no `QQ_ALLOW_ALL_USERS` flip.

   Security corollary worth keeping: a `"*"` entry **opens the gate for every chat on that platform** —
   for `group_allow_from` every group the bot is in, and for `allow_from` every DM sender. Treat `"*"` as
   an allow-all switch, not as a convenience.
2. **Rejected group messages are dropped silently — nothing is logged.** The handler `return`s before
   `_ingest`, and `_on_message` does not log the payload. So the openid **cannot** be harvested by sending
   a message while unauthorised, and `group_policy: pairing` / `disabled` never forward group traffic
   either (`_is_group_allowed` returns False for anything but `allowlist`-match or `open`).
3. **`hermes gateway setup` has no QQ group-allowlist step** — the wizard's QQ branch covers only DM policy
   and the home channel, and its home-channel prompt expects a "user/group **OpenID**".

#### Capture procedure used (temporary, then immediately reverted)

| Step | Action |
| --- | --- |
| 1 | Backup `config.yaml` and `.env` → `backups/*.bak-before-group-capture` |
| 2 | `hermes config set platforms.qqbot.extra.group_policy open` — **group only; `dm_policy` stays `allowlist`** |
| 3 | `QQ_ALLOW_ALL_USERS=true` in `.env` — required by the startup guard, see below |
| 4 | Restart the gateway; it boots only if the guard is satisfied (a useful self-check) |
| 5 | Operator sends a message in the group → the accepted turn logs `chat=<group_openid>` |
| 6 | Set `group_policy: allowlist` + `group_allow_from: [<group_openid>]`, revert `QQ_ALLOW_ALL_USERS=false`, restart |

**The startup guard, verified:** `gateway/run.py:2242-2267` `_own_policy_open_startup_violation()` aborts
startup with `"<platform>: open policy without allow-all opt-in"` when any enabled platform has
`dm_policy` **or** `group_policy` set to `open` unless `GATEWAY_ALLOW_ALL_USERS` or the platform's own
allow-all env var is truthy. `QQ_ALLOW_ALL_USERS` was used rather than `GATEWAY_ALLOW_ALL_USERS` because it
is scoped to QQ. It is guard-only while `dm_policy` remains `allowlist` — `_is_dm_allowed` gates on
`dm_policy`, not on the flag.

**Exposure during the window:** with `group_policy: open`, any member of any group the bot is in could get a
reply. It is bounded to one message in the operator's own test group and the setting is reverted in
step 6. Recorded explicitly because it is a deliberate, temporary loosening of an access control.

### 11.17 Group replies are rejected by QQ — a genuine Hermes-side gap

Captured `group_openid` **`56B2E66590BD2ED9A098C5D8B0123D68`** from the gateway log during the §11.16
window, allowlisted it, and reverted every temporary loosening. Inbound works, but **the outbound reply
fails**:

```text
send retry 1/3 after 1.0s: QQ Bot API error [400]
  /v2/groups/56B2E66590BD2ED9A098C5D8B0123D68/messages: 主动消息失败, 无权限
send retry 2/3 after 2.0s: … same
Send failed: QQ Bot API error [400] … 主动消息失败, 无权限
```

The agent did its job — the turn is in the log with `msg='你好'`, `model=deepseek-flash`,
`platform=qqbot`, and `session=agent:main:qqbot:group:56B2E66590BD2ED9A098C5D8B0123D68:A729C39060FB65742B0C808249E36326`.
Only the delivery is refused.

#### Root cause: `reply_to` is never populated for QQ

QQ distinguishes **passive replies** (must carry the inbound message's `msg_id`, allowed for a short window)
from **proactive messages** (need a separate, usually enterprise-only permission). The adapter is fully
wired for the passive path — `adapter.py:1414-1421`:

```python
async def _send_text_to(self, chat_type, target_id, content, reply_to=None, keyboard=None):
    body = self._build_text_body(content, reply_to)
    if reply_to:
        body["msg_id"] = reply_to          # <- passive reply
```

and it even tracks the per-chat inbound id (`self._last_msg_id`, line 167/574) — but only for typing
indicators and inline-keyboard approval prompts, **not for normal replies**.

The normal reply path gets its `reply_to` from the turn context, which is computed in
`gateway/run_turn.py:3181-3187`:

```python
_progress_reply_to = (
    event_message_id
    if (source.platform in (Platform.FEISHU, Platform.MATTERMOST) and source.thread_id and event_message_id)
    or (is_buzz and event_message_id and _progress_reply_in_thread)
    or _relay_prospective_thread_id
    else None
)
```

**`Platform.QQBOT` is absent from that list, so `reply_to` is always `None` for QQ.** DMs survive this
because QQ tolerates proactive c2c messages; **groups do not.** `reply_to_mode` (PlatformConfig, default
`"first"`) does not help — it governs progress threading, not this computation — so **there is no
config-only fix.**

#### Resolution chosen: a narrow adapter-level patch

Operator decision: patch the core file rather than seek 主动消息 permission. Rationale recorded as a
deviation — it conflicts with AGENTS.md §24.5-§24.6 ("prefer configuration changes over invasive Hermes
core modifications; prefer plugin/adapter extension points"), which is why it is documented rather than
applied silently.

**The patch**, in `gateway/platforms/qqbot/adapter.py` inside `send()`:

```python
# [LOCAL PATCH] QQ group messages must be PASSIVE replies carrying the inbound message
# id, or QQ rejects them as unauthorised proactive messages (HTTP 400 "主动消息失败, 无权限").
if reply_to is None and self._guess_chat_type(chat_id) == "group":
    reply_to = self._last_msg_id.get(chat_id)
```

Why this shape rather than editing the platform list in `run_turn.py`:

| Choice | Reason |
| --- | --- |
| **Adapter level, not `run_turn.py`** | Changing the platform list there would give *every* outbound message of the turn a `reply_to` — progress, interim, and final alike — and QQ counts each against a per-inbound-message passive-reply ceiling. |
| **Groups only** | `c2c` is verified working with proactive messages, so its path is untouched. `guild` untouched. |
| **Uses the existing caches** | `_last_msg_id[chat_id]` is already populated by `handle_message()` (adapter.py:571-575) and `_chat_type_map[chat_id]` by `_ingest()` (adapter.py:842) — both verified present, and `_guess_chat_type` reads the map rather than guessing from id shape. |

Applied via `staging/apply-qqbot-passive-patch.py`, which: refuses to run if the anchor does not match
exactly once, preserves the original as `adapter.py.orig-qqbot-passive`, **compiles the patched source
before writing**, verifies the marker landed, and is idempotent.

Companion change — keep a QQ turn to a single outbound message so it cannot exhaust the passive-reply
ceiling:

```bash
hermes config set display.platforms.qqbot.tool_progress off   # per-platform; CLI unaffected
```

**Durability:** the patch survives normal restarts but lives only in the pinned checkout. Any reinstall,
distribution change, or `hermes update` (already prohibited, §11.1) would discard it and silently
reintroduce the 400. `adapter.py.orig-qqbot-passive` sits beside the file as the revert reference.

**Status: applied, syntax-verified, and live-verified.** The operator sent a group message at 17:33:09 and
the reply was delivered:

```text
17:33:09 INFO gateway.run: response ready: platform=qqbot
  chat=56B2E66590BD2ED9A098C5D8B0123D68
  session=agent:main:qqbot:group:56B2E66590BD2ED9A098C5D8B0123D68:A729C39060FB65742B0C808249E36326
  time=1.9s api_calls=1 response=13 chars
```

No `send retry` and no `Send failed` follow it — the last failure in the log is the 17:22:35 attempt from
before the patch. **TASK.md Phase 7.4 (group @ mention) therefore passes, and Phase 7 is complete.**

**Recorded in `TASK.md` under Unresolved Issues, per AGENTS.md §24.13** ("Record unresolved issues in
TASK.md rather than hiding them").

Note the partial upside: with `group_allow_from` now holding the real `group_openid`, group messages **are**
ingested and the agent answers — the failure is purely at the QQ delivery step, and the 400 is visible only
in the log (chat-facing diagnostics are silenced per §11.15).

### 11.18 Persona v1.2.0 applied — and two things in the incoming file needed fixing

The operator supplied a substantially expanded persona. Backup:
`~/.hermes/backups/config.yaml.bak-before-persona-1.2.0`.

**Fix 1 — double-escaped newlines.** The supplied `system_prompt` stored its line breaks as `\\n` in the
JSON, which `json.loads` decodes to a literal backslash + `n`, **not** a newline. Measured on the incoming
file: **1541 chars, 0 real newlines, 70 literal `\n` sequences.** Applied verbatim, the prompt would have
reached the model as one long line full of visible `\n` text.

`staging/normalise-persona.py` converts them and reports both directions:

```text
system_prompt     : 1541 -> 1470 chars
real newlines     : 0 -> 70
literal \n left   : 0
```

**Fix 2 — platform wording regression.** The incoming prompt reverted to
`运行在用户本地微信机器人里` — the exact wording the operator had me change earlier the same day (§11.13),
for the reason the bot itself surfaced: it runs on QQ. Their instruction was preserved:
`运行在用户的聊天机器人里`. **Flagged for confirmation — if the revert was intentional, it goes back.**

`version` was bumped to **1.2.0** locally, because the incoming content differs materially from the
previously applied file that carried the same `1.1.0` string.

#### What Hermes actually injects, and what is therefore inert

`render_personality_prompt()` consumes exactly four fields (§11.7). Everything else in the expanded JSON is
documentation:

| Injected | Inert (no slot in the schema) |
| --- | --- |
| `description` (list previews only), `system_prompt`, `tone` ← `core_traits`, `style` ← `speech_style.general` | `identity`, `preferences`, `catchphrases`, `private_chat_behavior`, `group_chat_behavior`, `task_behavior`, `relationship_model`, `roles_and_permissions`, `social_boundaries`, `initiative_policy`, `initiative_state_schema`, and the sub-blocks `error_behavior` / `toxic_teasing` / `addressing_user` / `self_reference` |

The author clearly folded the important material into `system_prompt` — identity and relationship, the
preference list, speech rules, error handling, private-vs-group conduct, the L0–L3 ladder, initiative rules,
and social boundaries all now appear there. Verified rendered overlay: **1672 chars**, contains
云白 / 小云 / 昵称.

**Two gaps worth flagging:**

1. **"本云" is no longer instructed anywhere in the prompt.** The previous `system_prompt` carried a
   称呼和自称 section listing `我 / 小云 / 本云 / 本云宣布`; the new one dropped that section, while
   `speech_style.self_reference` still lists 本云 — but that field is inert. Verification confirms it:
   `contains 本云 : False`. The catchphrases (also inert) still use 本云. Fold the self-reference line into
   `system_prompt` if the 本云 voice is wanted back.
2. **`initiative_policy.quiet_hours` (23:00–08:00) and the cooldown values are not in the prompt.** The
   initiative *rules* are summarised, the numeric guards are not. Moot for V1 — proactive messaging needs
   Cron, which AGENTS.md §5 keeps disabled — but it will matter if that changes.

#### Re-verified after the rewrite

```text
region replaced : 100 -> 136 lines
system_prompt   : 1470 chars, 71 lines
tone            : 61 chars     style : 126 chars
PARSE OK · agent.max_turns = 32 · personalities = ['xiaoyun'] · display.personality = xiaoyun
rendered overlay: 1672 chars · VERDICT: overlay is active
```

The gateway re-reads `display.personality` per turn, so no restart was required for this change.

---

## 12. Standing operator decisions and prohibitions

These were issued by the operator on 2026-09-29 and are binding for the remainder of the deployment.

### 11.1 SQLite WAL-reset bug — accepted, and `hermes update` is prohibited

- The system SQLite is **3.45.1**, which falls in the affected range of
  [sqlite.org/wal.html#walresetbug](https://sqlite.org/wal.html#walresetbug). Hermes stores sessions
  in `~/.hermes/state.db`, so this is a real (if low-probability) data-integrity risk.
- **Decision: accept and record. Do not block the deployment.** The exposure is bounded — one bot, one
  local process, low write concurrency — and the alternative (supplying a newer SQLite to the venv)
  adds moving parts to a 1.6 GiB shared host.
- **`hermes update` must never be run automatically, and must not be run at all without a fresh,
  explicit instruction.** Reasons, both independently sufficient:
  1. it would move the checkout off the pinned commit and invalidate every verification in §9.10;
  2. it would not fix this bug anyway — the bug lives in Ubuntu's `libsqlite3`, not in Hermes, so
     `hermes doctor`'s suggested remedy is simply wrong for this host.
- **Any change to the system SQLite (apt, PPA, vendored wheel, library swap) is likewise prohibited
  without explicit instruction.** It would affect the whole host, including the pre-existing
  `nginx` / `main-site-editor` workload.
- Recorded so that a future agent reading a `hermes doctor` warning does not "helpfully" repair it.

### 11.2 `agent.max_turns` — reduced 500 → 32

**Semantics, verified against the installed source rather than assumed:** `agent.max_turns` is the
**maximum number of tool-calling iterations within a single conversation turn**, not a count of
conversation turns. It is passed through as `max_iterations` to the agent
(`hermes_cli/cli_session_mixin.py:565`, `cli_agent_setup_mixin.py:666`). `hermes chat --max-turns N`
documents it identically ("Maximum tool-calling iterations per conversation turn (default: 500)").

So the old value permitted **one user message to drive up to 500 model↔tool round trips** — on a
1.6 GiB host shared with live services that is an unbounded-feeling loop.

| Item | Value |
| --- | --- |
| Before | `agent.max_turns: 500` (config.yaml line 1145) |
| After | `agent.max_turns: 32` |
| Backup | `~/.hermes/backups/config.yaml.bak-before-max-turns` |
| Applied via | `hermes config set agent.max_turns 32` → `✓ Set agent.max_turns = 32` |
| Verified | `hermes config get agent.max_turns` → `32`; raw line → `  max_turns: 32`; total line count unchanged |
| Shadowing check | `.env` contains **no** `HERMES_MAX_ITERATIONS`, which would otherwise silently override config.yaml (a stale value there is a known trap — `hermes_cli/doctor_config.py:367`) |

32 iterations is generous for the V1 workload: with terminal, file, browser, code execution, and cron
disabled in Phase 6, a normal chat turn needs one or two tool calls. `--run-budget SECONDS` also exists
as a wall-clock cap per run if a time-based guard is wanted later.

### 11.3 Network-reachability constraints discovered while planning the provider set

Measured from the host; this narrows the options in Phases 5, 11, and 12.

| Endpoint | Result |
| --- | --- |
| `openrouter.ai/api/v1/models` | **200**, ~1.2–1.3 s (works, but slowest of the usable options) |
| `dashscope.aliyuncs.com/compatible-mode/v1/models` | 401 (auth required — reachable), **~0.08 s, most consistent** |
| `api.deepseek.com/v1/models` | 401 — reachable, ~0.18 s |
| `api.moonshot.cn`, `api.siliconflow.cn`, `open.bigmodel.cn` | 401 — reachable |
| `api.anthropic.com` | 403 — reachable |
| `api.groq.com` | 403 — reachable |
| **`api.openai.com`** | **connection timed out — network-blocked** |
| **`api.mistral.ai`** | **connection timed out — network-blocked** |

Consequences to carry forward:

- **OpenAI is not an option, for the main model or for STT.** Mistral likewise.
- Hermes' STT providers are `local | groq | openai | mistral`. With OpenAI and Mistral unreachable and
  `local` (faster-whisper) forbidden by AGENTS.md §13, **Phase 12 has exactly one usable provider:
  Groq.** This is why egress was tested now — it changes the Phase 12 plan before any work is done.
- Provider key env vars Hermes recognises include `DEEPSEEK_API_KEY` and `DASHSCOPE_API_KEY`, so both
  domestic options are first-class rather than a custom-endpoint workaround.
- Vision resolves through a **separate auxiliary model router** (`tools/vision_tools.py`:
  `_load_auxiliary_client`, `_cfg_auxiliary`), so the vision provider can differ from the main text
  model. One key is not automatically required to cover both, though it may.

---

## 13. Deviations from AGENTS.md / TASK.md

| # | Deviation | Status |
| --- | --- | --- |
| 1 | AGENTS.md §3 / §21 resource budgets re-based from nominal 2 GB to the measured 1.6 GiB; edited into both documents | applied |
| 2 | AGENTS.md §3 "dedicated host" assumption does not hold — host is shared with live nginx sites, `main-site-editor`, `frps`, and Aliyun agents (§3) | **accepted by operator**; mitigated by the dedicated `hermes` account (§8.1) and a pending `MemoryMax` (§8.4) |
| 3 | `vm.swappiness` changed `0 → 10` in `/etc/sysctl.conf` — a host-wide parameter affecting the pre-existing projects | applied with operator approval (§8.2); original preserved at `/etc/sysctl.conf.bak-before-hermes` |
| 4 | TASK.md changes broader than the plan: `/etc/sysctl.conf` edited, and a prior project (`/home/admin/chat_bot`) and stale `/tmp` scratch deleted | applied with explicit operator instruction; backups in `backups/` (§6) |
| 5 | TASK.md Phase 22 acceptance ("2C2G server remains stable") is **not satisfiable as written** on a shared host — it needs an explicit clause that the pre-existing services keep working. Not yet reworded | **open** |
| 6 | Phase 1.1 `apt upgrade` was executed on a live production host | completed without service impact; noted as a standing risk |
| 7 | The installer will pull a Hermes-managed **Node 26** into `HERMES_HOME` because the host's Node v18.19.1 fails the 22.22+/24.11+/26 gate, even though we disable the browser and WhatsApp features that need Node (§9.4) | accepted as an installer behaviour; ~50 MB disk, not resident |
| 8 | Installed from a **PyPI mirror** (Tsinghua TUNA) instead of the official index (§9.6 Gap 1) | applied with operator approval |
| 9 | **The dependency set is not hash-pinned.** Upstream's `uv.lock` is stale at this tag, so the `--locked` verification tier was skipped and packages were resolved fresh (§9.9 issue 1) | accepted caveat; the mirror was load-bearing |
| 10 | `ripgrep` left uninstalled although the installer suggests it — the File tool is V1-disabled and `grep` is the fallback (§9.10) | deliberate |
| 11 | AGENTS.md §15's media path `/var/lib/hermes/media/` is **wrong** for this install; Hermes uses `~/.hermes/image_cache`, `~/.hermes/audio_cache`, and `~/.hermes/cache/scratch/` (§9.11, §10.5) | **open — resolve in Phase 14** |
| 12 | **Default STT ships as local faster-whisper** (`stt.enabled: true`, `stt.local.model: "base"`), which AGENTS.md §13 forbids outright (§10.6) | **open — must change in Phase 12** |
| 13 | **`stt.language: "en"`** would force English recognition on Chinese voice messages, failing TASK.md 12.3 / 19.8 / 19.9 (§10.6) | **open — must change in Phase 12** |
| 14 | **Messaging bundles are full-access by default**: `hermes-weixin` and `hermes-qqbot` both equal `_HERMES_CORE_TOOLS`, which includes terminal, file, browser, code execution, cron, delegation, and computer use (§10.4) | mitigated by making Phase 6 mandatory and blocking exposure until it passes |
| 15 | **Cache retention mismatch**: Hermes prunes `cache/scratch/` after 24 h idle; AGENTS.md §15 requires ≤1 h for media (§10.5) | **open — resolve in Phase 14** |
| 16 | `hermes doctor` warns that system **SQLite 3.45.1 has the WAL-reset bug** and advises running `hermes update` — which would break the pin *and* would not fix it, since the bug is in Ubuntu's libsqlite3, not Hermes (§10.7) | **accepted by operator — documented risk, not blocking.** Risk further reduced: `hermes doctor` reports `state.db` runs in **rollback journal mode, not WAL**, so the WAL-reset defect does not apply to it. See §11 for the accompanying prohibition |
| 17 | `agent.max_turns` was 500, allowing a very long tool loop on a 1.6 GiB shared host (§10.7) | **resolved** — reduced to **32** (§11.2) |
| 18 | **Primary model is a third-party OpenAI-compatible relay** (`www.kldai.cc`) rather than a first-party provider. Measured latency 1.1–10.9 s and the operator reports periodic dropouts. The relay's `wire_api` is `responses` and `chat/completions` is actively refused for this model, so `transport: codex_responses` was required (§10.10, §10.11) | applied by operator decision; mitigated by an explicit DeepSeek fallback entry |
| 19 | The fallback provider's model id was wrong (`deepseek-chat` does not exist on this account) and its key was initially unset, making the fallback inert | **resolved** — key supplied, model corrected to `deepseek-flash` (§10.11) |
| 20 | `hermes config set` rewrites `config.yaml` and strips its template comments (§10.13) | accepted; pre-change backups retained deliberately |
| 21 | **Hermes lazily installs optional Python packages at runtime** (observed: `boto3` for the bedrock feature). Without a persisted mirror the fetch goes to the network-blocked `pypi.org` and stalls a whole turn (§10.12) | **mitigated** — mirror vars persisted in `.env`; **must also be supplied to the systemd unit in Phase 16** |
| 22 | Model ids had to be corrected from the operator's input on both providers (case-sensitivity + non-existent ids) (§10.11) | resolved; recorded so future edits verify against `/v1/models` first |
| 23 | **STT was enabled globally with the local faster-whisper provider and `language: en`** — a direct AGENTS.md §13 violation and a TASK.md 12.3/19.8/19.9 failure. It is a config-only toolset, so Phase 6's `platform_toolsets` work could not touch it (§10.16) | **resolved** — `stt.enabled` set to `false`; re-enabled in Phase 12 with Groq + auto/`zh` (§10.17) |
| 24 | The `cli` platform retained 17 toolsets including `terminal`, `file`, `browser`, `code_execution`, `computer_use` (§10.16) | **resolved** — converged to the same four toolsets as the messaging platforms (§10.17) |
| 25 | **AGENTS.md §11 assumes per-user long-term memory, but the built-in store has no user dimension** — one global `MEMORY.md` / `USER.md` pair is shared by every person and chat, so anything learned from one user is injected for all (§14.1) | **open — decision needed before a second user is allowlisted** |
| 26 | **`session_search` is not scoped by user and is live on the messaging platforms** — the isolation `build_session_key()` provides at the context layer is not enforced at the retrieval layer (§14.3, §14.4) | **open — decision needed before a second user or group is added** |
| 27 | **`group_sessions_per_user: true` means the bot follows no group conversation** — each member is a separate session, so it sees only the current speaker's own history and cannot know what anyone else in the group said, nor any display name (§14.2) | **open — likely worth revisiting in Phase 7.4/19; QQ supplies no names regardless** |
| 28 | **QQ Bot API v2 transmits no display names** (only `user_openid` / `member_openid`), so the bot cannot address anyone by name unless told (§14.2) | recorded as a platform constraint; the persona already compensates |

---

## 14. Memory architecture — per-user long-term memory, user identity, cross-chat joining

**Question asked (operator, 2026-09-29):** can the bot keep long-term memory per individual, can it tell
users apart, and can it join group-interaction memory with private-interaction memory?

Everything below was read from the installed v0.21.5 source and from `state.db` on the host. Nothing here
is inferred from documentation.

### 14.1 Per-user long-term memory — **NO**, there is no user dimension

The built-in memory is a **single global pair of files** shared by every person, every chat, and every
platform:

```text
~/.hermes/memories/MEMORY.md   (capacity 2 200 chars)
~/.hermes/memories/USER.md     (capacity 1 375 chars)
```

| Evidence | Value |
| --- | --- |
| `tools/memory_tool.py:38-40` `get_memory_dir()` | `return get_hermes_home() / "memories"` — **no user / session / chat component in the path** |
| `tools/memory_tool_store.py:212` | the only two destinations are `USER.md` and `MEMORY.md` |
| `memory` tool `target` enum | `user` \| `memory` — semantic is singular *"who **the user** is"* |
| `hermes memory status` | `Provider: (none — built-in only)` |
| `~/.hermes/memories/` on disk | **empty** — nothing has ever been written |

So with more than one QQ/Weixin user, entries written while talking to A are injected into B's system
prompt. This is **cross-user contamination by construction**, not a misconfiguration. AGENTS.md §11
("stable user preferences") cannot be satisfied per person with the built-in store alone.

The only per-instance isolation primitive in this release is a **profile** (`hermes_cli/profiles.py`
`_PROFILE_DIRS` includes `memories` and `sessions`; profiles clone `memories/MEMORY.md` and
`memories/USER.md`). But a profile is a separate Hermes instance / bot identity — **the gateway has no
route that assigns an end-user to a profile**, so profiles cannot be used to give each chat partner their
own memory without running one bot per person.

Available external providers (`honcho`, `openviking`, `mem0`, `holographic`, `retaindb`, `byterover`,
`supermemory`) are installed as plugins but inactive. Some have a per-user namespace concept. **AGENTS.md
§11 says not to add an external provider in the first deployment**, so this is out of V1 scope by policy,
not by capability.

### 14.2 Telling users apart — **YES**, and it is already working; but the model only sees opaque ids

Session keys are per participant and per chat, and this is proven by real rows:

```text
agent:main:qqbot:dm:A729C39060FB65742B0C808249E36326
agent:main:qqbot:group:56B2E66590BD2ED9A098C5D8B0123D68:A729C39060FB65742B0C808249E36326
```

| Evidence | Value |
| --- | --- |
| `gateway/session.py:673` `build_session_key()` | layout `<ns>:<platform>:<chat_type>[:<chat_id>][:<thread>][:<user>]` |
| `config.yaml:719` | **`group_sessions_per_user: true`** (explicit) → each member gets their own session inside a group |
| `state.db` `sessions` (7 rows) | `user_id` / `chat_id` / `chat_type` populated correctly for both the dm and the group session |
| Authorization | `dm_policy: allowlist` + `group_policy: allowlist`, matched on openid |

The same `user_openid` appears in both the dm key and the group key, so **identity is continuous across
group and private chat** at the infrastructure level.

Three caveats that matter:

1. **QQ Bot API v2 supplies no display name.** `gateway/platforms/qqbot/adapter.py` reads only
   `author.user_openid` (c2c) and `author.member_openid` (group) — there is no name field on the wire.
   The bot therefore **cannot know anyone's nickname** unless the person states it. This is precisely why
   the persona has to say "称呼不固定，根据上下文自由发挥".
2. **What the model actually receives** is `## Current Session Context` → `**Source:** Qqbot (DM with
   A729C39060FB65742B0C808249E36326)`, i.e. a **raw openid**, because `privacy.redact_pii` is `false`.
   Built by `gateway/session.py:375` `build_session_context_prompt()`, called from
   `gateway/run_agent_cache.py:629` — confirmed to be in the gateway turn path.
3. **The `[nickname]` sender prefix is NOT added in QQ groups.**
   `gateway/run_inbound.py:1413` `_prefix_inbound_sender_context()` only prepends `[name]` when
   `is_shared_multi_user_session()` is true, and with `group_sessions_per_user: true` that returns
   **False** (`gateway/session.py:633-641`). Consequence: in a group the bot sees only that one member's
   own session, has no name, and **does not see the other members' messages at all**.

### 14.3 Joining group memory with private memory — three layers, three different answers

| Layer | Joined? | Mechanism / evidence |
| --- | --- | --- |
| **Conversation context** | **No — deliberately.** Group and DM are different session keys, so context does not leak between them. This is what AGENTS.md §10 demands | `build_session_key()` layout, verified in `state.db` |
| **Long-term memory** | **Yes, but uncontrollably.** `MEMORY.md` / `USER.md` are global, so anything written in any chat is injected into every chat's prompt. There is **no attribution field**, so an entry cannot be traced to a person or a chat | §14.1 |
| **Retrieval (`session_search`)** | **Yes, and unscoped.** The search path takes no user or chat filter — `current_session_id` is used only to *exclude the current live session* (`session_search_tool.py:355-414`, `_list_recent_sessions:480-499`), not to scope results. One shared `state.db` | tool enabled on both `qqbot` and `weixin` |

### 14.4 ⚠️ The one item here that is a real risk, not just a limitation

`session_search` is **live on the public-facing platforms** and is **not restricted by user**. Any
authorised person can therefore induce the bot to read another person's private conversation out of
`state.db` — the isolation that `build_session_key()` establishes at the context layer is **not enforced
at the retrieval layer**.

Today the exposure is nil in practice: the DM allowlist holds only the operator, `group_allow_from` holds
one group, and `session_search` has never been invoked in a real turn. It becomes real the moment a
second person is allowlisted or a second group is added.

**Standing rule:** before adding any user or group, decide whether `session_search` stays enabled
(`AGENTS.md` §10 and §11 both point at isolation, and the tool is not isolation-aware). Options are to
disable it on the messaging platforms, or to accept and document that history is shared across everyone
who can reach the bot. **No change was made — this needs an explicit decision.**

### 14.5 What it would take to actually deliver per-user memory

| Option | Character |
| --- | --- |
| **A. Convention inside the persona prompt** — instruct the model to prefix entries with an identity tag, e.g. `[user:<openid>] 喜欢喝咖啡`, and to read only its own tags | zero code, zero new services; uses the existing global `MEMORY.md`; relies on the model's compliance; 2 200/1 375-char budget is shared by everyone |
| **B. External memory provider** (mem0 / honcho / …) | proper per-user namespacing, but adds a service or API dependency to a 1.6 GiB shared host and **violates AGENTS.md §11** for V1 |
| **C. Patch the memory store to be per-session/per-user** | correct but invasive; `memory_tool_store.py` has drift detection and snapshot logic, so the blast radius is larger than the QQ passive-reply patch (§11.17) and it is not durable across upgrades |

**No option was implemented. This is an open decision.**

---

## 15. Change log

- 2026-09-29 — Phase 0 executed. Baseline recorded. No host change.
- 2026-09-29 — Phase 1.1 and 1.2 executed: system updated (80 packages), minimal dependencies installed (`unzip`, `ffmpeg`, `sqlite3`).
- 2026-09-29 — Phase 2 executed: 2 GiB `/swapfile` created, enabled, persisted in `/etc/fstab`; persistence proven without a reboot via `swapoff` + `swapon --all`.
- 2026-09-29 — Residue audit. `apt-get clean` released 177 M of regenerable cache.
- 2026-09-29 — Shared-host finding raised (§3). Phase 3 halted for decisions.
- 2026-09-29 — Operator decisions received and applied (§8):
  - dedicated `hermes` service account created, media cache at `/var/lib/hermes/media`, account locked and SSH-inaccessible;
  - `/home/admin/chat_bot` backed up locally (verified 63 files / 364 147 bytes, plus Gitee remote) and then deleted from the server;
  - stale `/tmp` scratch removed (≈90 MB) — live Aliyun IPC, `systemd-private-*`, X sockets, and `snap-private-tmp` preserved and verified intact afterwards;
  - eight scratch files copied to `backups/tmp-scratch/` before removal;
  - `vm.swappiness` changed `0 → 10`, runtime and persisted value verified, original at `/etc/sysctl.conf.bak-before-hermes`;
  - post-change impact check passed: `nginx`, `main-site-editor`, `prune-recorder-updates.timer`, `ssh`, `aliyun` all `active`.
- 2026-09-29 — **Phase 3.1 completed.** Authoritative source established (`NousResearch/hermes-agent`). Release pinned to tag `v2026.9.24` / v0.21.5 / commit `f97608f1…`. Installer fetched from the pinned tag, checksummed (`2017ddf0…`), and stored at `installer/install-v2026.9.24.sh`; `--skip-browser` and 11 other flags confirmed present in that exact file. Host prerequisites verified (`git`, `curl`, `xz`, `g++`). Four pre-flight gaps found: PyPI unusable (blocking), `~/.local/bin` missing from the service account's PATH, `linger` not enabled, and — positively — no root required on the install path. **No installer was executed.**
- 2026-09-29 — Operator chose Tsinghua TUNA as the PyPI index and authorised Phase 3.2.
- 2026-09-29 — **Phase 3.2 completed.** Installer verified byte-identical on the server (SHA-256 match), then executed as `hermes` from disk with the TUNA mirror injected. 6 m 5 s, **exit code 0**. uv 0.12.20; system Python 3.12.3 reused; managed Node 26.10.0; repo cloned and **pinned to `f97608f178d1ffeca59860195ab7da295f7c8e5f`**; `--skip-browser` and `--skip-computer-use` both honoured; 58 bundled skills synced; setup wizard skipped (no terminal). `uv.lock --locked` verification did not run (stale lockfile) — dependency set is not hash-pinned. Standalone installer copy removed afterwards.
- 2026-09-29 — **Phase 3.3 completed.** Pin verified independently (`git rev-parse HEAD` = pin; `chore: release v0.21.5 (2026.9.24)`; clean worktree). `hermes --version` = `v0.21.5 (2026.9.24)`. Real subcommands confirmed: `hermes gateway`, `hermes tools`, `hermes doctor`. No Chromium/Playwright binary, no `ms-playwright` cache, no browser process, no local model weights. Footprint 2.0 GB. **Warning recorded: `hermes update` must not be run — it would break the pin.**
- 2026-09-29 — Config credential scan performed before mirroring: the only `sk-` occurrence is a commented example at `config.yaml:1090`; `.env` holds no API keys (setup skipped). `server-mirror/` re-pointed at the real artefact paths and switched to connecting as `hermes` (admin cannot traverse the `700` `HERMES_HOME`). 5 artefacts mirrored, 0 failures, 0 uncommented credential-shaped hits.
- 2026-09-29 — **Phase 4 completed.** Platform registry confirms `weixin` → `hermes-weixin` and `qqbot` → `hermes-qqbot`; credential variables, allowlist knobs, and both QR-login flows identified. Real tool command is `hermes tools list --platform <p>` — bare `hermes tools` and `--summary` need a TTY, and `hermes chat --list-toolsets` does not exist in this release. **Critical:** both messaging bundles default to the full `_HERMES_CORE_TOOLS` set, so QQ and Weixin would start with terminal, file write, browser, code execution, cron, delegation and computer use enabled; Phase 6 is therefore the highest-risk step and blocks exposure. Vision/STT/TTS/memory/LLM mechanisms recorded; two default STT values conflict with AGENTS.md §13 (§10.6); `hermes doctor` rc=0 with a SQLite WAL-reset warning whose suggested fix would break the pin.
- 2026-09-29 — **Operator decisions applied (§11).** SQLite WAL-reset bug accepted and documented; `hermes update` and any system-SQLite change explicitly prohibited. `agent.max_turns` semantics investigated against source (tool-calling iterations per conversation turn, not turns) then reduced **500 → 32**, with a config backup taken and the `HERMES_MAX_ITERATIONS` shadowing trap checked. Provider egress measured: `api.openai.com` and `api.mistral.ai` are network-blocked, which reduces Phase 12's STT options to Groq alone.
- 2026-09-29 — **Phase 5 config applied.** Operator supplied relay `base_url` (`https://www.kldai.cc/v1`), `wire_api = "responses"`, and model `GPT-6-Sol`, electing to add a fallback and to enter the key personally. `transport: codex_responses` was derived from `config_providers.py:47-49` rather than assumed. Written: `providers.kldai` (key bound to endpoint via `key_env`), `fallback_providers` → DeepSeek direct, and `model.{provider,default,base_url}`. Verified through Hermes itself: `hermes fallback list` shows `Primary: GPT-6-Sol (via kldai)` with a 1-entry fallback chain; `hermes doctor` rc=0, config v46. Credential slots appended to `.env` **commented out** (lines 544/546) pending the operator. Relay reachability confirmed (`/v1/responses` answers 401 = live endpoint).
- 2026-09-29 — **Incident + recovery (§10.13).** A `cat >> … <<YAML` heredoc was executed by the *local* shell instead of the remote one; a mangled 6-line comment fragment reached the server and the intended keys did not. config.yaml was restored from backup, then the change was re-applied via local-file → `scp` → `cat` → fragment removed. No functional loss; the heredoc approach is now prohibited.
- 2026-09-29 — Noted that `hermes config set` strips template comments when it rewrites `config.yaml` (comments 1 999 → 1 736; code lines 139 → 148 = only the intended edits). Pre-change backups retained as the last annotated copy.
- 2026-09-29 — **Phase 5.3 PASSED.** Both operator keys supplied. Two model-id errors in the operator's input found and corrected against the providers' own `/v1/models` output: the relay is case-sensitive and exposes `gpt-6-sol` (not `GPT-6-Sol`) among 8 ids and **no DeepSeek models at all**; DeepSeek direct exposes `deepseek-flash` and `deepseek-v4-pro` (not `deepseek-chat`). Confirmed the relay **refuses `chat/completions`** for `gpt-6-sol` (400) and serves it on `/v1/responses` (200), validating `transport: codex_responses`. Final evidence: `rc=0` in 30 s, stdout `PHASE5-OK-PERSISTED`, usage `model=gpt-6-sol`, `api_calls=1`, `completed=true`, `failed=false`.
- 2026-09-29 — **Root-caused a hang that was not a model problem (§10.12).** Three earlier `hermes -z` attempts were killed by `timeout` (rc=124) with no output. Cause: Hermes lazily installs `boto3` for the bedrock feature at runtime, and the TUNA mirror set during Phase 3 was absent from the runtime environment, so `uv` hit the network-blocked `pypi.org` and retried for ~84 s per attempt. Fix: persist `UV_DEFAULT_INDEX` / `UV_INDEX_URL` / `PIP_INDEX_URL` in `.env`. Same command then completed in 30 s. **Flagged as a Phase 16 prerequisite for the systemd unit.**
- 2026-09-29 — Noted for Phase 11: the operator reports DeepSeek **V4.1 Flash has vision capability**, i.e. `deepseek-flash`. The vision auxiliary router currently defaults to Nous Portal, which is not configured and logs `Auxiliary Nous client unavailable` — so Phase 11 should point `auxiliary.vision.*` at a working provider (likely `deepseek-flash`) rather than leaving it on the default.
- 2026-09-29 — **Phase 6 completed.** Operator elected to keep `session_search` and remove `skills`, `clarify`, `todo` as well as the AGENTS.md §5 list. `hermes tools disable` applied to both `qqbot` and `weixin`; verified by re-reading `hermes tools list --platform`, which now shows only `vision`, `tts`, `memory`, `session_search` enabled on each. MCP confirmed unconfigured. No Chromium process, no `ms-playwright` cache. `hermes doctor` clean. Two items Phase 6 could not reach and both need a decision: **STT is enabled globally with local faster-whisper and `language: en`** (config-only toolset, violates §13, and TASK.md orders platform setup before STT), and **the `cli` platform retains 17 toolsets** including terminal/file/browser/code_execution.
- 2026-09-29 — **Phase 6 closed out.** Both open items resolved by operator decision: `stt.enabled` set to `false` (§13 violation removed; Groq + auto/`zh` deferred to Phase 12), and `cli` converged to the same 13-item disable list. **All three platforms — `cli`, `qqbot`, `weixin` — now have exactly 4 toolsets: `memory`, `session_search`, `tts`, `vision`.** TASK.md's unqualified Phase 22 criteria (terminal/file/code-execution/MCP disabled) now hold for every platform, and the Phase 7→12 ordering hazard is gone: no platform can trigger local Whisper before STT is properly configured.
- 2026-09-29 — **Phase 7 completed** (§11). QQ onboarded via a purpose-built non-interactive runner around `qr_register()` (the wizard is menu-only). Credentials written to `.env`; `dm_policy: allowlist` chosen over the default `pairing`; QR-login supplies the operator's own openid, which was used as the allowlist entry. Group replies initially failed with HTTP 400 `主动消息失败, 无权限` — root-caused to `run_turn.py` never setting `reply_to` for `Platform.QQBOT`, so outbound messages carried no passive-reply `msg_id`. Fixed with a narrow adapter-level patch (§11.17, and a documented AGENTS.md §24.5-6 deviation). Persona 云白/小云 injected and revised twice, now v1.2.0.
- 2026-09-29 — **Memory architecture audited (§14).** Answers, all read from source and `state.db` rather than documentation: (a) per-user long-term memory **does not exist** — one global `MEMORY.md`/`USER.md` pair with no user dimension, currently empty; (b) users **are** distinguished — session keys are per participant and per chat, `group_sessions_per_user: true`, allowlists keyed on openid — but the model receives only a **raw openid** (no display names: QQ Bot API v2 does not transmit them) and, because group sessions are per-user, receives neither the `[nickname]` prefix nor the other members' messages; (c) group/private joining behaves differently per layer — deliberately **not** joined at the context layer, **uncontrollably** joined in global memory (no attribution), and **unscoped** at the `session_search` retrieval layer, which is the one real privacy gap and is live on both messaging platforms. **Four new open decisions recorded (deviations 25–28). No configuration was changed by this audit.**
