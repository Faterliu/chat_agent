# AGENTS.md

## 项目

**Hermes QQ + 微信轻量多模态 Agent**

本项目用于在一台 **2 vCPU / 2 GB RAM 的 Ubuntu 服务器**上部署 Hermes Agent，并构建一个轻量、持久化、多模态的聊天 Agent。

第一版生产范围严格限定为：

- QQ 消息接入
- 微信消息接入
- 文本聊天
- 多轮会话
- 轻量长期记忆
- Vision
- STT
- 可选 TTS
- 远程 LLM / 多模态 API
- 通过 systemd 实现 7×24 小时运行

V1 **不是**一个通用自主 Agent。

---

## 1. 主要目标

构建一个稳定的 QQ + 微信 AI 聊天 Agent，使其能够：

1. 接收文本、图片和语音消息。
2. 按用户 / 会话维持独立的上下文。
3. 保存经过选择的长期用户信息 / 项目信息。
4. 使用远程 LLM、Vision、STT 和 TTS Provider。
5. 返回文本以及可选的语音回复。
6. 在进程崩溃和服务器重启后恢复运行。
7. 在 2C2G 服务器的现实资源限制内稳定运行。

---

## 2. 架构

目标架构：

```text
                     QQ / 微信
                         │
             ┌───────────┴───────────┐
             │                       │
        QQ Adapter              Weixin Adapter
             │                       │
             └───────────┬───────────┘
                         │
                   Hermes Gateway
                         │
                   Session Store
                      SQLite
                         │
                 Built-in Memory
                USER.md / MEMORY.md
                         │
          ┌──────────────┼──────────────┐
          │              │              │
        Text           Vision          STT
          │              │              │
          └──────────────┼──────────────┘
                         │
                    Remote LLM
                         │
                  ┌──────┴──────┐
                  │             │
                Text           TTS
                  │             │
                  └──────┬──────┘
                         │
                    QQ / 微信
```

服务器负责：

- 编排
- Session
- Memory
- 媒体转发
- API 请求

重型 AI 推理必须放在远程服务完成。

---

## 3. 硬性资源约束

默认环境：

```text
CPU: 2 vCPU
RAM: 2 GB
Swap: 推荐 2 GB
OS: Ubuntu 20.04 / 22.04 / 24.04
```

实现必须以低空闲内存占用为目标。

### 除非任务明确要求，否则不得引入重型常驻服务。

避免：

- Chromium
- Playwright
- 本地 LLM 推理
- 本地 Vision 模型
- 本地 Whisper / faster-whisper
- PostgreSQL
- Redis
- 本地向量数据库
- 多个常驻 Worker
- 除非选定通道 / Provider 强制要求，否则不增加额外 Node.js 常驻服务

---

## 4. V1 允许组件

以下组件允许并预期使用：

- Hermes Agent
- Hermes Gateway
- QQ Adapter
- Weixin Adapter
- SQLite
- 内置 Session 持久化
- 内置轻量 Memory
- ffmpeg
- systemd
- 远程 LLM API
- 远程 Vision API / 模型
- 远程 STT API
- 远程或轻量网络 TTS Provider
- 有边界的媒体缓存
- 最小化日志

---

## 5. V1 禁用组件

除非 `TASK.md` 明确改变范围，否则以下能力必须保持关闭：

```text
Browser Tool
Chromium
Playwright
Computer Use
Terminal Tool
Shell Tool
File Tool
Code Execution
MCP
Web Search
Hermes 内置 Cron Tool
Sub-Agent
Delegation
Image Generation
ACP / IDE Integration
Local LLM
Local Vision Model
Local Whisper
```

不要因为 Hermes 支持这些能力就默认启用。

### Cron 边界

这里禁用的是：

```text
Hermes 内置 Cron / Scheduled Task Tool
模型可调用的定时调度能力
```

以下主机级运维机制允许使用：

```text
systemd timer
systemd-tmpfiles
crontab
```

它们只能用于：

- 媒体缓存清理
- 日志轮转
- 轻量主机维护

不得通过这些机制给模型提供新的自主调度权限。

---

## 6. 安全边界

该 Agent 是**聊天 Agent**，不是服务器管理 Agent。

不得向用户暴露任意服务器执行能力。

### 必须遵守的安全规则

- 不向用户暴露 shell。
- 不向用户暴露 sudo。
- 不向用户暴露任意文件读写工具。
- 不启用浏览器自动化。
- 不启用任意 Python / 代码执行。
- V1 不启用 MCP。
- API Key 不得提交到 Git。
- Secret 必须存放在受保护的环境变量 / 配置文件中。
- Secret 文件建议使用 `chmod 600`。
- 日志不得输出完整 API Key、Access Token、Refresh Token、密码或授权 Cookie。

---

## 7. 消息平台范围

仅启用：

```text
QQ
微信
```

V1 不启用 Telegram、Discord、Slack、飞书、钉钉、WhatsApp 或其他 Adapter。

不要为了节省 RAM 而删除其他平台源码。

未加载的源码不会显著占用运行时内存。

优先采用：

```text
不配置
不加载
不启动
```

而不是删除源码。

---

## 8. QQ 要求

QQ 必须使用当前安装版本中 Hermes 支持的 QQ Adapter / 官方 QQ Bot 集成方式。

要求：

- 支持私聊
- 在可用时支持群聊 @
- 明确访问策略
- 初始测试阶段使用用户 / 群白名单
- 临时断线后自动重连
- 进程重启后自动恢复连接

在限流和访问控制验证完成前，不得直接公开开放 Bot。

---

## 9. 微信要求

微信必须使用当前版本 Hermes 支持的 Weixin Adapter。

要求：

- 按当前版本要求完成扫码 / 账号授权
- 使用当前支持的入站机制
- 在支持时持久化登录 / 授权状态
- 在 Adapter 要求时正确维护 Context Token
- Gateway 重启后自动恢复

正常服务重启不应要求每次重新人工授权。

---

## 10. Session 要求

Session 必须保留。

Session 必须按来源和会话身份隔离。

至少避免以下场景的上下文泄漏：

- QQ 用户 A
- QQ 用户 B
- QQ 私聊
- QQ 群聊
- 微信用户 A
- 微信用户 B
- QQ 与微信

使用 Hermes 当前版本支持的最轻量持久化方式，优先 SQLite。

### Session 不等于长期 Memory

Session 负责当前对话上下文。

长期 Memory 负责跨 Session 的稳定信息。

---

## 11. Memory 要求

V1 优先使用 Hermes 内置轻量 Memory。

建议从以下机制开始：

```text
USER.md
MEMORY.md
Hermes 内置 Memory 行为
```

在确认内置 Memory 不够用之前，不增加外部 Memory Provider。

适合长期保存：

- 稳定用户偏好
- 长期项目名称
- 稳定技术环境
- 长期工作约定
- 非敏感的持久上下文

不得主动保存：

- 密码
- API Key
- Refresh Token
- OTP
- 银行信息
- 身份证件数据
- 其他认证凭据

---

## 12. Vision 要求

Vision 启用。

重型图像推理必须使用远程服务。

推荐链路：

```text
QQ / 微信图片
      ↓
Adapter / 媒体下载
      ↓
临时本地文件
      ↓
远程多模态模型
      ↓
响应
      ↓
清理临时媒体
```

不得在该服务器上运行本地 Vision 模型。

需要对以下内容设置合理限制：

- 图片大小
- 图片数量
- 临时存储时长

临时图片必须自动清理。

---

## 13. STT 要求

STT 启用。

优先级：

1. 如果平台已经提供 Transcript / ASR，优先直接使用。
2. 否则使用远程 STT。
3. 仅在格式转换确有需要时使用 ffmpeg。

V1 不运行本地 Whisper / faster-whisper。

输入语音视为临时数据，处理后必须清理。

---

## 14. TTS 要求

TTS 作为**可选响应模式**启用。

默认仍应返回文本。

仅在以下情况下生成 TTS：

- 用户明确要求语音回复；
- 或未来有明确配置的 UX 规则要求。

优先使用远程 / 轻量网络 TTS。

不得运行重型本地 TTS 模型。

生成的 TTS 音频在发送后或短期保留后必须删除。

---

## 15. 媒体缓存策略

Vision / STT / TTS 需要有边界的临时媒体存储。

建议路径：

```text
/var/lib/hermes/media/
```

或 Hermes 当前版本支持的临时缓存目录。

建议保留时间：

```text
图片：<= 1 小时
输入语音：<= 1 小时
生成语音：<= 1 小时
```

必须防止媒体文件无限增长。

需要提供自动清理机制。

允许使用：

```text
systemd timer
systemd-tmpfiles
crontab
```

但不得为了媒体清理启用 Hermes 内置 Cron Tool。

---

## 16. LLM 要求

所有主要推理必须走远程 API。

可选示例：

- GPT
- Claude
- Gemini
- Qwen
- DeepSeek
- 其他兼容远程模型

主模型必须满足文本对话需求。

Vision：

- 优先选择原生支持图片输入的主模型；
- 或配置独立远程 Vision 模型。

不得在未验证 Provider 能力的情况下假设某模型支持某项能力。

---

## 17. 工具配置原则

修改 Hermes Tool 配置前，必须检查当前安装版本。

使用类似命令：

```bash
hermes --help
hermes tools
hermes gateway --help
```

不要盲目复制旧版本文档中的 Toolset 名称。

Hermes 迭代快，当前安装版本应作为事实来源。

---

## 18. 依赖策略

只安装 V1 当前范围真正需要的依赖。

基础依赖可包括：

```text
curl
wget
git
unzip
ffmpeg
sqlite3
htop
ca-certificates
```

不安装 Chromium / Playwright。

不下载模型权重。

不要为了方便默认引入 Docker，除非有明确运维收益且资源开销可接受。

---

## 19. 进程管理

Hermes Gateway 必须通过 systemd 运行。

要求：

```text
开机启动
异常自动重启
较短重启延迟
日志可查看
只能存在一个活动 Gateway 实例
```

推荐：

```ini
Restart=always
RestartSec=5
```

不得运行重复 Hermes Gateway 实例。

---

## 20. 日志

至少记录：

- Hermes 启动 / 停止
- QQ 连接状态
- 微信连接状态
- LLM Provider 错误
- Vision 错误
- STT 错误
- TTS 错误
- Session 错误
- Memory 错误
- 未预期异常

不得记录 Secret。

日志必须轮转或保持容量可控。

---

## 21. 资源目标

期望运行指标：

```text
空闲：尽量 < 800 MB RAM
普通聊天：尽量 < 1.2 GB RAM
短时媒体处理：尽量 < 1.5 GB RAM
持续 > 1.7 GB RAM：需要排查
```

这些是工程目标，不是绝对保证。

如果内存过高，优先排查：

- 意外运行 Chromium
- 意外运行本地 Whisper
- 重复 Gateway 进程
- 不需要的 Node Worker
- 未清理媒体
- 日志无限增长
- 过重的 Memory Provider
- 失控重试

---

## 22. Swap

建议配置 2 GB Swap 以提高稳定性。

Swap 不能替代修复内存泄漏。

正常聊天期间，系统应主要依赖物理内存稳定运行。

---

## 23. 限流

公开使用前，必须配置或实现：

- 单用户限流
- 最大文本长度
- 最大图片大小
- 最大音频大小
- 必要时群白名单
- 测试阶段用户白名单

初始建议：

```text
每用户每分钟 10–30 次请求
```

根据真实 Provider 配额和使用情况调整。

---

## 24. Agent 开发规则

修改本项目时：

1. 完整阅读 `AGENTS.md`。
2. 阅读 `TASK.md`。
3. 不得静默扩展项目范围。
4. 未有明确任务要求时，不得开启已禁用的 Hermes Tool。
5. 优先修改配置，而不是侵入式修改 Hermes Core。
6. 优先使用 Hermes Plugin / Adapter 扩展点，而不是 Fork 核心。
7. 系统必须保持适合 2C2G。
8. 编辑配置前必须确认当前安装版本真实 CLI / Tool 名称。
9. 保持 systemd 兼容。
10. 不得在 Diff、日志、示例输出或 Commit 中泄露 Secret。
11. 每个阶段完成后执行对应验证。
12. 未解决问题写入 `TASK.md` / `DEPLOYMENT_NOTES.md`，不得隐藏。

---

## 25. 当前仓库状态 / 执行上下文

当前工作区可能仅包含：

```text
AGENTS.md
TASK.md
```

不得假设：

- Hermes 已安装
- Hermes 配置已存在
- systemd 已配置
- QQ Adapter 已配置
- 微信 Adapter 已配置
- 当前 Shell 就是目标 2C2G Ubuntu 服务器

执行任何安装或系统修改前，必须先确认当前执行环境。

至少执行：

```bash
pwd
id
hostname
uname -a
command -v hermes || true
```

只有在确认当前机器就是目标服务器后，才能继续执行：

```text
apt 安装
Swap 配置
Hermes 安装
/var/lib 下目录创建
systemd 修改
```

如果当前环境不是目标服务器，不得伪造执行结果。

---

## 26. Hermes 版本发现与安装原则

Hermes 迭代速度快。

安装前必须：

1. 确认当前官方仓库 / 官方文档。
2. 确认目标 release / tag / commit。
3. 确认当前版本实际安装方式。
4. 确认是否真的支持浏览器跳过参数。
5. 将以上信息记录到 `DEPLOYMENT_NOTES.md`。

不得直接复制旧文档中的安装命令并假设仍然有效。

安装后必须读取实际 CLI：

```bash
hermes --version || true
hermes --help
hermes tools || true
hermes gateway --help || true
```

如果某条命令不存在：

- 不得猜测替代命令；
- 必须通过当前版本 `--help`、源码或对应版本官方文档确认。

---

## 27. DEPLOYMENT_NOTES.md 要求

真实部署开始后创建：

```text
DEPLOYMENT_NOTES.md
```

持续记录：

- 服务器基线
- OS 版本
- CPU / RAM / Swap
- Hermes 实际版本
- release / tag / commit
- 实际安装方式
- 实际 CLI
- 实际配置路径
- QQ Adapter 名称
- 微信 Adapter 名称
- 实际 Gateway 启动命令
- LLM / Vision / STT / TTS Provider
- systemd 服务名
- 与本任务文档的任何偏差
- 已知问题

该文件用于后续升级和复现部署。

---

## 28. 变更策略

如果未来需要：

```text
MCP
Hermes Cron
Web Search
Browser
Terminal
Sub-Agent
External Memory Provider
```

每次只新增一种能力。

每次新增必须：

1. 说明必要性；
2. 评估运行时 / 资源影响；
3. 定义安全边界；
4. 在 `TASK.md` 中添加任务；
5. 独立测试；
6. 重新检查内存占用。

---

## 29. V1 定义

项目完成后应表现为：

```text
轻量
持久
多模态
QQ + 微信
AI Chat Agent
```

V1 不得演化为通用自主服务器 Agent。
