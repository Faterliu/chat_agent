---
name: hermes-shared-host-ops
description: 在共享的生产 Ubuntu 主机上为 Hermes QQ+微信 网关施工时的操作规程。当需要 SSH 到 8.148.73.94（admin@）做安装、改配置、建 systemd 单元、清理文件、跑 Phase 3–22 任何阶段时使用。包含本机 Bash 环境残缺的绕行方式、共享主机上不可触碰的路径、以及备份→校验→删除的强制顺序。
agent_created: true
---

# 在共享生产主机上施工（Hermes V1）

## 铁律：这台机器不是实验机

`admin@8.148.73.94` 上同时跑着**线上的** nginx 多站点（80/443）、`main-site-editor.service`（`editorapi` 用户，127.0.0.1:8787，会 sudo 调 root 助手）、`frps.service`、`prune-recorder-updates.timer`，以及阿里云 aegis/cloudmonitor/assist 代理。物理内存只有 **1.6 GiB**，已用约 480 MB。

所以：

- 任何改全机参数的动作用户已授权的才做（例：`vm.swappiness` 0→10 已授权）。
- 重启类高风险操作（`systemctl restart` 全机服务、`reboot`）前先确认会影响谁。
- TASK.md Phase 22 的"2C2G 服务器保持稳定"在共享机上**无法照原样验收**，验收必须补一句"既有服务仍然正常"。
- 不要碰别的项目：`/opt/{frp,imgtool,leleo-home-page,main-site-editor}`、`/home/admin/my_images`、`/home/admin/myweb`、`/etc/systemd/system/frps.service`（mode 600，可能含 token，**绝不 cat**）。

## `/tmp` 里绝对不能删的东西

删除会直接打断线上服务：

| 路径 | 原因 |
| --- | --- |
| `/tmp/aliyun_assist_service.sock`、`/tmp/AliyunAssistClientSingleLock.lock` | 被 `aliyun-service` 持有（用 `lsof +D /tmp` 确认） |
| `/tmp/systemd-private-*` | 各单元的 `PrivateTmp` 命名空间（chrony / main-site-editor / ModemManager / polkit / systemd-logind / systemd-resolved） |
| `/tmp/.X11-unix`、`.ICE-unix`、`.XIM-unix`、`.font-unix` | 活动 X socket |
| `/tmp/snap-private-tmp` | snap 运行时状态 |

清理前先 `sudo du -sh /tmp/* /tmp/.[!.]*` 列清单；清理后逐项复验仍在，并 `systemctl is-active aliyun.service`。

## 删除的强制顺序

1. **先备份到本地**（`C:\file\HermesAgent\backups\`），用字节数+文件数逐项校验与远端一致。
2. 打印完整删除清单给用户，标明哪些**不**删及原因。
3. 才执行删除。
4. 复验：服务仍 active、保留项仍存在、磁盘变化。

`chat_bot` 这类有 git 远端的项目要先 `git remote -v` 确认已推送，再删本地副本。

## 本机（Windows）环境的坑

WorkBuddy 的 Bash 工具 PATH 残缺：**没有** `mkdir`、`cp`、`mv`、`sed`、`awk`、`dirname`、`basename`、`head`、`grep`。可用：`ssh`、`scp`、`sftp`、`tar`、`rm`、`test`。

- 需要文件操作就写 **Python 脚本**，用托管解释器绝对路径调用：
  `C:/Users/liuzhuo/.workbuddy/binaries/python/versions/3.13.12/python.exe`
- 不要把本地命令管道给 `head` / `grep`。
- `~` 不可靠（会误报 `no ~/.ssh`），判断本机路径用 PowerShell 或 Python。
- 远端命令里 `head`/`grep`/`sed`/`awk` 都正常可用，那段是 Ubuntu。

## `set -e` 的陷阱

远程脚本加 `set -e` 时，一个**预期就会失败**的命令（典型：以非属主身份 `ls` 一个 750 目录 → rc=2）会静默中止后续步骤，而且 stdout 是块缓冲的，前面的成功输出也可能整段看不到。

对策：远程维护脚本**不要用 `set -e`**；对可能失败的 `ls` 显式 `|| true`。看到"脚本中途停住 + 退出码 2"先怀疑这个，而不是先怀疑权限或依赖。

## 隔离设定（已落地，勿重复创建）

- 服务账号 `hermes`：`uid=993(hermes)`，系统账号，home `/var/lib/hermes`（`drwxr-x---`），shell `/bin/bash` + 密码保持锁定，无 sudo、无附加组。**已装操作者的公钥**（`.ssh` 700 / `authorized_keys` 600，均 `hermes:hermes`），因此可 `ssh hermes@8.148.73.94` 直接登录；密码通道仍是关的，只有公钥这一条路。
- 媒体目录 `/var/lib/hermes/media`（750），即 AGENTS.md §15 的路径。
- 维护命令可用两种身份：`ssh hermes@…`，或从 `admin` 走 `sudo -u hermes -s /bin/bash`。
- 待补：systemd 单元的 `MemoryMax` / `TasksMax`、媒体目录容量上限（共享机上比独占机更重要）。

## 本地镜像

`tools/sync_from_server.py`（用托管 Python 跑）把服务器侧的部署产物镜像到 `server-mirror/`：

```bash
"<managed python>" tools/sync_from_server.py            # 同步
"<managed python>" tools/sync_from_server.py --dry-run  # 只看
```

对服务器**只读**；排除 `.hermes/.env`（凭据）、`sessions/logs/memories/*_cache`（运行时与用户数据）、以及 `node/`+`hermes-agent/`（约 2 GB，可由 pin + 安装器复现）。新增产物路径后要往脚本里的 `MANIFEST` 追加。

**必须用 `hermes@8.148.73.94` 连接，不能用 `admin`。** `HERMES_HOME` 是 mode 700 且属主 hermes，`admin` 连目录都进不去，会把所有 Hermes 产物静默误报成 `[absent]`——第一次跑就踩了这个坑。`/etc` 下的目标都是全局可读，所以 hermes 无需 sudo。脚本里的 `DEFAULT_HOST` 已按此设定。

## Hermes 安装状态（Phase 3 已完成）

- 来源 `github.com/NousResearch/hermes-agent`；**已装 v0.21.5，pin 在 commit `f97608f178d1ffeca59860195ab7da295f7c8e5f`（tag `v2026.9.24`）**。`git -C /var/lib/hermes/.hermes/hermes-agent rev-parse HEAD` 可复核。
- **绝对不要跑 `hermes update`**。它会脱离 pin，让所有既有核验作废（`--version` 会提示"4534 commits behind"来诱惑你）。
- 重新安装时：用 `installer/install-v2026.9.24.sh`（本地存证副本，sha256 `2017ddf0cc7bc6cfb70d40dc9fba1d916f47dbcccf5fe73bdee2cf93a11262af`）从磁盘执行，**不要 `curl | bash`**，否则被审阅的脚本与装上的版本会漂移。先 `sha256sum` 核对再执行。
- 安装命令（以 `hermes` 身份）：`bash install-v2026.9.24.sh --skip-browser --skip-computer-use --commit f97608f1… --non-interactive`。`--skip-browser` 是绕开 Playwright `--with-deps`（唯一需要 root 的步骤）的唯一方式，所以整个安装可非特权完成。
- **装之前必须换 PyPI 源**：官方 `pypi.org/simple/` 在这台机上 12 秒超时、`/simple/requests/` 只有 8.9 KB/s。用 TUNA `https://pypi.tuna.tsinghua.edu.cn/simple`（实测 20.7 MB/s）配 `UV_DEFAULT_INDEX` + `UV_INDEX_URL` + `PIP_INDEX_URL` + `PIP_TRUSTED_HOST`。安装器**没有 `--tag`**，只能 `--commit <完整40位SHA>`。
- 已知非致命问题：① 该 tag 的 `uv.lock` 相对 `pyproject.toml` 已过期，`--locked` 校验会被跳过、依赖全新解析 → **依赖集没有哈希锁定**；② ripgrep 装不上（非交互无终端），已按 V1 范围有意不装；③ 安装器的 `sudo` 步骤会失败但仍打印 `✓ Build tools installed`，是误导信息。

### 布局与命令（实测值）

| 项 | 值 |
| --- | --- |
| CLI | `/var/lib/hermes/.local/bin/hermes`（`~/.local/bin` 已由安装器写进 `.bashrc`） |
| 代码 | `/var/lib/hermes/.hermes/hermes-agent` |
| 配置 | `/var/lib/hermes/.hermes/config.yaml` |
| 凭据 | `/var/lib/hermes/.hermes/.env`（mode 600，**永不镜像、永不打印**） |
| 托管运行时 | `.hermes/bin/uv`（0.12.20）、`.hermes/node`（v26.10.0）；Python 复用系统 3.12.3 |
| 真实子命令 | `hermes gateway`（+ `install/start/stop/status`）、`hermes tools`、`hermes doctor`、`hermes setup`、`hermes logs`、`hermes status` |
| 清单位置 | `/var/lib/hermes/.hermes/{image_cache,audio_cache}` —— **不是** AGENTS.md §15 写的 `/var/lib/hermes/media/` |
| 开机自启 | 用户级服务需 `sudo loginctl enable-linger hermes`（`/var/lib/systemd/linger/` 目前为空）；或 `sudo hermes gateway install --system`。Phase 16 再定 |

## 能力盘点与安全收敛（Phase 4 事实）

- **平台 key**：`weixin`（toolset `hermes-weixin`）、`qqbot`（toolset `hermes-qqbot`）。
- **凭据**：微信 `WEIXIN_TOKEN` + `WEIXIN_ACCOUNT_ID`（扫码登录，连 iLink bot 身份）；QQ `QQ_APP_ID` + `QQ_CLIENT_SECRET`，且自带扫码注册流程。名单开关：`WEIXIN_ALLOWED_USERS` / `WEIXIN_GROUP_ALLOWED_USERS` / `WEIXIN_GROUP_POLICY`。
- **工具命令**：用 `hermes tools list --platform <p>`；`enable/disable --platform <p> NAME...` 也支持非交互。**裸 `hermes tools` 和 `--summary` 需要真 TTY**（SSH 里会报 `requires an interactive terminal`）。`hermes chat --list-toolsets` **在本版本不存在**。顶层 `toolsets:` 已废弃，只能改 `platform_toolsets`。
- **⚠️ 全量默认**：`hermes-weixin` / `hermes-qqbot` = `_HERMES_CORE_TOOLS` 全量，无收窄。V1 必须逐平台 disable：`web browser terminal file code_execution image_gen connections delegation cronjob computer_use`。保留 `vision tts memory`。未通过这项收敛**不得让平台可达**。
- **供应商**：LLM 与 Vision 都用 `OPENROUTER_API_KEY`（默认模型 `anthropic/claude-opus-4.6`）；TTS 默认 Edge TTS（联网免费）；STT 是 config-only（`stt.enabled`），**默认是本地 faster-whisper + `language: "en"`，两项都违反 AGENTS.md §13，且会让中文识别失败**。
- **记忆**：内置 `~/.hermes/memories/MEMORY.md` + `USER.md`（2200 / 1375 字符上限，每 10 轮 nudge）；**全实例一份，无用户维度**（详见下节）；会话在 `~/.hermes/state.db`。
- **清单位置**：`image_cache/`、`audio_cache/`、`cache/scratch/`（TMPDIR）。scratch **闲置 24 小时**才清，与 AGENTS.md §15 的 ≤1 小时不符。
- **诊断**：`hermes doctor`（rc=0 为干净）。它关于 SQLite 的建议是"run hermes update"——**在这台机上既是错的（bug 在系统 libsqlite3）又会破坏 pin，别照做**。

## 绝对禁令（操作者已明令）

- **永不运行 `hermes update`。** 两条理由各自成立：会脱离 pin 使既有核验作废；而且它修不了 `hermes doctor` 报的 SQLite 告警（bug 在 Ubuntu 的 libsqlite3，不在 Hermes）。doctor 给"run hermes update"建议时**不要照做**。
- **永不动系统 SQLite**（apt / PPA / 换库 / vendored wheel）。会影响全机，包括线上的 nginx 与 main-site-editor。SQLite 3.45.1 的 WAL-reset bug 已被操作者接受为有界风险，记录即可。
- 任何主机级变更前先确认自己在正确的机器上（这台是共享生产机）。

## 资源参数与网络约束（实测）

- `agent.max_turns` = **32**（原 500）。语义是**「单个对话轮次内的工具调用迭代上限」**，不是对话轮数，内部映射 `max_iterations`。改前先确认 `.env` 里没有 `HERMES_MAX_ITERATIONS`——它会静默盖过 config.yaml。改配置用 `hermes config set <点分键> <值>`，先 `cp` 一份 config 到 `~/.hermes/backups/`。
- **网络：`api.openai.com` 与 `api.mistral.ai` 被墙（超时）**。可用：DashScope ~0.08s、DeepSeek ~0.18s、Moonshot / SiliconFlow / Zhipu 可达、Anthropic 与 Groq 可达、OpenRouter ~1.2s（最慢）。
- **推论：Hermes 的 STT 供应商 `local|groq|openai|mistral` 里只剩 Groq 可用**（local faster-whisper 被 §13 禁止，openai/mistral 被墙）。
- Hermes 原生认 `DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` / `OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `XAI_API_KEY` / `MISTRAL_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` 等。**Vision 走独立辅助模型路由**（`tools/vision_tools.py` 的 `_load_auxiliary_client`），可与主文本模型用不同供应商。
- `hermes model` 是**纯交互式选择器**，无非交互参数 → 无 TTY 时要改 `model.default` / `model.provider` / `model.base_url` + 写 `.env` 的 key。

## 修改 Hermes 配置的规矩（Phase 5 踩过坑后定的）

**绝不在远程命令串里用 heredoc。** `cat >> file <<YAML` 会被**本地** Git-Bash shim 解析并执行，正文变成 `providers:: command not found` 之类的本地报错，服务器只收到半截揉坏的注释（连注释里的撇号和引号都被改写）。替代路径（一次就成功）：

1. 本地用 Write 生成片段文件（放 `staging/config-fragments/`，同时作为变更的可复现来源）
2. `scp` 上传到 `/var/lib/hermes/<片段名>`
3. 远端 `sed -i "s/\r$//"` 去掉 CRLF，再 `cat "$F" >> "$C"` 追加
4. **立即 `rm -f "$F"`**，并 `ls -la /var/lib/hermes/` 确认没有残留

**追加新顶层键前先确认不存在**：`grep -nE "^(providers|fallback_providers|model_aliases):" config.yaml`。YAML 重复键会踩雷。

**`hermes config set` 会重写整个 config.yaml 并剥离模板注释**（实测注释 1999→1736 行，字节 121555→108217，而**代码行只按预期变化**）。所以改前备份是唯一还带着 Hermes 自身文档的副本，**不要删**：
- `~/.hermes/backups/config.yaml.bak-before-max-turns`
- `~/.hermes/backups/config.yaml.bak-before-phase5`（仍带完整注释）

判断"是不是被写坏"的正确方法：比较**代码行**（`grep -vE "^[[:space:]]*#|^[[:space:]]*$"`）而不是总行数或字节数；再用 Hermes 自己校验（`hermes config get <点分键>`、`hermes doctor`、`hermes fallback list`）。

**多行 python 内联脚本也会被本地 shim 弄坏。** 校验配置不要拼多行 `python3 -c "..."`，改用 `hermes config get` 或写成本地脚本 + scp。

## 供应商与降级链（Phase 5 已配）

- 主：OpenAI 兼容中转站。`config.yaml` 里
  ```yaml
  providers:
    kldai:
      base_url: "https://www.kldai.cc/v1"
      key_env: "KLDAI_API_KEY"
      transport: codex_responses
  model: {provider: kldai, default: GPT-6-Sol, base_url: "https://www.kldai.cc/v1"}
  ```
- 降级：`fallback_providers: [{provider: deepseek, model: deepseek-chat, key_env: DEEPSEEK_API_KEY}]`。用 `hermes fallback list` 查看；`hermes fallback add` 是交互式选择器（需 TTY），无 TTY 时直接写 `fallback_providers` 列表，条目必填 `provider` + `model`，可选 `base_url` / `key_env`。
- **坑：字段名。** 现行名是 **`transport`**，`api_mode` 是旧别名。源码警告用错会**静默降级成 `chat_completions`**。Codex 术语的 `wire_api = "responses"` 对应 Hermes 的 **`codex_responses`**（`config_providers.py:47-49` 有 `responses → codex_responses` 映射）。
- 凭据槽位以**注释形式**写入 `.env`（避免半配置状态）：`#KLDAI_API_KEY=` / `#DEEPSEEK_API_KEY=`。由操作者自行填写，agent 不接触密钥值。

## Phase 5 已配好（2026-09-29 实测通过）

- 主：`providers.kldai` → `https://www.kldai.cc/v1`，`key_env: KLDAI_API_KEY`，**`transport: codex_responses`**；`model.default: gpt-6-sol`。
- 降级：`fallback_providers: [{provider: deepseek, model: deepseek-flash, key_env: DEEPSEEK_API_KEY}]`。
- 验证：`hermes fallback list` 应显示 `Primary: gpt-6-sol (via kldai)` + 1 条降级；`hermes -z "…" --usage-file /tmp/u.json` 约 30 秒返回，usage 里 `model` 是 `gpt-6-sol`、`completed: true`、`api_calls: 1`。usage 里 `provider` 显示 `custom` 是**正常**的（命名 providers 条目都归到 custom 计费类别）。
- **改模型 id 前必须先查供应商自己的 `/v1/models`**，不要信文档或记忆：
  - 中转站 kldai.cc：8 个 id、**大小写敏感**（`gpt-6-sol`，不是 `GPT-6-Sol`）；**没有任何 DeepSeek 模型**。
  - DeepSeek 直连：只有 `deepseek-flash` 和 `deepseek-v4-pro`（**没有 `deepseek-chat`**）。`deepseek-flash` 具备视觉能力。
- 该中转站的 `gpt-6-sol` **只接受 responses 线**：`/v1/chat/completions` 返回 400，`/v1/responses` 返回 200。

### ⚠️ Hermes 会在运行时懒安装 Python 包 —— 镜像源必须持久化

`agent.log` 会出现 `Lazy-installing boto3==… for feature 'provider.bedrock'`。若运行时环境没有镜像源，uv 会去打**被墙的 pypi.org**，重试 3 次耗 ~84 秒，把整个 turn 拖死（表现为 `hermes -z` 挂到 timeout、无输出、无 usage 文件 —— **很容易误判成模型或供应商问题**）。

`.env` 里必须常驻：

```
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

**Phase 16 的 systemd 单元也必须用 `Environment=`/`EnvironmentFile=` 提供这三个变量**，因为 systemd 不读 `.bashrc`。

## 工具收敛现状（Phase 6 已完成并收尾）

**`cli` / `qqbot` / `weixin` 三者完全一致，各只有 4 个 toolset**：`memory`、`session_search`、`tts`、`vision`。其余（web / browser / terminal / file / code_execution / image_gen / connections / delegation / cronjob / computer_use / skills / clarify / todo）全关。

- 收敛命令：`hermes tools disable --platform <p> NAME [NAME...]`（非交互可用）。
- **复验不要看命令回显**，要 `hermes tools list --platform <p>` 重读状态。
- 其它平台保留出厂 `hermes-<platform>` 包是可以的：它们**不配置、不加载、不启动**（AGENTS.md §7 明确偏好这种做法而不是删源码）。
- `cli` 也一并收敛了：它是操作者界面，但 TASK.md Phase 22 的验收项没限定平台，收敛后验收无歧义。

### ⚠️ STT 不在 `platform_toolsets` 里 —— 已关闭，Phase 12 再开

`stt` 是 **config-only toolset**（`_CONFIG_ONLY_TOOLSETS`）：`hermes tools list` 显示"✗ disabled"**只是渲染**，真正的开关是 **`stt.enabled`**，且 `platform_toolsets` 对它无效。

出厂默认违规：`stt.enabled=true` + `stt.local.model=base`（**本地 faster-whisper，§13 明禁**）+ `stt.language=en`（中文按英文识别）。**现已 `stt.enabled=false`**，Phase 12 用 Groq + 语言 auto/`zh` 再打开。

**记住这个类别的存在**：`hermes tools disable` 关不掉 config-only 的 toolset。以后见到"工具列表显示 disabled 但行为却开着"的怪象，先查 config-only 类别（当前只有 `stt`）与它自己的开关。

## 人格 / 提示词注入（2026-09-29 实践）

- **定义**放 `agent.personalities.<name>`；**激活**靠 **`display.personality`**。两者缺一不可。
- `render_personality_prompt()` **只消费四个字段**：`system_prompt`、`tone`（渲染成 `Tone: …`）、`style`（`Style: …`）、`description`（仅列表预览）。其它自定义字段（如 catchphrases）**Hermes 读不到**，要么折进 `system_prompt`，要么就只是文档。
- 改 `agent.personalities` 用**精确行替换**（锚点 `  personalities: {}`），**必须断言锚点唯一**。追加第二个顶层 `agent:` 块会因重复键**丢掉整个 `agent:` 节**（含 `max_turns`）。写后必须核验 `agent.max_turns` 还在。
- **更新已存在的人格：按区域替换，不要追加。** 从唯一的 `  personalities:` 行向后扫，吞掉空行与 4+ 空格缩进行，停在第一个既非空也非 4 空格缩进的行（即其后注释示例的起点）。尾部空分隔行要保留。这是纯文本拼接，config.yaml 里其它注释全不受影响。
- **技术 slug 不必跟着显示名改。** 人格键 `agent.personalities.<slug>` 与 `display.personality` 是内部标识；只要昵称没变，slug 保持原样更省事（改名要动三处）。
- **`hermes -z` 验证不了人格**：`hermes_cli/oneshot.py:588` 传 `ephemeral_system_prompt=skills_prompt`，刻意绕过覆盖层。只有**交互式 CLI**（`cli_init_mixin.py:249`）和**消息网关**（`gateway/run_config_loaders.py:93`）会读。验证要用 Hermes 自己的解析器（`from hermes_cli.config_effective import load_user_config_effective` + `hermes_cli.personality.resolve_ephemeral_system_prompt`），不要用单发模式。
- 运行时切换：`/personality <name>`（CLI 与已连接聊天均可），网关每轮重读。
- `~/.hermes/SOUL.md` 是安装器写的风格指令，与人格覆盖层**同时注入**，不冲突但要知道有这个叠加。

## 启动器与显示设置（都有坑）

- **启动网关必须用 `/var/lib/hermes/.local/bin/hermes`，绝不要用 `$REPO/hermes`。** 后者是源码入口，会用**系统**解释器，立刻死在 `ModuleNotFoundError: No module named 'dotenv'`。启动器里是 `exec venv/bin/python $REPO/hermes "$@"`。Hermes 的报错完全不提示这一点，只有官方安装文档写了。可复用脚本：`staging/restart-gateway.sh`。
- **聊天里出现 `🧠 Reasoning:` 块** → 关 `display.show_reasoning`（默认 `true`）。
- 会影响聊天观感的相邻键：`display.tool_progress`（`all` 会把工具活动打进聊天）、`interim_assistant_messages`、`busy_ack_detail`、`suppress_warning_notifications`（`false` 会让 `⚠️ Model fallback:` 横幅露出来）。
- 改 `display.*` 后**重启网关**确认生效。

## 中转站（kldai.cc）实测不可靠

- **Hermes 侧的 `codex_responses` 路由是对的**（日志 `agent.model_metadata` 会打印 route），但中转站会间歇性拒绝：`HTTP 400 Upstream rejected illegal short-input distillation or heartbeat probing` —— 那是**它自己的反滥用启发式误判**，不是请求格式错。
- 直接探测 `/v1/responses`：同一形状的请求时而 200 时而 45 秒超时；最简单的问题也要 **25–45 秒**。对比 `deepseek-flash`（api.deepseek.com）**0.19 秒**。
- 也就是说 `fallback_providers` 的降级项反而在承担全部流量。遇到"主模型不可用"先直接探测中转站，别怀疑 Hermes 配置。

## 报错/诊断通知的路由（能力边界，别承诺做不到的事）

- 决策点在 **`gateway/warning_notifications.py`**（"Delivery policy for engine diagnostics, never assistant or command responses"）。规则：`warning_notifications_enabled(platform) = not resolve_display_setting(user_config, platform_key, "suppress_warning_notifications", False)`。
- **粒度是「平台」，不是「聊天」。** `resolve_display_setting` 先读 `display.platforms.<平台>.<键>`，再退回全局 `display.<键>`。**没有"只在操作者私聊显示"的目标概念**；诊断永远发到发起该回合的那个聊天。
- 所以"对别人静默、给自己发"这种需求：**同一平台内做不到**。只能全局或按平台静音，静音后操作者改看 `hermes logs errors`。
- 想主动把错误摘要推给操作者 → 需要定时任务 + `hermes send` → 那是 Hermes Cron，V1 禁用（AGENTS.md §5），属 V5。
- **全局静默一条命令**：`hermes config set display.suppress_warning_notifications true`（改完重启网关）。它拦得住 fallback 横幅等 **notice/诊断**类；闸门链是 `is_diagnostic_notice()` → `render_notification(diagnostic=…)` → `warning_notifications_enabled()`。**日志不受影响**，操作者改看 `hermes logs errors|--since 1h|-f`。
- **⚠️ 有一条错误路径该开关管不到**：`run_turn_runner.py:1930-1937` 在模型解析彻底失败时，把 ***"I couldn't connect to the AI model service"*** 当作 **`final_response`（助手文本）** 返回，不是 notice，会发到触发它的聊天，且无配置可关。**所以"报错只到我这里"真正靠的是白名单，不是显示开关。**
- **加群之前必须先决定**：静音（已全局静默）还是接受群成员看到引擎告警。事后无法撤回。

## 主模型仍是 kldai 中转站时要记住

- 2026-09-29 起**主模型已换成 `deepseek-flash`（deepseek 直连）**，中转站降为 `fallback_providers` 里的 `provider: kldai`。
- 降级条目里写 **`provider: kldai`（命名引用）**，端点与 `transport: codex_responses` 都从 `providers:` 块继承。**不要**在降级条目里直接写 `base_url` —— 有丢掉 Responses 线格式的风险，而该中转站只接受 responses。
- `hermes config set model.provider <新>` 会主动警告遗留的 `model.base_url` 仍指向上一个供应商，并给出修复提示——注意看它的输出。

## QQ 群授权：群号不是群 id（踩过）

- 白名单匹配的是 **`group_openid`**（每个机器人特有的不透明标识），**QQ 群号（如 `1107720324`）填进去无效**。`access_policy_mixin.py` 的 `_entry_matches(entries, target)` 就是 `target in entries`——**精确匹配，无通配符/前缀**。
- **被拒的群消息静默丢弃、零日志**（handler 在 `_ingest` 前 `return`），`_on_message` 也不记录报文 → **无法靠发被拒消息捞 openid**。`group_policy: pairing`/`disabled` 同样不放行群流量。
- `hermes gateway setup` **没有** QQ 群白名单步骤。
- **唯一可行路径：临时 `group_policy: open` 抓一次 openid，然后立刻锁回 allowlist。** 注意启动守护：任一已启用平台的 `dm_policy` 或 `group_policy` 为 `open` 时，必须有 `GATEWAY_ALLOW_ALL_USERS` 或该平台的 allow-all 变量为真，**否则网关拒绝启动**。用 QQ 专属的 `QQ_ALLOW_ALL_USERS=true` 更收敛；只要 `dm_policy` 仍是 `allowlist`，它纯属守护用途。
- **这是对访问控制的有意临时放宽**——窗口期内该机器人所在任何群的任何成员都可能得到回复。必须明确告知操作者，并在同一次操作里还原。

## 块级替换：必须缩进 + 必须写后自校验（踩过，差点造成安全回退）

写 `platforms:` / `fallback_providers:` 这类块的脚本，如果写成 `["key:"] + yaml_body.splitlines()` 而**忘了给子行加缩进**，会产出**语法合法但结构错误**的文件：

```yaml
platforms:
qqbot:            # 掉到顶层了
  enabled: true
```

`platforms:` 解析成 null → **所有策略静默回退到内置默认**（dm/group 都是 `pairing`，即陌生人可申请访问）。**没有任何报错**，只有 `hermes config get platforms.qqbot.extra.group_policy` 返回 "Config key not set" 才暴露。

**规矩**：块替换脚本必须（1）`[KEY] + [INDENT + ln for ln in body.splitlines()]`；（2）**写后重新解析文件、断言值可达**，不可达就拒绝报告成功。区域扫描也必须能识别"结构已被破坏"的情况——扫描只吃空行和 2 空格缩进行，若下一条是顶层键就会提前停下、抓不到损坏区域，此时应从备份恢复而不是就地修补。

## QQ 群回复被拒是 Hermes 侧缺口（v0.21.5）

- 症状：群消息被正常接收、agent 正常作答，但投递失败 `HTTP 400 .../v2/groups/<openid>/messages: 主动消息失败, 无权限`。
- 根因：QQ 要求**被动回复**带 `msg_id`；适配器拿到 `reply_to` 时会正确附加（`qqbot/adapter.py:1414-1421`），但 **`gateway/run_turn.py:3181-3187` 计算 `_progress_reply_to` 的平台白名单只有 FEISHU / MATTERMOST / Buzz / relay，没有 `Platform.QQBOT`** → QQ 的 `reply_to` 恒为 `None`。DM 能通是因为 QQ 容忍 c2c 主动消息，群不行。
- `reply_to_mode` 管的是进度线程化，**救不了**；无纯配置解法。要修就得改核心（与 AGENTS.md §24.5/§24.6 冲突）或向 QQ 申请主动消息权限。

## ⚠️ 读源码别只看基类：适配器可能覆盖了它

我在 `_entry_matches` 上犯过这个错——读了基类 `access_policy_mixin.py`（`return target in entries`）就断言"没有通配符"，**没注意到 QQ 适配器覆盖了它**（`qqbot/adapter.py:1669-1671`）:

```python
def _entry_matches(self, entries, target):
    normalized_target = str(target).strip().lower()
    return any(str(e).strip().lower() in ("*", normalized_target) for e in entries)
```

**支持 `"*"`，且大小写不敏感。** 这个错误让我多做了一次"临时开放策略 + 动启动守护"的重操作，本来 `group_allow_from: ["*"]` 就够了。

**教训**：grep 到某个方法定义后，要确认**子类是否重写**（在适配器目录里再 grep 一次同名方法）；`self.<method>()` 调用的可能是覆盖版本，不是你以为的基类版本。

**安全推论**：`"*"` 等于全开——`group_allow_from` 里是所有群，`allow_from` 里是所有私聊发送者。**当 allow-all 开关看待。**

## QQ 群被动回复补丁（本地，已应用）

补丁位置 `gateway/platforms/qqbot/adapter.py` 的 `send()`：

```python
if reply_to is None and self._guess_chat_type(chat_id) == "group":
    reply_to = self._last_msg_id.get(chat_id)
```

- **只作用于群**：c2c 主动消息 QQ 接受，不动。
- **不要改成去动 `run_turn.py` 的平台白名单**：那会让整个回合每条出站消息都带 `reply_to`，而 QQ 对**单条入站消息只有 5 条被动回复额度**。
- 复用已有缓存：`_last_msg_id`（`handle_message()` 写）、`_chat_type_map`（`_ingest()` 写，`_guess_chat_type` 读它而非猜 id 形状）。
- 应用脚本 `staging/apply-qqbot-passive-patch.py`：锚点唯一性断言 + 写前 compile + 写后验证 + 幂等；原文件留在 `adapter.py.orig-qqbot-passive`。
- 配套 `display.platforms.qqbot.tool_progress off`，把 QQ 回合压到单条出站消息。
- **不持久**：重装/换部署方式/`hermes update` 都会丢，并静默重现 `400 主动消息失败, 无权限`。

## 人格 JSON 来料校验（踩过）

应用外部给的人格 JSON 前，**必须**先检查两件事：

1. **换行是否被双重转义。** 如果 `system_prompt` 在 JSON 里写成 `\\n`，`json.loads` 解出来是**字面反斜杠+n**，不是换行。判据：解析后 `sp.count("\n") == 0` 但 `sp.count("\\n")` 很大。转换就一句 `sp.replace("\\n", "\n")`。`staging/normalise-persona.py` 就是干这个的。
2. **平台措辞是否回退。** 模板作者经常会写回"运行在微信机器人里"。当前要求是**平台无关**（`运行在用户的聊天机器人里`），因为机器人实际跑在 QQ 上，模型会自己发现矛盾。

另外注意 `version` 可能不随内容变——同样的版本号可能对应差别很大的内容，必要时本地升号以便追溯。

**注入范围永远只有四个字段**：`description`（仅列表预览）、`system_prompt`、`tone`←`personality.core_traits`、`style`←`speech_style.general`。其余（`identity`/`preferences`/`catchphrases`/`relationship_model`/`initiative_policy`/`social_boundaries`…）**全部惰性**。所以要盯的是：**作者想表达的规则是否真的折进了 `system_prompt`**——常见漏项是口癖、自称方式（如"本云"）、以及 quiet_hours/cooldown 这类数值。

## 记忆与身份：三条容易想当然的结论（2026-09-29 查证）

**① 没有"按人的长期记忆"。** 内置 store 是**全实例一份的一对文件**，路径里没有任何 user/session 组件：

```text
tools/memory_tool.py:38-40   get_memory_dir() -> get_hermes_home() / "memories"
tools/memory_tool_store.py:212   目的地只有 USER.md 与 MEMORY.md
memory 工具 target 枚举      user | memory   （语义是单数 "who THE user is"）
```

多用户共用一个机器人时，跟 A 聊出来的条目会注入 B 的 prompt。**这是结构性串味，不是配置错。** AGENTS.md §11 的"按人稳定偏好"用内置 store 做不到。

唯一的实例级隔离原语是 **profile**（`hermes_cli/profiles.py` 的 `_PROFILE_DIRS` 含 `memories`/`sessions`，profile 有独立 `HERMES_HOME`），但 profile 是"一路 bot / 一个实例"，**网关没有把终端用户路由到 profile 的机制**，所以不能拿它做按人记忆。

`hermes memory setup` 可选外部 provider：`honcho / openviking / mem0 / holographic / retaindb / byterover / supermemory`（已装插件、未启用）。部分有 per-user namespace，但 **AGENTS.md §11 禁止 V1 上外部 provider**。

**② 能区分用户，但模型只拿到不透明 ID。** 会话键按参与者+聊天隔离（实测行）：

```text
agent:main:qqbot:dm:A729C39060FB65742B0C808249E36326
agent:main:qqbot:group:56B2E66590BD2ED9A098C5D8B0123D68:A729C39060FB65742B0C808249E36326
```

`gateway/session.py:673 build_session_key()` 的布局是 `<ns>:<platform>:<chat_type>[:<chat_id>][:<thread>][:<user>]`；`config.yaml` 显式 `group_sessions_per_user: true`。

两个反直觉后果：

- **QQ Bot API v2 不传昵称**——适配器只读 `author.user_openid` / `author.member_openid`，线上没有 name 字段。**机器人不可能知道任何人的名字**，除非对方自己说。人格里"称呼不固定、自由发挥"不是风格选择，是**被迫的**。
- 模型看到的是 `## Current Session Context` 里的 `**Source:** Qqbot (DM with <openid>)`（`gateway/session.py:375 build_session_context_prompt()`，由 `run_agent_cache.py:629` 调，确认在网关回合路径上），而 `privacy.redact_pii=false`，所以是**裸 openid**。
- **群里的 `[昵称]` 前缀不会加**：`run_inbound.py:1413 _prefix_inbound_sender_context()` 仅在 `is_shared_multi_user_session()` 为真时才加，而 `group_sessions_per_user: true` 时它返回 **False**（`session.py:633-641`）。
- **`group_sessions_per_user: true` 意味着机器人不参与群聊**——每个成员各自一个会话，它只看得到当前说话人自己的历史，**看不到其他成员说过什么**。想让机器人跟整个群的上下文走，要把它改成 `false`（代价：群里所有人共用一个会话、互相可见，`[昵称]` 前缀才会生效）。

**③ "群记忆与私聊记忆能否联合"——分三层，答案不同：**

| 层 | 联合吗 | 依据 |
| --- | --- | --- |
| 对话上下文 | **不联合（有意）**：群与私聊是不同会话键，AGENTS.md §10 要求的隔离 | `build_session_key()` |
| 长期记忆 | **被动全联合**：`MEMORY.md`/`USER.md` 全局，任何聊写入的都注入到所有聊；**无归属字段**，无法追溯到人/聊 | ① |
| 检索 `session_search` | **联合且无作用域**：搜索路径不带任何 user/chat 过滤，`current_session_id` **只用来排除当前活跃会话**（`session_search_tool.py:355-414`、`_list_recent_sessions:480-499`），不是 scope。全机共用一个 `state.db` | 见下 ⚠️ |

### ⚠️ 唯一的真实风险：`session_search` 在多用户下越过隔离

它在 `qqbot`/`weixin` 上**是开着的**，且**不按用户过滤**。任何被授权的人都能诱导机器人从 `state.db` 里读出**别人的私聊内容**——`build_session_key()` 在上下文层建立的隔离，在**检索层没有被执行**。

当前实际暴露为零（私聊白名单只有操作者、群白名单只有一个群、该工具从未在真实回合里被调用）。**但再加一个用户或一个群就变成真的。**

**规矩：在把任何用户或群加入白名单前，先裁定 `session_search` 是否保留在消息平台上。** 要么在消息平台上关掉它，要么明确接受"历史对能接触到机器人的所有人共享"并记录。

### 身份是连续的（这是好事，将来可用）

同一个 `user_openid` 同时出现在 dm 键和群键里，所以"某人跨私聊+群"在基础设施层是可关联的。但当前没有任何机制去做这件事——因为记忆没有 user 维度。想做"按人记忆 + 群/私聊可联合"，三条路：**A.** 在人格提示里约定带归属标记的条目（如 `[user:<openid>] …`），零代码但靠模型自觉、字符预算被所有人共享；**B.** 上外部 memory provider，违反 AGENTS.md §11；**C.** 改 memory store 让它按 session/user 分目录，侵入式且 `memory_tool_store.py` 有 drift 检测与快照逻辑，爆炸半径比 QQ 补丁大、升级同样会丢。

## 每阶段结束必做

1. 复验该阶段的 Acceptance 项。
2. 更新 `DEPLOYMENT_NOTES.md`（主机基线、真实命令、偏离项、变更日志）。
3. 跑一次镜像同步。
4. 追加 `C:\file\HermesAgent\.workbuddy\memory\YYYY-MM-DD.md`。
