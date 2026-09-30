# AGENTS.md

## 项目与现状

本项目在 `8.148.73.94` 的共享 Ubuntu 24.04 服务器上运行轻量 QQ／微信聊天机器人。主机为 2 vCPU、约 1.6 GiB 可见内存、2 GiB swap，还承载网站等业务。机器人只负责聊天、会话、记忆及远程多模态 API，不提供服务器管理能力。

以 **2026-09-30** 的只读核验结果为准：Hermes 固定在 v0.21.5（提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f`）；QQ 私聊和群 @ 文本回复已于前一日实测，微信账号尚未接入。主模型为远程 `deepseek-flash`，备用 `kldai/gpt-6-sol` 曾不稳定。`stt.enabled=false`；Vision、TTS、媒体清理、限流和微信端到端能力尚未验收。当前只有一个**手动启动**的网关，没有 Hermes systemd 单元或重启自恢复保证。当前任务见 `TASK.md`，证据与维护步骤见 `DEPLOYMENT_NOTES.md`。

## 路径与补丁

- 本地仓库：`C:\file\HermesAgent`；远程：`ssh hermes@8.148.73.94`。本机 Windows 终端不是目标服务器。
- 远程 `HERMES_HOME=/var/lib/hermes/.hermes`；源码 `/var/lib/hermes/.hermes/hermes-agent`；正确启动器 `/var/lib/hermes/.local/bin/hermes`；运行日志 `/var/lib/hermes/.hermes/logs/agent.log`。不要直接运行源码目录的 `./hermes`。本地 `server-mirror/` 可能滞后于服务器。
- **不得直接运行 `hermes update`。**升级或重装前后核对固定提交和两份本地改动：QQ 群被动回复补丁位于 `gateway/platforms/qqbot/adapter.py`；用户隔离补丁为 `patches/hermes-v0.21.5-user-scope.patch`，SHA-256 `db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d`。后者已部署，不能重复运行首次部署脚本。备份、适用提交和回滚步骤见 `DEPLOYMENT_NOTES.md` §14.6；回滚时保留 QQ 补丁。

## 用户数据隔离

QQ／微信用户身份为可信网关提供的 **`(platform, user_id)`**，必须与 SQLite 当前会话行的 `source/user_id/chat_type/chat_id` 一致；缺失或不一致时，记忆与历史检索均拒绝访问，绝不回退到全局数据。两个平台不自动合并身份。

| 场景 | 长期记忆 | `session_search` |
| --- | --- | --- |
| 私聊 | 该用户的 `private/USER.md`、`MEMORY.md` | 同平台该用户的私聊和群聊历史 |
| 群聊 | 该用户所有群共用的 `groups/USER.md`、`MEMORY.md` | 仅该用户在当前群的历史 |

记忆目录为 `HERMES_HOME/memories/users/<platform>/<用户哈希>/{private,groups}/`。私聊只可通过只读 `memory(action="read", target="group")` 按需读取群记忆；群聊不能读取私聊记忆。`/memory` 待审批记录按用户及私聊／群聊隔离。CLI 保留原有管理行为。部署前全局记忆和未归属待审批数据为空，故未迁移；日后若出现，先查明归属，不得擅自分配。

改动 `session_search` 时，全文／中文／回退 SQL、浏览、标题、直接读取、滚动、消息锚点和压缩会话关联必须全部在返回内容前校验归属。消息平台拒绝跨 profile 查询；无权限目标统一显示未找到。`group_sessions_per_user=true`：机器人不会自动看到群内其他成员的原始消息。

## 安全与资源边界

- `cli`、`weixin` 仅启用 `memory`、`session_search`、`tts`、`vision`；`qqbot` 另启用受限 `cronjob`，只支持本人私聊的一次性文字提醒。不得擅自启用浏览器、终端／Shell、任意文件读写、代码执行、MCP、Web 搜索、通用自主 Cron、子代理／委派、图像生成、ACP，或本地 LLM／视觉／Whisper。主机级定时器只可用于日志、媒体等维护，不能暴露给模型。
- QQ 保持私聊和群白名单；扩大访问前验证每用户限流、消息和媒体大小上限。密钥只放在受限配置／环境文件中，不得进入 Git、日志和示例输出。长期记忆不得保存凭据、验证码、证件或金融信息。
- 重计算走远程 API。启用 STT 前选用平台转录或远程中文 STT，不触发默认本地 faster-whisper；TTS 默认不生成语音。媒体应限量、短期留存并自动清理，先核实实际缓存路径。
- 这是共享主机：不要停止其他业务、启动第二个生产网关或把整机重启当作常规测试。原工程观察线为整机普通聊天低于 900 MB、短时媒体低于 1.1 GB，约 1.3 GB 或持续换入须调查；本次整机内存占用约 676 MiB，旧的“低于 600 MB”目标尚未达到。不能只看网关 RSS。

## 修改流程

1. 先读本文件、`TASK.md` 相关任务及 `DEPLOYMENT_NOTES.md` 最新记录；核实目标主机、源码提交、配置、现有补丁和工作树。历史计划与现状冲突时以已验证的运行事实为准。
2. 优先改配置或 Hermes 扩展点。源码变更须有适用提交、补丁、备份与回滚步骤。生产部署前核查未归属记忆，备份数据库、配置及源码；停原网关后再启动**一个**网关，验证连接、回复、日志和资源，失败则回滚。不要覆盖用户已有修改。
3. 用临时 `HERMES_HOME` 和合成 A／B 用户、两个 QQ 群、微信、`/new`、压缩会话测试隔离，不连接真实模型提供方。Hermes 测试使用 `scripts/run_tests.sh`；生产 venv 缺 pytest 时另建隔离测试环境。测试程序取得结果后立即停止。
4. 所有源码和文本使用 UTF-8，保留中文。Python 读写文本显式指定 `encoding="utf-8"`；中文文件不用 `echo`、`type` 或不明编码重定向修改。PowerShell 读取行范围用 `Get-Content -Encoding utf8 file -TotalCount N | Select-Object -Last M`，不用 `Select-Object -Index`；Bash 用 `nl -ba file | sed -n '起始,结束p'`。受限环境的 Python 语法检查用 `compile(Path('script.py').read_text(encoding='utf-8'), 'script.py', 'exec')`，避免写入 `__pycache__`。
5. 更新 `DEPLOYMENT_NOTES.md` 的验证证据，并把未解决事项写入 `TASK.md`。区分缺工具、网络或权限问题与代码错误。

V1 仍待微信真实接入、远程多模态、媒体和日志治理、限流及 systemd 故障恢复等验收；完成之前不要宣称项目已全部上线。

## QQ 提醒

用户已于 2026-09-30 授权启用。`cronjob_manage` 在 QQ 中只允许创建、查看和移除本人的私聊提醒；每次重新校验数据库身份，拒绝群聊、跨用户目标、脚本／技能／模型和上下文参数。一次性提醒最长 30 天，每用户最多 20 条记录，按北京时间解析无时区的绝对时间。

任务复用网关内置调度器，正文作为固定数据打印，不运行后台模型或加载记忆；执行脚本只能由受限实现生成。补丁为 `patches/hermes-v0.21.5-qq-reminder.patch`，叠加在用户隔离补丁之上。网关停止期间不能按时投递，systemd 自恢复尚未完成；QQ 实际投递结果和维护方法见部署记录。
