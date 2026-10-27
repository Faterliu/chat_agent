# chat_agent：QQ／微信聊天机器人

基于 Hermes Agent 的轻量聊天项目，运行在共享 Ubuntu 服务器上：模型推理走远程 API，会话存 SQLite，长期记忆按用户隔离，QQ 与微信共用一个手动网关（无 systemd 自恢复，不宣称 24×7）。

## 仓库范围

Hermes 主程序（固定 v0.21.5，提交 `f97608f`）和实际运行的补丁只存在于服务器 `HERMES_HOME`（`/var/lib/hermes/.hermes`），**本仓库既不含主程序，也不含补丁**。

本仓库保存：

- 部署与运维文档、待办与差距清单；
- 人格源 `source/personas/xiaoyun.json`（真正生效的是服务器 `config.yaml` 的 `agent.personalities.xiaoyun.system_prompt`，同名 JSON 镜像不生效）；
- 少量源码模块（表情包工具、图片缓存策略、人格化错误提示、social 与事件主动关心、web-deepseek 插件）与配置片段；
- 表情包映射表 `doro/manifest.txt` 与两个维护脚本（表情包原图不入库）。

`documents/server-mirror/` 只镜像少数服务器配置文件与主机改动（`config.yaml`、`SOUL.md`、`sysctl.conf`、`fstab` 等），**不是服务器程序的完整镜像**，且可能滞后；实际状态以服务器核验为准。

## 现状（2026-10-27）

已上线：QQ／微信白名单私聊（QQ 另有群 @ 被动回复）、按用户隔离的长期记忆与会话检索、一次性提醒（30 天内、每人每平台 20 条）、轻量主动关心与生日、事件驱动的一次性主动关心（P1，仅私聊）、入站图片识别、42 张表情包与 140 条 emoji 映射、图片缓存清理（满 50 张删最旧 20 张，另每月维护）。

待验收：TTS／远程 STT、每用户消息／图片／搜索限流、其他媒体与日志容量、跨月图片清理、第二用户／第二群隔离、关心长期投递与事件关心的真实链路、微信会话过期、单网关自动恢复。

已知差距：微信端 GIF 只显示静态图（QQ 正常），目前没有公开可用的原生动画方案，不用文件附件替代。

## 目录

```
AGENTS.md                 运行现状、安全与数据隔离、维护入口、微信差距、修改与验证流程
README.md                 项目说明与更新记录（本文件）
documents/                待办、emoji 清单、微信差距、server-mirror 快照
source/personas/          人格源
source/                   部署模块、web-deepseek 插件、配置片段
scripts/                  deploy-persona-config.py / gen-emoji-list.py / sync_from_server.py
doro/                     表情包映射表、图片与映射维护脚本
```

## 文档入口

- 运行现状、操作约束与维护流程：[AGENTS.md](AGENTS.md)
- 任务与待办：[documents/TASK.md](documents/TASK.md)
- emoji 映射参考：[documents/EMOJI_LIST.md](documents/EMOJI_LIST.md)
- 微信侧差距明细：[documents/WECHAT_BACKLOG.md](documents/WECHAT_BACKLOG.md)

# 更新记录

[v1.0.4] 2026-10-27
1. 同步 P1 主动交互决策层源码到 `source/social/proactive_*`，与线上逐字节一致；记录状态机、挂载点与开关位置。
2. 现状与待办补事件主动关心：代码已上线、隔离测试 57 项通过，但部署后无真实消息，链路未验收。

[v1.0.3] 2026-10-24
1. 人格升级到 1.3.1：补回“本云”自称的使用边界，新增技术梗式比喻与对熟人拍板的示范台词、小脾气（嘴碎但不教育人）、认错腔调、临时称呼规则、L3 翻旧账限定在具体事件、自我介绍的分寸。
2. README 校正：明确仓库不含 Hermes 主程序与补丁，`documents/server-mirror/` 不是程序镜像；补上目录结构与当前已上线／待验收清单。
3. 移除历史提交中硬编码的接口密钥（该密钥需作废重建）。

[v1.0.2] 2026-10-22
1. 添加表情包映射。
2. 长对话裁剪设置。
3. 文件整理：脚本进 `scripts/`、源码镜像进 `source/`、文档与补丁备份进 `documents/`。
4. 说明合并：现状、数据边界、目录、内存、token 归入 `AGENTS.md`，本文件只留项目说明与更新记录。

[v1.0.1] 2026-10-09
1. 精简工具说明、重复关心提示及JSON返回.
2. 压缩上限改为64000 token；合成成对样本输入减少约12.94%。

[v1.0.0] 2026-10-08
1. Hermes v0.21.5，QQ／微信单网关，长期记忆按用户隔离，受限提醒和轻量主动关心已部署。


# AGENT默认不修改本文档
