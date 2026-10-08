"""为共享小云人格增加提醒文案规则；只修改一个配置字段。"""

import os
from pathlib import Path
import sys
import tempfile

import yaml

HOME = Path("/var/lib/hermes/.hermes")
RULE = (
    "【定时提醒文案】\n"
    "创建提醒时，cronjob_manage 的 prompt 是到点直接发送的最终文字。"
    "按当前人格写成简短自然的提醒，可适度关心或轻松调侃，让用户感觉是小云在提醒。"
    "保留用户指定的事项、对象和必要时间信息，不编造细节，不改变原意；"
    "从提醒触发时的角度措辞，不写成创建确认或给后台模型的指令。"
    "用户明确要求原样发送或正式简洁时，优先遵循其要求。"
    "name 保持简短事项标题。仅在工具返回成功后确认提醒已创建。"
    "到点按已保存正文发送，不会再次调用模型生成文案。"
)


def main():
    path = HOME / "config.yaml"
    original = yaml.safe_load(path.read_text(encoding="utf-8"))
    if original.get("display", {}).get("personality") != "xiaoyun":
        raise RuntimeError("当前不是小云人格，不自动修改其他人格")
    entry = original["agent"]["personalities"]["xiaoyun"]
    before = entry["system_prompt"]
    if not isinstance(before, str) or not before.strip():
        raise RuntimeError("缺少原有人格提示词")
    if "【定时提醒文案】" in before:
        raise RuntimeError("提醒文案规则已配置，不重复应用")
    entry["system_prompt"] = before.rstrip() + "\n\n" + RULE
    text = yaml.safe_dump(original, allow_unicode=True, sort_keys=False, width=10000)
    checked = yaml.safe_load(text)
    if checked != original:
        raise RuntimeError("配置序列化校验失败")
    # 排除目标字段后，所有配置语义必须与修改前完全相同。
    checked["agent"]["personalities"]["xiaoyun"]["system_prompt"] = before
    if checked != yaml.safe_load(path.read_text(encoding="utf-8")):
        raise RuntimeError("发现非目标配置变化")
    if sys.argv[1:] == ["--check"]:
        print("共享人格提醒文案规则可应用，其他配置语义不变")
        return
    if sys.argv[1:]:
        raise RuntimeError("未知参数")
    mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(dir=HOME, prefix=".reminder-persona-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print("已更新共享小云人格的提醒文案规则")


if __name__ == "__main__":
    main()
