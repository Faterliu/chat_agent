# AGENTS.md

## 项目与现状

本项目在 `8.148.73.94` 的共享 Ubuntu 24.04 服务器上运行轻量 QQ／微信聊天机器人。主机为 2 vCPU、约 1.6 GiB 可见内存、2 GiB swap，还承载网站等业务。机器人只负责聊天、会话、记忆及远程多模态 API，不提供服务器管理能力。

以 **2026-10-09** 的核验结果为准：Hermes 固定在 v0.21.5（提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f`）；QQ 私聊和群 @ 文本回复已实测，微信已接入同一个网关，仅开放授权账号私聊，真实收发、多轮上下文及平台身份隔离已验证。主模型为远程 `cn:deepseek-v4.1-flash`，经 `https://wb.yinxingye.space/v1` 中转，provider 仍为 deepseek；备用 `kldai/gpt-6-sol` 曾不稳定。`stt.enabled=false`；Vision 已启用远程路由（2026-10-20，QQ／微信真实发图均已验收）；表情包已上线（2026-10-20 起，**仅 QQ 私聊**，2026-10-22 扩到 18 张并加上 emoji 映射，真实发图已验收）；TTS、媒体清理和限流尚未验收。当前只有一个**手动启动**的网关，没有 Hermes systemd 单元或重启自恢复保证。当前任务见 `documents/TASK.md`，证据与维护步骤见 `documents/DEPLOYMENT_NOTES.md`，微信相对 QQ 落后的能力见 `documents/WECHAT_BACKLOG.md`。对外介绍按「单个手动网关、多模态能力尚未全部验收」表述，不能视为完整的 24×7 服务；微信群聊未开放。

## 路径与补丁

- 本地仓库：`C:\file\HermesAgent`；远程：`ssh hermes@8.148.73.94`。本机 Windows 终端不是目标服务器。
- 远程 `HERMES_HOME=/var/lib/hermes/.hermes`；源码 `/var/lib/hermes/.hermes/hermes-agent`；正确启动器 `/var/lib/hermes/.local/bin/hermes`；运行日志 `/var/lib/hermes/.hermes/logs/agent.log`。不要直接运行源码目录的 `./hermes`。本地 `documents/server-mirror/` 可能滞后于服务器。
- **不得直接运行 `hermes update`。**升级或重装前后核对固定提交和两份本地改动：QQ 群被动回复补丁位于 `gateway/platforms/qqbot/adapter.py`；用户隔离补丁为 `documents/patches/hermes-v0.21.5-user-scope.patch`，SHA-256 `db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d`。后者已部署，不能重复运行首次部署脚本。备份、适用提交和回滚步骤见 `documents/DEPLOYMENT_NOTES.md` §14.6；回滚时保留 QQ 补丁。

## 仓库目录

根目录只放 `AGENTS.md`（本文件）与 `README.md`（项目说明与更新记录），其余按用途分四个目录，运行脚本前须核对适用状态：

| 目录 | 内容 |
| --- | --- |
| `documents/` | [TASK.md](documents/TASK.md)（已完成与待办）、[DEPLOYMENT_NOTES.md](documents/DEPLOYMENT_NOTES.md)（部署证据与回滚）、[WECHAT_BACKLOG.md](documents/WECHAT_BACKLOG.md)（微信差距）、[EMOJI_LIST.md](documents/EMOJI_LIST.md)（emoji 映射清单）；含 `patches/`（固定版本补丁）、`backups/`（人格与旧项目备份）、`server-mirror/`（可能滞后的服务器文件副本） |
| `scripts/` | 部署、构建、核对与运维脚本（`apply-*`、`deploy-*`、`build-*`、`restart-*`、`qq-onboard.py`、`social-admin.py` 等）；`scripts/test/` 是可重跑的回归测试（贴纸工具 19 项、emoji 映射 15 项、生产配置核对 22 项、空库隐藏、媒体白名单边界、故障文案） |
| `source/` | 部署到网关的代码本体与素材：`sticker_tool.py`、`emoji_stickers.py`、`persona_errors.py`、`web-deepseek/` 插件、`personas/xiaoyun.json` 人格源，以及 `social-work/`、`token-work/`、`config-fragments/` 实验素材 |
| `doro/` | 表情包原图与自助脚本（`manifest.txt`、`mapping.txt`、`rename-stickers.py`、`sync-stickers.py`、`apply-mapping.py`），本地私有，未纳入版本库 |

新加素材或脚本时按此归类；根目录不要再堆文件。QQ／微信当前仅向白名单开放，维护前阅读部署记录并保留现有 QQ 群回复补丁。

## 用户数据隔离

QQ／微信用户身份为可信网关提供的 **`(platform, user_id)`**，必须与 SQLite 当前会话行的 `source`、`user_id`、`chat_type`、`chat_id` 四项一致；缺失或不一致时，记忆与历史检索均拒绝访问，绝不回退到全局数据。两个平台不自动合并身份。

| 场景 | 长期记忆 | `session_search` |
| --- | --- | --- |
| 私聊 | 该用户的 `private/USER.md`、`MEMORY.md` | 同平台该用户的私聊和群聊历史 |
| 群聊 | 该用户所有群共用的 `groups/USER.md`、`MEMORY.md` | 仅该用户在当前群的历史 |

记忆目录为 `HERMES_HOME/memories/users/<platform>/<用户哈希>/{private,groups}/`。私聊只可通过只读 `memory(action="read", target="group")` 按需读取群记忆；群聊不能读取私聊记忆。`/memory` 待审批记录按用户及私聊／群聊隔离。CLI 保留原有管理行为。部署前全局记忆和未归属待审批数据为空，故未迁移；日后若出现，先查明归属，不得擅自分配。

改动 `session_search` 时，全文／中文／回退 SQL、浏览、标题、直接读取、滚动、消息锚点和压缩会话关联必须全部在返回内容前校验归属。消息平台拒绝跨 profile 查询；无权限目标统一显示未找到。对外口径：用户以 `(平台, user_id)` 区分，QQ 与微信不合并身份；私聊可只读取群记忆，群聊读不到私聊记忆；身份无法核实即拒绝记忆与检索。`group_sessions_per_user=true`：机器人不会自动看到群内其他成员的原始消息。

## 安全与资源边界

- `cli` 仅启用 `memory`、`session_search`、`tts`、`vision`；`qqbot`、`weixin` 另启用受限 `cronjob`（本人私聊一次性文字提醒）与受限 `web_search`（仅 DeepSeek Search API，单次检索）。`qqbot` 另有受限 `sticker`（只从 `HERMES_HOME/stickers/` 的 manifest 取图，库空时对模型不可见）。不得擅自启用 `web_extract`、浏览器、终端／Shell、任意文件读写、代码执行、MCP、通用自主 Cron、子代理／委派、图像生成、ACP，或本地 LLM／视觉／Whisper。主机级定时器只可用于日志、媒体等维护，不能暴露给模型。
- QQ 保持私聊和群白名单；扩大访问前验证每用户限流、消息和媒体大小上限。密钥只放在受限配置／环境文件中，不得进入 Git、日志和示例输出。长期记忆不得保存凭据、验证码、证件或金融信息。
- 重计算走远程 API。启用 STT 前选用平台转录或远程中文 STT，不触发默认本地 faster-whisper；TTS 默认不生成语音。媒体应限量、短期留存并自动清理，先核实实际缓存路径。
- 这是共享主机：不要停止其他业务、启动第二个生产网关或把整机重启当作常规测试。原工程观察线为整机普通聊天低于 900 MB、短时媒体低于 1.1 GB，约 1.3 GB 或持续换入须调查；本次整机内存占用约 643 MiB，旧的“低于 600 MB”目标尚未达到。不能只看网关 RSS。

## 修改流程

1. 先读本文件、`documents/TASK.md` 相关任务及 `documents/DEPLOYMENT_NOTES.md` 最新记录；核实目标主机、源码提交、配置、现有补丁和工作树。历史计划与现状冲突时以已验证的运行事实为准。
2. 优先改配置或 Hermes 扩展点。源码变更须有适用提交、补丁、备份与回滚步骤。生产部署前核查未归属记忆，备份数据库、配置及源码；停原网关后再启动**一个**网关，验证连接、回复、日志和资源，失败则回滚。不要覆盖用户已有修改。
3. 用临时 `HERMES_HOME` 和合成 A／B 用户、两个 QQ 群、微信、`/new`、压缩会话测试隔离，不连接真实模型提供方。Hermes 测试使用 `scripts/run_tests.sh`；生产 venv 缺 pytest 时另建隔离测试环境。测试程序取得结果后立即停止。
4. 所有源码和文本使用 UTF-8，保留中文。Python 读写文本显式指定 `encoding="utf-8"`；中文文件不用 `echo`、`type` 或不明编码重定向修改。PowerShell 读取行范围用 `Get-Content -Encoding utf8 file -TotalCount N | Select-Object -Last M`，不用 `Select-Object -Index`；Bash 用 `nl -ba file | sed -n '起始,结束p'`。受限环境的 Python 语法检查用 `compile(Path('script.py').read_text(encoding='utf-8'), 'script.py', 'exec')`，避免写入 `__pycache__`。
5. 更新 `documents/DEPLOYMENT_NOTES.md` 的验证证据，并把未解决事项写入 `documents/TASK.md`。区分缺工具、网络或权限问题与代码错误。

V1 仍待真实语音输入、媒体和日志治理、限流及 systemd 故障恢复等验收；完成之前不要宣称项目已全部上线。

## 微信接入

使用固定版本内置的腾讯 iLink 扫码适配器，凭据保存在受限 `.env` 和 `HERMES_HOME/weixin/accounts/`，不得同步至本地仓库。`WEIXIN_DM_POLICY=allowlist`，只允许扫码授权返回的用户身份；`WEIXIN_GROUP_POLICY=disabled`。普通微信群不在本次接入范围。账号、轮询进度与会话令牌由适配器持久化；正常重启无需重新扫码，重启后真实回复已确认。QQ／微信共用 `display.personality=xiaoyun`，实际频道解析的完整人格提示词一致；记忆与聊天记录仍分别隔离。

人格源 `source/personas/xiaoyun.json` 为 v1.2.6（system_prompt 2396 字符），但**运行时读取的是 `HERMES_HOME/config.yaml` 的 `agent.personalities.xiaoyun.system_prompt`**；`/var/lib/hermes/xiaoyun.json` 只是镜像副本，改它不生效。v1.2.4 曾只写镜像，导致【联网搜索】从未上线，2026-10-19 改配置后才真正生效。全部注入内容集中在 system_prompt；tone、style 保留为空，description 为显示说明。现行三段工具规则：v1.2.4【联网搜索】——天气、新闻、价格、比分等实时信息先调 `web_search`，不得声称「没接上数据」，摘要不足时说不确定；v1.2.5【对话检索】——提到「上次／之前／还记得吗」或换过新会话要接着聊旧事时先查 `session_search`，当前会话已有的直接看上下文，没查过不说「没记录」；v1.2.5【记住对方】——首次私聊或得知称呼、身份、长期偏好时当场写 `USER.md`，敏感信息不写，对方说不用记就照做；v1.2.6 说话方式——一条消息只说一件事，多条建议最多给两条、其余等对方追问，不用编号／短横线／列点／总结句与客套收尾，超过三行压到三行以内（对方明确要步骤或清单才展开）。部署必须用 `scripts/deploy-persona-config.py`（ruamel 往返、断言仅目标键变化、0600）；配置按文件签名缓存、网关每轮重新解析，因此无需重启。备份见 `documents/backups/personas/` 与 `HERMES_HOME/backups/persona-*`；勿用历史导入脚本覆盖当前源。

## QQ／微信提醒

用户已于 2026-09-30 授权两平台启用。`cronjob_manage` 只允许创建、查看和移除当前平台本人的私聊提醒；每次重新校验数据库身份，拒绝群聊、跨用户／跨平台目标、脚本／技能／模型和上下文参数。一次性提醒最长 30 天，每平台每用户最多 20 条记录，按北京时间解析无时区的绝对时间。

创建时由当前聊天模型按小云人格写好最终提醒正文，保留事项及必要时间信息；用户要求原样发送时优先遵循。到点发送已保存正文，不再次调用模型或读取记忆；已有任务不自动改写。

用户可见说法：「2 分钟后提醒我喝水」「查看我的提醒」「取消某条提醒」；只发给当前平台的本人，最长 30 天，依赖网关持续运行，实际投递受平台权限与会话有效期约束；群提醒和循环提醒未开放。需要保留原话时说明「届时原样发送」。

任务复用网关内置调度器，正文作为固定数据打印，不运行后台模型或加载记忆；执行脚本只能由受限实现生成。先应用用户隔离、QQ 提醒补丁，再叠加 `documents/patches/hermes-v0.21.5-weixin-reminder.patch`；均已部署，不得重复首次部署。旧 `qq_reminder` 标记及 `scripts/qq_reminders/` 名称为兼容保留，实际归属和收件人均按平台校验。网关停止期间不能按时投递，systemd 自恢复尚未完成；实际验收及维护方法见部署记录。

## 主动关心与生日（2026-10-08）

已部署 `documents/patches/hermes-v0.21.5-social.patch`，SHA-256 `11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f`；仅叠加于固定提交及既有隔离／提醒补丁。首次部署脚本不得重跑。QQ／微信启用受限 `social_manage`，CLI 不启用；不开放通用工具搜索、MCP、Shell 或文件访问。

- `HERMES_HOME/social.db` 独立 SQLite、DELETE 日志、0600、3 秒锁等待；四表分别存设置、跟进、生日和投递，不复制原始对话。没有新服务；复用网关约 60 秒维护循环，每次最多一个投递。
- 身份和会话再次交叉核验，仅本人私聊，拒绝群聊、跨用户／平台／profile。每轮重新绑定不可变消息版本，避免缓存串用户；新消息使旧候选待复核，模型跳过复核则不发送。
- 当前两个白名单用户已开启，新用户需同意。正常聊天模型提取具体未来事件或未结束日常话题；不另调模型，不收集敏感或第三方事件。每轮最多新增 1 条、每人最多 5 条；无明确日期仅存候选，7 天到期。
- 事件结束两小时后，只有日期则次日 18 点；日常话题 24 小时后。最长安排 30 天，过期 48 小时不补发；关心每人 48 小时最多一次，23–08 点静默、两小时内私聊或存在在途聊天则延后。不回应不追发。
- 公历生日须明确订阅，只存月日，默认 09:00，可选 08:00–22:59；非闰年 2 月 29 日按 3 月 1 日。同人同时间合并，只通知订阅者；不受关心开关／48 小时限制，错过当天不补发。每人最多 20 条。
- 文案创建时人格化，到点纯文字 API 单次请求；绕过媒体／本地文件解析和适配器重试。请求前持久化申领，超时／崩溃／无确认记为 unknown，绝不自动重发。关闭关心不影响生日或旧 Cron 提醒。
- 普通候选静默维护，回复自然接话，不播报已记录、问候时间、工具参数或后台异常。优先 batch 同一事务完成复核＋最多一项新增，任意失败全批回滚；返回只含操作数。list 仅用户查询时调用，默认只看跟进，生日须显式选 view，隐藏内部路由。
- 用户可见说法：「查看待跟进事项」「这件事已经结束」「不要主动关心我」「重新开启主动关心」；生日版本为「我的生日是公历 5 月 20 日，每年早上 9 点祝福我，我确认订阅」「查看生日订阅」「取消这条生日订阅」。关闭关心不影响生日或已有明确提醒。
- 已结束跟进留 30 天、投递记录留 90 天，设置与生日由用户删除。存储失败写 `social.pause` 暂停，人工核查后才能解除。

208 项隔离／回归通过，两平台自动候选写入及测试生日投递已验证。当时单个手动网关 PID 798937；此前内存调整后真实聊天 RSS 约 226.55 MiB，本次重启后约 192.20 MiB，仅为启动快照。两平台静默回复此前已实测，各一次 batch，耗时约 13.9／10.1 秒。测试候选与订阅已清理；长期到点关心仍待观察。完整备份和回滚见部署记录；回滚保留 social.db、最新会话和旧提醒，不能恢复旧业务数据。

## 低内存启动（2026-10-08）

服务器保留启动器 `/var/lib/hermes/start-chat-agent.sh`，在启动 Python 前设置 `MALLOC_ARENA_MAX=2`、`MALLOC_TRIM_THRESHOLD_=131072`；手动重启优先用此启动器。不在 Python 启动后才靠 `.env` 设置分配器参数。聊天、缓存容量、并发、超时、工具、人格和调度配置均未修改。

离线合成负载 RSS 211.29→127.27 MiB；生产实际聊天后 251.57→226.55 MiB，约下降 10%，包含重启后的缓存差异，不能保证长期固定上限。QQ／微信真实回复已确认，整机约 677 MiB、swap 106 MiB；本次只调整进程启动环境，没有源码补丁。备份及恢复原分配器方法见部署记录。启动器仍需手动运行，不能视为 systemd 自恢复。

## token 精简（2026-10-09）

已叠加 `documents/patches/hermes-v0.21.5-token.patch`，SHA-256 `e4cd9c316eb97d7f4415b7ab78f93b12a18bc4cea6e7a2e1e02040bd0b2b3888`；不得重复应用或升级 Hermes。静态关心规则归入工具说明，动态尾部保留可信状态及当前北京时间；pending 保留 Unix 字段并附北京时间，避免模型自行换算。工具参数、权限、数据字段及缓存分层不变，JSON 紧凑输出。

`compression.threshold_tokens=64000`，其余保护和摘要策略保持；模型仍为 `cn:deepseek-v4.1-flash`、推理 `medium`。218 项隔离回归通过，四组成对样本输入减少约 12.94%，输出和缓存表现不同，不能承诺费用或延迟同比下降。真实测试累计18次、86,767 token；单次1024只为验收上限，未修改生产输出配置。

当时单网关 PID **860930**（2026-10-20 为启用图片识别重启后为 **1434050**）；两平台真实回复已确认；聊天后 RSS 约233.86 MiB、整机约690.14 MiB、swap约98.7 MiB，仅为快照。原 QQ 补丁保留，密钥未改。回退仅恢复本次五个源码文件及压缩字段，保留最新配置其他项、密钥、数据库和提醒；步骤见补丁同名 Markdown及部署记录。较早压缩的摘要细节与长期频率仍须观察。

## 联网搜索（2026-10-19）

已部署 `plugins/web/deepseek/`（**新增目录**，不改固定提交的任何现有源码文件），把 DeepSeek 官方 Search API（`POST https://api.deepseek.com/v1/tools/search`）接成 Hermes 的 `web_search` 后端。只实现检索，**未实现** `/fetch`，因此 `web_extract`、`web`、`browser` 工具集仍然关闭。

- `web.backend=deepseek`；`platform_toolsets` 的 `qqbot`／`weixin` 加入 `search`（qqbot 现为 cronjob、memory、search、session_search、social、sticker、tts、vision，其中 `sticker` 见「表情包」且库空时自动隐藏；weixin 仍为 cronjob、memory、search、session_search、social、tts、vision），`cli` 保持四项不变。
- 密钥只放受限 `.env`：`DEEPSEEK_SEARCH_API_KEY`、`DEEPSEEK_SEARCH_API_BASE=https://api.deepseek.com/v1/tools`（0600，未进 Git／日志／示例）。插件只记录结果条数，不记录检索词。
- 聊天模型与中转地址未改；搜索是独立的一次 HTTPS 请求，不经过模型回合，每轮多出的只有 `web_search` 的 schema（实测约 +199 token）。
- 已知缺口：**没有每用户检索次数上限**，配额只能靠厂商后台与日志观察；QQ／微信带搜索的真实回复尚未验收。
- 备份、证据与回退步骤见 `documents/DEPLOYMENT_NOTES.md`「联网搜索（2026-10-19）」。

## 图片识别（2026-10-20）

已用**纯配置**启用远程视觉，不改固定提交源码：`config.yaml` 新增 `auxiliary.vision`（`provider: custom`、`model: "cn:deepseek-v4.1-flash"`、`base_url: "https://wb.yinxingye.space/v1"`、`key_env: DEEPSEEK_API_KEY`、`timeout: 60`、`reasoning_effort: none`）。`platform_toolsets` 原本已含 `vision`，未改权限；`stt`、`tts`、模型、人格均未动。

- 主模型仍被判定为文本路由（`decide_image_input_mode=text`），QQ／微信入站图片由网关 `_enrich_message_with_vision` 调辅助视觉生成 2–4 句描述，连同缓存路径注入聊天上下文；模型也可在聊天中调 `vision_analyze` 复看。**描述是普通历史文本**：写入 `state.db` 后每轮随历史重发，直到 64k 压缩阈值摘要；图片本身不重复上传。
- 已实测：中转接受 `image_url`；中文 966×577 截图 3.5 秒准确读出内容与模型名；隔离与生产配置下 `vision_analyze_tool` 均成功；单网关 PID **1438884**（2026-10-20 故障提示人格化后重启），两平台连接正常，RSS 约 197 MiB。**QQ／微信真实发图均已验收**（QQ 09:57：描述 3.0 秒、整轮 16.5 秒、自行补调 `vision_analyze`；微信 10:01：描述 2.3 秒、整轮 6.6 秒；均正确识别 Doro）。
- 隐私与费用：图片经中转发送给模型提供方；每张入站图多一次视觉请求（约 2–4 秒、数百 token）。每用户图片张数／频率、`cache/images/` 留存清理与限流尚未做。
- 回退：停网关，恢复 `HERMES_HOME/backups/vision-20261020T015112Z/config.yaml`（或删除 `auxiliary.vision` 块），用低内存启动器启一个网关。

## 故障提示口吻（2026-10-20）

新增 `gateway/persona_errors.py`（本地源 `source/persona_errors.py`），并以 `documents/patches/hermes-v0.21.5-persona-errors.patch` 改 `gateway/run.py`、`gateway/run_turn.py`。启用 `display.persona_error_voice: true` 时，限流、鉴权、策略拒绝、连接中断、端点不可达、连接错误、崩溃、超时、未登录、存储失败的聊天提示改为云白口吻；关闭开关即逐条回退原英文文案，无需回滚代码。当前生产已启用，单网关 PID **1438884**。补丁仅叠加固定提交与既有补丁，备份／回退见 `documents/DEPLOYMENT_NOTES.md`「故障提示人格化（2026-10-20）」；不要重复应用补丁，升级前先反向卸载。

## 表情包（2026-10-20）

用户问能否加发送表情包；已搭好“空素材库”骨架，首批验收范围定为 **QQ 私聊**。投递层没有新协议：两端适配器本就有 `send_image_file`，网关 `MEDIA:` 出站管线可直接复用。

- 新增 `tools/sticker_tool.py`（本地源 `source/sticker_tool.py`，部署后 sha256 `21f055f77a840785d4ee07e2cadb87353950a0e0bb1dc0bf2a2009d83a4482d3`）：`send_sticker(sticker_id)` 只从 `HERMES_HOME/stickers/manifest.json` 取图，校验路径不越出 `stickers/`、扩展名 png/jpg/jpeg/gif/webp、1 B–2 MiB、路径无空白后返回 `MEDIA:<绝对路径>`。库空或索引损坏时 `check_fn` 为 False，工具对模型完全不可见（零 token）。进程内 8 秒全局冷却。
- 工具说明已含行为约束：仅情绪明显时用、一轮最多一张、严肃／故障／长回答不用、发图后正文照常写、不描述图片。
- 改 4 个源文件：`toolsets.py`（新增 `sticker` 工具集）、`gateway/run.py`（`_AUTO_APPEND_MEDIA_TOOL_NAMES` 加 `send_sticker`）、`tools/tool_search.py`（`sticker` 进 `_DIRECT_SURFACE_TOOLSETS`，否则工具被降级成目录存根、拿不到枚举）、`gateway/platforms/qqbot/adapter.py`（`_send_media` 群聊回填被动回复 `msg_id`，否则 QQ 以 `400 主动消息失败, 无权限` 拒绝图片）。补丁 `documents/patches/hermes-v0.21.5-stickers.patch`，sha256 `c5bf29b489256926864c20e3e0f249ec182b95ad6f012a7f516f61222b288586`，反向 dry-run 四文件通过。
- 配置 `platform_toolsets.qqbot` 加 `sticker`；**微信未加**。素材库 `HERMES_HOME/stickers/`（0700，`manifest.json` 0600，`README.md` 说明格式）。加图只需放文件＋改索引，**新会话即生效，不必改代码或重启**（枚举与说明每次构建工具定义时现读）。
- 上线：13 张 doro GIF（`doro_2`–`doro_14`，用户删掉 doro_1）＋13 条 manifest，2026-10-20 重启 **PID 1449132**（27 个 schema）。首次真机测试时图被投递层静默丢弃——`/var/lib` 在 MEDIA 禁用前缀里；加 `gateway.media_delivery_allow_dirs = ["/var/lib/hermes/.hermes/stickers/packs"]`（只放行素材目录，`config.yaml` 仍被拒）后重启 **PID 1450085**，**QQ 私聊真实发图验收通过**。
- 隔离验证：`scripts/test/test-stickers.py` 19 项全通过；`scripts/test/check-sticker-exposed.py` 证明空库隐藏、有素材可见。注意隔离素材放 `/tmp`，绕过了 `/var/lib` 禁用前缀，**媒体类改动必须真机验收**。
- 未完成：发送频率观察（偏多就把 8 秒冷却调成 5 分钟或做按用户限流）；GIF 是否保留动画；群聊与微信未开放（微信状态见 `documents/WECHAT_BACKLOG.md`）；按用户频控与媒体张数上限未做。备份／回退见 `documents/DEPLOYMENT_NOTES.md`「表情包（2026-10-20）」。

## 表情包情绪映射（2026-10-22）

实测确认 QQ 官方机器人**发不出经典黄脸**（`<face id="1"/>`、`[微笑]`、`/微笑` 都按原文显示），所以改成“程序端把 emoji 换成表情包”：`gateway/emoji_stickers.py` 在 `base.py` 的 `send_final_ledgered` 里摘掉已映射的 emoji，文字发送成功后停 1.2 秒补一张图。

- 映射（16 条，2026-10-22 第二批补到 13 张图全覆盖、第三批加 😄）：`😭→doro_3`、`😎→doro_2`、`🙄→doro_6`、`👀→doro_9`、`🥺→doro_14`、`😤→doro_4`、`😊→doro_5`、`😪→doro_7`、`😡/😠→doro_8`、`🤔/🤨→doro_10`、`🤗/😄→doro_12`、`😌→doro_11`、`🥹→doro_13`；未映射的 emoji 原样保留。改映射只改 `display.emoji_stickers.mapping`，不动代码、不用重启。
- **映射表顺序＝优先级**（`_strip_marked` 遍历 mapping 而非按句中位置，多个已映射 emoji 同现时只补顺序靠前那张）；键按子串匹配，不能写 `❤`、单个肤色修饰符或组合 emoji 的片段。
- 挑映射用 `documents/EMOJI_LIST.md`（`scripts/gen-emoji-list.py` 生成，码点由脚本算）：18 张图现状＋备选、16 组约 200 个 emoji、三个匹配坑。
- **自助维护素材与映射（2026-10-22）**：`doro/` 目录里原图＋`manifest.txt`（`id | 文件名 | 场景`）＋`mapping.txt`（`emoji -> doro_N`，行序即优先级）＋三个脚本。`python doro\sync-stickers.py --apply` 按 sha256 差异上传图片、0600、重建 `HERMES_HOME/stickers/manifest.json`（备份、`load_manifest()` 复核、`--prune` 才删线上多余文件）；`python doro\apply-mapping.py` 本地校验→scp→生产 venv 用 ruamel 往返写 `display.emoji_stickers.mapping`（备份、只动该键、逐条自检、失败自动回滚、不重启）；`rename-stickers.py` 按 `doro_N` 自然序两阶段改名，并同步改两份 txt 的引用（token 精确匹配）。三个脚本都有 Windows 控制台 UTF-8 兜底。当前线上 18 张（doro_1–doro_18），映射 16 条。
- 新图流程：丢图 → `rename-stickers.py --apply` → 在 `manifest.txt` 补场景行 → `sync-stickers.py --apply`；manifest 变动后老会话可能仍用旧 schema，`/new` 即可。
- 生效范围：仅 `qqbot`、仅短回复（≤3 行且 ≤200 字）；代码块、长回答不动；一回合最多补一张。
- 与 `send_sticker` 共用冷却（`tools/sticker_tool.try_acquire()`，工具优先），映射侧 300 秒；图片只从 manifest 取。
- 补丁 `documents/patches/hermes-v0.21.5-emoji-stickers.patch`（sha256 `7d72ea46…`，反向 dry-run 通过）；单网关 **PID 1472108**；隔离测试 15 项通过。回退：`display.emoji_stickers.enabled: false`，无需重启。
- 教训：往 `send_final_ledgered` 插代码时，锚点必须核对整段（首版脚本把 `delivery_adapter = ...` 赋值行一起替换掉了），改完要 `sed` 复核整段函数。


