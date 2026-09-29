# AGENTS.md

## Project

**Hermes QQ + Weixin Lightweight Multimodal Agent**

This repository/project deploys a lightweight, persistent, multimodal chat agent on a **2 vCPU / 2 GB RAM Ubuntu server** using Hermes Agent.

The first production scope is intentionally narrow:

- QQ messaging
- Weixin/WeChat messaging
- Text chat
- Multi-turn sessions
- Lightweight long-term memory
- Vision
- STT
- Optional TTS
- Remote LLM / multimodal APIs
- 24×7 systemd-managed operation

This project is **not** a general-purpose autonomous agent in V1.

---

## 0. Repository State and Execution Context

At project start, the repository may contain only planning documents such as `AGENTS.md` and `TASK.md`.

Do **not** assume that:

- Hermes is already installed,
- a Hermes config already exists,
- the current shell is the target 2C2G server,
- systemd service files already exist, or
- any adapter/provider has already been configured.

Before making host-level changes, confirm that the current execution environment is the intended target server. If it is not the target server, do not apply package, swap, systemd, or `/var/lib` changes there.

The execution entry point is `TASK.md` Phase 0. Establish the real host baseline first, then discover the current Hermes installation method and installed-version capabilities before editing configuration.

---

## 1. Primary Objective

Build a stable QQ + Weixin AI chat agent that can:

1. Receive text, image, and voice messages.
2. Maintain per-user/per-chat conversation sessions.
3. Retain selected long-term user/project information.
4. Use remote LLM, Vision, STT, and TTS providers.
5. Return text and optional audio responses.
6. Survive process crashes and server reboots.
7. Stay within the practical limits of a 2C2G server.

---

## 2. Architecture

Target architecture:

```text
                     QQ / Weixin
                         │
             ┌───────────┴───────────┐
             │                       │
        QQ Adapter              Weixin Adapter
             │                       │
             └───────────┬───────────┘
                         │
                   Hermes Gateway
                         │
                   Session Store
                      SQLite
                         │
                 Built-in Memory
                USER.md / MEMORY.md
                         │
          ┌──────────────┼──────────────┐
          │              │              │
        Text           Vision          STT
          │              │              │
          └──────────────┼──────────────┘
                         │
                    Remote LLM
                         │
                  ┌──────┴──────┐
                  │             │
                Text           TTS
                  │             │
                  └──────┬──────┘
                         │
                    QQ / Weixin
```

The server is responsible for orchestration, sessions, memory, media transfer, and API requests.

Heavy AI inference must remain remote.

---

## 3. Hard Resource Constraints

Assume:

```text
CPU: 2 vCPU
RAM: 2 GB
Swap: 2 GB recommended
OS: Ubuntu 20.04 / 22.04 / 24.04
```

The implementation must be optimized for low idle memory use.

### Do not introduce heavy resident services unless explicitly required.

Avoid:

- Chromium
- Playwright
- local LLM inference
- local Vision models
- local Whisper/faster-whisper
- PostgreSQL
- Redis
- local vector databases
- multiple permanent worker processes
- extra Node.js services unless strictly required by a selected channel/provider

---

## 4. V1 Allowed Components

The following components are allowed and expected:

- Hermes Agent
- Hermes Gateway
- QQ Adapter
- Weixin Adapter
- SQLite
- built-in session persistence
- built-in lightweight memory
- ffmpeg
- systemd
- remote LLM API
- remote Vision API/model
- remote STT API
- remote or lightweight network TTS provider
- bounded media cache
- minimal logging

---

## 5. V1 Disabled Components

The following capabilities must remain disabled in V1 unless TASK.md explicitly changes the scope:

```text
Browser Tool
Chromium
Playwright
Computer Use
Terminal Tool
Shell Tool
File Tool
Code Execution
MCP
Web Search
Hermes Cron Tool / model-exposed scheduled-task capability
Sub-Agent
Delegation
Image Generation
ACP / IDE integration
Local LLM
Local Vision Model
Local Whisper
```

Do not enable them merely because Hermes supports them.

### Scheduler boundary

The V1 ban applies specifically to **Hermes/agent-facing scheduling capabilities that the model can invoke**.

Host-level maintenance scheduling is allowed when it is not exposed to the LLM. Approved examples include:

- `systemd-tmpfiles` for age-based temporary-file cleanup,
- a dedicated `systemd` timer for media/cache housekeeping,
- `crontab` only when a systemd-native mechanism is not practical.

Host-level schedulers may be used only for infrastructure maintenance such as media cleanup, log rotation, or health housekeeping. They must not accept user-authored commands, must not be callable by the model, and must not be used to implement user-facing Agent workflows in V1.

---

## 6. Security Boundaries

This agent is a **chat agent**, not a server administration agent.

It must not be given arbitrary server execution capability.

### Required security rules

- No shell access exposed to users.
- No sudo access exposed to users.
- No arbitrary file read/write tool exposed to users.
- No browser automation.
- No arbitrary Python/code execution.
- No MCP access in V1.
- API keys must never be committed to Git.
- Secrets must be stored in protected environment/config files.
- Secret files should use restrictive permissions such as `chmod 600`.
- Logs must never print complete API keys, access tokens, refresh tokens, passwords, or authorization cookies.

---

## 7. Messaging Scope

Only these channels are enabled:

```text
QQ
Weixin / WeChat
```

Do not enable Telegram, Discord, Slack, Feishu, DingTalk, WhatsApp, or other adapters in V1.

Do not delete their source code solely to save RAM.

Unused code does not materially affect runtime memory if it is not loaded.

Prefer:

```text
not configured
not loaded
not started
```

over source deletion.

---

## 8. QQ Requirements

QQ must use the supported Hermes QQ adapter / official QQ bot integration available in the installed Hermes version.

Required behavior:

- private message support
- group @ mention support where available
- explicit access policy
- user or group allowlist during initial testing
- reconnect after transient connection failure
- automatic recovery after process restart

Do not expose the bot publicly until rate limiting and access control are verified.

---

## 9. Weixin Requirements

Weixin must use the supported Hermes Weixin adapter available in the installed version.

Required behavior:

- QR/account authorization as required
- long-poll or current supported inbound mechanism
- persisted login/auth state when supported
- context token handling when required by the adapter
- automatic recovery after gateway restart

Avoid designs that require manual re-authentication after every normal service restart.

---

## 10. Session Requirements

Session support is mandatory.

Sessions must be isolated by source and conversation identity.

At minimum, prevent context leakage between:

- QQ user A
- QQ user B
- QQ private chat
- QQ group chat
- Weixin user A
- Weixin user B
- QQ and Weixin channels

Persist sessions with the lightest supported Hermes mechanism, normally SQLite.

### Session is not the same as long-term memory.

Session handles current conversational context.

Long-term memory handles stable information across sessions.

---

## 11. Memory Requirements

V1 should prefer Hermes built-in lightweight memory first.

Preferred starting point:

```text
USER.md
MEMORY.md
built-in Hermes memory behavior
```

Do not add an external memory provider in the first deployment unless built-in memory is demonstrably insufficient.

Suitable memory content:

- stable user preferences
- long-lived project names
- stable technical environment
- long-term working conventions
- non-sensitive persistent context

Do not intentionally store:

- passwords
- API keys
- refresh tokens
- OTPs
- banking details
- identity-document data
- other credentials or authentication secrets

---

## 12. Vision Requirements

Vision is enabled.

Heavy image inference must be remote.

Preferred behavior:

```text
QQ / Weixin image
      ↓
adapter/media fetch
      ↓
temporary local file
      ↓
remote multimodal model
      ↓
response
      ↓
temporary media cleanup
```

Do not run a local Vision model on this server.

Implement reasonable limits for:

- image size
- image count
- temporary storage duration

Temporary image files must be cleaned automatically.

---

## 13. STT Requirements

STT is enabled.

Priority:

1. Use platform-provided transcript/ASR if already available.
2. Otherwise use remote STT.
3. Use ffmpeg only for necessary format conversion.

Do not run local Whisper/faster-whisper in V1.

Input audio should be treated as temporary data and cleaned after processing.

---

## 14. TTS Requirements

TTS is enabled as an **optional response mode**.

Default behavior should remain text response.

Generate TTS when:

- the user explicitly asks for a voice response, or
- a future configured UX rule requires it.

Prefer remote/lightweight TTS such as a network TTS provider.

Do not run large local TTS models.

Temporary TTS audio must be removed after delivery or short retention.

---

## 15. Media Cache Policy

Vision/STT/TTS require bounded temporary media storage.

Preferred path:

```text
/var/lib/hermes/media/
```

or a Hermes-supported temporary cache directory.

Recommended retention:

```text
images: <= 1 hour
input audio: <= 1 hour
generated audio: <= 1 hour
```

The implementation must prevent unbounded media accumulation.

Provide a cleanup mechanism.

---

## 16. LLM Requirements

All primary inference must use remote APIs.

Allowed examples include:

- GPT
- Claude
- Gemini
- Qwen
- DeepSeek
- other API-compatible remote models

Choose a main model that supports the required text workload.

For Vision:

- prefer a main model that already supports image input, or
- configure a separate remote Vision model.

Never assume a model capability without validating it against the selected provider.

---

## 17. Tooling and Version-Discovery Policy

Hermes evolves quickly. Treat installation commands, toolset names, adapter names, config paths, and CLI subcommands found in this repository as examples unless they have been verified against the selected Hermes release.

Before installation:

1. identify the current authoritative Hermes source/repository/documentation,
2. choose and record the release/tag/commit being deployed when feasible,
3. verify the supported installation method for that release,
4. only then execute the installation command.

After installation, inspect the installed version before changing Hermes configuration. Use the actual CLI discovered on the target host. Commands may include:

```bash
hermes --version
hermes --help
hermes tools
hermes gateway --help
```

If a documented subcommand does not exist, do not guess its replacement. Use `--help` and the selected release documentation/source to discover the equivalent.

The selected/installed Hermes version is the deployment source of truth. Do not blindly copy historical toolset names or old installation snippets.

---

## 18. Dependency Policy

Install only dependencies required by the current V1 scope.

Base dependencies may include:

```text
curl
wget
git
unzip
ffmpeg
sqlite3
htop
ca-certificates
```

Do not install Chromium/Playwright.

Do not install model weights.

Do not add Docker merely for convenience unless there is a concrete operational benefit and memory overhead is acceptable.

---

## 19. Process Management

Hermes Gateway must run under systemd.

Required properties:

```text
start on boot
restart on failure
short restart delay
clear log access
single active gateway instance
```

Preferred behavior:

```ini
Restart=always
RestartSec=5
```

Do not run duplicate Hermes Gateway instances.

---

## 20. Logging

Log at least:

- Hermes startup/shutdown
- QQ connection state
- Weixin connection state
- LLM provider failures
- Vision failures
- STT failures
- TTS failures
- session failures
- memory failures
- unexpected exceptions

Do not log secrets.

Logs must rotate or otherwise remain bounded.

---

## 21. Resource Targets

Desired runtime targets:

```text
Idle: preferably < 800 MB RAM
Normal chat: preferably < 1.2 GB RAM
Short media bursts: preferably < 1.5 GB RAM
Sustained > 1.7 GB RAM: investigate
```

These are engineering targets, not guarantees.

If memory is high, first inspect:

- accidental Chromium
- accidental local Whisper
- duplicate gateway processes
- unused Node workers
- stale media
- excessive logs
- unexpectedly heavy memory provider
- runaway retries

---

## 22. Swap

A 2 GB swap file is recommended for resilience.

Swap is not a substitute for fixing a memory leak.

The system should remain functional primarily within physical RAM during normal chat operation.

---

## 23. Rate Limiting

Before public exposure, configure or implement:

- per-user rate limits
- maximum message length
- maximum image size
- maximum audio size
- group allowlist where applicable
- user allowlist during testing

A reasonable starting point is approximately:

```text
10–30 requests per user per minute
```

Adjust based on provider quotas and usage.

---

## 24. Development Rules for Agents

When modifying this project:

1. Read `AGENTS.md` completely.
2. Read `TASK.md`.
3. Confirm whether the current shell is the intended target server before making host-level changes.
4. Do not expand scope silently.
5. Do not enable disabled Hermes tools without explicit task requirements.
6. Prefer configuration changes over invasive Hermes core modifications.
7. Prefer Hermes plugin/adapter extension points over forking core code.
8. Keep the system simple enough for 2C2G.
9. Validate actual installed Hermes CLI/tool names before editing config.
10. Preserve compatibility with systemd.
11. Do not expose secrets in diffs, logs, sample outputs, or commits.
12. Run the relevant validation step after each implementation phase.
13. Record unresolved issues in TASK.md rather than hiding them.

---

## 25. Change Policy

If a future requirement needs one of the following:

```text
MCP
Cron
Web Search
Browser
Terminal
Sub-Agent
External Memory Provider
```

add it one capability at a time.

For each new capability:

1. document why it is needed,
2. estimate runtime/resource impact,
3. define the security boundary,
4. add it to TASK.md,
5. test it independently,
6. re-check memory usage.

---

## 26. V1 Definition

The project is complete when it behaves as:

```text
Lightweight
Persistent
Multimodal
QQ + Weixin
AI Chat Agent
```

It must not drift into a general autonomous server agent during V1.
