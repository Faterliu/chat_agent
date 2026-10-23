# chat_agent：QQ／微信聊天机器人

基于 Hermes Agent 的轻量聊天项目，运行在共享 Ubuntu 服务器上。模型推理走远程 API，会话存在 SQLite，长期记忆按用户隔离。Hermes 主程序在服务器上，本仓库只保存部署文档、补丁和辅助脚本。

一句话现状：Hermes 固定 v0.21.5，QQ／微信共用一个手动网关；用户隔离、受限提醒、主动关心与生日、图片识别、表情包与 emoji 映射已上线，TTS、媒体清理、限流和 systemd 自恢复尚未验收。

- 运行现状、操作约束、微信差距与维护流程：[AGENTS.md](AGENTS.md)
- 任务与待办：[documents/TASK.md](documents/TASK.md)
- emoji 映射参考：[documents/EMOJI_LIST.md](documents/EMOJI_LIST.md)

# 更新记录
[v1.0.0] 2026-10-08
1. Hermes v0.21.5，QQ／微信单网关，长期记忆按用户隔离，受限提醒和轻量主动关心已部署。

[v1.0.1] 2026-10-09
1. 精简工具说明、重复关心提示及JSON返回.
2. 压缩上限改为64000 token；合成成对样本输入减少约12.94%。

[v1.0.2] 2026-10-22
1. 添加表情包映射。
2. 长对话裁剪设置。
3. 文件整理：脚本进 `scripts/`、源码镜像进 `source/`、文档与补丁备份进 `documents/`。
4. 说明合并：现状、数据边界、目录、内存、token 归入 `AGENTS.md`，本文件只留项目说明与更新记录。


# AGENT默认不修改本文档
