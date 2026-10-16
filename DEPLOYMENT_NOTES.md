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
| 平台 | QQ 私聊与群白名单；微信仅授权账号私聊，真实收发和多轮上下文已验证 |
| 模型 | 主用 `cn:deepseek-v4.1-flash`（provider=deepseek，wb 中转），备用 `kldai/gpt-6-sol` |
| 工具 | 基础四工具不变；QQ／微信另启用受限 `cronjob` 私聊提醒 |
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

## 微信私聊接入（2026-09-30）

使用 v0.21.5 内置腾讯 iLink 适配器，无源码补丁和新增常驻服务。用户扫码确认后保存账号令牌，仅将授权响应中的用户 ID 加入白名单：`WEIXIN_DM_POLICY=allowlist`、`WEIXIN_ALLOW_ALL_USERS=false`、`WEIXIN_GROUP_POLICY=disabled`。微信工具仍为 memory、session_search、tts、vision，提醒未开放，STT 关闭。

- 辅助脚本：`staging/connect-weixin.py` 负责授权及配置；`staging/activate-weixin.sh` 验证固定提交与既有补丁、重启单个网关，启动检查失败自动恢复扫码前 `.env`。已有凭据时授权脚本拒绝覆盖。
- 备份：`/var/lib/hermes/.hermes/backups/weixin-20260930T133207Z/`，含受限 `.env`、config.yaml、SQLite、微信适配器及既有补丁相关源码。秘密不复制回本地。
- 微信依赖已具备；实际配置加载和适配器策略验证通过：放行授权用户，拒绝合成陌生用户和群聊；全局 USER.md、MEMORY.md 仍为空。未新增模型调用测试。
- 21:36:20（北京时间）微信连接，随后 QQ 连接，网关报告两个平台；仅一个网关 PID 508342，启动快照整机使用 724 MiB、swap 88 MiB。QQ 群回复、用户隔离及 QQ 提醒实现保留。
- 凭据、轮询进度和回复会话令牌位于 `HERMES_HOME/weixin/accounts/`，不得镜像。普通微信群通常不会由此扫码机器人接收，本次未开放。

用户确认微信收到回复并正确回忆测试暗号，QQ 收到连接测试回复。只读检查实际私聊会话：两平台身份均通过 `resolve_gateway_scope`；记忆目录不同且已创建；相互会话归属被拒绝，双方检索过滤均无法匹配另一平台的会话。用户指定测试暗号在微信消息中出现 3 次、QQ 中 0 次，只返回计数，未导出原始私聊内容。账号凭据、轮询进度、回复会话令牌均已持久化。

关闭微信时先停单个网关，仅移除本次新增的 WEIXIN_* 环境配置，再启动一个网关；若期间无其他配置修改可恢复首次扫码备份 `.env`。不要恢复旧数据库、删除记忆或覆盖 QQ 提醒任务。重配账号前先核实原凭据及授权关系。

扫码程序已退出，临时二维码与渲染依赖已清理；本地维护脚本和受限服务器备份保留。

重启检查：当前配置与 SQLite 再次备份到 `backups/weixin-20260930T134742Z/` 后，正常停止原网关并启动一个网关（PID 509661）。QQ、微信均无需重新授权即连接，微信回复会话令牌恢复成功，启动日志中微信错误计数为 0。整机使用约 651 MiB、swap 88 MiB；服务器临时启动脚本已清理。用户确认重启后微信收到回复，文字接入及正常重启恢复验收完成；群聊、提醒、多模态与故障自恢复未包含在本次验收中。

## 微信人格与受限提醒（2026-09-30）

用户授权微信复用 QQ 人格并增加提醒。核验全局 `display.personality=xiaoyun` 后，以真实 QQ／微信频道调用网关 `_get_system_prompt_for_channel`，两者均与全局人格解析结果完全一致。无需复制或另设人格；会话上下文和记忆仍按平台隔离。数据库 system_prompt 字段不能代替该运行时人格核验。

受限提醒沿用 QQ 实现，新增微信平台许可，收件人固定为当前平台私聊。任务查看、取消及 20 条额度按平台和用户分别计算，拒绝跨平台目标；30 秒至 30 天、一次性、最多 1000 字等原有限制不变。兼容已有 QQ 任务，保留内部 `qq_reminder` 标记和 `scripts/qq_reminders/` 路径名；归属必须同时匹配 platform、user_id、chat_id 和 dm。执行时仍是固定正文、`no_agent=true`，不运行后台模型。

- 增量补丁：`patches/hermes-v0.21.5-weixin-reminder.patch`；服务器 `/var/lib/hermes/weixin-reminder-v0.21.5.patch`；SHA-256 `49c2d49b5319fffb1a3a0954f54f030b374587f338c0c2033731a0811277161e`。
- 适用固定提交及已部署的用户隔离／QQ 提醒补丁；部署脚本 `staging/deploy-weixin-reminder-v0.21.5.sh` 不得重复执行。
- 备份：`/var/lib/hermes/.hermes/backups/weixin-reminder-20260930T140846Z/`，含 config.yaml、SQLite、相关源码和已有提醒任务快照。
- 临时源码、独立测试 venv 与 HERMES_HOME 下，`scripts/run_tests.sh -j 1` 三个文件、135 项测试全部通过（提醒 60、身份 5、原生 Cron 70）。无真实提供方或第二生产网关。
- 给 weixin 启用 cronjob 后，单个网关重新连接 QQ／微信；启动快照整机内存约 625 MiB、swap 89 MiB。原有 QQ 群回复和用户隔离保留，增量补丁反向应用检查通过。

微信真实提醒已投递，用户确认收到；任务状态 completed／ok，次数 1/1，投递错误及未验证标记为空。投递依赖微信上下文令牌及平台权限，短时测试不能保证长时间不互动后仍可主动发送。

临时源码、测试 venv、补丁生成文件和服务器临时脚本已清理；保留本地部署脚本、补丁和受限备份，生产单网关持续运行。

回滚前先由管理端暂停微信提醒；停单个网关，对本次增量补丁执行 `git apply -R --check`、`git apply -R`，恢复本次 config.yaml，启动一个网关。保留 QQ 提醒、群回复、用户隔离和微信登录凭据；不恢复旧数据库或任务快照。不能在此增量仍生效时直接反向应用旧 QQ 提醒补丁，应先回滚此增量。

## 人格化提醒文案（2026-09-30）

用户要求到点提醒也使用人格语气。在共享 `agent.personalities.xiaoyun.system_prompt` 末尾增加“定时提醒文案”规则：创建时，模型将 cronjob_manage 的 prompt 写成小云语气的最终提醒文字，保留事项、对象及必要时间信息；不编造细节，用户要求原样发送或正式简洁时优先遵循。name 仍是简短事项标题。触发时原样发送该正文，不新增后台模型调用；已有任务不改写。

配置辅助脚本为 `staging/apply-reminder-persona.py`，只允许修改该 system_prompt 字段；应用前验证序列化和其他配置语义一致，已配置时拒绝重复追加。部署脚本为 `staging/deploy-reminder-persona.sh`。无源码补丁，提醒权限、投递和调度逻辑不变。

备份：`/var/lib/hermes/.hermes/backups/reminder-persona-20260930T144643Z/`，含配置、SQLite、相关源码及任务快照。正常停止原网关、应用配置、启动单个网关；失败自动恢复 config.yaml。回滚只恢复该配置备份或移除新增规则，不恢复旧数据库或提醒任务。新规则下的实际人格化文案待用户测试。

部署后，两平台的实际频道人格解析均包含新增规则且提示词完全一致；QQ／微信已重新连接，整机使用约 612 MiB。本地人格源 `staging/personas/xiaoyun.json` 同步为 v1.2.1，避免后续重应用人格覆盖规则。服务器临时部署脚本已清理。

## 人格 JSON 精简（2026-09-30）

按用户要求先完整备份，再精简本地人格源。备份 `backups/personas/xiaoyun-v1.2.1-full-20260930T233626.json` 与原文件逐字节一致，SHA-256 `407b4c9699677bf626de3dce1e19bd830b84e038cc8af0577a3f4c6de8736455`；恢复与字段说明见同目录 README.md。

精简源 v1.2.2 保留 id、name、nickname、version、description、system_prompt、tone、style，共 8 个字段；原 30,886 字节降至 5,591 字节。性格 core_traits、说话风格 general 转成 Hermes 直接消费的 tone／style，其他未接入的结构化字段移入完整备份。system_prompt（含提醒规则）内容不改写，身份元数据只供维护，description 只供显示。

`staging/apply-persona.py` 新增直接字段支持并兼容旧格式。验证精简前后有效四字段完全相同，并在服务器调用固定版本的 render_personality_prompt，确认精简结果与当前生产人格配置及渲染结果完全一致。未修改生产配置、源码或网关；服务器临时校验文件已删除。本地校验最初缺 PyYAML，改用 AST 提取纯字段转换函数完成验证，不属于逻辑错误。

## 轻量主动关心与生日（2026-10-08）

用户授权后增加独立 `HERMES_HOME/social.db`，SQLite DELETE／0600／3 秒锁等待。四表保存用户开关、跟进摘要、生日月日和投递状态，不复制完整聊天。QQ／微信本人私聊分别绑定可信身份和当前会话；群聊、CLI、跨用户／平台／profile 均拒绝。已有两位白名单用户已开启，新账号默认关闭。

正常聊天模型通过受限 `social_manage` 保存具体未来事件或未结束日常话题，并提前写好人格文案；无需用户专门设置提醒，不增加后台提取或发送模型。新消息增加版本，旧事项必须逐条复核，跳过工具即暂停。每轮最多 1 个新候选、每人最多 5 个；模糊日期候选 7 天过期，安排最长 30 天、超过到点 48 小时失效。

默认事件结束两小时后，只有日期则次日 18 点，日常话题 24 小时后。普通关心每人 48 小时最多一次，23–08 点静默，两小时内私聊或任一在途聊天延后；不回应不追发。生日必须用户确认，公历月日、默认 09:00、可选 08:00–22:59，每人最多 20 条；非闰年 2/29 按 3/1，错过当天不补发。同人同时间合并，只通知订阅者；关闭普通关心不影响生日和已有明确提醒。

复用网关约 60 秒维护循环，每次最多一个任务。先事务申领再发固定文字，发送前重查会话、白名单和最新版本；直接调用平台纯文字 API 单次请求，绕过原适配器媒体／文件解析与重试。超时、崩溃或无确认记录 unknown，不自动重发；已结束跟进保留 30 天，投递记录 90 天。存储失败写 `social.pause` 暂停，须人工核查后解除。没有新守护进程或第二网关。

### 补丁与测试

- 完整补丁：`patches/hermes-v0.21.5-social.patch`；SHA-256 `11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f`。适用固定提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f` 及现有用户隔离、QQ／微信提醒和 QQ 群回复改动；禁止 Hermes 更新或重复首次部署。
- 维护源码与测试在 `staging/social-work/updated/`；基准为此次生产源码快照，`staging/build-social-patch.py` 生成 UTF-8／LF 增量。首次部署脚本 `staging/deploy-social-v0.21.5.sh`，当前已部署，不得重跑。
- 最新隔离临时源码、独立 venv 和合成数据，`scripts/run_tests.sh -j 1` 四文件 **208 项通过**：social 73、身份 5、QQ／微信提醒 60、原生 Cron 70。未调用真实模型，未启动测试网关。
- 覆盖用户／平台／群／profile、A→B→A 缓存、/new 与压缩归属、每消息复核、更新／取消、中文摘要、时间／闰年／限额、锁、并发申领、崩溃恢复、无确认、纯文字单次 API 及现有提醒回归。
- 首轮测试把“昨日事件、今日 18 点跟进”误判为过去时间，修正了测试日期，保留合法行为。部署检查又发现 CLI 独立工具目录和工具延迟发现；中间一次 schema 检查失败后自动恢复原网关，补齐目录和 social 直接可见声明后，全链路回归通过。CLI 仍不开放 social，也未新增通用工具搜索入口。

### 部署证据与回滚

部署前固定提交、原有补丁、两位白名单与数据库私聊行交叉校验通过；全局记忆和全局待审批记录为空，只输出计数，身份和私聊正文未导出。

- 初始备份：`/var/lib/hermes/.hermes/backups/social-20261008T015006Z/`，含配置、受限环境、SQLite、原有提醒快照及相关源码。
- 完整增量备份：`backups/social-catalog-20261008T015541Z/`，含调整前源码、配置、state.db／social.db 和最终补丁。中间失败备份 `social-catalog-20261008T015322Z/` 保留作审计；不作为完整回滚基准。
- 2026-10-08 部署后单个网关 **PID 739299**，QQ／微信正常连接；各平台实际模型 schema 包含 social_manage，CLI 不含 social。SQLite DELETE、0600，启用用户 2，初始候选／生日／投递均为 0。
- 原 QQ 群回复、身份隔离、提醒补丁保留，完整增量反向应用检查通过。整机内存约 **643 MiB**，swap **104 MiB**；没有升级 Hermes 或重启共享主机。
- 用户真实聊天候选及生日订阅、实际主动投递仍待验收；不能承诺微信长期无互动后可主动发送。原有手动网关与 systemd 待办不变。

回滚：按前述正确启动环境停止单个网关；在固定源码目录执行 `git apply -R --check /var/lib/hermes/social-v0.21.5.patch`，再 `git apply -R`；恢复 **初始备份** `social-20261008T015006Z/config.yaml`，启动一个网关并核验 QQ／微信。最终补丁可同时撤回目录修正，不需再撤回中间补丁。保留 social.db、最新 state.db、微信凭据和 Cron 任务；不要恢复旧数据库／任务快照。保留所有早先补丁。关闭新代码后数据库不会调度；重新启用前核查过期生日、待复核事项和 unknown 投递，禁止补发不确定消息。

### 首条消息延迟修复

用户实测“整理书桌”首条消息迟迟未回复，后发生日订阅才一起回复。只读工具动作核查发现模型多次提交超出 30 天有效范围的旧日期，并重复重试，之后又尝试普通提醒／记忆兜底；没有存储或提供方错误。QQ 最终退为日常候选，微信未成功保存该事件。不能把这次失败写为完整候选验收。

增加每轮服务器北京时间，并支持 `today/tomorrow/day_after_tomorrow`、中文今天／明天／后天及追加明确结束时间，均由服务器解析；日期错误返回当前时间与保存候选的建议。提示词要求日期不明时仅存候选、不重复猜日期、不使用 Cron／memory 代替；已有 pending 直接复核，无需先 list。

- 针对前版 SHA-256 `309ea89e45e1116887d75529c631c9c71dc134b294fd7d675e152a5840349bbd` 的增量为 `patches/hermes-v0.21.5-social-clock-fix.patch`，SHA-256 `571eeba5b8ba3c1d6de3d1f040a9b2e5f630a7c84f6fc23d7551efcdc071be92`。修复已合入上述最终完整补丁，禁止在最终版重复叠加。
- 新隔离环境使用实际前版源码，官方脚本四文件 194 项通过，social 59（新增 5 个服务器相对日期用例）。测试不连接提供方。
- 更新前备份 `backups/social-catalog-20261008T020955Z/`；完整替换补丁后实际 schema／身份核验通过，QQ／微信连接，单个网关 PID 739299，整机约 643 MiB、swap 104 MiB。
- 两平台测试生日已成功写入。安排仅将“测试对象”订阅临时提前约三分钟以验真实投递；普通关心冷却不作绕过。单条自然聊天及时回复复测及测试数据清理进行中。

### 静默记录与投递确认

日期修复后，QQ／微信都从单条“公园拍照”消息创建候选并完成本轮复核，用户确认两边可单独回复；耗时约 32.4／44.1 秒。但回复仍播报“记好了”、问候时间和测试生日后台改动，不符合用户要求的默默记录。

按用户纠正，新增 `batch`：一个事务完成最多六项维护、最多一项新增，任何错误全部回滚；只返回操作数，不向回复暴露安排详情。普通近况静默维护，只自然接话，不承诺几点问候、不讨论参数或后台变化；明确管理请求才调用 list。列表默认只返回跟进，生日须选择 view，不返回内部路由。生日／明确提醒的创建确认保留。减少工具往返，不承诺消除远程模型延迟。

- 静默增量适用前版 SHA-256 `9c2c69b7837a048a18a88bcb77459aa2c1ebc267f5603e61831ec7006369c2dd`：`patches/hermes-v0.21.5-social-silent-fix.patch`，SHA-256 `3fde54cfafbc87fd99da76db1aa0778507e08fa8c41bbeb262b5845ec000d945`。已合入最终完整补丁，不重复叠加。
- 更新前备份 `backups/social-catalog-20261008T022410Z/`；部署后单个网关 PID 741516，两平台连接、实际工具 schema 与身份校验通过；整机约 650 MiB、swap 107 MiB。
- 用户确认提前的测试生日两边都收到。QQ 接口确认成功，微信因成功响应可省略／置空确认字段，被前版严格校验误标 failed；按固定 SDK 兼容 `ret/errcode` 的可选成功语义，新增六个用例。非零错误仍拒绝，异常仍不重发。只对本次对应测试投递按用户明确确认修正为 sent，没有重发。
- 208 项回归通过，包含批量事务回滚、权限／额度、列表最小返回、微信确认兼容。静默回复及往返改善已通过最后复测，测试候选与订阅已删除；保留两条投递验收状态。

最终回滚仍使用上述完整补丁反向应用和 **初始** `social-20261008T015006Z/config.yaml`；当前后续备份含 social 启用配置，不能用它代替完整功能回滚基准。`.gitattributes` 仅为本次 social 补丁／脚本强制 LF，避免 Windows 换行改变校验哈希；既有补丁不改写。

### 最终实测与清理

用户分别发送单条烤面包近况，确认 QQ／微信均自然接话，没有播报已记录、问候时间或后台参数；平台标签由用户自行添加，仅引号内文字属于机器人回复。用户认为“第一次烤面包”的口语推测无需修改，保持现有文风。

只读元数据核验：两平台各调用一次 social_manage(action=batch)，结果成功，各新增一条面包候选；无其他工具调用。本轮从会话消息入库至最终回复约 QQ 13.9 秒、微信 10.1 秒，上一轮约 32.4／44.1 秒。这是两次样本，不能视为持续延迟保证。

已按授权删除当前两位测试用户的书桌、拍照、面包候选及“测试对象”生日订阅；social.db 中候选 0、生日 0、启用用户 2、sent 投递验收记录 2。真实聊天历史保留，后续谈及这些话题仍可能生成新候选。隔离测试源码／venv 和临时测试部署脚本已清理，维护助手、补丁及备份保留。

收尾核验固定提交与最终补丁哈希一致，反向应用检查及 QQ 群被动回复标记通过；单个手动网关 PID 741516，social.pause 不存在，整机内存约 682 MiB、swap 107 MiB。进程检查首次因命令匹配过窄漏报，使用 PID 和进程元数据复核后确认运行正常，不属于网关故障。普通关心在真实日期、聊天冷却后的长期投递和微信上下文失效行为仍待观察；systemd 未完成。

## 运行内存调整（2026-10-08）

用户授权在功能不变前提下尝试降低网关内存。只读核验 glibc 2.39，主要为匿名内存；没有本地模型。单纯导入或三个合成 Agent 的回收仅节省约 1–2 MiB，未据此调整缓存、并发或会话功能。远程没有 rg，源码检索改用 Python，不属于代码故障。

### 离线对比

临时 HERMES_HOME 下禁用网络，十个线程构造假 HTTPS 客户端、合成 ChatCompletion 与文字缓冲，随后退出。没有调用真实提供方或启动第二个网关。脚本为 `staging/profile-gateway-allocator.py`。

| 启动参数 | 合成负载后 RSS | 活动耗时 |
| --- | --- | --- |
| 默认分配器 | 211.29 MiB | 0.441 秒 |
| MALLOC_ARENA_MAX=2 | 166.38 MiB | 0.380 秒 |
| 再加 MALLOC_TRIM_THRESHOLD_=131072 | 127.27 MiB | 0.373 秒 |

采用最后一组参数，限制 arena 数并固定自动回收阈值；没有添加周期 gc 或 malloc_trim、替换分配器、修改 Python 依赖。表中结果不包含随后人工 malloc_trim 的收益，合成负载不能代表生产长期峰值。

### 部署与验收

- 备份：`/var/lib/hermes/.hermes/backups/low-memory-20261008T030924Z/`，受限保存 config.yaml、.env、Cron 任务快照、state.db／social.db、源码差异／归档及前后测量。业务数据库快照使用 SQLite backup 接口。
- 切换前核实单网关、在途 Agent 为 0、固定提交、social 补丁及 QQ 群回复标记；未归属记忆及待审批计数均为 0。
- 正常停止 PID 741516，使用新启动器启动单个网关 **PID 745940**；QQ／微信连接、模型工具 schema 和本人私聊归属核验通过，两个参数在运行进程环境中生效。
- 源码差异与 config.yaml 逐字节保持一致；记忆、历史、提醒、生日、主动关心、人格、缓存容量、并发和超时配置没有变动。旧的 208 项逻辑回归结果沿用，本次没有改逻辑，也未重复启动隔离测试网关。
- 启动时 RSS 189.31 MiB，仅作启动快照。用户确认 QQ／微信实际回复正常；会话元数据本轮耗时约 4.0／2.4 秒，仅输出计数和时长。
- 真实聊天后 **RSS 251.57→226.55 MiB**，约减少 **25.02 MiB／9.95%**；PSS 239.07→214.35 MiB，新进程 Swap 0、20 个线程。差值包含重启清空部分运行缓存的影响，不能全部归因于分配器参数；持续多轮、并发和长期运行仍需观察。
- 收尾整机内存约 677 MiB、swap 106 MiB，仅一个项目网关；原 QQ 群回复与补丁反向应用检查通过。隔离测量目录及服务器一次性脚本已清理，保留启动器、维护助手和备份。共享主机未重启，其他业务未停止。

### 启动与回退

低内存启动器 `/var/lib/hermes/start-chat-agent.sh`（0700）；本地源 `staging/start-chat-agent-low-memory.sh`。先确认原网关已退出，再用 `nohup /var/lib/hermes/start-chat-agent.sh` 配合受限日志文件启动单个网关。仍是手动运行，没有故障自恢复。后续源码部署脚本若直接调用旧启动器，应显式沿用这两个启动参数。

回退仅需正常停止当前单网关，使用原 `/var/lib/hermes/.local/bin/hermes gateway run` 启动，并在启动前移除 `MALLOC_ARENA_MAX`、`MALLOC_TRIM_THRESHOLD_`；保留原 HERMES_HOME 与三个包镜像环境。核验两平台连接及单实例。不要恢复旧配置、数据库或提醒快照，也无需撤回源码补丁。两个参数须在 Python 启动前设置，不能仅在已启动进程加载的 `.env` 中添加。

`C:\file\pidfliter.md` 原有主站、Codex 与隧道章节保留，末尾追加此次新 PID；旧 PID 741516 已退出。修改白名单前先备份，不覆盖其他项目内容。

## 人格重复内容合并（2026-10-08）

用户授权合并重复内容。人格源更新为 v1.2.3，将 tone／style 中独有的复杂问题拆解、不过度煽情等要求并入 system_prompt，两个字段保留为空；合并 AI 身份、群聊隐私、主动闲聊和表达风格的重复描述。个人偏好、L0–L3、纠错、任务处理和定时提醒文案整段保留，显示 description 与身份元数据未改写。关心工具与每轮静默维护提示均未修改。

- 本地逐字节备份 `backups/personas/xiaoyun-v1.2.2-before-merge-20261008.json`，SHA-256 `b9b5bd23d9b5164c11ba8291c39a40b0af53c12b00e1ae7ebc6aa5fba682c28c`；源 `staging/personas/xiaoyun.json`。
- 实际渲染 1905→1644 字符，减少 261 字符／13.7%；新 system_prompt SHA-256 `71851b60f3fd37c736fc4f553584abff3d13476c59625466a5d28a9ce6b2187f`。字符比例不是总请求 token 或费用的同比降幅。
- 服务器备份 `/var/lib/hermes/.hermes/backups/persona-merge-20261008T064702Z/`，包含 config.yaml、.env、Cron 快照、state.db／social.db、远程旧人格源及相关源码；目录 0700、文件 0600。数据库使用 SQLite backup 接口，没有回写旧业务数据。
- `staging/deploy-persona-merge.py` 在固定提交和既有补丁预检后，只替换 YAML 中小云条目，其他配置语义及条目外文字保持；原子更新 config.yaml 和 `/var/lib/hermes/xiaoyun.json`，失败自动恢复。首次合并已执行，脚本再次执行会因旧人格不匹配拒绝覆盖。
- 核实当前版本 `GatewayConfigLoadersMixin._get_system_prompt_for_channel` 每轮加载当前 profile 配置，生产进程没有 HERMES_EPHEMERAL_SYSTEM_PROMPT 覆盖。无需停机或重启，新规则从下一轮聊天生效。
- 使用现有私聊路由调用 QQ／微信实际频道解析方法，均等于新人格；核验单网关 PID 745940、低内存启动参数、QQ 群被动回复标记及 social 补丁反向检查通过，未归属记忆／审批均为 0。源码差异逐字节保持一致。
- 维护脚本语法和 YAML 序列化／非目标配置校验通过；没有运行 Agent、连接模型提供方或启动第二网关，本次未额外发送真实聊天测试，不消耗 DeepSeek token。服务器临时上传目录及脚本已清理。

回退：仅把上述服务器备份的 config.yaml 与 xiaoyun-before.json 恢复至原配置和 `/var/lib/hermes/xiaoyun.json`；本地源恢复自 v1.2.2 备份。恢复前核查是否有后续配置修改，有则只还原小云条目，保留后续修改。用原子替换保留权限并核验两平台解析，下一轮生效，无需重启。不要恢复数据库、微信凭据或 Cron 任务快照，也无需撤回源码补丁。

## 用户更换 DeepSeek 密钥后的接口测试（2026-10-08）

用户自行修改 DEEPSEEK_API_KEY 后授权测试。调用固定版本真实凭据解析器，确认其读取值与当前 .env 一致，不输出密钥。当前实际 Base URL 为非 DeepSeek 官方域名；模型仍为 deepseek-flash。

- 模型列表接口 HTTP 200，但未列出当前模型 deepseek-flash。
- 两次最小 chat/completions 请求均返回 HTTP 503、api_error／no_healthy_account；首次约 1.32 秒，复查与重试共约 0.84 秒。每次最多 64 输出 token，没有成功生成回复；失败请求实际计费需以接口服务商为准。
- 当前新配置的聊天可用性未通过，错误提示可能涉及中转上游账号／模型路由，不能仅凭模型列表成功断言聊天权限正常或密钥无误。需核对服务商支持的模型名及上游状态。
- 本次仅接口测试，未修改配置、模型、密钥或源码，未重启网关；临时客户端随脚本结束关闭，没有额外后台进程。现有缓存会话是否已切换新密钥未验收。

## 中转接口切换与通路验证（2026-10-08）

用户授权使用 `https://wb.yinxingye.space/v1` 及其提供的测试密钥先验证、再修改生产配置。密钥仅经 SSH 标准输入传递，未写入本地文件、源码或文档，也未输出；正式值仅保存到服务器受限 .env。

- 模型列表 HTTP 200，提供 `cn:deepseek-v4-flash` 等模型；旧名称 deepseek-flash 仍为 503／no_healthy_account。按实际名称测试普通回复 HTTP 200、1.76 秒、48 token；模拟工具调用 HTTP 200、1.75 秒、367 token，返回正确函数调用，没有执行工具动作。
- 保留 provider=deepseek，将 model.default 改为 `cn:deepseek-v4-flash`，model.base_url 与 DEEPSEEK_BASE_URL 同为新地址，并更新 DEEPSEEK_API_KEY。只修改这四个配置项，其他配置语义、人格、原有补丁及源码保持；没有升级 Hermes。
- 备份 `/var/lib/hermes/.hermes/backups/api-change-20261008T073926Z/`，包含 config.yaml、.env、state.db／social.db、Cron 快照和相关源码，目录 0700／文件 0600。维护脚本 `staging/deploy-deepseek-endpoint.py` 不含密钥，原子更新，部署失败会恢复配置并重启单个原网关。
- 固定提交、既有补丁、未归属记忆／审批为 0、在途 Agent 为 0 核验后，正常停止 PID 745940，使用低内存启动器启动单个网关 **PID 770716**；QQ／微信重新连接，两个分配器启动参数保留。
- 使用 Hermes 实际凭据解析器核对新地址和密钥，再用 OpenAI 客户端验证新模型的流式文本回复。流式测试及后续路由检查共约 4.51 秒，不能视作纯模型响应时长。两平台模型工具 schema、本人私聊路由、social 数据库模式和计数核验通过；启动 RSS 189.57 MiB，仅为启动快照。
- 本次通路验证没有发送平台真实消息，QQ／微信新配置真实聊天仍待用户复测。用户计划撤销测试密钥；当前网关依赖这枚密钥，撤销前须换入有效密钥并重启，否则后续模型请求可能失败。没有代用户撤销密钥。
- 服务器临时上传脚本清理，进程白名单追加新 PID 并保留全部原内容。未重启共享主机或停止其他业务。

回退：正常停止单个网关，核查后恢复本次备份的 config.yaml 和 .env，并用 `/var/lib/hermes/start-chat-agent.sh` 启动一个网关；不得恢复业务数据库或 Cron 快照。备份保留的是切换前配置，其 deepseek-flash 通路此前测试失败，因此回退仅还原配置，不能保证旧接口恢复可用。恢复前有后续修改时，仅还原上述四个配置项。测试密钥撤销后不得重新启用它。

### 用户再次替换密钥后的验证

用户自行替换 .env 密钥后，使用 Hermes 实际解析的新凭据测试当前 `cn:deepseek-v4-flash`：HTTP 200、正常结束、1.79 秒，输入 34／输出 14，共 48 token。密钥未输出；本次未修改配置或重启网关，PID 770716 仍运行。现有缓存客户端是否使用新密钥不能由独立接口测试证明，须重启后验收。


## 模型名修正为 4.1（2026-10-08）

按用户纠正拉取模型列表，HTTP 200；cn:deepseek-v4-flash 与 cn:deepseek-v4.1-flash 均存在。改用其指定的 cn:deepseek-v4.1-flash：普通回复 HTTP 200、2.65 秒／53 token，模拟工具调用 HTTP 200、1.84 秒／352 token，工具未执行动作。

使用 staging/deploy-deepseek-endpoint.py 的 --model-only cn:deepseek-v4.1-flash 模式，只更新 model.default；地址、.env、人格和其他配置语义保持，源码差异未变。备份 /var/lib/hermes/.hermes/backups/model-change-20261008T130757Z/，目录 0700／文件 0600，含原配置、环境、数据库、提醒和相关源码。旧 PID 770716 正常退出，低内存启动器启动单个网关 PID 798937，两平台连接、工具 schema、本人私聊路由和流式回复核验通过；流式及后续路由检查共约 4.12 秒，启动 RSS 192.20 MiB。重启已加载用户自行替换的新密钥，未恢复旧测试密钥；.env 逐字节保持。

服务器临时脚本及目录清理，进程白名单备份后追加新 PID，原内容完整保留。平台真实收发尚未额外验收。回退时正常停止单网关，仅恢复本次备份的 config.yaml 中 model.default 为 cn:deepseek-v4-flash，再通过低内存启动器启动一个网关；保留最新密钥、数据库及提醒任务。有后续配置变化时不得整份覆盖。

## 聊天 token 精简：隔离验证（2026-10-09）

用户授权精简工具说明、结果及往返，压缩上限改为 64000，保留模型、medium、小云人格和各平台隔离。先在 `/var/lib/hermes/token-work-20261009/` 创建固定提交加当前修改的源码快照，没有第二生产网关。

最终增量补丁 `patches/hermes-v0.21.5-token.patch`，SHA-256 `e4cd9c316eb97d7f4415b7ab78f93b12a18bc4cea6e7a2e1e02040bd0b2b3888`；改动五文件，哈希清单和回退见同名 Markdown。核心工具顺序及稳定/动态提示分层已有确定实现，保持原代码。关心静态要求归入工具定义，动态尾部只携带可信状态；pending 保留 due/expires 并附北京时间，避免模型手算。JSON 紧凑序列化，字段和权限不删减。

官方 `scripts/run_tests.sh -j 1` 五文件 **218 项通过**（原有 208＋新增 10），最新完整运行约 28.9 秒。新增覆盖 schema 去说明后结构相等、规则完整、JSON 字段/中文、64K 有效阈值、提示失效与顺序、动态版本和 A→B→A、北京时间字段准确、压缩关联原文/身份边界。测试与假工具执行使用独立 HERMES_HOME；没有向平台投递。

隔离环境首次缺显式 HERMES_PYTHON，官方脚本随后清除了自定义环境变量；已按官方入口指定测试解释器并使用文件相对路径。新增合成 Agent 漏了 _memory_store 和夹具误用 tools 配置字段，也已修正。这些是测试环境/夹具问题，生产逻辑未因之修改。可选 tiktoken 只装入临时测试 venv，没有更改生产依赖。

真实请求截至当前 **10 次、47,993 token**，包含失败验收的 usage；缓存读计入输入总量，推理计入输出，不重复计数。第 4 次精简 batch 错带生日 clock，被既有严格参数校验拒绝；已补明确归属。第 8、10 次因 max_tokens=512 同时限制推理，全部预算用于推理并返回 length，没有工具调用；没有擅自降低 medium 或提高上限，也没有部署。普通聊天样本输入 4882→4228，减少约 13.4%，仅属合成单请求，不能当作所有聊天或费用的同比收益。

用户已把原八次上限增至十二次。现等待授权单次 1024、累计最多十八次，十万 token 总预算保持，以完成四组成对重测。生产仍为原源码、256000 压缩上限、单网关 PID 798937；配置/.env/业务数据库/提醒和进程白名单未被本次测试修改。部署助手已准备，但以完整成对验收通过、补丁哈希一致和预算门槛为前提。


### 最终验收与部署

用户再次授权单次测试上限1024、累计最多18次，十万 token 总预算保持。最终八次请求的四组成对场景全部通过：普通聊天不调用工具，待办复核＋新事件一次 batch，生日参数与原文正确，成功维护后自然接话且不追加工具。所有工具只在临时 SocialStore 执行，没有发送平台提醒。实测 batch 精简版输出566 token，证明512的原测试限制不足以容纳本次 medium 推理及调用。

| 四组成对样本 | 精简前 | 精简后 |
| --- | --- | --- |
| 输入 token（含缓存） | 19744 | 17189 |
| 缓存读 token | 17920 | 13568 |
| 输出 token（含推理） | 752 | 1089 |
| 其中推理 token | 391 | 757 |
| 模型请求／工具调用 | 4／2 | 4／2 |
| 四次响应耗时合计 | 10.89秒 | 12.56秒 |

输入减少2555／12.94%；输入加输出减少约10.82%。缓存命中和推理具有样本波动，不能把缓存当作token数量减少，也不宣称延迟改善。全部调试真实请求累计18次、**86,767 token**，包含此前失败的10次；用户后续真实聊天不计入这个受控测试预算。完整usage和合成响应见 staging/token-work/results/model-report-verified.json；没有密钥或真实聊天正文。

备份 `/var/lib/hermes/.hermes/backups/token-optimization-20261009T032942Z/`，目录0700／文件0600，含配置/.env、SQLite backup快照、Cron任务、相关源码、补丁清单和测试证据。停止前单网关、在途0、未归属记忆/审批0；固定提交、源码前哈希和既有social补丁核验通过。正常停止PID798937，应用五文件补丁，只把compression.threshold_tokens改为64000，通过低内存启动器启动单网关**PID860930**，QQ／微信重新连接。

两平台实际七工具schema一致（10707字符），配置顺序反转、清缓存后仍相同；发现机制保留。有效压缩阈值64000，protect_last_n仍20；其余摘要/保护策略与medium未改。修改后源码哈希、增量反向检查及QQ被动回复标记通过，.env逐字节保持，没有恢复旧密钥。social启用用户2、候选0、生日0、sent验收记录2，权限路由和DELETE/0600检查通过。服务器保留 `/var/lib/hermes/token-v0.21.5.patch` 与哈希清单用于维护，首次部署助手再次运行会拒绝重复应用。

用户确认QQ／微信两边正常，元数据确认部署后两平台均有assistant消息；没有打印真实内容。启动RSS190.16 MiB，聊天后RSS233.86 MiB、21线程、进程swap0；整机约690.14 MiB、swap98.7 MiB，均为快照。当前在途0且仅一个项目网关，没有重启主机或影响其他业务。

回退仅恢复本次五个源码文件及当前配置的压缩字段256000，保留最新密钥、人格、数据库和提醒。自动失败回退助手已准备；手动步骤见 patches/hermes-v0.21.5-token.md。进程白名单先保存完整备份，再追加860930，原字节前缀保持；当前长期压缩摘要细节和频率仍待观察。

收尾：确认没有临时测试进程后，移除 `/var/lib/hermes/token-work-20261009/` 下源码、venv与合成数据库；本地保留五文件前后快照、哈希、回归和真实对照报告，验收快照亦存入受限服务器备份。生产单网关860930、QQ/微信连接、在途0，未留下新端口或测试服务。白名单追加验收说明前再次完整备份，所有原字节保持。
