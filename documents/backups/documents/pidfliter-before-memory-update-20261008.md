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
