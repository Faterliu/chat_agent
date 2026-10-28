"""事件抽取与主动关心决策：单次直连 /chat/completions，不重试、不重放。

约定：任何网络失败、非 200、JSON 不合法或字段不合格都返回 None，调用方据此终结本次机会，
绝不再调用一次模型（P1 One-shot 要求）。
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import logging
import os
import re

logger = logging.getLogger(__name__)
BJ = timezone(timedelta(hours=8))

DEFAULT_TIMEOUT = 25.0
MAX_CHARS = 120

EXTRACT_SYSTEM = (
    "你是信息抽取器，只输出 JSON，不解释。判断用户最新一条消息是否包含「用户本人未来会发生、"
    "且时间可确定」的具体事件（考试、面试、出行、比赛、会议、复诊、截止日期等）。规则：\n"
    "1. 只算用户本人的事；转述别人的事（我妈明天手术、我朋友面试）不算。\n"
    "2. 时间必须能从消息或最近对话里确定（明天、下周三、10月25日、明晚7点）。"
    "“以后”“最近”“过几天”“有空”都算不明确。\n"
    "3. 用户明确说已取消、已改期、不想被问这件事时，用 action=\"cancel\" 并给出对应 key。\n"
    "4. 只输出：{\"action\":\"create|cancel|none\",\"key\":\"事件-日期\",\"summary\":\"不超过30字\","
    "\"when\":\"YYYY-MM-DD 或 YYYY-MM-DDTHH:MM\",\"confident\":true|false}\n"
    "   key 是稳定的中文短标识，例如 面试-2026-10-25；同一件事再次提到必须给出完全相同的 key。\n"
    "   when 写事件开始时刻：知道几点开始就写 YYYY-MM-DDTHH:MM（24 小时制），只知道日期就写 YYYY-MM-DD；"
    "系统会在开始后留缓冲再联系。\n"
    "   summary 必须保留原话里的日期线索（如“后天下午三点开会”），不要写成“下午三点开会”。\n"
    "5. 任何不确定都输出 action=\"none\"。"
)

DECIDE_SYSTEM = (
    "你是“小云”（本云），正在给一位熟悉的朋友发一条主动关心的私聊消息。只输出 JSON，不解释。\n"
    "语气：口语、短、具体，可以带一点自嘲或技术比喻；不端着、不客服腔、不说“作为AI”。\n"
    "硬规则：\n"
    "1. 只发一条短文本，不超过 60 字，单段，不用列表、不加链接、不提表情包。\n"
    "2. 不编造事件结果，不假装知道对方现在如何；只按常识问一句，或说一句轻的。\n"
    "3. 不追问、不施压，不用“你怎么不回我”“我一直在等”这类话。\n"
    "4. 不提“我记录过”“系统提醒”“后台”“任务”之类；要像自然想起。\n"
    "5. 如果最近对话已经聊过这件事的结果、或对方明确不想被打扰，输出 decision=\"SKIP\"。\n"
    "输出：{\"decision\":\"SEND|SKIP\",\"reason\":\"简短原因\",\"message\":\"正文\"}；SKIP 时 message 为空字符串。"
)


def _cfg():
    try:
        from hermes_cli.config import load_config_readonly
        return load_config_readonly() or {}
    except Exception:
        return {}


def _home():
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or ".")


def _dotenv_value(name):
    try:
        for line in (_home() / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def api_key(cfg, provider):
    prov = (cfg.get("providers") or {}).get(provider) or {}
    names = [((cfg.get("social") or {}).get("proactive") or {}).get("key_env"),
             prov.get("key_env"), prov.get("api_key_env")]
    names.append(provider.upper().replace("-", "_") + "_API_KEY")
    for name in names:
        if not name or not isinstance(name, str):
            continue
        value = os.environ.get(name) or _dotenv_value(name)
        if value:
            return value
    return ""


def route(cfg=None):
    """(url, model, key, timeout) —— 复用与主对话相同的远程模型与凭据。"""
    cfg = _cfg() if cfg is None else cfg
    model_cfg = cfg.get("model") or {}
    prov = ((cfg.get("social") or {}).get("proactive") or {})
    provider = prov.get("provider") or model_cfg.get("provider") or ""
    model = prov.get("model") or model_cfg.get("default") or ""
    base = prov.get("base_url") or model_cfg.get("base_url") or ""
    if not base and provider:
        base = "https://api.%s.com/v1" % provider
    if not (base and model):
        return None
    return (base.rstrip("/") + "/chat/completions", model, api_key(cfg, provider or ""),
            float(prov.get("timeout") or DEFAULT_TIMEOUT))


async def post_json(payload, url, key, timeout):
    """单次 POST；模块级函数，便于隔离测试替换。"""
    import httpx
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.warning("Proactive model HTTP %s", response.status_code)
            return None
        return response.json()


def parse_content(body):
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    return content if isinstance(content, str) else None


def parse_json(text):
    if not isinstance(text, str):
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def clean_message(text, limit=MAX_CHARS):
    """只接受一条纯文本短句：带链接、过长或为空一律判为不合法（不静默改写内容）。"""
    if not isinstance(text, str):
        return ""
    value = " ".join(str(text).split())
    if re.search(r"https?://|www\.", value, re.IGNORECASE):
        return ""
    if not value or len(value) > limit:
        return ""
    return value


async def _chat(system, user, max_tokens, temperature=0.3):
    target = route()
    if not target:
        return None
    url, model, key, timeout = target
    body = await post_json({"model": model, "stream": False, "temperature": temperature,
                            "max_tokens": max_tokens,
                            "messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": user}]}, url, key, timeout)
    return parse_json(parse_content(body))


def _clock(now):
    return datetime.fromtimestamp(now, BJ).isoformat()


def _history(recent):
    lines = []
    for role, content in recent or ():
        who = "用户" if role == "user" else "小云"
        text = " ".join(str(content or "").split())
        if text:
            lines.append("%s：%s" % (who, text[:200]))
    return "\n".join(lines[-12:])


async def extract(text, recent, now):
    """返回 {'action','key','summary','when','confident'} 或 None。"""
    payload = ("服务器当前北京时间=%s\n最近对话：\n%s\n用户最新消息：\n%s\n只输出 JSON。"
               % (_clock(now), _history(recent) or "（无）", " ".join(str(text or "").split())[:600]))
    value = await _chat(EXTRACT_SYSTEM, payload, max_tokens=400, temperature=0.1)
    if not value:
        return None
    action = value.get("action")
    if action not in ("create", "cancel", "none"):
        return None
    key = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff:\-]", "", str(value.get("key") or ""))[:60]
    return {"action": action, "key": key,
            "summary": " ".join(str(value.get("summary") or "").split())[:180],
            "when": str(value.get("when") or "").strip()[:19],
            "confident": value.get("confident") is True}


async def decide(summary, trigger_at, recent, memory, now, last_inbound=None, limit=MAX_CHARS):
    """返回 {'decision','reason','message'} 或 None。"""
    minutes = int(max(0, now - last_inbound) // 60) if last_inbound else None
    payload = ("服务器当前北京时间=%s\n计划关心的真实事件：%s\n该事件触发时间：%s\n距用户上次说话：%s\n"
               "长期记忆摘要：\n%s\n最近对话：\n%s\n只输出 JSON。"
               % (_clock(now), summary, _clock(trigger_at),
                  ("%d 分钟前" % minutes) if minutes is not None else "未知",
                  (memory or "（无）")[:1200], _history(recent) or "（无）"))
    value = await _chat(DECIDE_SYSTEM, payload, max_tokens=400)
    if not value:
        return None
    decision = str(value.get("decision") or "").upper()
    if decision not in ("SEND", "SKIP"):
        return None
    reason = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff\-]", "", str(value.get("reason") or ""))[:40] or "model"
    if decision == "SKIP":
        return {"decision": "SKIP", "reason": reason, "message": ""}
    message = clean_message(value.get("message"), limit)
    if not message:
        return None
    return {"decision": "SEND", "reason": reason, "message": message}
