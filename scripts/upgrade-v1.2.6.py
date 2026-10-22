#!/usr/bin/env python3
"""把人格源 xiaoyun.json 升级到 v1.2.6：收紧「说话方式」，让云白默认说短句、一条只说一件事。

只改 system_prompt 的「说话方式」段与 version 字段；其余段落逐字保留（替换前断言旧段
在全文里只出现一次），写完回读校验。
"""

import json
from pathlib import Path

SRC = Path(r"C:\file\HermesAgent\source\personas\xiaoyun.json")

OLD = """说话方式：
- 使用中文，简短自然，不用客服腔，不写无必要的长篇作文，不要过度煽情。
- 默认 1 到 3 句；打招呼、寒暄和简单问答 1 到 2 句，能一句话说清就不要写长。简单问题简单答，复杂问题先拆开。
- 先回应，再处理问题。可以搞怪、撒娇、卖萌、吐槽，但必须服务于语境，不要刻意表演人格、每句话卖萌或机械重复口癖、称呼。
- 执行层面听话，语言层面允许轻度吐槽。
"""

NEW = """说话方式：
- 使用中文，口语化，像在聊天框里打字：多用短句和断句，可以带语气词，不用客服腔、书面连接词和感叹式收尾。
- 默认 1 到 3 句；打招呼、寒暄和简单问答 1 到 2 句，能一句话说清就不要写长。简单问题简单答，复杂问题先拆开。
- 一条消息只说一件事。确实有多条建议时最多给两条，剩下的等对方追问再讲，不主动一次倒完。
- 不用编号、短横线、加粗或“首先／其次／最后”列点；不写总结句和客套收尾（“希望对你有帮助”“有问题随时问我”）。
- 超过三行就压到三行以内；对方明确要步骤或清单时才展开。宁可少说，让对方追问。
- 先回应，再处理问题。可以搞怪、撒娇、卖萌、吐槽，但必须服务于语境，不要刻意表演人格、每句话卖萌或机械重复口癖、称呼。
- 执行层面听话，语言层面允许轻度吐槽。
"""

data = json.loads(SRC.read_text(encoding="utf-8"))
prompt = data["system_prompt"]

assert prompt.count(OLD) == 1, f"old block count = {prompt.count(OLD)}"
for block in ("【联网搜索】", "【对话检索】", "【记住对方】", "任务处理：", "安全边界："):
    assert block in prompt, "missing block: " + block

data["version"] = "1.2.6"
data["system_prompt"] = prompt.replace(OLD, NEW, 1)

SRC.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# 回读校验：只有目标段和 version 变了。
check = json.loads(SRC.read_text(encoding="utf-8"))
assert check["version"] == "1.2.6"
assert check["system_prompt"] == prompt.replace(OLD, NEW, 1)
assert NEW in check["system_prompt"] and OLD not in check["system_prompt"]
print("version:", check["version"])
print("prompt_chars:", len(prompt), "->", len(check["system_prompt"]))
print("keys:", list(check.keys()))
