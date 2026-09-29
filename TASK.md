# TASK.md

## Hermes QQ + Weixin Lightweight Multimodal Agent

### Execution Goal

Deploy Hermes Agent on a **2 vCPU / 2 GB RAM Ubuntu server** as a 24×7 QQ + Weixin multimodal chat agent with:

- text chat
- multi-turn session
- built-in lightweight long-term memory
- Vision
- STT
- optional TTS
- remote LLM APIs
- automatic restart and boot recovery

Follow all constraints in `AGENTS.md`.

## Current Repository State

At the start of this execution plan, assume the workspace contains only the engineering documents unless the environment proves otherwise. In particular, do **not** assume that Hermes, configuration files, service files, adapters, or application code already exist.

The first operational step is to confirm that the current shell is the intended target server. Host-level changes must be made only on that target host.

During execution, create/update `DEPLOYMENT_NOTES.md` with:

- target host baseline (non-secret),
- selected Hermes source and version/tag/commit,
- verified installation method,
- actual CLI commands/subcommands discovered,
- actual config paths and adapter names,
- deviations from this plan.

---

# Phase 0 — Preflight

## 0.0 Confirm execution target

Before installing packages or changing system files, determine whether the current shell is the intended 2C2G target server.

Run:

```bash
pwd
id
hostname
uname -a
command -v hermes || true
```

If this is not the target server, do not create swap, install Hermes, write systemd units, or modify `/var/lib` here. Move execution to the authorized target host first.

Record the result in `DEPLOYMENT_NOTES.md`.

## 0.1 Verify target server

Run on the confirmed target host:

```bash
uname -a
lsb_release -a
free -h
df -h
nproc
```

Acceptance:

- [ ] current shell is confirmed to be the intended target server
- [ ] Ubuntu 20.04 / 22.04 / 24.04 or compatible supported environment
- [ ] 2 vCPU available
- [ ] approximately 2 GB RAM available
- [ ] at least 10 GB free disk recommended
- [ ] network connectivity works
- [ ] DNS works
- [ ] baseline recorded in `DEPLOYMENT_NOTES.md`

---

# Phase 1 — Base system

## 1.1 Update system

```bash
sudo apt update
sudo apt upgrade -y
```

## 1.2 Install minimal dependencies

```bash
sudo apt install -y \
  curl \
  wget \
  git \
  unzip \
  ffmpeg \
  sqlite3 \
  htop \
  ca-certificates
```

Acceptance:

- [ ] `ffmpeg -version` works
- [ ] `sqlite3 --version` works
- [ ] no Chromium installed as part of this phase

---

# Phase 2 — Swap

## 2.1 Create 2 GB swap

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

Verify:

```bash
free -h
```

## 2.2 Persist swap

Ensure `/etc/fstab` contains:

```text
/swapfile none swap sw 0 0
```

Acceptance:

- [ ] swap appears in `free -h`
- [ ] swap survives reboot

---

# Phase 3 — Discover and install Hermes

## 3.1 Establish the authoritative installation source

Before executing any installer command:

1. identify the current official Hermes repository/documentation,
2. determine the release/tag/commit to deploy when feasible,
3. verify the installation method supported by that release,
4. verify whether a browser/Playwright skip option exists and its exact current name,
5. record the source, selected version, and verified installation method in `DEPLOYMENT_NOTES.md`.

**Do not execute an installation snippet copied from an older document merely because it appears in this repository or prior chat history.**

## 3.2 Install Hermes Agent

Execute only the installation method verified in Phase 3.1.

Requirements:

- avoid Chromium/Playwright if the selected release permits it,
- do not install local model weights,
- do not enable unrelated messaging platforms,
- do not add Docker unless the verified deployment method requires it or it has a documented operational advantage within the 2C2G budget.

## 3.3 Validate installation identity and CLI

Run the commands that exist in the selected release. Start with:

```bash
command -v hermes
hermes --version || true
hermes --help
```

Use `hermes --help` to discover the real gateway/tools commands if historical subcommands differ.

Record in `DEPLOYMENT_NOTES.md`:

- executable path,
- reported version (if available),
- selected release/tag/commit,
- actual gateway command,
- actual tool-inspection command.

Acceptance:

- [ ] authoritative source identified
- [ ] selected Hermes version/revision recorded
- [ ] installation method verified before execution
- [ ] Hermes CLI starts successfully
- [ ] actual gateway command or equivalent is identified
- [ ] no Chromium/Playwright dependency was intentionally installed
- [ ] no local model was installed

---

# Phase 4 — Inspect installed Hermes capabilities

Use the installed CLI as the source of truth. Begin with:

```bash
hermes --version || true
hermes --help
hermes tools || true
hermes gateway --help || true
```

If `tools` or `gateway` is not a valid subcommand, discover the equivalent from `hermes --help` and the selected release documentation/source. Do not invent a replacement command.

Record in `DEPLOYMENT_NOTES.md`:

- available toolsets and their exact names
- actual configuration path
- actual QQ adapter name
- actual Weixin adapter name
- current gateway launch command
- current memory configuration mechanism
- current Vision/STT/TTS configuration mechanism

Do not edit config based only on historical examples.

Acceptance:

- [ ] current Hermes version-specific tool names documented
- [ ] correct config file identified
- [ ] current QQ/Weixin adapter names identified
- [ ] current gateway startup command identified
- [ ] findings recorded in `DEPLOYMENT_NOTES.md`

---

# Phase 5 — Configure remote LLM

## 5.1 Add primary model

Configure one remote text-capable LLM.

Possible providers:

```text
GPT
Claude
Gemini
Qwen
DeepSeek
other supported remote provider
```

## 5.2 Protect credentials

Store API keys in:

- environment variables, or
- protected Hermes config/secret files

Apply restrictive permissions where appropriate:

```bash
chmod 600 <secret-file>
```

Do not commit secrets.

## 5.3 Test text chat

Test with a simple prompt.

Acceptance:

- [ ] remote LLM responds successfully
- [ ] API key is not embedded in source code
- [ ] API key does not appear in logs
- [ ] no local inference process starts

---

# Phase 6 — Disable execution-heavy tools

Inspect actual tool names with:

```bash
hermes tools
```

Disable all V1-unneeded execution tools.

Target disabled capabilities:

```text
Terminal
Shell
File Tool
Browser
Playwright
Computer Use
Web Search
Code Execution
MCP
Hermes Cron Tool / model-exposed scheduled-task capability
Delegation
Sub-Agent
Image Generation
ACP / IDE integration
```

Do not delete source files simply to save RAM.

Acceptance:

- [ ] bot cannot execute shell commands
- [ ] bot cannot browse the web through browser automation
- [ ] bot cannot arbitrarily read/write server files
- [ ] bot cannot execute arbitrary Python/shell code
- [ ] MCP is disabled
- [ ] no Chromium process appears after normal chat use

Check:

```bash
ps aux | grep -Ei 'chromium|chrome|playwright'
```

---

# Phase 7 — Configure QQ

## 7.1 Prepare QQ bot credentials

Create/configure the required QQ bot/application.

Obtain the current required credentials, such as:

```text
AppID
ClientSecret / AppSecret
```

Use current QQ/Hermes documentation for exact names.

## 7.2 Configure QQ adapter

Enable only the QQ adapter.

Initial access policy:

- allow personal test account
- allow specific test group(s)
- require @ mention in groups if supported/preferred

## 7.3 Test QQ private chat

Send:

```text
你好
```

Expected path:

```text
QQ
→ QQ Adapter
→ Hermes Gateway
→ Session
→ LLM
→ Delivery
→ QQ
```

## 7.4 Test QQ group chat

Test:

```text
@机器人 你好
```

Acceptance:

- [ ] QQ private message receives reply
- [ ] QQ group @ receives reply
- [ ] non-allowed users/groups are rejected or ignored
- [ ] adapter reconnects after temporary connection loss
- [ ] gateway restart restores QQ connection automatically

---

# Phase 8 — Configure Weixin

## 8.1 Enable Weixin adapter

Use the supported Hermes Weixin integration.

## 8.2 Complete authorization

Perform required QR/account authorization.

## 8.3 Validate session continuity

Test:

```text
微信：
你好
```

Acceptance:

- [ ] inbound Weixin message is received
- [ ] response is delivered
- [ ] normal gateway restart does not require unnecessary repeated authorization when persistence is supported
- [ ] context token/state handling works correctly
- [ ] long-poll or current supported receive loop remains stable

---

# Phase 9 — Session isolation

Session persistence is mandatory.

## 9.1 Test same-user multi-turn context

User A:

```text
我叫小明。
```

Then:

```text
我叫什么？
```

Expected:

```text
你叫小明。
```

## 9.2 Test user isolation

User B asks:

```text
我叫什么？
```

The bot must not answer `小明` unless User B separately provided that information.

## 9.3 Test channel isolation

Verify QQ and Weixin sessions do not accidentally share transient chat context.

Acceptance:

- [ ] same chat preserves multi-turn context
- [ ] different users do not leak context
- [ ] group/private sessions are separated
- [ ] QQ/Weixin session identities are separated
- [ ] sessions survive gateway restart where supported

---

# Phase 10 — Built-in memory

Do not add an external memory provider yet.

Use Hermes built-in lightweight memory mechanism, preferably including:

```text
USER.md
MEMORY.md
```

or the current equivalent.

## 10.1 Memory policy

Allow long-term storage of:

- stable user preferences
- long-lived project names
- stable development environment
- long-term working conventions

Do not persist:

- passwords
- API keys
- tokens
- OTP codes
- banking data
- sensitive credentials

## 10.2 Test cross-session recall

Session 1:

```text
我的服务器使用 Ubuntu。
```

Start a new session or otherwise reset transient context.

Ask:

```text
我的服务器系统是什么？
```

Expected:

```text
Ubuntu
```

if that information was intentionally persisted.

Acceptance:

- [ ] session memory and long-term memory are distinguishable
- [ ] long-term memory persists across sessions
- [ ] memory files/store can be inspected
- [ ] sensitive credentials are not intentionally stored

---

# Phase 11 — Vision

Enable remote Vision.

Do not install a local Vision model.

## 11.1 Configure model

Preferred:

```text
one multimodal remote LLM
```

Alternative:

```text
remote Vision model
→ image description
→ main text LLM
```

## 11.2 Configure media limits

Set reasonable limits for:

- maximum image size
- supported formats
- number of images per message
- cache lifetime

## 11.3 Test images

Test:

- [ ] normal photo
- [ ] screenshot
- [ ] Chinese text screenshot
- [ ] source-code screenshot
- [ ] simple chart

Acceptance:

- [ ] QQ image can be understood
- [ ] Weixin image can be understood
- [ ] image processing does not start local model inference
- [ ] temporary images are cleaned after processing/retention period

---

# Phase 12 — STT

Enable speech-to-text.

Priority:

```text
platform transcript/ASR
→ remote STT fallback
→ no local Whisper
```

## 12.1 QQ

If QQ already supplies ASR/transcript data, use it first.

Otherwise forward/process audio with a remote STT provider.

## 12.2 Weixin

If Weixin provides transcript, use it.

Otherwise:

```text
download audio
→ ffmpeg conversion if required
→ remote STT
→ text
→ LLM
```

## 12.3 Test Chinese voice message

Send a voice message such as:

```text
你好，请告诉我我们刚才聊了什么。
```

Acceptance:

- [ ] QQ voice input can produce text
- [ ] Weixin voice input can produce text
- [ ] Chinese recognition is usable
- [ ] no local Whisper/faster-whisper model is loaded
- [ ] temporary input audio is cleaned

---

# Phase 13 — TTS

Enable optional TTS.

Default output remains text.

Generate audio only when requested.

Example:

```text
用语音告诉我什么是快速排序。
```

Preferred provider type:

```text
remote/lightweight TTS
```

Do not deploy a heavy local TTS model.

Acceptance:

- [ ] Chinese TTS output can be generated
- [ ] QQ can receive the supported audio/audio-file format
- [ ] Weixin can receive the supported audio/audio-file format
- [ ] text responses remain default
- [ ] generated audio is cleaned after short retention

---

# Phase 14 — Media cache

Create or validate a bounded media cache.

Suggested path:

```text
/var/lib/hermes/media/
```

or Hermes-native equivalent.

Recommended retention:

```text
images <= 1 hour
input audio <= 1 hour
TTS audio <= 1 hour
```

## 14.1 Scheduler boundary for cleanup

The V1 restriction on Cron means **the Hermes Cron/model-exposed scheduled-task tool must remain disabled**. It does **not** prohibit host-level maintenance scheduling.

For media cleanup, prefer the lightest host-level mechanism in this order when practical:

1. `systemd-tmpfiles` for simple age-based temporary-file cleanup,
2. a dedicated `systemd` timer/service for explicit cleanup logic,
3. `crontab` only as a fallback when a systemd-native mechanism is not practical.

The cleanup scheduler must:

- run outside the Hermes model/tool interface,
- not be callable by the LLM,
- not accept user-authored commands,
- perform infrastructure housekeeping only.

Do **not** enable the Hermes Cron tool to satisfy this phase.

Check:

```bash
du -sh /var/lib/hermes 2>/dev/null || true
```

Acceptance:

- [ ] media directory does not grow indefinitely
- [ ] stale media is automatically removed
- [ ] active media is not deleted before processing completes
- [ ] cleanup is implemented with a host-level mechanism, not Hermes Cron
- [ ] the cleanup mechanism is not exposed to the model/user

---

# Phase 15 — Logging

Enable minimal operational logging.

Required log categories:

```text
gateway start/stop
QQ connect/disconnect
Weixin connect/disconnect
LLM errors
Vision errors
STT errors
TTS errors
session errors
memory errors
unexpected exceptions
```

Do not log secrets.

Enable bounded logs via:

- systemd journal retention, and/or
- logrotate, and/or
- Hermes-native rotation

Acceptance:

- [ ] logs are useful for debugging
- [ ] API keys/tokens are not printed
- [ ] log growth is bounded

---

# Phase 16 — systemd service

Create a systemd service for the actual Hermes Gateway start command discovered earlier.

Example structure:

```ini
[Unit]
Description=Hermes QQ Weixin Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<service-user>
WorkingDirectory=<hermes-working-directory>
ExecStart=<actual-hermes-gateway-command>
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Do not copy placeholder paths literally.

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes
sudo systemctl start hermes
```

Validate:

```bash
systemctl status hermes
journalctl -u hermes -f
```

Acceptance:

- [ ] `systemctl start hermes` works
- [ ] `systemctl stop hermes` works
- [ ] `systemctl restart hermes` works
- [ ] process crash causes automatic restart
- [ ] server reboot causes automatic startup
- [ ] only one active gateway instance exists

---

# Phase 17 — Resource validation

Check:

```bash
free -h
htop
ps aux --sort=-%mem | head -20
```

Desired targets (calibrated to the deployed host's visible RAM — see the measured baseline in `DEPLOYMENT_NOTES.md`):

```text
Idle: < 600 MB used if practical
Normal chat: < 900 MB used if practical
Short media bursts: < 1.1 GB used if practical
Investigate above: ~1.3 GB used, or any sustained swap-in activity
```

The confirmed host reports roughly 1.6 GiB of visible RAM, so a nominal "2 GB" budget is not usable as an alarm threshold on this machine. Re-derive the numbers if the deployment moves to a different host.

Investigate if present:

```text
Chromium
Playwright
local Whisper
local model server
duplicate Hermes process
unexpected Node workers
stale media
unbounded logs
```

Acceptance:

- [ ] normal operation fits safely in 2 GB RAM
- [ ] swap is not continuously thrashing
- [ ] no unexpected heavy background process remains

---

# Phase 18 — Security hardening

## 18.1 Access policy

Configure:

- QQ allowlist during testing
- QQ group allowlist
- Weixin access policy where available
- per-user rate limit
- maximum text length
- maximum image size
- maximum audio size

Initial per-user limit:

```text
10–30 requests/minute
```

Adjust based on real provider quotas.

## 18.2 Secrets

Verify:

```bash
git status
git grep -nE '(API_KEY|SECRET|TOKEN|PASSWORD)' .
```

Review results manually.

Acceptance:

- [ ] no secrets committed
- [ ] config permissions are restricted
- [ ] no arbitrary shell/file/browser/code-execution capability is exposed
- [ ] public access is not enabled before rate limits and access controls are verified

---

# Phase 19 — Functional acceptance test

Complete all tests below.

## 19.1 QQ text

```text
QQ → Hermes → LLM → QQ
```

- [ ] pass

## 19.2 Weixin text

```text
Weixin → Hermes → LLM → Weixin
```

- [ ] pass

## 19.3 Multi-turn context

```text
我叫小明
→
我叫什么？
```

- [ ] pass

## 19.4 Session isolation

User A / User B must not share transient context.

- [ ] pass

## 19.5 Long-term memory

Stable information survives a new session.

- [ ] pass

## 19.6 QQ Vision

Send screenshot/image and ask for explanation.

- [ ] pass

## 19.7 Weixin Vision

Send screenshot/image and ask for explanation.

- [ ] pass

## 19.8 QQ STT

Send Chinese voice message.

- [ ] pass

## 19.9 Weixin STT

Send Chinese voice message.

- [ ] pass

## 19.10 QQ TTS

Request voice response.

- [ ] pass

## 19.11 Weixin TTS

Request voice response.

- [ ] pass

---

# Phase 20 — Reboot recovery test

Run:

```bash
sudo reboot
```

After recovery verify:

- [ ] systemd automatically starts Hermes
- [ ] QQ reconnects
- [ ] Weixin reconnects
- [ ] sessions remain available
- [ ] long-term memory remains available
- [ ] no manual service start is required
- [ ] no unexpected repeated login is required where auth persistence is supported

---

# Phase 21 — Media cleanup test

Generate/test:

- several images
- several voice inputs
- several TTS outputs

Wait past configured retention or manually invoke cleanup.

Acceptance:

- [ ] stale image files removed
- [ ] stale voice files removed
- [ ] stale TTS files removed
- [ ] media directory size returns to expected level

---

# Phase 22 — Final V1 verification

V1 is complete only if all of the following are true:

- [ ] 2C2G server remains stable
- [ ] QQ stays online
- [ ] Weixin stays online
- [ ] text chat works
- [ ] multi-turn context works
- [ ] session isolation works
- [ ] lightweight long-term memory works
- [ ] Vision works
- [ ] STT works
- [ ] optional TTS works
- [ ] heavy AI inference is remote
- [ ] Chromium is not running
- [ ] Playwright is not running
- [ ] local LLM is not running
- [ ] local Vision model is not running
- [ ] local Whisper is not running
- [ ] Terminal/Shell tool is disabled
- [ ] File tool is disabled
- [ ] Code Execution is disabled
- [ ] MCP is disabled
- [ ] Hermes Cron/model-exposed scheduled-task capability is disabled
- [ ] Sub-Agent/Delegation is disabled
- [ ] systemd restarts Hermes automatically
- [ ] server reboot restores service automatically
- [ ] temporary media is cleaned
- [ ] secrets are protected
- [ ] logs remain bounded
- [ ] memory usage is acceptable for 2 GB RAM

---

# Deferred Work

Do not implement these in V1.

Future upgrade order:

```text
V2
External Memory Provider evaluation
(Mem0 / Hindsight / other suitable provider)

V3
Web Search

V4
Restricted read-only MCP

V5
Hermes Cron / model-exposed scheduled reminders

V6
Limited Tool Calling

V7
Browser / Computer Use
```

For every deferred capability:

1. justify the need,
2. estimate memory/process impact,
3. define access/security boundary,
4. add a dedicated task,
5. test independently,
6. re-run full RAM and security validation.

---

# Deliverables

At completion, provide:

- [ ] final Hermes configuration with secrets removed/redacted
- [ ] systemd service file
- [ ] environment/config template
- [ ] QQ setup notes
- [ ] Weixin setup notes
- [ ] selected LLM/Vision/STT/TTS provider list
- [ ] media cache cleanup configuration
- [ ] operational commands
- [ ] validation results
- [ ] observed idle RAM
- [ ] observed normal-chat RAM
- [ ] known limitations
- [ ] any deviations from `AGENTS.md`
- [ ] `DEPLOYMENT_NOTES.md` with verified Hermes version, install source, real commands, and host baseline

---

# Operational Commands

Record the final real commands used in this deployment.

Template:

```bash
# Service
sudo systemctl status hermes
sudo systemctl restart hermes
sudo systemctl stop hermes
sudo systemctl start hermes

# Logs
journalctl -u hermes -f

# Resources
free -h
htop
ps aux --sort=-%mem | head -20

# Disk/media
df -h
du -sh /var/lib/hermes 2>/dev/null || true

# Hermes
hermes --help
hermes tools
hermes gateway --help
```

Update this section if the installed Hermes version uses different commands.

---

# Unresolved Issues

Recorded per `AGENTS.md` §24 clause 13. See `DEPLOYMENT_NOTES.md` for the full evidence.

## UNRESOLVED-1 — QQ group replies are rejected as unauthorised proactive messages

- **Symptom:** inbound group messages are ingested and the agent produces a reply, but QQ refuses delivery:
  `HTTP 400 /v2/groups/<group_openid>/messages: 主动消息失败, 无权限`.
- **Cause (verified in source, v0.21.5):** QQ requires passive replies to carry the inbound `msg_id`.
  `gateway/platforms/qqbot/adapter.py:1414-1421` attaches it correctly *when given a `reply_to`*, but
  `gateway/run_turn.py:3181-3187` computes `_progress_reply_to` only for
  `FEISHU` / `MATTERMOST` / Buzz / relay routes — **`Platform.QQBOT` is absent, so `reply_to` is always
  `None` for QQ.** DMs tolerate proactive messages; groups do not.
- **No configuration-only fix exists.** `reply_to_mode` governs progress threading, not this computation.
- **Impact:** TASK.md Phase 7.4 (group @ mention) and the group half of Phase 19 cannot pass.
- **Resolution (operator-chosen): a narrow core patch was applied.** `gateway/platforms/qqbot/adapter.py`
  `send()` now falls back to `self._last_msg_id.get(chat_id)` for **group chats only**, producing a
  passive reply. Deliberately *not* the alternative of adding `Platform.QQBOT` to `run_turn.py`'s
  `_progress_reply_to` list, because that would widen `reply_to` to every outbound message of a turn
  and QQ caps passive replies per inbound message. Original preserved as
  `adapter.py.orig-qqbot-passive`; applied by `staging/apply-qqbot-passive-patch.py`.
- **This is a deviation from AGENTS.md §24 clauses 5-6** (prefer config/extension points over invasive
  core edits). It is documented rather than silent, and it is **not durable**: any reinstall,
  distribution change, or `hermes update` discards the patch and silently reintroduces the HTTP 400.
- **Status: RESOLVED and live-verified (2026-09-29).** The group reply was delivered at 17:33:09 —
  `response ready: platform=qqbot chat=56B2E66590BD2ED9A098C5D8B0123D68 … time=1.9s` with no subsequent
  `send retry` or `Send failed`. Phase 7.4 (group @ mention) therefore passes and Phase 7 is complete.
  Companion change: `display.platforms.qqbot.tool_progress = off`, keeping a QQ turn to one outbound
  message. **The durability caveat above still stands** — the patch is not part of any distribution, so
  re-verify group replies after any reinstall or distribution change.

## UNRESOLVED-2 — the relay provider is unreliable

- Largely mitigated by promoting `deepseek-flash` to primary and demoting the relay to a fallback
  (`DEPLOYMENT_NOTES.md` §11.12). Retained here because the relay measured 25–45 s per trivial prompt with
  intermittent timeouts and a misfiring anti-abuse `400`, so it should not be promoted back without
  re-measurement.
