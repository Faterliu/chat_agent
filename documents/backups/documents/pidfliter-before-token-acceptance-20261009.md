# 服务器进程白名单
agent注意：添加时不要删除已有进程。
## 主站（yinxingye.space / www.yinxingye.space）

- PID：70506（nginx master）、285818、285819（nginx worker）。作用：监听 80/443 并提供主站静态页面，同时将 `/editor-api/` 请求转发至内容编辑 API。
- PID：250394（python3，`main-site-editor.service`）。作用：监听 `127.0.0.1:8787`，处理主站 `/editor-api/` 内容写入请求。

## Codex App Mobile（`apps/mobile` / `codexapp`；服务器快照：2026-09-29 10:20:09 +08:00）

- PID：70506，`nginx: master process`；PID：285818、285819，`nginx: worker process`。作用：通过 `updates.yinxingye.space` 提供 App 更新清单和 APK 下载。
- PID：1146，`sshd`（`ssh.service` 主进程）。作用：为 `scripts/release-android.ps1` 提供 SSH 连接，以检查服务器发布目录并上传、发布更新。

- PID：264090、264187（sshd 反向隧道会话；PID 264187 持有 127.0.0.1:4501 监听）。作用：将本机 Relay 反向转发到服务器，供 Nginx WebSocket 上游使用（核对时间：2026-09-29 10:26:25 +08:00）。

## chat_agent（Hermes／QQ／微信）

检查时间：2026-10-08 10:38:20 +08:00。

- PID：741516，`hermes`（Python 3.12，用户 hermes，PPID 1）。作用：同一网关处理 QQ／微信消息、会话与记忆、定时提醒、生日和主动关心调度，属于项目必须保留的进程。
- 当前项目共 1 个进程、21 个线程，无项目子进程；RSS 248.47 MiB、PSS 236.35 MiB。QQ、微信和调度共用该进程，SQLite 无独立数据库进程。
- 当前为手动启动，尚未配置项目 systemd 自恢复；PID 在重启后会变化，清理前须重新核验身份。

## chat_agent 进程更新（低内存启动）

核验日期：2026-10-08。此前 PID 741516 已正常退出，当前应保留的新 PID 为 **745940**。

- PID：745940，`hermes`（Python 3.12，用户 hermes）。作用：同一网关承载 QQ／微信聊天、记忆和历史检索、提醒、生日与主动关心调度；当前项目仍只有 1 个进程。
- 仅调整 glibc 启动参数，功能与源码未改；用户确认两平台回复正常。聊天后 RSS 226.55 MiB、PSS 214.35 MiB、20 个线程，较调整前 RSS 减少约 25 MiB。
- 手动启动器：`/var/lib/hermes/start-chat-agent.sh`。PID 仍会随重启变化；本条替代上方 chat_agent 的旧 PID，其他项目条目原样保留。


## chat_agent 进程更新（中转接口切换）

核验日期：2026-10-08。此前 PID 745940 已正常退出，当前应保留的新 PID 为 **770716**。

- PID：770716，`hermes`（Python 3.12，用户 hermes）。作用：同一网关处理 QQ／微信聊天、会话和记忆、提醒、生日及主动关心；项目仍只有 1 个网关。
- 主模型切换为 `cn:deepseek-v4-flash`，接口 `https://wb.yinxingye.space/v1`。普通回复、工具调用、流式通路及两平台连接已核验；平台真实聊天仍待复测。
- 低内存启动参数和既有源码补丁保留，启动 RSS 约 189.57 MiB，仅为启动快照。本条更新 chat_agent 的 PID，其他项目原有条目完整保留。


## chat_agent 进程更新（DeepSeek 4.1）

核验日期：2026-10-08。此前 PID 770716 已正常退出，当前应保留 **798937**。

- PID：798937，`hermes`（Python 3.12，用户 hermes）。同一网关承载 QQ／微信、会话、记忆、提醒、生日及主动关心；项目仍只有 1 个网关。
- 主模型改为 cn:deepseek-v4.1-flash，地址和当前密钥保持；普通回复、工具调用和流式通路通过，两平台重新连接。启动 RSS 约 192.20 MiB，仅为启动快照。
- 保留低内存启动参数及全部既有补丁。此条更新项目 PID，原有其他条目完整保留。


## chat_agent：token 精简部署（2026-10-09）

- 当前网关 PID：860930；旧 PID 798937 已正常退出（历史记录保留）。
- 命令：/var/lib/hermes/.hermes/hermes-agent/venv/bin/python /var/lib/hermes/.hermes/hermes-agent/hermes gateway run
- 单个手动网关承载 QQ／微信，继续使用低内存启动器；没有新增常驻服务。
- 增量补丁与 64000 token 压缩上限已生效；模型及 medium 推理保持。
- 启动 RSS 约 190.16 MiB，仅为启动快照；两平台连接、工具和身份核验通过，真实收发待用户复测。
- 备份：/var/lib/hermes/.hermes/backups/token-optimization-20261009T032942Z/

添加时不要删除已有进程。其他项目和历史进程条目原样保留。
