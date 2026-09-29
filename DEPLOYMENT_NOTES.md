# DEPLOYMENT_NOTES.md

Project: Hermes QQ + Weixin Lightweight Multimodal Agent
Scope of this file: verified facts, real commands, and deviations. No secrets.
Status: Phase 0 (Preflight) — executed
Last updated: 2026-09-29

---

## 1. Execution context

- Operator workstation: Windows (win32). All host-level work is performed **over SSH to the target host**. No package, swap, systemd, or `/var/lib` change is made on the local workstation.
- Remote entry point: `ssh admin@8.148.73.94`
  - Authentication: `publickey` (no password prompt; `BatchMode=yes` succeeds)
  - Client key: `C:\Users\liuzhuo\.ssh\id_ed25519` — ED25519, `SHA256:2Uf6Uz83hwbZVsxwG2aMcHAl3QNMkK+Pw3rynXNLXkc`
  - Client config: `C:\Users\liuzhuo\.ssh\config` contains a host entry for `8.148.73.94`
  - Server host key: ED25519 `SHA256:ITJw4b4dQxd0UIXekwdSzIoGBBnd+1j7bfsNwfVd8qw`
  - Remote `authorized_keys` line 4 grants: agent-forwarding, port-forwarding, pty, user-rc, x11-forwarding
  - Remote `admin` = `uid=1000(admin) gid=1000(admin) groups=1000(admin)`; passwordless sudo `(ALL) NOPASSWD: ALL`

---

## 2. Target host baseline (Phase 0.0 / 0.1)

| Item | Observed | Acceptance |
| --- | --- | --- |
| Execution target confirmed | Commands ran on `8.148.73.94`, not the workstation | pass |
| Hostname | `iZn4aetqy7dj6wsl6t9c7hZ` (Aliyun ECS naming) | — |
| OS | Ubuntu 24.04.2 LTS (Noble Numbat) | pass |
| Kernel | `6.8.0-63-generic` x86_64 | — |
| CPU | 2 vCPU (`nproc` = 2) | pass |
| RAM | total 1.6 GiB, used 475 MiB, available 1.1 GiB, buff/cache 847 MiB | **pass with caveat — see §4.1** |
| Swap | none (0 B); no swap entry in `/etc/fstab` | **Phase 2 required** |
| Disk | `/dev/vda3` 40 G total, 31 G available (18% used) | pass (>= 10 GB) |
| Time | `Asia/Shanghai` (CST +0800), NTP active, clock synchronized | pass |
| Private IP | `172.18.22.31/18` on `eth0` | — |
| DNS | `getent hosts github.com` → `20.205.243.166` | pass |
| Egress | github.com 200, registry.npmjs.org 200, pypi.org 200 | pass (latency note in §4.3) |
| Hermes installed | `command -v hermes` → not found | matches AGENTS.md §0 assumption |
| Hermes artefacts | no `/var/lib/hermes`, no `~/.hermes`, no hermes systemd unit | matches AGENTS.md §0 assumption |
| Uptime | 11 days, load average 0.06 / 0.02 / 0.00 | clean baseline |

Raw commands used (Phase 0.0 / 0.1):

```bash
pwd; id; hostname; uname -a; command -v hermes || true
cat /etc/os-release; lsb_release -a
nproc; free -h; df -h /; swapon --show; grep -i swap /etc/fstab
sudo -n true; sudo -n -l
date; timedatectl; getent hosts github.com; ip -4 addr show scope global
```

---

## 3. Package inventory relevant to Phase 1

Present on the image:

| Tool | Version |
| --- | --- |
| curl | 8.5.0 |
| wget | 1.21.4 |
| git | 2.43.0 |
| htop | 3.3.0 |
| python3 | 3.12.3 |
| node | v18.19.1 |
| npm | 9.2.0 |

Missing, targeted by Phase 1.2: `unzip`, `ffmpeg`, `sqlite3`

Must remain absent (AGENTS.md §3, §5): `chromium`, `playwright`, local model weights

---

## 4. Findings, risks, and decisions needed

### 4.1 RAM is 1.6 GiB, not 2.0 GiB — alarm threshold must be re-derived

AGENTS.md §21 defines `Sustained > 1.7 GB RAM: investigate`. On this host that threshold exceeds physical RAM, so it can never fire before the OOM killer does. The budget was written for "2 GB"; the real ceiling here is ~1.6 GiB, and ~1.1 GiB is currently available.

Proposed adjustment (NOT yet applied — needs a decision):

```text
Idle:                 < 600 MB used
Normal chat:          < 900 MB used
Short media bursts:   < 1.1 GB used
Investigate above:    ~1.3 GB used, or any sustained swap-in activity
```

This is a deviation from AGENTS.md §21 and must be recorded as such if adopted. Per AGENTS.md §24 and §25 it should be reflected in the documents rather than silently applied.

### 4.2 No swap — Phase 2 is a prerequisite, not a hardening extra

`free -h` shows 0 B swap and `/etc/fstab` has no swap entry. Combined with §4.1 this makes Phase 2 blocking for anything memory-elastic. Not yet created.

### 4.3 PyPI egress latency

`https://pypi.org` answered HTTP 200 but took 7.75 s (github 0.93 s, npm registry 0.73 s). If the selected Hermes install method pulls from PyPI, use generous timeouts and consider a domestic mirror. Relevant to Phase 3.1 verification.

### 4.4 Pre-installed runtimes are extra surface, not a green light

Node 18.19.1 and Python 3.12.3 come from the image. AGENTS.md §3 warns against extra Node services and §18 against unnecessary dependencies. Do not add a runtime just because one is present; only satisfy the selected release's actual requirements.

### 4.5 Server-side password authentication is enabled

`ssh -v` reported `Authentications that can continue: publickey,password`. Key auth works and is what we use. Disabling password auth is a reasonable hardening candidate but it is **outside V1 scope** and would change the operator's access path — record only, do not apply without explicit approval.

---

## 5. Phase 3.1 — Hermes source and installation method

**Not yet established.** Per AGENTS.md §17 and TASK.md Phase 3.1, the following must be filled in *before* any installer command is executed. Deliberately blank.

- Authoritative source / repository / documentation: TBD
- Selected release / tag / commit: TBD
- Verified installation method for that release: TBD
- Browser/Playwright skip option, exact current name: TBD

---

## 6. Discovered CLI / config / adapter facts

**Not yet discovered.** To be filled during Phase 3.3 and Phase 4 using the real installed CLI.

- Hermes executable path: TBD
- `hermes --version`: TBD
- Gateway launch command: TBD
- Tool-inspection command: TBD
- Config file path: TBD
- QQ adapter name: TBD
- Weixin adapter name: TBD
- Memory configuration mechanism: TBD
- Vision / STT / TTS configuration mechanism: TBD

---

## 7. Deviations from AGENTS.md / TASK.md

No deviation has been applied. §4.1 and §4.5 are candidate deviations awaiting a decision.

---

## 8. Change log

- 2026-09-29 — Phase 0 executed over SSH from the operator workstation. Host baseline, package inventory, and egress recorded. **No host-level change was made**: no package installed, no swap created, no systemd unit written, no `/var/lib` path touched.
