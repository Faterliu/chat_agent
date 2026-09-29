# TASK.md

## Hermes QQ + 微信轻量多模态 Agent

### 执行目标

在一台 **2 vCPU / 2 GB RAM Ubuntu 服务器**上部署 Hermes Agent，使其作为 7×24 小时运行的 QQ + 微信多模态聊天 Agent，具备：

- 文本聊天
- 多轮 Session
- 内置轻量长期 Memory
- Vision
- STT
- 可选 TTS
- 远程 LLM API
- 自动重启和开机恢复

必须遵守 `AGENTS.md` 中的全部约束。

---

# Phase 0 — 开工前预检

## 0.1 确认当前执行环境

首先执行：

```bash
pwd
id
hostname
uname -a
command -v hermes || true
```

确认当前 Shell 是否就是目标服务器。

不得假设当前工作区已经安装 Hermes。

如果当前机器不是目标 2C2G Ubuntu 服务器：

- 停止所有系统级修改；
- 不执行 apt；
- 不创建 Swap；
- 不修改 systemd；
- 不创建 `/var/lib/hermes`；
- 不伪造执行结果。

## 0.2 检查服务器

在确认目标服务器后执行：

```bash
uname -a
lsb_release -a
free -h
df -h
nproc
```

验收：

- [ ] Ubuntu 20.04 / 22.04 / 24.04 或兼容支持环境
- [ ] 2 vCPU 可用
- [ ] 约 2 GB RAM 可用
- [ ] 建议至少 10 GB 可用磁盘
- [ ] 网络连接正常
- [ ] DNS 正常

## 0.3 建立部署记录

创建：

```text
DEPLOYMENT_NOTES.md
```

至少记录：

```text
hostname
OS
kernel
CPU
RAM
disk
swap
当前是否已安装 Hermes
```

---

# Phase 1 — 基础系统

## 1.1 更新系统

```bash
sudo apt update
sudo apt upgrade -y
```

## 1.2 安装最小依赖

```bash
sudo apt install -y \
  curl \
  wget \
  git \
  unzip \
  ffmpeg \
  sqlite3 \
  htop \
  ca-certificates
```

验收：

- [ ] `ffmpeg -version` 正常
- [ ] `sqlite3 --version` 正常
- [ ] 本阶段未安装 Chromium

---

# Phase 2 — Swap

## 2.1 创建 2 GB Swap

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

检查：

```bash
free -h
```

## 2.2 持久化 Swap

确保 `/etc/fstab` 包含：

```text
/swapfile none swap sw 0 0
```

验收：

- [ ] `free -h` 可看到 Swap
- [ ] 重启后 Swap 仍自动挂载

---

# Phase 3 — 确认版本并安装 Hermes

## 3.1 确认当前官方 Hermes 版本和安装方式

不要先执行历史文档中的安装命令。

先确认：

1. 当前官方 Hermes 仓库 / 官方文档；
2. 目标 release / tag / commit；
3. 当前版本真实安装方式；
4. 当前安装器是否真的支持跳过 Browser / Playwright；
5. 当前系统是否满足该版本依赖。

将结果写入：

```text
DEPLOYMENT_NOTES.md
```

至少记录：

```text
Hermes source/repository
release/tag/commit
installation method
browser skip support
installation date
```

## 3.2 安装 Hermes

仅在 Phase 3.1 完成后，使用刚刚确认的当前版本官方安装方式。

如果当前版本明确支持 skip-browser 选项，则使用。

如果不支持，不得自行编造参数。

## 3.3 验证 CLI

安装后执行：

```bash
hermes --version || true
hermes --help
hermes tools || true
hermes gateway --help || true
```

如果命令不存在：

- 不得猜测替代命令；
- 使用当前版本 `--help`、源码或对应版本官方文档确认。

验收：

- [ ] Hermes CLI 正常启动
- [ ] 已识别当前真实 Gateway 启动命令
- [ ] 未主动安装 Chromium / Playwright
- [ ] 未安装本地模型
- [ ] 实际 Hermes 版本已写入 `DEPLOYMENT_NOTES.md`

---

# Phase 4 — 发现当前 Hermes 能力

使用当前版本实际可用命令进行检查。

优先尝试：

```bash
hermes tools
```

记录：

- 可用 Toolset
- 实际配置文件路径
- 实际 QQ Adapter 名称
- 实际微信 Adapter 名称
- 当前 Gateway 启动命令
- 当前 Memory 配置方式
- 当前 Vision / STT / TTS 配置方式

不得仅根据旧文档直接编辑配置。

如果历史命令已变化，使用当前版本：

```text
--help
源码
同版本官方文档
```

确认。

验收：

- [ ] 已记录当前版本真实 Tool 名称
- [ ] 已确认正确配置路径
- [ ] 已确认真实 Gateway 启动命令
- [ ] 已将上述信息写入 `DEPLOYMENT_NOTES.md`

---

# Phase 5 — 配置远程 LLM

## 5.1 配置主模型

配置一个远程文本 LLM。

可选：

```text
GPT
Claude
Gemini
Qwen
DeepSeek
其他受支持远程 Provider
```

## 5.2 保护凭据

API Key 存放在：

- 环境变量；
- 或受保护的 Hermes 配置 / Secret 文件。

需要时执行：

```bash
chmod 600 <secret-file>
```

不得提交 Secret。

## 5.3 测试文本聊天

发送简单 Prompt。

验收：

- [ ] 远程 LLM 正常回复
- [ ] API Key 未写死在源码
- [ ] API Key 未出现在日志
- [ ] 未启动本地推理进程

---

# Phase 6 — 关闭执行型重工具

先确认当前版本实际 Tool 名称。

如支持：

```bash
hermes tools
```

则使用该命令检查。

关闭所有 V1 不需要的执行能力。

目标禁用：

```text
Terminal
Shell
File Tool
Browser
Playwright
Computer Use
Web Search
Code Execution
MCP
Hermes 内置 Cron
Delegation
Sub-Agent
Image Generation
ACP / IDE Integration
```

不得为了省 RAM 直接删除源码。

验收：

- [ ] Bot 不能执行 Shell
- [ ] Bot 不能使用 Browser 自动化
- [ ] Bot 不能任意读取 / 写入服务器文件
- [ ] Bot 不能执行任意 Python / Shell 代码
- [ ] MCP 关闭
- [ ] Hermes 内置 Cron Tool 关闭
- [ ] 普通聊天后没有 Chromium 进程

检查：

```bash
ps aux | grep -Ei 'chromium|chrome|playwright'
```

---

# Phase 7 — 配置 QQ

## 7.1 准备 QQ Bot 凭据

创建 / 配置当前版本所需 QQ Bot / 应用。

获取实际所需凭据，例如：

```text
AppID
ClientSecret / AppSecret
```

具体名称以当前 QQ / Hermes 文档为准。

## 7.2 配置 QQ Adapter

仅启用 QQ Adapter。

初始访问策略：

- 允许自己的测试账号
- 允许指定测试群
- 群聊在支持 / 需要时要求 @ Bot

## 7.3 测试 QQ 私聊

发送：

```text
你好
```

预期链路：

```text
QQ
→ QQ Adapter
→ Hermes Gateway
→ Session
→ LLM
→ Delivery
→ QQ
```

## 7.4 测试 QQ 群聊

发送：

```text
@机器人 你好
```

验收：

- [ ] QQ 私聊可正常回复
- [ ] QQ 群 @ 可正常回复
- [ ] 未授权用户 / 群被拒绝或忽略
- [ ] 临时断线后 Adapter 自动重连
- [ ] Gateway 重启后 QQ 自动恢复连接

---

# Phase 8 — 配置微信

## 8.1 启用 Weixin Adapter

使用当前版本 Hermes 支持的微信集成。

## 8.2 完成授权

执行当前版本要求的扫码 / 账号授权。

## 8.3 验证会话连续性

测试：

```text
微信：
你好
```

验收：

- [ ] 可以收到微信入站消息
- [ ] 可以正常发送回复
- [ ] 在支持持久化时，普通 Gateway 重启不会无意义地重复要求授权
- [ ] Context Token / 状态维护正常
- [ ] Long Poll 或当前支持的接收循环保持稳定

---

# Phase 9 — Session 隔离

Session 持久化必须开启。

## 9.1 测试同用户多轮上下文

用户 A：

```text
我叫小明。
```

然后：

```text
我叫什么？
```

预期：

```text
你叫小明。
```

## 9.2 测试用户隔离

用户 B：

```text
我叫什么？
```

除非用户 B 自己提供过，否则 Bot 不得回答 `小明`。

## 9.3 测试平台隔离

确认 QQ 与微信不会意外共享临时聊天上下文。

验收：

- [ ] 同一会话保留多轮上下文
- [ ] 不同用户不串话
- [ ] 群聊 / 私聊分离
- [ ] QQ / 微信会话身份隔离
- [ ] 在支持时，Gateway 重启后 Session 可恢复

---

# Phase 10 — 内置 Memory

暂不添加外部 Memory Provider。

使用 Hermes 内置轻量 Memory，例如：

```text
USER.md
MEMORY.md
```

或当前版本等效机制。

## 10.1 Memory 策略

允许长期保存：

- 稳定用户偏好
- 长期项目名称
- 稳定开发环境
- 长期工作约定

不得持久化：

- 密码
- API Key
- Token
- OTP
- 银行数据
- 敏感认证凭据

## 10.2 测试跨 Session 回忆

Session 1：

```text
我的服务器使用 Ubuntu。
```

启动新 Session 或清除临时上下文。

询问：

```text
我的服务器系统是什么？
```

如果该信息已被明确长期保存，预期：

```text
Ubuntu
```

验收：

- [ ] Session 与长期 Memory 可区分
- [ ] 长期 Memory 可跨 Session
- [ ] Memory 文件 / 存储可检查
- [ ] 敏感凭据不会被主动长期保存

---

# Phase 11 — Vision

启用远程 Vision。

不得安装本地 Vision 模型。

## 11.1 配置模型

优先：

```text
一个支持多模态的远程 LLM
```

备选：

```text
远程 Vision 模型
→ 图片描述
→ 主文本 LLM
```

## 11.2 配置媒体限制

设置：

- 最大图片大小
- 支持格式
- 单消息最大图片数量
- 缓存生命周期

## 11.3 测试图片

测试：

- [ ] 普通照片
- [ ] 截图
- [ ] 中文文字截图
- [ ] 源码截图
- [ ] 简单图表

验收：

- [ ] QQ 图片可理解
- [ ] 微信图片可理解
- [ ] 图片处理不会启动本地模型
- [ ] 临时图片在处理后 / 保留期后自动删除

---

# Phase 12 — STT

启用语音转文字。

优先级：

```text
平台 Transcript / ASR
→ 远程 STT fallback
→ 不使用本地 Whisper
```

## 12.1 QQ

如果 QQ 已提供 ASR / Transcript，优先直接使用。

否则调用远程 STT。

## 12.2 微信

如果微信已有 Transcript，直接使用。

否则：

```text
下载音频
→ 必要时 ffmpeg 转换
→ 远程 STT
→ 文本
→ LLM
```

## 12.3 测试中文语音

发送：

```text
你好，请告诉我我们刚才聊了什么。
```

验收：

- [ ] QQ 语音可以转换成文本
- [ ] 微信语音可以转换成文本
- [ ] 中文识别可用
- [ ] 未加载本地 Whisper / faster-whisper
- [ ] 临时输入语音自动清理

---

# Phase 13 — TTS

启用可选 TTS。

默认回复仍然是文本。

仅在用户明确要求时生成音频。

示例：

```text
用语音告诉我什么是快速排序。
```

优先：

```text
远程 / 轻量 TTS
```

不得部署重型本地 TTS。

验收：

- [ ] 可生成中文 TTS
- [ ] QQ 可接收当前支持的音频 / 音频文件格式
- [ ] 微信可接收当前支持的音频 / 音频文件格式
- [ ] 默认仍为文本回复
- [ ] 生成音频在短期保留后自动清理

---

# Phase 14 — 媒体缓存与清理

创建或确认一个有边界的媒体缓存。

建议：

```text
/var/lib/hermes/media/
```

或 Hermes 当前版本原生目录。

建议保留：

```text
图片 <= 1 小时
输入语音 <= 1 小时
TTS 音频 <= 1 小时
```

### 允许的清理机制

可以使用：

```text
systemd-tmpfiles
systemd timer
crontab
Hermes 自身非模型工具的静态启动清理逻辑
```

优先顺序：

```text
systemd-tmpfiles
→ systemd timer
→ crontab（仅作为 fallback）
```

### 明确禁止

不得为了媒体清理开启：

```text
Hermes 内置 Cron Tool
Hermes 模型可调用 Scheduled Task 能力
```

这里的目标是**主机级维护**，不是给 Agent 增加自主定时能力。

检查：

```bash
du -sh /var/lib/hermes 2>/dev/null || true
```

验收：

- [ ] 媒体目录不会无限增长
- [ ] 过期媒体自动删除
- [ ] 正在处理的媒体不会被提前删除
- [ ] Hermes 内置 Cron Tool 仍保持关闭

---

# Phase 15 — 日志

启用最小必要运维日志。

至少包括：

```text
Gateway 启停
QQ 连接 / 断开
微信连接 / 断开
LLM 错误
Vision 错误
STT 错误
TTS 错误
Session 错误
Memory 错误
未预期异常
```

不得记录 Secret。

使用以下任一方式限制日志增长：

- systemd journal retention
- logrotate
- Hermes 原生日志轮转

验收：

- [ ] 日志足够用于故障排查
- [ ] API Key / Token 未输出
- [ ] 日志增长有边界

---

# Phase 16 — systemd 服务

使用此前确认的真实 Hermes Gateway 启动命令创建 systemd 服务。

示例结构：

```ini
[Unit]
Description=Hermes QQ Weixin Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<service-user>
WorkingDirectory=<hermes-working-directory>
ExecStart=<actual-hermes-gateway-command>
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

不得直接照抄占位符路径。

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes
sudo systemctl start hermes
```

验证：

```bash
systemctl status hermes
journalctl -u hermes -f
```

验收：

- [ ] `systemctl start hermes` 正常
- [ ] `systemctl stop hermes` 正常
- [ ] `systemctl restart hermes` 正常
- [ ] 进程崩溃后自动重启
- [ ] 服务器重启后自动启动
- [ ] 只有一个活动 Gateway 实例

---

# Phase 17 — 资源验证

执行：

```bash
free -h
htop
ps aux --sort=-%mem | head -20
```

目标：

```text
空闲：尽量 < 800 MB
普通聊天：尽量 < 1.2 GB
短时媒体：尽量 < 1.5 GB
持续 > 1.7 GB：排查
```

若发现以下内容需排查：

```text
Chromium
Playwright
本地 Whisper
本地模型服务
重复 Hermes 进程
异常 Node Worker
未清理媒体
无边界日志
```

验收：

- [ ] 正常运行可稳定控制在 2 GB RAM 内
- [ ] Swap 不持续抖动
- [ ] 无异常重型后台进程

---

# Phase 18 — 安全加固

## 18.1 访问策略

配置：

- 测试阶段 QQ 白名单
- QQ 群白名单
- 微信访问策略（如支持）
- 单用户限流
- 最大文本长度
- 最大图片大小
- 最大音频大小

初始建议：

```text
10–30 次请求 / 用户 / 分钟
```

根据真实 Provider 配额调整。

## 18.2 Secret 检查

执行：

```bash
git status
git grep -nE '(API_KEY|SECRET|TOKEN|PASSWORD)' .
```

人工检查结果。

验收：

- [ ] 无 Secret 被 Commit
- [ ] 配置文件权限受限
- [ ] 未暴露任意 Shell / File / Browser / Code Execution
- [ ] 在限流和访问控制验证前未公开开放

---

# Phase 19 — 功能验收

完成以下全部测试。

## 19.1 QQ 文本

```text
QQ → Hermes → LLM → QQ
```

- [ ] 通过

## 19.2 微信文本

```text
微信 → Hermes → LLM → 微信
```

- [ ] 通过

## 19.3 多轮上下文

```text
我叫小明
→
我叫什么？
```

- [ ] 通过

## 19.4 Session 隔离

用户 A / 用户 B 不共享临时上下文。

- [ ] 通过

## 19.5 长期 Memory

稳定信息可跨新 Session 保留。

- [ ] 通过

## 19.6 QQ Vision

发送截图 / 图片并要求解释。

- [ ] 通过

## 19.7 微信 Vision

发送截图 / 图片并要求解释。

- [ ] 通过

## 19.8 QQ STT

发送中文语音。

- [ ] 通过

## 19.9 微信 STT

发送中文语音。

- [ ] 通过

## 19.10 QQ TTS

要求语音回复。

- [ ] 通过

## 19.11 微信 TTS

要求语音回复。

- [ ] 通过

---

# Phase 20 — 重启恢复测试

执行：

```bash
sudo reboot
```

恢复后验证：

- [ ] systemd 自动启动 Hermes
- [ ] QQ 自动重连
- [ ] 微信自动重连
- [ ] Session 仍可用
- [ ] 长期 Memory 仍可用
- [ ] 不需要人工启动服务
- [ ] 在支持持久化授权时，不会无意义重复登录

---

# Phase 21 — 媒体清理测试

生成 / 测试：

- 多张图片
- 多条语音输入
- 多次 TTS 输出

等待超过保留时间或手动触发主机清理机制。

验收：

- [ ] 过期图片删除
- [ ] 过期输入语音删除
- [ ] 过期 TTS 音频删除
- [ ] 媒体目录大小恢复到预期水平
- [ ] 清理机制不依赖 Hermes 内置 Cron Tool

---

# Phase 22 — 最终 V1 验证

只有以下全部满足时，V1 才算完成：

- [ ] 2C2G 服务器稳定
- [ ] QQ 持续在线
- [ ] 微信持续在线
- [ ] 文本聊天正常
- [ ] 多轮上下文正常
- [ ] Session 隔离正常
- [ ] 轻量长期 Memory 正常
- [ ] Vision 正常
- [ ] STT 正常
- [ ] 可选 TTS 正常
- [ ] 重型 AI 推理均为远程
- [ ] Chromium 未运行
- [ ] Playwright 未运行
- [ ] 本地 LLM 未运行
- [ ] 本地 Vision 模型未运行
- [ ] 本地 Whisper 未运行
- [ ] Terminal / Shell Tool 关闭
- [ ] File Tool 关闭
- [ ] Code Execution 关闭
- [ ] MCP 关闭
- [ ] Hermes 内置 Cron Tool 关闭
- [ ] Sub-Agent / Delegation 关闭
- [ ] systemd 可自动重启 Hermes
- [ ] 服务器重启后自动恢复服务
- [ ] 临时媒体自动清理
- [ ] Secret 受保护
- [ ] 日志容量受控
- [ ] 2 GB RAM 下内存使用可接受

---

# 延后工作

V1 不实现以下内容。

后续升级顺序：

```text
V2
评估外部 Memory Provider
（Mem0 / Hindsight / 其他适合 Provider）

V3
Web Search

V4
受限只读 MCP

V5
Hermes Cron / Scheduled Reminder

V6
有限 Tool Calling

V7
Browser / Computer Use
```

每个延后能力都必须：

1. 说明需求；
2. 估算内存 / 进程影响；
3. 定义访问 / 安全边界；
4. 新增专门任务；
5. 独立测试；
6. 重新执行完整 RAM 和安全验证。

---

# 交付物

完成后提供：

- [ ] 最终 Hermes 配置（Secret 已移除 / 脱敏）
- [ ] systemd Service 文件
- [ ] 环境变量 / 配置模板
- [ ] QQ 配置说明
- [ ] 微信配置说明
- [ ] 实际使用的 LLM / Vision / STT / TTS Provider
- [ ] 媒体缓存清理配置
- [ ] 运维命令
- [ ] 验收结果
- [ ] 实测空闲 RAM
- [ ] 实测普通聊天 RAM
- [ ] 已知限制
- [ ] 与 `AGENTS.md` 的任何偏差
- [ ] 完整 `DEPLOYMENT_NOTES.md`

---

# 运维命令

在真实部署后记录实际使用命令。

模板：

```bash
# 服务
sudo systemctl status hermes
sudo systemctl restart hermes
sudo systemctl stop hermes
sudo systemctl start hermes

# 日志
journalctl -u hermes -f

# 资源
free -h
htop
ps aux --sort=-%mem | head -20

# 磁盘 / 媒体
df -h
du -sh /var/lib/hermes 2>/dev/null || true

# Hermes
hermes --version || true
hermes --help
hermes tools || true
hermes gateway --help || true
```

如果当前 Hermes 版本命令不同，更新本节为真实命令。
