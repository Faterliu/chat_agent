# 人格完整设计备份

`xiaoyun-v1.2.1-full-20260930T233626.json` 是精简前的逐字节备份，含人格化提醒规则。

SHA-256：`407b4c9699677bf626de3dce1e19bd830b84e038cc8af0577a3f4c6de8736455`。

当前人格源为 `source/personas/xiaoyun.json` v1.2.3，只保留有效注入字段和基本身份元数据。此前删除的结构化设计包括：身份细节、偏好和口癖、聊天／任务行为、关系等级、权限、社交边界、主动策略、订阅／冷却／静默时间、主动状态结构及旧导入记录。其中已写入 system_prompt 的人格文字仍保留。

v1.2.2 曾将 personality.core_traits、speech_style.general 转为 tone、style；v1.2.3 将这些字段的独有要求并入 system_prompt，tone、style 保留为空，避免重复注入。其余结构化字段目前未被导入脚本或 Hermes 读取，也不会自动执行。

以后完成相应功能适配时，再从备份挑选字段恢复。需完整恢复时，将备份复制回当前人格源；`scripts/apply-persona.py` 仍兼容旧嵌套格式。单独加回旧性格／风格列表时，须同步更新 tone／style，导入脚本优先读取这两个直接字段。历史 `normalise-persona.py` 不应直接覆盖当前精简源。

## 重复内容合并备份（2026-10-08）

`xiaoyun-v1.2.2-before-merge-20261008.json` 是合并前逐字节备份，SHA-256 `b9b5bd23d9b5164c11ba8291c39a40b0af53c12b00e1ae7ebc6aa5fba682c28c`。人格注入文本 1905→1644 字符，减少 13.7%；个人偏好、L0–L3、纠错、任务处理和提醒文案整段保留。生产回退及受限服务器备份见 documents/DEPLOYMENT_NOTES.md 的“人格重复内容合并”。
