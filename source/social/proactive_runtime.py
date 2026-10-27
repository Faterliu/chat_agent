"""事件驱动主动关心：复用网关维护循环，单任务、单次发送、终态不复跑。

流水线：INTAKE → EVENT → GATE → CONTEXT → DECIDE → REVIEW → SEND → RECORD。
不新增进程、不新增网关、不调用 Agent（只有一次轻量 chat/completions）。
"""
import asyncio
from datetime import datetime, timedelta
import hashlib
import logging
from pathlib import Path
import re
import sqlite3
import time

from gateway import proactive_brain as brain
from gateway.social_runtime import BLOCKED, configured, send_text_once
from tools.proactive_store import BJ, ProactiveStore
from tools.social_store import due_for, source_key

logger = logging.getLogger(__name__)

QUIET_START, QUIET_END = 23, 8
QUIET_RESUME = (8, 30)
CONTEXT_MESSAGES = 12
MESSAGE_LIMIT = 120

TRIGGER_HINTS = re.compile(
    r"明天|后天|今晚|明早|明晚|下周|下个月|月底|月初|年底|周[一二三四五六日天]|星期[一二三四五六日天]|"
    r"礼拜[一二三四五六日天]|(?:[0-9]{1,2}|[一二三四五六七八九十]{1,3})(?:月|号|日)|"
    r"[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}|[0-9]{1,2}[:：][0-9]{2}")
EVENT_HINTS = re.compile(
    r"考试|笔试|机考|面试|复试|面谈|答辩|开题|汇报|路演|出差|出行|航班|机票|高铁|火车|比赛|决赛|"
    r"半决赛|报名|截止|ddl|deadline|开会|会议|约会|见面|复诊|复查|体检|手术|签约|入职|离职|搬家|"
    r"生日|周年|论文|期末|期中|考核|测评|培训|讲座|直播|上线|验收|交稿|提交|办证|签证|出院|住院")


def looks_like_event(text):
    """低成本规则预筛：同时出现时间词与事件词才排队，避免无谓的模型调用。"""
    if not isinstance(text, str):
        return False
    value = " ".join(text.split())
    if not 4 <= len(value) <= 500 or value.startswith("/"):
        return False
    return bool(TRIGGER_HINTS.search(value) and EVENT_HINTS.search(value))


def enabled(home):
    from hermes_cli.config import load_config_readonly
    from hermes_constants import get_hermes_home
    if Path(home).resolve() != Path(get_hermes_home()).resolve():
        return False
    social = (load_config_readonly() or {}).get("social") or {}
    if social.get("enabled") is not True:
        return False
    if (Path(home) / "social.pause").exists():
        return False
    return (social.get("proactive") or {}).get("enabled") is True


def _event_key(platform, user_id, key, summary):
    basis = (key or "").strip() or " ".join(str(summary or "").split()).lower()
    return hashlib.sha256(("%s\0%s\0%s" % (platform, user_id, basis)).encode("utf-8")).hexdigest()[:32]


def _out_of_quiet(stamp):
    """触发时刻落在 23:00–08:00 时顺延到当日/次日 08:30，避免候选因静默而白丢。"""
    local = datetime.fromtimestamp(stamp, BJ)
    if local.hour >= QUIET_START or local.hour < QUIET_END:
        target = local.replace(hour=QUIET_RESUME[0], minute=QUIET_RESUME[1], second=0, microsecond=0)
        if local.hour >= QUIET_START:
            target += timedelta(days=1)
        return target.timestamp()
    return stamp


def _event_time(when, now):
    """把抽取到的 when 还原成事件本身的时间点（仅用于记录，缺省为 None）。"""
    try:
        when = str(when or "").strip()
        if len(when) == 10:
            local = datetime.fromisoformat(when).replace(hour=20, tzinfo=BJ)
        elif len(when) >= 16:
            local = datetime.fromisoformat(when[:16]).replace(tzinfo=BJ)
        else:
            return None
        return local.timestamp()
    except (ValueError, TypeError):
        return None


def _session_rows(home, platform, user_id, chat_id):
    """只读会话库，校验归属后取该用户私聊最近若干条消息。返回 (session_id, rows) 或 None。"""
    path = Path(home) / "state.db"
    if not path.is_file():
        return None
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        row = db.execute("SELECT id FROM sessions WHERE source=? AND user_id=? AND chat_type='dm' AND chat_id=? "
                         "ORDER BY started_at DESC LIMIT 1", (platform, user_id, chat_id)).fetchone()
        if not row:
            return None
        session_id = row[0]
        owner = db.execute("SELECT source,user_id,chat_type,chat_id FROM sessions WHERE id=?",
                           (session_id,)).fetchone()
        if tuple(owner or ()) != (platform, user_id, "dm", chat_id):
            return None
        rows = db.execute("SELECT role,content FROM messages WHERE session_id=? AND role IN ('user','assistant') "
                          "ORDER BY timestamp DESC LIMIT ?", (session_id, CONTEXT_MESSAGES)).fetchall()
    finally:
        db.close()
    return session_id, list(reversed(rows))


def _memory(home, platform, user_id, chat_id):
    from hermes_constants import get_hermes_home
    from tools.gateway_user_scope import GatewayUserScope
    if Path(home).resolve() != Path(get_hermes_home()).resolve():
        return ""
    try:
        directory = GatewayUserScope(platform, user_id, "dm", chat_id).memory_dir("private")
    except Exception:
        return ""
    parts = []
    for name in ("USER.md", "MEMORY.md"):
        try:
            text = (directory / name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            parts.append(text[:800])
    return "\n".join(parts)


def _record_sent(runner, session_id, text):
    """发送成功后按现有会话机制追加一条 assistant 消息；失败不影响投递结论。"""
    if not (runner and session_id and text):
        return False
    db = getattr(runner, "_session_db", None)
    db = getattr(db, "_db", db)
    append = getattr(db, "append_message", None)
    if not append:
        return False
    append(session_id, role="assistant", content=text)
    return True


class ProactiveRuntime:
    def __init__(self, home, runner, loop):
        self.home, self.runner, self.loop = str(Path(home).resolve()), runner, loop
        self.future = None
        self.started = False

    def busy(self, platform=None, user_id=None):
        if getattr(self.runner, "_running_agents", {}):
            return True
        return bool(platform) and (self.home, platform, user_id) in BLOCKED

    def tick(self):
        if self.future and not self.future.done():
            return
        if not self.loop or self.loop.is_closed() or not enabled(self.home):
            return
        if not self.started:
            try:
                ProactiveStore(self.home).recover()
                self.started = True
            except Exception:
                logger.warning("Proactive store unavailable; tick skipped")
                return
        self.future = asyncio.run_coroutine_threadsafe(self.step(), self.loop)

    async def step(self):
        try:
            store = ProactiveStore(self.home)
            await asyncio.to_thread(store.cleanup)
            if await self.intake_step(store):
                return
            await self.deliver_step(store)
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning("Proactive tick unavailable; no automatic retry")

    # ── EVENT ──
    async def intake_step(self, store):
        row = await asyncio.to_thread(store.next_intake)
        if not row:
            return False
        # 先消费再抽取：进程崩溃也不会重新识别同一条消息。
        await asyncio.to_thread(store.close_intake, row["id"], "consumed")
        now = time.time()
        context = await asyncio.to_thread(_session_rows, self.home, row["platform"], row["user_id"], row["chat_id"])
        result = await brain.extract(row["text"], context[1] if context else [], now)
        if not result or result["action"] == "none" or not result["confident"]:
            return True
        if result["action"] == "cancel":
            # 取消按事件键匹配；键对不上时退回摘要精确匹配，绝不扩到"包含"以外。
            removed = await asyncio.to_thread(
                store.cancel, row["platform"], row["user_id"],
                _event_key(row["platform"], row["user_id"], result["key"], result["summary"]), None)
            if not removed and result["summary"]:
                await asyncio.to_thread(store.cancel, row["platform"], row["user_id"], None, result["summary"])
            return True
        try:
            trigger = due_for("event", result["when"], now)
        except (ValueError, TypeError):
            return True
        if not trigger:
            return True
        trigger = _out_of_quiet(trigger)
        expires = trigger + 12 * 3600
        await asyncio.to_thread(
            store.create, row["platform"], row["user_id"], row["chat_id"],
            context[0] if context else None,
            _event_key(row["platform"], row["user_id"], result["key"], result["summary"]),
            result["summary"] or "待跟进事件", _event_time(result["when"], now), trigger, expires)
        return True

    # ── GATE → CONTEXT → DECIDE → REVIEW → SEND → RECORD ──
    async def deliver_step(self, store):
        item = await asyncio.to_thread(store.pick)
        if not item:
            return
        task_id = item["task_id"]

        async def settle(status, reason):
            await asyncio.to_thread(store.settle, task_id, status, reason)

        from gateway.config import Platform
        adapter = (getattr(self.runner, "adapters", None) or {}).get(Platform(item["platform"]))
        if not adapter or not getattr(adapter, "is_connected", False):
            return await settle("SKIPPED", "adapter_unavailable")
        allow = getattr(adapter, "_is_dm_allowed", None)
        if not allow or not allow(item["user_id"]):
            return await settle("SKIPPED", "not_authorized")
        if self.busy(item["platform"], item["user_id"]):
            return await settle("SKIPPED", "busy")
        context = await asyncio.to_thread(_session_rows, self.home, item["platform"], item["user_id"], item["chat_id"])
        if not context:
            return await settle("SKIPPED", "session_missing")
        memory = await asyncio.to_thread(_memory, self.home, item["platform"], item["user_id"], item["chat_id"])
        decision = await brain.decide(item["event_summary"], item["trigger_at"], context[1], memory,
                                      time.time(), limit=MESSAGE_LIMIT)
        if not decision:
            return await settle("SKIPPED", "model_failed_or_invalid")
        if decision["decision"] != "SEND":
            return await settle("SKIPPED", "model_skip:" + decision["reason"])
        text = decision["message"]
        item["text"] = text
        ledger = await asyncio.to_thread(store.begin_send, item)
        if not ledger:
            return await settle("SKIPPED", "review_changed")
        try:
            result = await asyncio.wait_for(
                send_text_once(adapter, item["platform"], item["chat_id"], text), timeout=30)
        except BaseException as exc:
            await asyncio.to_thread(store.finish, task_id, ledger, "UNKNOWN", "send_exception")
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        success = bool(getattr(result, "success", False))
        status = "SENT" if success and getattr(result, "message_id", None) else ("UNKNOWN" if success else "FAILED")
        await asyncio.to_thread(store.finish, task_id, ledger, status, None)
        if status == "SENT":
            try:
                await asyncio.to_thread(_record_sent, self.runner, context[0], text)
            except Exception:
                logger.debug("Proactive history append skipped")
        logger.info("Proactive delivery finished status=%s", status)

    def stop(self):
        if self.future and not self.future.done():
            self.future.cancel()


async def intake(source, event, platform):
    """入站钩子：只做规则预筛后落库，不调模型、不阻塞回复。"""
    try:
        from hermes_constants import get_hermes_home
        home = str(get_hermes_home())
        if getattr(source, "chat_type", None) != "dm" or not getattr(source, "user_id", None):
            return
        if not configured(home) or not enabled(home):
            return
        text = getattr(event, "text", "") or ""
        if not looks_like_event(text):
            return
        key = source_key(getattr(event, "message_id", None))
        if not key:
            return
        await asyncio.to_thread(
            lambda: ProactiveStore(home).intake(platform, source.user_id, source.chat_id,
                                                key, " ".join(text.split())[:500]))
    except Exception:
        logger.warning("Proactive intake unavailable; skipped")
