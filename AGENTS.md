# AGENTS.md

操作约束与当前事实的**浓缩版**。细节、证据、备份与回滚步骤在 `documents/DEPLOYMENT_NOTES.md`（下称「部署记录」），任务与待办在 `documents/TASK.md`，微信差距在 `documents/WECHAT_BACKLOG.md`，emoji 映射清单在 `documents/EMOJI_LIST.md`。历史计划与现状冲突时，以已验证的运行事实为准。

## 一、项目与现状

- 位置：共享 Ubuntu 24.04（`8.148.73.94`，2 vCPU／约 1.6 GiB／2 GiB swap，还跑着网站等业务）；本仓库是 `C:\file\HermesAgent`，本机不是目标服务器。
- Hermes 固定 **v0.21.5**（提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f`）。主模型 `cn:deepseek-v4.1-flash`，经 `https://wb.yinxingye.space/v1` 中转；备用 `kldai/gpt-6-sol` 曾不稳定。
- 已上线并真机验收：QQ 私聊／群 @、微信授权账号私聊、用户隔离、受限提醒、主动关心与生日、远程视觉、表情包与 emoji→表情包映射。
- 未验收：TTS、媒体清理、限流、systemd 自恢复。`stt.enabled=false`，微信群聊未开放。
- 当前只有一个**手动启动**的网关，无自动重启；对外按「单个手动网关、多模态尚未全部验收」表述，不能宣称完整 24×7 服务。

## 二、仓库目录

根目录只放 `AGENTS.md` 与 `README.md`，其余按用途分四个目录；新素材／脚本按此归类，不要再往根目录堆。

| 目录 | 内容 |
| --- | --- |
| `documents/` | `TASK.md`、`DEPLOYMENT_NOTES.md`、`WECHAT_BACKLOG.md`、`EMOJI_LIST.md`；含 `patches/`、`backups/`、`server-mirror/` |
| `scripts/` | 部署／构建／核对／运维脚本；`scripts/test/` 是可重跑的回归（贴纸 19 项、emoji 映射 15 项、生产配置 22 项、空库隐藏、媒体白名单、故障文案） |
| `source/` | 部署到网关的代码本体与素材：`sticker_tool.py`、`emoji_stickers.py`、`persona_errors.py`、`web-deepseek/`、`personas/xiaoyun.json`，以及 `social-work/`、`token-work/`、`config-fragments/` |
| `doro/` | 表情包原图与自助脚本，本地私有、未纳入版本库（`.gitignore` 排除） |

## 三、路径与补丁

- 远程 `HERMES_HOME=/var/lib/hermes/.hermes`，源码 `/var/lib/hermes/.hermes/hermes-agent`，启动器 `/var/lib/hermes/.local/bin/hermes`，日志 `HERMES_HOME/logs/agent.log`。**不要**直接跑源码目录的 `./hermes`，也不要把启动器参数写进 `.env` 代替启动器（`/var/lib/hermes/start-chat-agent.sh` 在 Python 启动前设 `MALLOC_ARENA_MAX=2`、`MALLOC_TRIM_THRESHOLD_=131072`）。
- **不得运行 `hermes update`**。升级或重装前后核对固定提交、工作树，以及：QQ 群被动回复补丁（在 `gateway/platforms/qqbot/adapter.py`）、用户隔离补丁 `documents/patches/hermes-v0.21.5-user-scope.patch`（sha256 `db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d`）、token 精简补丁（sha256 `e4cd9c316eb97d7f4415b7ab78f93b12a18bc4cea6e7a2e1e02040bd0b2b3888`）。补丁均已部署，**首次部署脚本不得重跑**；升级前先反向卸载，回滚时保留 QQ 补丁。
- 本地 `documents/server-mirror/` 可能滞后于服务器；人格源以 `source/personas/xiaoyun.json` 为准，**运行时真正生效的是 `HERMES_HOME/config.yaml` 的 `agent.personalities.xiaoyun.system_prompt`**，`/var/lib/hermes/xiaoyun.json` 只是镜像副本，改它无效（v1.2.4 曾因此让【联网搜索】一直没上线）。

## 四、用户数据隔离（硬约束）

- 身份是网关提供的 **`(platform, user_id)`**，必须与 SQLite 当前会话行的 `source`、`user_id`、`chat_type`、`chat_id` 一致；缺失或不一致就拒绝访问记忆与检索，**绝不回退全局数据**。QQ 与微信不合并身份。
- 记忆目录 `HERMES_HOME/memories/users/<platform>/<用户哈希>/{private,groups}/`：

  | 场景 | 长期记忆 | `session_search` |
  | --- | --- | --- |
  | 私聊 | 该用户的 `private/USER.md`、`MEMORY.md` | 同平台该用户的私聊和群聊历史 |
  | 群聊 | 该用户所有群共用的 `groups/USER.md`、`MEMORY.md` | 仅该用户在当前群的历史 |

- 私聊只可**只读**读群记忆（`memory(action="read", target="group")`），群聊读不到私聊记忆；`/memory` 待审批记录按用户与场景隔离；`group_sessions_per_user=true`，机器人看不到群内他人原始消息。
- 改 `session_search` 时，全文／中文／回退 SQL、浏览、标题、直接读取、滚动、消息锚点、压缩会话关联都要在返回前校验归属；无权限目标统一显示未找到。
- 部署前核查未归属记忆，出现就查清归属，不得擅自分配。

## 五、安全与资源边界

- 工具集：`cli` 仅 `memory`、`session_search`、`tts`、`vision`；`qqbot` 为 `cronjob`、`memory`、`search`、`session_search`、`social`、`sticker`、`tts`、`vision`（库空时 sticker 自动隐藏）；`weixin` 同 qqbot 但**无 `sticker`**。
- 不得擅自启用：`web_extract`、浏览器、终端／Shell、任意文件读写、代码执行、MCP、通用自主 Cron、子代理／委派、图像生成、ACP、本地 LLM／视觉／Whisper。主机级定时器只许做日志／媒体维护，不能暴露给模型。
- QQ／微信只向白名单开放；扩大访问前先验每用户限流与消息／媒体大小上限。密钥只进受限配置／`.env`，不进 Git、日志、示例输出；长期记忆不存凭据、验证码、证件、金融信息。
- 重计算走远程 API；STT 要用远程中文转录，不触发本地 faster-whisper；媒体限量、短期留存、待清理（`cache/images/` 尚未做清理与限流）。
- 共享主机：不要停别人的业务、不要起第二个生产网关、不要把整机重启当常规测试。整机普通聊天低于 900 MB、短时媒体低于 1.1 GB，约 1.3 GB 或持续换入须调查（只看网关 RSS 不够）。

## 六、修改流程

1. 先读本文件、`documents/TASK.md` 相关任务、部署记录最新章节；核实目标主机、提交、配置、既有补丁与工作树。
2. 优先改配置或既有扩展点。源码变更必须有适用提交、补丁、备份与回滚步骤。生产部署前备份数据库／配置／源码，停原网关后只启**一个**网关，验证连接、真实回复、日志与资源，失败即回滚；不得覆盖用户已有修改。
3. 隔离测试用临时 `HERMES_HOME` 与合成 A／B 用户、两个 QQ 群、微信、`/new`、压缩会话，不连真实模型提供方；Hermes 自带测试走 `scripts/run_tests.sh`，生产 venv 缺 pytest 时另建隔离环境；测试进程拿到结果立即停。
4. 全部文本 UTF-8、保留中文；Python 读写显式 `encoding="utf-8"`；中文文件不用 `echo`／`type` 重定向改；PowerShell 取行用 `Get-Content -Encoding utf8 -TotalCount N | Select-Object -Last M`；语法检查用 `compile(Path(...).read_text(encoding='utf-8'), ..., 'exec')`，避免生成 `__pycache__`。
5. 把验证证据写进部署记录，未解决事项写进 `documents/TASK.md`；区分「缺工具／网络／权限」与「代码错误」。

## 七、功能现状与硬规则

- **人格**：`display.personality=xiaoyun`，v1.2.6（system_prompt 2396 字符），全部注入集中在 system_prompt，tone／style 留空。三段工具规则：实时信息先 `web_search`（不得说“没接上数据”）；提旧事先 `session_search`（没查过不说“没记录”）；首次私聊或得知称呼／长期偏好当场写 `USER.md`（敏感信息不写，对方说不用记就照做）。说话方式：一条消息一件事、最多两条建议、不用列点／总结句、超三行压到三行内（对方要步骤才展开）。部署只用 `scripts/deploy-persona-config.py`（ruamel 往返、仅改目标键、0600），按文件签名热加载、**无需重启**。
- **提醒**：`cronjob_manage` 仅本人私聊一次性文字提醒，最长 30 天、每平台每人 20 条，按北京时间解析；每次重新校验身份，拒绝群聊／跨用户／跨平台／脚本／模型参数。正文在创建时按人格写好，到点原样发送、不再调模型。用户可说「2 分钟后提醒我喝水」「查看我的提醒」「取消某条提醒」；群提醒与循环提醒未开放。
- **主动关心与生日**：独立 `social.db`（0600，DELETE 日志），只存简短事项不复制对话，仅本人私聊、两平台分别管理。事件结束 2 小时后（只有日期则次日 18 点）／日常话题 24 小时后提醒，过期 48 小时不补发；每人 48 小时最多一次，23–08 点静默、两小时内有聊天则延后，不回应不追发。生日须明确订阅，只存月日、默认 09:00。候选静默维护不播报；投递不确定记 unknown，绝不自动重发；存储失败写 `social.pause` 待人工解除。用户可说「查看待跟进事项」「这件事已经结束」「不要主动关心我」「我的生日是公历 5 月 20 日……」。
- **图片识别**：纯配置 `auxiliary.vision`（同模型、同中转，`key_env DEEPSEEK_API_KEY`）。主模型判定为文本路由，入站图片由网关生成 2–4 句描述注入上下文（描述是普通历史文本，会随历史重发到压缩阈值），模型也可调 `vision_analyze` 复看。图片经中转发给提供方；每用户张数／频率与 `cache/images/` 清理未做。
- **联网搜索**：`plugins/web/deepseek/`（只检索，无 `/fetch`，故 `web_extract`／`web`／`browser` 关闭），`web.backend=deepseek`，密钥只在 `.env`，插件只记结果条数不记检索词。缺每用户检索次数上限，真实带搜索问答尚未验收。
- **故障文案**：`display.persona_error_voice: true` 时限流／鉴权／策略拒绝／断连／超时等提示改为云白口吻；关闭开关即逐条回退英文原文。
- **表情包**：`send_sticker(id)` 只从 `HERMES_HOME/stickers/manifest.json` 取图（png/jpg/jpeg/gif/webp，1 B–2 MiB，路径不得带空白），返回 `MEDIA:<绝对路径>` 由既有出站管线投递；库空则工具对模型不可见。素材目录必须留在 `gateway.media_delivery_allow_dirs`（`/var/lib` 在 MEDIA 禁用前缀里）。仅 QQ 私聊，8 秒全局冷却。
- **emoji→表情包映射**：`gateway/emoji_stickers.py` 挂在 `send_final_ledgered`，短回复（≤3 行、≤200 字、无代码块）里把已映射 emoji 摘出正文，文字发完停 1.2 秒补一张图；一回合最多一张，与 `send_sticker` 共用冷却（映射侧 300 秒）。**映射表顺序＝优先级**，键是子串匹配，不能写半截 emoji；以 `doro/mapping.txt` 为准。加图与改映射全在 `doro/`：改 `mapping.txt` → `python doro\apply-mapping.py`（校验→备份→写入→逐条自检→失败回滚）；新图丢进去 → `rename-stickers.py --apply` → 在 `manifest.txt` 补场景行 → `sync-stickers.py --apply`（sha256 差异上传、重建 manifest、`load_manifest()` 复核）。不需要重启，老会话可能仍用旧 schema，`/new` 即可。
- **预算**：`compression.threshold_tokens=64000`，推理 `medium`；工具说明与动态尾部已精简（218 项回归、合成样本 −12.94%）。表情包场景表随 schema 每轮发送，条目越多越贵（18 张约 529 字符）；低内存启动器下生产聊天 RSS 约 226 MiB。

## 八、踩过的坑

- 往 `send_final_ledgered` 这类热点函数插代码，锚点必须核对整段：首版脚本把 `delivery_adapter = ...` 赋值行一起替换掉，功能静默失效；改完要 `sed` 复核整段。
- 媒体改动必须真机验收：隔离测试素材放 `/tmp` 绕过了 `/var/lib` 禁用前缀，掩盖了投递被静默丢弃的问题。
- 批量改路径要区分「本仓库路径」与「服务器路径」：`HERMES_HOME/backups/…`、git ref 名、服务器配置镜像都不该被加仓库前缀。
- 配置类改动多在下一轮生效；只有**素材索引与工具枚举**变更才需要 `/new`。先分清是哪一类，再决定要不要重启或新会话。
