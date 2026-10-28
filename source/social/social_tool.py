"""仅由可信网关内联执行器调用；注册入口本身拒绝访问。"""
import json
from tools.registry import registry


def denied(args, **kwargs):
    return json.dumps({"success": False, "error": "仅可在已核实身份的本人私聊中使用。"}, ensure_ascii=False, separators=(",", ":"))


SCHEMA = {
    "name": "social_manage",
    "description": (
        "本人私聊主动关心与公历生日。可信状态提供当前北京时间、enabled、revision、pending；相对日期以当前时间为准，不沿用历史日期。每轮依据真实消息复核所有 pending：仍有效 review、变化 update、结束 complete、拒绝 cancel；不复核暂停发送。pending 的 due_bj/expires_bj 是北京时间，调度由服务端负责；review 只传 id，无需换算时间戳或重算问候时间。优先一次 batch 完成全部复核及最多一项新增；直接用 pending，无需先 list，成功后不再查询；无维护事项不调用。enabled=true 可从自然聊天记录本人具体未来事件 event 或未结束日常话题 topic，无需刻意设置提醒；禁止模糊愿望、第三方事件、健康/财务/创伤/私密关系。事件若已被事件通道登记，会返回 deduplicated，视为已处理即可，不必重试或换路径。普通候选静默维护，只自然接话，不宣告记住了、记下来了、记录了、加入跟进、会提醒，不展示存储/调度、问候时间、工具参数、后台变化或历史测试故障。显式提醒、生日订阅或管理查询才确认。list 仅明确查询：默认 followups，生日 birthdays，全部 all；不检查无关生日。when 支持 today/tomorrow/day_after_tomorrow，可加结束时间 HH:MM（tomorrow 17:00），或结束时间 ISO/YYYY-MM-DD。日期不明省略 when 仅存 event 候选不发送；topic 省略 when。事件结束2小时后或次日18点，topic 24小时后。text 是当前人格的最终正文，后台不调模型，不假装知道结果、不强求回复。失败不反复猜日期，不以 cronjob/memory 代替；Cron 仅显式提醒。拒绝关心立即 settings enabled=false，新用户同意后开启；关闭不影响生日/Cron。生日须明确确认 confirmed=true；subject 简称，month/day 公历月日，不存出生年，只通知订阅本人；text≤160字，默认北京时间09:00，可选08:00–22:59；非闰年2月29日按3月1日并告知。"
    ),
    "parameters": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "action": {"type": "string", "enum": ["batch", "record", "review", "update", "complete", "cancel", "list", "settings", "birthday_add", "birthday_remove"]},
            "operations": {"description": "batch 顶层仅 action、operations；其他参数放在各操作内，勿带 clock。", "type": "array", "minItems": 1, "maxItems": 6, "items": {
                "type": "object", "additionalProperties": False, "required": ["action"], "properties": {
                    "action": {"type": "string", "enum": ["record", "review", "update", "complete", "cancel"]},
                    "id": {"type": "string"}, "kind": {"type": "string", "enum": ["event", "topic"]},
                    "summary": {"type": "string", "maxLength": 180}, "text": {"type": "string", "maxLength": 600},
                    "when": {"type": "string"},
                }}},
            "id": {"type": "string"}, "kind": {"type": "string", "enum": ["event", "topic"]},
            "view": {"type":"string", "enum":["followups","birthdays","all"]},
            "summary": {"type": "string", "maxLength": 180}, "text": {"type": "string", "maxLength": 600},
            "when": {"type": "string"}, "enabled": {"type": "boolean"},
            "subject": {"type": "string", "maxLength": 40}, "month": {"type": "integer", "minimum": 1, "maximum": 12},
            "day": {"type": "integer", "minimum": 1, "maximum": 31}, "clock": {"type": "string", "description": "仅 birthday_add 的北京时间 HH:MM，默认09:00；不是服务器当前时间。"}, "confirmed": {"type": "boolean"},
        }, "required": ["action"],
    },
}
registry.register(name="social_manage", toolset="social", schema=SCHEMA, handler=denied,
                  description="本人私聊主动关心与生日订阅", emoji="🌱")
