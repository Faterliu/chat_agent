"""仅由可信网关内联执行器调用；注册入口本身拒绝访问。"""
import json
from tools.registry import registry


def denied(args, **kwargs):
    return json.dumps({"success": False, "error": "仅可在已核实身份的本人私聊中使用。"}, ensure_ascii=False)


SCHEMA = {
    "name": "social_manage",
    "description": (
        "管理本人私聊主动关心和公历生日订阅。正常聊天可记录用户本人明确的未来事件(event)或具体未结束的日常话题(topic)；"
        "每轮最多新增一项，禁止模糊愿望、第三方事件及健康、财务、创伤、私密关系等敏感话题。"
        "新消息后必须逐一 review 仍有效事项；信息变化用 update，完成用 complete，拒绝用 cancel；不复核则暂停发送。"
        "when 可用 today/tomorrow/day_after_tomorrow，带明确结束时间可用 tomorrow 17:00，由服务器按北京时间解析；"
        "也可用事件结束的 ISO 日期时间或 YYYY-MM-DD。不明确则省略保存候选，不发送；topic 必须省略 when。"
        "记录失败不要反复猜日期，不要改用 cronjob 或 memory 代替；Cron 只处理用户明确要求的提醒。"
        "topic 默认 24 小时后，事件结束 2 小时后或次日 18 点；text 是按当前人格提前写好的最终关心正文，后台不调用模型。"
        "用户说不要主动关心时 settings enabled=false；新用户须同意后开启。生日必须用户明确确认，confirmed=true；"
        "month/day 为公历月日，不存出生年，subject 是订阅对象的简短称呼，通知只发订阅本人。生日 text 最多160字。默认 09:00 北京时间，允许08:00–22:59；"
        "2 月 29 日非闰年按 3 月 1 日并告知用户。禁用主动关心不影响生日和 cronjob 明确提醒。"
    ),
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": ["record", "review", "update", "complete", "cancel", "list", "settings", "birthday_add", "birthday_remove"]},
            "id": {"type": "string"}, "kind": {"type": "string", "enum": ["event", "topic"]},
            "summary": {"type": "string", "maxLength": 180}, "text": {"type": "string", "maxLength": 600},
            "when": {"type": "string"}, "enabled": {"type": "boolean"},
            "subject": {"type": "string", "maxLength": 40}, "month": {"type": "integer", "minimum": 1, "maximum": 12},
            "day": {"type": "integer", "minimum": 1, "maximum": 31}, "clock": {"type": "string"}, "confirmed": {"type": "boolean"},
        }, "required": ["action"],
    },
}
registry.register(name="social_manage", toolset="social", schema=SCHEMA, handler=denied,
                  description="本人私聊主动关心与生日订阅", emoji="🌱")
