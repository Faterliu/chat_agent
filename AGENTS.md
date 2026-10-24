# AGENTS.md

本文件统一记录运行现状、操作约束与微信差距；只维护当前结论，不追加部署流水账。待办见 `documents/TASK.md`，映射参考见 `documents/EMOJI_LIST.md`，实际状态以服务器核验为准。整理日期：2026-10-23，最近运行核验：2026-10-22。

## 要求
1. 本文档新增内容必须为精简后的内容；
2. 非必要不新增其他文档；
3. 运行中的副产物在运行结束后必须清理；
4. 运行中新增的各种脚本（包括测试脚本）倾向于不保留，除非需长期使用；
5. 默认不保留回退、backup等内容，除非明确要求；

## 运行环境

- 本地仓库 `C:\file\HermesAgent`；目标为共享 Ubuntu 24.04：`8.148.73.94`，2 vCPU、约1.6 GiB内存、2 GiB swap，另有网站业务。
- Hermes固定 **v0.21.5**，提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f`。主模型 `cn:deepseek-v4.1-flash`，中转 `https://wb.yinxingye.space/v1`；备用模型曾不稳定。
- **QQ与微信共用一个手动网关**，没有systemd自恢复，不宣称24×7。QQ开放白名单私聊和群@；微信仅授权账号私聊，用户明确暂不加群。
- 远程 `HERMES_HOME=/var/lib/hermes/.hermes`（下称HOME），源码 `HOME/hermes-agent`，Python `HOME/hermes-agent/venv/bin/python`；配置/凭据为 `HOME/config.yaml`、`.env`，日志 `HOME/logs/agent.log`。
- 通过 `/var/lib/hermes/start-chat-agent.sh` 启动；它在Python启动前设置 `MALLOC_ARENA_MAX=2`、`MALLOC_TRIM_THRESHOLD_=131072`，调用 `/var/lib/hermes/.local/bin/hermes`。不要直接跑源码目录的 `./hermes`，不要用.env代替启动环境。保留现有清华PyPI镜像环境。
- 根目录只放AGENTS与README；`documents/` 放文档与服务器快照（`server-mirror/` 可能滞后）；`scripts/` 只留长期用的三个脚本（`deploy-persona-config.py` 导入人格、`gen-emoji-list.py` 生成 emoji 清单、`sync_from_server.py` 刷服务器快照），一次性部署脚本用完即删；部署源码在 `source/`，表情包原图在 `doro/doro/`、总表与脚本在 `doro/`。

## 安全与数据隔离

- **不得运行 `hermes update`、重跑首次部署脚本、覆盖已有修改、启动第二个生产网关或干扰其他业务。**升级/重装须先核对固定提交与服务器工作树上的全部已部署改动（QQ群被动回复、用户隔离、提醒、social、token、媒体）。本地不留补丁副本，历史版本以远程 git 为准。
- 工具集：CLI仅 `memory/session_search/tts/vision`；QQ与微信同为 `cronjob/memory/search/session_search/social/sticker/tts/vision`。库空时隐藏sticker。
- 不擅自向模型开放终端、代码执行、任意文件读写、浏览器、MCP、子代理、通用自主Cron、图像生成、ACP或本地模型。检索仅 `web_search`，不开放 `web_extract`。主机定时任务仅用于维护。
- 白名单扩大前先完成每用户限流及消息/媒体上限验证。密钥只存受限配置/.env，不打印、不入Git或日志；长期记忆不存凭据、验证码、证件或金融信息。
- 身份由可信网关提供 `(platform,user_id)`，须与SQLite会话的 `source/user_id/chat_type/chat_id` 一致；缺失或不符就拒绝，**绝不回退全局数据**，QQ与微信不合并身份。
- 记忆位于 `HOME/memories/users/<platform>/<用户哈希>/{private,groups}/`。私聊读写本人private，可按需只读本人groups；群聊只读写本人共用groups，不能读private。审批与缓存同样隔离，`group_sessions_per_user=true`。
- 私聊可检索同平台本人私聊及群聊；群聊仅检索本人在当前群的历史。搜索、回退SQL、浏览、标题、直接读取、滚动、锚点和压缩关联均须校验归属，无权限统一显示未找到。部署前发现未归属记忆/审批须查清，不得擅自分配。
- 会话上下文来自服务器 `HOME/state.db`，不读取手机/电脑聊天历史。两库state.db/social.db使用DELETE日志模式；不要擅自替换共享主机SQLite。

## 已有功能与维护入口

- **人格与搜索**：`source/personas/xiaoyun.json` 是人格源，真正生效的是 `config.yaml` 的 `agent.personalities.xiaoyun.system_prompt`，服务器同名JSON镜像不生效。只用 `scripts/deploy-persona-config.py` 导入，热加载无需重启。保持实时信息先搜索、旧事先检索、称呼/长期偏好及时建档；QQ/微信真实联网问答均已通过。
- **提醒与关心**：仅本人私聊、平台分别管理。提醒只允许30天内一次性固定文字，每人每平台20条；到点不调用模型。social只存事项摘要，普通关心48小时最多一次、23–08点静默、近期聊天延后，不回应不追发；发送只要求文案至少复核过一次（`f.revision<=reviewed`），新入站不再让旧跟进失效，无更新待办时 reviewed 水位随入站前移；生日须明确订阅，仅存月日。不确定投递记unknown且不自动重发；存储失败写 `social.pause`，人工核查后解除。
- **视觉与媒体**：辅助视觉走远程API，入站图片生成描述写入历史并参与后续上下文，原图可由 `vision_analyze` 复看。STT关闭，未来只能用远程中文转录，不启本地Whisper。共享入站上限128 MiB，不代表每用户限额。
- **图片清理**：`HOME/cache/images/` 达50张删最旧20张；每月北京时间首次空闲维护保留最新20张。忙碌或目标图片不足5分钟则延后、每分钟重试，50张是清理触发值而非硬上传限制；不删除表情包。其他媒体有上游每小时24小时过期规则，实际边界待验收。
- **表情包**：42张、140条emoji映射，QQ/微信授权私聊共用。唯一编辑表为 `doro/manifest.txt`：`id | 画面 | 适用场景 | 已映射`；多个完整emoji空格分隔，行序即优先级，同类可多对一，不能重复或互为子串。管理脚本只有两个：新图先 `rename-stickers.py --apply` 编号，补表后 `sync-stickers.py --apply` 一次推完（图片→manifest.json→映射，按这个顺序，映射会核 id）；只改映射用 `--only mapping`，只动图用 `--only images`，`--list` 只读核对、默认不带 `--apply` 就是预览。
- `send_sticker(sticker_id)` 只读 `HOME/stickers/manifest.json`，单图1 B–2 MiB，路径无空白；素材目录须在 `gateway.media_delivery_allow_dirs`。自动配图仅短回复（≤3行、≤200字、无代码块），文字后1.2秒补一张，映射侧300秒冷却，与工具共享状态。配置热加载；旧会话工具枚举未更新时才用 `/new`。
- 保持推理medium、压缩阈值64000 token；表情包场景说明每轮随schema发送，新增时保持简短。关闭聊天进度回执；`display.persona_error_voice=true` 提供人格化故障提示。

## 微信差距与待验收

- **GIF动画未解决**：QQ同图会动，微信IMAGE仅静态；文件附件打开能动，但用户明确拒绝附件替代。当前未找到公开且验证可用的原生动画方式；不重复发图试探、不擅自换接入方案，也不宣称已全部对齐。
- 微信已有2000字分块、部分短句拆气泡；文字和图片分开发送。入站引用可解析，`context_token` 仅代表回复会话关联，不证明客户端显示引用气泡。
- 共同待验收：TTS/远程STT、每用户消息/图片/搜索限流、其他媒体与日志容量、真实跨月图片清理、第二用户/第二群隔离、关心长期投递及微信会话过期、单网关自动恢复。微信另需观察入站贴纸/引用图片、输入状态和可见引用样式。

## 修改与验证

1. 先读本文件及TASK相关项，核对目标主机、固定提交、服务器工作树与配置。优先配置/扩展点；源码改动须说明适用版本与回滚方式。
2. 生产变更前受限备份配置、SQLite（用backup接口）和相关源码，目录0700、文件0600；记录目标字段、哈希和结果到该次备份目录。配置/素材按实际热加载能力处理；需要重启时先停旧网关，再经低内存启动器只启一个，验证连接、真实回复、日志和整机资源，失败回滚。
3. 回滚只恢复本次相关字段/源码，保留QQ群补丁、用户隔离、当前凭据、数据库及提醒任务；不得整份覆盖旧业务快照。要旧版本改动从远程 git 历史取，本地不留补丁副本；服务器备份在 `HOME/backups/`。
4. 隔离测试使用临时HOME和合成用户/群，不连真实提供方；需要跑 Hermes 自带测试时在生产 venv 缺 pytest 的情况下另建隔离环境。媒体变更须检查真实部署路径及平台效果，API accepted不等于手机端验收。结束后清理本次临时进程/文件，不停无关进程。
5. 使用匹配实际Shell的命令；检索优先rg，远程缺少时用grep/Python。中文文本读写显式UTF-8，勿盲目转换编码；PowerShell取行用 `Get-Content -Encoding utf8 -TotalCount END | Select-Object -Last COUNT`；Python语法检查用compile，不写字节码缓存。区分环境权限/工具缺失与代码错误。
6. 共享主机普通聊天内存目标低于900 MB、短时媒体低于1.1 GB，接近1.3 GB或持续换入须调查整机；不以整机重启作常规测试。修改后同步本文件现状及TASK待办，证据保存在对应备份/测试结果中。
