# 服务器进程白名单
添加时不要删除已有进程。
## 主站（yinxingye.space / www.yinxingye.space）

- PID：70506（nginx master）、285818、285819（nginx worker）。作用：监听 80/443 并提供主站静态页面，同时将 `/editor-api/` 请求转发至内容编辑 API。
- PID：250394（python3，`main-site-editor.service`）。作用：监听 `127.0.0.1:8787`，处理主站 `/editor-api/` 内容写入请求。

## Codex App Mobile（`apps/mobile` / `codexapp`；服务器快照：2026-09-29 10:20:09 +08:00）

- PID：70506，`nginx: master process`；PID：285818、285819，`nginx: worker process`。作用：通过 `updates.yinxingye.space` 提供 App 更新清单和 APK 下载。
- PID：1146，`sshd`（`ssh.service` 主进程）。作用：为 `scripts/release-android.ps1` 提供 SSH 连接，以检查服务器发布目录并上传、发布更新。

- PID：264090、264187（sshd 反向隧道会话；PID 264187 持有 127.0.0.1:4501 监听）。作用：将本机 Relay 反向转发到服务器，供 Nginx WebSocket 上游使用（核对时间：2026-09-29 10:26:25 +08:00）。
