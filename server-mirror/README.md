# 服务器文件镜像

本目录保存 `hermes@8.148.73.94` 的部署文件副本，便于查看差异与准备恢复。副本可能滞后，实际状态以服务器核验和 [部署记录](../DEPLOYMENT_NOTES.md) 为准。

## 内容与边界

远程绝对路径按原目录结构保存，例如 `config.yaml` 位于 `var/lib/hermes/.hermes/config.yaml`。

镜像清单包含配置、`SOUL.md`、无凭据的 `.env.example`、swap／swappiness 配置，以及未来可能部署的 systemd、清理和日志轮转文件。缺失文件表示尚未部署，不代表同步失败。`SOUL.md` 是运行提示词副本，不作为维护文档翻译或改写。

不复制 `.env`、会话、日志、记忆、媒体缓存和上游运行环境。当前 `.env` 已含真实凭据，严禁同步。`config.yaml` 若被直接写入密钥也不安全；同步工具不会自动脱敏，复制前须检查，发现秘密时不得保留或提交。

## 使用

在仓库根目录运行：

```bash
python tools/sync_from_server.py --dry-run
python tools/sync_from_server.py
```

工具默认以 `hermes` 账号连接，因为数据目录权限为 700；可用 `--host` 或 `HERMES_TARGET_HOST` 覆盖目标。服务器侧仅执行读取操作，`--prune` 会删除服务器已不存在的本地镜像文件，使用前检查本地改动。

历史核验曾成功同步 5 个文件；本次仅更新说明，未刷新镜像。2026-09-30 服务器仍无 Hermes systemd 服务，媒体清理和日志治理尚待验收。同步工具不会生成或覆盖本说明。
