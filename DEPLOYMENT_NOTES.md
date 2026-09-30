# 部署与维护记录

2026-09-30 通过只读 SSH 核验版本、进程、关键配置、补丁文件与备份。QQ 实际回复和隔离测试的验收证据来自 2026-09-29，本次未重新调用模型。待办见 [TASK.md](TASK.md)，操作约束见 [AGENTS.md](AGENTS.md)。

## 当前部署

| 项目 | 已核实状态 |
| --- | --- |
| 服务器 | `hermes@8.148.73.94`，Ubuntu 24.04，共享网站等业务 |
| 资源 | 2 vCPU，1613 MiB 可见内存，2047 MiB swap，`swappiness=10` |
| Hermes | v0.21.5，发布标签 `v2026.9.24` |
| 固定提交 | `f97608f178d1ffeca59860195ab7da295f7c8e5f` |
| 运行方式 | 单个手动网关；未部署 `/etc/systemd/system/hermes.service` |
| 平台 | 仅 `qqbot` 已配置，私聊与群白名单；微信尚未接入 |
| 模型 | 主用 `deepseek/deepseek-flash`，备用 `kldai/gpt-6-sol` |
| 工具 | 基础四工具不变；QQ 另启用受限 `cronjob` 私聊提醒 |
| STT | `enabled=false`，遗留 `language: en`，启用前必须调整 |
| 会话 | SQLite；`group_sessions_per_user=true` |
| 限制与显示 | `agent.max_turns=32`；人格 `xiaoyun`；隐藏推理与警告通知，QQ 工具进度关闭 |

本次快照整机内存使用 676 MiB、可用 937 MiB，swap 已用 87 MiB；这是单次观测，不是负载验收。普通聊天低于 900 MB、短时媒体低于 1.1 GB 为工程目标；接近 1.3 GB 或持续换入须调查。应同时检查共享业务和网关，不能只看网关 RSS。

## 文件与运行环境

| 用途 | 远程路径 |
| --- | --- |
| 数据目录 `HERMES_HOME` | `/var/lib/hermes/.hermes` |
| 源码 | `/var/lib/hermes/.hermes/hermes-agent` |
| 安装器启动器 | `/var/lib/hermes/.local/bin/hermes` |
| Python | `/var/lib/hermes/.hermes/hermes-agent/venv/bin/python` |
| 配置／凭据 | `/var/lib/hermes/.hermes/config.yaml`、`.env` |
| 会话数据库 | `/var/lib/hermes/.hermes/state.db` |
| 运行日志 | `/var/lib/hermes/.hermes/logs/agent.log` |
| 用户记忆 | `/var/lib/hermes/.hermes/memories/users/<platform>/<用户哈希>/{private,groups}/` |
| 实际缓存目录 | `HERMES_HOME` 内的 `image_cache/`、`audio_cache/`、`cache/` |

早期创建的 `/var/lib/hermes/media/` 未被默认缓存使用；清理规则尚未验收。密钥保存在受限 `.env`，不复制、打印或提交。`server-mirror/` 是本地副本，可能滞后，不包含凭据和聊天数据。

安装来源为 `NousResearch/hermes-agent` 的固定发布，安装器保存在 `installer/install-v2026.9.24.sh`；安装时跳过浏览器和计算机操作。Python 3.12.3，安装时管理的 uv 为 0.12.20、Node 为 26.10.0。锁文件检查因陈旧未完成，依赖未完全按哈希锁定。

Hermes 会在运行时安装部分可选依赖。以下环境必须保留，未来 systemd 服务也须显式传入：

```text
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

## 已修复问题及验证

**QQ 群回复：**固定版本未正确传递群消息的被动回复 `msg_id`，导致 HTTP 400。已在 `gateway/platforms/qqbot/adapter.py` 的群聊发送路径补充原消息 ID，保留 `adapter.py.orig-qqbot-passive`。本地应用脚本为 `staging/apply-qqbot-passive-patch.py`。2026-09-29 群回复已投递，用户确认收到；升级或重装可能覆盖此改动。

**模型与人格：**中转 `gpt-6-sol` 曾出现超时和误判 HTTP 400，改为 DeepSeek 主用。中转使用 `codex_responses` 传输，模型名区分大小写。云白／小云人格来自 `staging/personas/xiaoyun.json` v1.2.0；有效内容须进入 Hermes 实际消费的 `system_prompt`、`tone`、`style` 等字段，JSON 中额外行为字段不会自动生效。

**SQLite：**系统 SQLite 3.45.1 被 Hermes 检测为存在 WAL 风险，当前改用 DELETE 日志模式。用户已接受并记录此风险；不要照诊断提示运行 `hermes update`，也不要未经明确指示替换共享主机的 SQLite。

### 14.6 用户记忆与历史检索隔离

保留本节编号，供已有补丁与文档引用。

- 本地补丁：`patches/hermes-v0.21.5-user-scope.patch`；服务器副本：`/var/lib/hermes/user-scope-v0.21.5.patch`。
- SHA-256：`db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d`。
- 适用提交为上述固定 v0.21.5。补丁已部署，不包含 QQ 群回复改动，不能重复运行首次部署脚本 `staging/deploy-user-scope-v0.21.5.sh`。
- 身份绑定可信网关的 `(platform, user_id)`，与当前数据库会话行交叉校验；身份缺失或不一致时拒绝访问，目录名使用哈希。
- 每用户分别使用 `private/` 与 `groups/` 下的 `USER.md`、`MEMORY.md`。所有群共用该用户的群记忆，私聊不自动加载它；私聊可按需只读调用 `memory(action="read", target="group")`。缓存、后台写入与 `/memory` 审批沿用绑定作用域。
- 私聊检索同平台该用户的私聊及群聊历史；群聊仅检索该用户在当前群的历史。SQL 检索、浏览、标题、直接读取、滚动、锚点和压缩会话均校验归属；消息平台拒绝跨 profile 访问，无权限统一显示未找到。CLI 保留原管理行为。
- 部署前全局记忆与全局待审批记录为空，未迁移未归属数据。2026-09-30 再次确认全局 `USER.md`、`MEMORY.md` 为空；未重新扫描待审批内容。

隔离环境中，以 A／B 用户、两个 QQ 群、微信用户、独立新会话和压缩关联构造测试，覆盖中文回退、各类检索、跨 profile、身份缺失、缓存切换与审批边界。`scripts/run_tests.sh` 通过 **7 个文件、141 项测试**，未连接真实提供方或启动第二个生产网关。

2026-09-29 21:01（北京时间），补丁后 QQ 私聊和群消息均进入网关并生成回复，无发送错误，用户确认群回复收到。数据库对应私聊／群聊记录和独立记忆目录均已核验；测试后网关 RSS 为 248,520 KiB。只验收了当前白名单用户和群，微信仅通过合成数据测试。

## 维护与回滚

常规维护先核对固定提交、工作树及两份补丁。生产变更前备份配置、SQLite 和被修改源码；以短维护窗口停原网关，再启动一个网关，核对新日志中的 QQ 连接、实际回复、补丁和资源状态。失败时恢复，不重启共享主机。

已有隔离补丁备份目录：

```text
/var/lib/hermes/.hermes/backups/user-scope-20260929T125523Z/
  config.yaml
  state.db
  source-before.tar.gz
```

文件权限为 600，源码备份包含部署前的 QQ 群回复补丁。此次只读核验确认三个文件仍存在。

回滚隔离补丁时，先停止并确认原网关退出，在固定源码目录中执行：

```bash
cd /var/lib/hermes/.hermes/hermes-agent
git apply -R --check /var/lib/hermes/user-scope-v0.21.5.patch
git apply -R /var/lib/hermes/user-scope-v0.21.5.patch
```

反向应用失败时，从 `source-before.tar.gz` 恢复对应源码，并仅移除补丁新增的 `tools/gateway_user_scope.py` 和 `tests/tools/test_gateway_user_scope.py`。不要覆盖后续用户数据或无关源码；不要自动恢复旧数据库。重新启动前确认 QQ 补丁仍在。回滚会恢复原有全局记忆／检索行为，因此必须限制访问，并及时恢复隔离。

网关应通过 `/var/lib/hermes/.local/bin/hermes gateway run` 启动，使用原 `HERMES_HOME`、工作目录和上述包镜像环境。`staging/restart-gateway.sh` 是早期手动重启辅助脚本，运行前核对进程匹配、日志路径和当前工作树；不能把它当作 systemd 服务。启动后只保留一个网关，以 `agent.log` 中本次新增记录判断连接，避免把历史日志当作新连接证据。

可在目标服务器上进行以下只读检查：

```bash
/var/lib/hermes/.local/bin/hermes --version
/var/lib/hermes/.local/bin/hermes tools list --platform qqbot
/var/lib/hermes/.local/bin/hermes doctor
git -C /var/lib/hermes/.hermes/hermes-agent rev-parse HEAD
pgrep -af '[h]ermes gateway run'
free -m
vmstat 1 3
```

不要直接运行源码目录的 `./hermes`，它可能调用系统解释器导致缺依赖。跨 PowerShell／SSH 的多行修改应使用 UTF-8 文件传输后执行，避免内联 heredoc 和复杂嵌套引号。`hermes config set` 会重写配置并丢失部分模板注释，修改前保留备份。

## 记录摘要

- 2026-09-29：主机准备、固定版本安装、远程文本模型、工具收缩及 QQ 接入完成；旧 `/home/admin/chat_bot` 已备份后退役，不属于当前部署。
- 2026-09-29：QQ 群被动回复和用户数据隔离补丁完成，隔离测试与 QQ 实际回复通过。
- 2026-09-30：只读核验当前状态，将维护文档统一精简为中文；微信、多模态、清理、限流、日志治理及 systemd 仍待验收。

## QQ 私聊提醒（2026-09-30）

用户授权启用提醒后，在固定 v0.21.5 和原有两份补丁之上增加受限实现。原生 Cron 支持全局任务及自主模型／脚本，消息平台改由内联执行器重新验证当前会话身份，只开放本人 QQ 私聊的 create／list／remove；直接注册表调用被拒绝。CLI 原管理接口保留。

仅一次性提醒：最长 30 天，至少提前 30 秒，每用户最多 20 条（含已完成记录，移除后释放额度），正文最多 1000 字。无时区绝对时间按北京时间解释。目标固定为当前私聊，拒绝群聊、任意目标、模型、技能、上下文及用户脚本参数；附件／静默标记也被拒绝。正文编码为数据，由固定生成脚本打印，调度阶段 `no_agent=true`，不调用模型、记忆或检索。

任务保存在 `HERMES_HOME/cron/jobs.json`，固定正文脚本位于 `HERMES_HOME/scripts/qq_reminders/`。取消时清理对应脚本，发送已开始时不保证能撤回。设定 `cron.wrap_response=false`、`cron.max_parallel_jobs=1`；复用现有网关 ticker，不增设常驻服务。网关关闭时不能准时提醒，开机与崩溃自恢复尚未验收。

- 补丁：`patches/hermes-v0.21.5-qq-reminder.patch`；SHA-256 `a6963923d87472e1e2aed67ecc85e253c86a6505e5fe707296ca744f0b1f79ba`。
- 部署脚本：`staging/deploy-qq-reminder-v0.21.5.sh`，仅适用于尚未应用提醒补丁的既有固定版本；不得重复运行。
- 备份：`/var/lib/hermes/.hermes/backups/qq-reminder-20260930T070841Z/`，含配置、SQLite、相关源码及已有任务快照（若原先存在）。
- 隔离测试使用临时源码及独立 uv 测试环境，`scripts/run_tests.sh -j 1` 通过三个文件、101 项测试，不调用提供方。调度器 no_agent 执行路径已实际验证；QQ 真实到点投递结果见下方。

回滚时先停止单个网关，在固定源码目录对 `/var/lib/hermes/qq-reminder-v0.21.5.patch` 执行 `git apply -R --check` 和 `git apply -R`，恢复本次备份的配置，再按原环境启动一个网关。保留 QQ 群回复及用户隔离补丁。已经创建的提醒必须先由管理端逐个暂停，避免关闭工具后仍然投递；不自动覆盖现有数据库或任务文件。

实测：用户于 15:11 创建“提醒功能测试”，目标时间 15:13:10；2026-09-30 15:13:53（北京时间）通过已连接 QQ 适配器投递，返回真实 message_id。任务状态为 completed、last_status=ok、次数 1/1，投递错误和未验证标记均为空。用户确认收到提醒。内置调度器按约 60 秒周期检查，不承诺秒级准时。

部署后仅一个网关（PID 481948），RSS 约 243 MiB；观察到整机使用约 607 MiB。原有 QQ 被动回复及用户隔离补丁均保留，提醒补丁反向应用检查通过。临时源码、独立测试环境和服务器临时部署脚本已清理；已完成的用户提醒记录保留，可通过查看／移除管理。
