# 聊天 token 精简补丁

## 适用范围

固定 Hermes v0.21.5，提交 `f97608f178d1ffeca59860195ab7da295f7c8e5f`，已经部署 QQ 群回复、用户隔离、两平台提醒及最终 social 补丁。

增量补丁：`hermes-v0.21.5-token.patch`，SHA-256 `e4cd9c316eb97d7f4415b7ab78f93b12a18bc4cea6e7a2e1e02040bd0b2b3888`。五个文件的修改前后哈希见 `source/token-work/manifest.json`。不能重复应用，不能用它替代既有补丁。

## 内容

- 关心静态规则集中到 social 工具说明；动态尾部保留可信标记、当前北京时间和 enabled/revision/pending。
- pending 保留原 due/expires，同时附 due_bj/expires_bj 北京时间；不修改数据库和工具返回字段，避免模型手算 Unix 时间戳。
- 精简记忆、历史检索及提醒说明；参数结构、权限和返回字段不变。
- 明确 batch 顶层仅 action/operations；clock 仅生日 HH:MM，防止把当前时间传给 batch。
- JSON 紧凑序列化，缩短提醒成功消息；读取和列表不截断。
- 工具顺序、系统提示分层和作用域缓存沿用已有实现，没有修改核心排序代码。
- 部署配置仅把 `compression.threshold_tokens` 从 256000 改为 64000；人格、模型、medium 推理及保护/摘要策略保持。

## 验证及部署门槛

`scripts/test/test_token_optimization.py` 配合官方 `scripts/run_tests.sh -j 1`：原有 208 项加 10 项新增，共 218 项通过。只使用临时 HERMES_HOME、合成用户、模拟接口，未启动第二个生产网关。

真实对照必须全部通过并满足授权次数与十万 token 上限后，才运行 `scripts/deploy-token-optimization.py`。脚本检查报告与当前补丁哈希一致、源码哈希未变、单网关且无在途聊天、未归属记忆/审批为空。密钥只在服务器使用，不进入本地记录。

部署助手复用同目录 `deploy-deepseek-endpoint.py` 中的单网关停启函数；上传两份脚本到临时维护目录。备份配置、环境、SQLite backup 快照、提醒及相关源码后，正常停止网关，应用补丁与唯一配置字段，再通过低内存启动器启动一个网关。检查失败自动回退。

## 回退

先检查当前源码与本次修改后哈希一致、没有后续改动，再正常停止单网关。只恢复本次备份 `source-before.tar.gz` 中这五个文件，或对已核实的增量补丁执行 `git apply -R --check` 后反向应用。只把当前 YAML 的 `compression.threshold_tokens` 改回 256000，保留后续配置变化。

通过 `/var/lib/hermes/start-chat-agent.sh` 启动一个网关，核验 QQ/微信连接、单实例及用户边界。不要恢复旧 .env、数据库、Cron 任务、微信凭据或人格；备份中的业务数据仅供事故调查。

## 当前状态

2026-10-09：最终218项回归及四组成对真实模型验收通过。用户授权将单次测试上限增至1024、累计18次，总预算仍十万；实际用了86,767 token。早期 clock 参数误用及两次512推理截断的记录保留于部署日志，不计作成功验收。

输入19744→17189（-12.94%），输出752→1089，缓存读17920→13568；模型调用4→4、工具调用2→2。只是合成样本，缓存收益不算输入减少，也不保证总费用/延迟同比下降。

部署备份：`/var/lib/hermes/.hermes/backups/token-optimization-20261009T032942Z/`。正常停止798937后启动单网关860930，两平台连接及真实回复已确认，64K生效；.env逐字节保持，原QQ补丁保留。启动RSS190.16 MiB、聊天后233.86 MiB；源码及配置回退仅使用本次备份，不恢复业务数据。
