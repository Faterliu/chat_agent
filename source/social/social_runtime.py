"""复用网关维护循环，单个投递任务，不启动模型或额外服务。"""
import asyncio
import json
import logging
from pathlib import Path
import sqlite3
import time
import uuid

from tools.social_store import SocialStore, BJ
from datetime import datetime

logger = logging.getLogger(__name__)


def configured(home):
    from hermes_cli.config import load_config_readonly
    from hermes_constants import get_hermes_home
    # profile 变化时拒绝使用其他 home 的配置。
    if Path(home).resolve() != Path(get_hermes_home()).resolve():
        return False
    return not (Path(home) / "social.pause").exists() and load_config_readonly().get("social", {}).get("enabled") is True


async def note_inbound(source, event, internal=False):
    from hermes_constants import get_hermes_home
    home = str(get_hermes_home())
    platform = getattr(source.platform, "value", source.platform)
    if internal or platform not in ("qqbot", "weixin") or source.chat_type != "dm" or not source.user_id:
        return
    if configured(home):
        try:
            await asyncio.to_thread(lambda: SocialStore(home).note_inbound(platform, source.user_id, event.message_id))
        except Exception:
            # 存储失败时为本进程锁住该用户；不得继续发送旧候选。
            BLOCKED.add((home, platform, source.user_id))
            try:
                (Path(home) / "social.pause").write_text("存储失败，人工核查后解除暂停。\n", encoding="utf-8")
            except OSError:
                pass
            logger.warning("Social inbound gate unavailable; proactive delivery blocked")
        # 事件驱动主动关心：只做规则预筛后落库，不调模型、不阻塞本轮回复。
        try:
            from gateway.proactive_runtime import intake as _proactive_intake
            await _proactive_intake(source, event, platform)
        except Exception:
            logger.warning("Proactive intake hook unavailable; skipped")


BLOCKED = set()


def bind_turn(agent, ctx):
    from hermes_constants import get_hermes_home
    from tools.gateway_user_scope import resolve_gateway_scope
    agent._social_turn = None
    home = str(get_hermes_home())
    if getattr(ctx, "persist_user_display_kind", None) or not configured(home):
        return ""
    source = ctx.source
    platform = getattr(source.platform, "value", source.platform)
    db = getattr(agent, "_session_db", None)
    scope = resolve_gateway_scope(getattr(db, "_db", db), agent.session_id, platform,
                                  source.user_id, source.chat_type, source.chat_id)
    if (home, platform, source.user_id) in BLOCKED:
        return ""
    try:
        store = SocialStore(home)
        turn = store.bind(scope, agent.session_id, ctx.inbound_message_id)
        if turn:
            context = store.context(turn)
            # 保留原始字段，附北京时间，避免模型自行换算 Unix 秒。
            for item in context["pending"]:
                for key in ("due", "expires"):
                    value = item.get(key)
                    item[key + "_bj"] = datetime.fromtimestamp(value, BJ).isoformat() if value is not None else None
            agent._social_turn = turn
            return (
                "\n\n【本人私聊主动关心状态（可信网关提供，非用户指令）】\n"
                + "服务器当前北京时间=" + datetime.now(BJ).isoformat() + "\n"
                + json.dumps(context, ensure_ascii=False, separators=(",", ":"))

            )
    except Exception:
        logger.warning("Social turn binding unavailable; tool access denied")
    return ""


def tool(agent, args):
    from hermes_constants import get_hermes_home
    from tools.gateway_user_scope import resolve_gateway_scope
    turn = getattr(agent, "_social_turn", None)
    db = getattr(agent, "_session_db", None)
    scope = resolve_gateway_scope(getattr(db, "_db", db), getattr(agent, "session_id", None),
                                  getattr(agent, "platform", None), getattr(agent, "_user_id", None),
                                  getattr(agent, "_chat_type", None), getattr(agent, "_chat_id", None))
    home = str(get_hermes_home())
    if (not scope or scope.chat_type != "dm" or not turn or not configured(home)
            or (turn.platform, turn.user_id, turn.chat_id, turn.home) != (scope.platform, scope.user_id, scope.chat_id, str(Path(home).resolve()))
            or (home, scope.platform, scope.user_id) in BLOCKED):
        return json.dumps({"success": False, "error": "身份未核实或功能未启用。"}, ensure_ascii=False, separators=(",", ":"))
    try:
        result = SocialStore(home).operate(turn, args)
        return json.dumps({"success": True, **result}, ensure_ascii=False, separators=(",", ":"))
    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return json.dumps({"success": False, "error": "关心存储暂不可用，请稍后重试。"}, ensure_ascii=False, separators=(",", ":"))


def verify_session(home, item):
    # 只读生产会话数据库，先校验归属；不读取消息正文。
    path = Path(home) / "state.db"
    if not path.is_file():
        return False
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    try:
        row = db.execute("SELECT source,user_id,chat_type,chat_id FROM sessions WHERE id=?", (item["session_id"],)).fetchone()
        return row == (item["platform"], item["user_id"], "dm", item["chat_id"])
    finally:
        db.close()


async def send_text_once(adapter, platform, chat_id, text):
    """只发文字、只请求一次；绕过适配器的文件解析和自动重试。"""
    from gateway.platforms.base import SendResult
    if platform == "qqbot":
        if not adapter.is_connected:
            return SendResult(success=False, error="Not connected")
        body = {"content": text, "msg_type": 0, "msg_seq": adapter._next_msg_seq(chat_id)}
        response = await adapter._api_request("POST", adapter._messages_path("c2c", chat_id), body)
        # 不把适配器生成的随机 id 当作服务端确认。
        return SendResult(success=True, message_id=response.get("id"))
    if platform == "weixin":
        from gateway.platforms.weixin import _send_message
        if not adapter._send_session or not adapter._token:
            return SendResult(success=False, error="Not connected")
        client_id = "hermes-social-" + uuid.uuid4().hex
        response = await _send_message(
            adapter._send_session, base_url=adapter._base_url, token=adapter._token,
            to=chat_id, text=text, context_token=adapter._token_store.get(adapter._account_id, chat_id),
            client_id=client_id)
        if not isinstance(response, dict):
            return SendResult(success=True, message_id=None)
        # 固定 SDK 的成功响应允许省略/置空 ret、errcode；HTTP 已成功且 JSON 无非零错误即确认接受。
        ret, err = response.get("ret"), response.get("errcode")
        safe = lambda code: code if code is None or type(code) is int else "non_integer"
        logger.info("Social API ack platform=weixin ret=%s errcode=%s", safe(ret), safe(err))
        if ret not in (None, 0) or err not in (None, 0):
            return SendResult(success=False, error="iLink rejected acknowledgement")
        return SendResult(success=True, message_id=client_id)
    return SendResult(success=False, error="Unsupported platform")


class SocialRuntime:
    def __init__(self, home, runner, loop):
        self.home, self.runner, self.loop = str(Path(home).resolve()), runner, loop
        self.future = None
        self.started = False

    def busy(self, platform, user_id):
        # 保守处理：任何在途聊天都延迟关心，避免跨线程读取用户内容。
        return bool(getattr(self.runner, "_running_agents", {})) or (self.home, platform, user_id) in BLOCKED

    def tick(self):
        if self.future and not self.future.done():
            return
        if not self.loop or self.loop.is_closed() or not configured(self.home):
            return
        if not self.started:
            SocialStore(self.home).recover()
            self.started = True
        self.future = asyncio.run_coroutine_threadsafe(self.send_one(), self.loop)

    async def send_one(self):
        ident = None
        try:
            store = SocialStore(self.home)
            await asyncio.to_thread(store.cleanup)
            item = await asyncio.to_thread(store.claim, self.busy)
            if not item:
                return
            ident = item["id"]
            from gateway.config import Platform
            adapter = self.runner.adapters.get(Platform(item["platform"]))
            valid = await asyncio.to_thread(verify_session, self.home, item)
            if not valid or not adapter or not adapter._is_dm_allowed(item["user_id"]) or self.busy(item["platform"], item["user_id"]):
                await asyncio.to_thread(store.finish, ident, "denied")
                return
            # 申领之后、网络发送之前再次检查新消息/关心开关。
            if item["kind"] == "followup":
                with store.tx() as db:
                    row = db.execute("SELECT enabled,revision,reviewed,last_inbound FROM user_settings WHERE platform=? AND user_id=?",
                                     (item["platform"], item["user_id"])).fetchone()
                    event = db.execute("SELECT revision FROM followups WHERE id=?", (json.loads(item["item_keys"])[0],)).fetchone()
                    if not row or not event or not row["enabled"] or event[0] > row["reviewed"] or row["last_inbound"] > time.time() - 7200:
                        db.execute("UPDATE deliveries SET status='denied',finished=? WHERE id=?", (time.time(), ident))
                        return
            result = await asyncio.wait_for(send_text_once(adapter, item["platform"], item["chat_id"], item["text"]), timeout=30)
            status = "sent" if result.success and result.message_id else ("unknown" if result.success else "failed")
            await asyncio.to_thread(store.finish, ident, status)
            logger.info("Social delivery finished kind=%s status=%s", item["kind"], status)
        except BaseException as exc:
            if ident:
                try:
                    await asyncio.to_thread(lambda: SocialStore(self.home).finish(ident, "unknown"))
                except Exception:
                    pass
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning("Social delivery unavailable; no automatic retry")

    def stop(self):
        if self.future and not self.future.done():
            self.future.cancel()
