"""隔离数据、合成身份、假适配器；不连接提供方或生产网关。"""
import asyncio
from datetime import datetime
import json
import sqlite3
from types import SimpleNamespace as NS

import pytest
from tools.gateway_user_scope import GatewayUserScope
from tools.social_store import BJ, DAY, SocialStore, SocialTurn, birthday_next, due_for
from gateway import social_runtime as runtime

NOW = datetime(2026, 10, 8, 10, tzinfo=BJ).timestamp()


def begin(home, platform="qqbot", uid="A", msg="m1", sid="s1", now=NOW):
    store = SocialStore(home, now)
    store.note_inbound(platform, uid, msg)
    scope = GatewayUserScope(platform, uid, "dm", "chat-" + uid)
    return store, store.bind(scope, sid, msg)


def record(store, turn, **kwargs):
    return store.operate(turn, {"action": "record", "kind": "topic", "summary": "练习画画", "text": "今天画得怎么样？", **kwargs})


def birthday(store, turn, **kwargs):
    return store.operate(turn, {"action": "birthday_add", "subject": "自己", "month": 10, "day": 9,
                               "text": "生日快乐呀～", "confirmed": True, **kwargs})


def state_db(home, rows):
    db = sqlite3.connect(home / "state.db")
    db.execute("CREATE TABLE sessions(id TEXT,source TEXT,user_id TEXT,chat_type TEXT,chat_id TEXT)")
    db.executemany("INSERT INTO sessions VALUES(?,?,?,?,?)", rows)
    db.commit()
    db.close()


def test_database_permissions_and_journal(tmp_path):
    s = SocialStore(tmp_path, NOW)
    with s.tx() as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 3000
    assert s.path.stat().st_mode & 0o777 == 0o600


def test_opt_in_and_disable_preserve_birthdays(tmp_path):
    s, t = begin(tmp_path)
    with pytest.raises(ValueError):
        record(s, t)
    s.operate(t, {"action": "settings", "enabled": True})
    record(s, t)
    birthday(s, t)
    s.operate(t, {"action": "settings", "enabled": False})
    assert len(s.operate(t, {"action": "list"})["birthdays"]) == 1
    assert SocialStore(tmp_path, NOW + DAY).claim()["kind"] == "birthday"
    assert SocialStore(tmp_path, NOW + 2 * DAY).claim() is None


@pytest.mark.parametrize("platform,uid", [("qqbot", "B"), ("weixin", "A"), ("weixin", "B")])
def test_user_and_platform_isolation(tmp_path, platform, uid):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    item = record(s, t)
    b, bt = begin(tmp_path, platform, uid)
    assert b.context(bt)["pending"] == []
    with pytest.raises(ValueError, match="未找到"):
        b.operate(bt, {"action": "cancel", "id": item["id"]})
    assert s.context(t)["pending"][0]["id"] == item["id"]


@pytest.mark.parametrize("scope", [None, GatewayUserScope("qqbot", "A", "group", "g1"),
                                   GatewayUserScope("weixin", "A", "group", "g2"), GatewayUserScope("cli", "A", "dm", "c")])
def test_group_and_unverified_binding_denied(tmp_path, scope):
    s, t = begin(tmp_path)
    assert s.bind(scope, "s1", "m1") is None


def test_new_session_compression_and_aba_cache(tmp_path):
    s, a = begin(tmp_path)
    s.seed("qqbot", "A")
    item = record(s, a)
    _, b = begin(tmp_path, uid="B", sid="other")
    assert s.context(b)["pending"] == []
    s.note_inbound("qqbot", "A", "new-msg")
    a2 = s.bind(GatewayUserScope("qqbot", "A", "dm", "chat-A"), "compressed-new", "new-msg")
    assert s.context(a2)["pending"][0]["id"] == item["id"]
    with pytest.raises(ValueError):
        record(s, a)
    s.operate(a2, {"action": "review", "id": item["id"]})
    assert SocialStore(tmp_path, NOW + DAY).claim()["user_id"] == "A"


def test_new_message_holds_until_all_events_reviewed(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    one = record(s, t)
    s, t2 = begin(tmp_path, msg="m2", now=NOW + 60)
    two = record(s, t2, summary="学习吉他")
    later = SocialStore(tmp_path, NOW + DAY + 120)
    assert later.claim() is None
    s.operate(t2, {"action": "review", "id": one["id"]})
    assert later.claim()
    # 下一次新消息即使模型完全跳过工具也不会继续发旧事项。
    begin(tmp_path, msg="m3", now=NOW + DAY + 180)
    assert SocialStore(tmp_path, NOW + 3 * DAY).claim() is None


def test_inbound_dedup_and_missing_id_fail_closed(tmp_path):
    s, t = begin(tmp_path)
    s.note_inbound("qqbot", "A", "m1")
    assert s.context(t)["revision"] == 1
    s.note_inbound("qqbot", "A", None)
    assert s.bind(GatewayUserScope("qqbot", "A", "dm", "chat-A"), "s1", None) is None
    with pytest.raises(ValueError):
        s.context(t)


def test_one_record_per_turn_and_cap(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    first = record(s, t)
    assert record(s, t, summary="另一个事项")["id"] == first["id"]
    for i in range(2, 6):
        s, t = begin(tmp_path, msg=f"m{i}")
        record(s, t, summary=f"事项{i}")
    s, t = begin(tmp_path, msg="m6")
    with pytest.raises(ValueError, match="5"):
        record(s, t)


@pytest.mark.parametrize("args", [
    {"action": "record", "recipient": "B"}, {"action": "list", "profile": "other"},
    {"action": "record", "sql": "DELETE"}, {"action": "settings", "enabled": "false"},
    {"action": "record", "path": "/tmp/a"}, {"action": "settings", "model": "x"},
])
def test_argument_and_approval_bypass_denied(tmp_path, args):
    s, t = begin(tmp_path)
    with pytest.raises(ValueError):
        s.operate(t, args)


def test_cross_home_denied(tmp_path):
    s, t = begin(tmp_path)
    other = tmp_path / "profile"
    other.mkdir()
    with pytest.raises(ValueError):
        SocialStore(other, NOW).operate(t, {"action": "list"})


@pytest.mark.parametrize("when,expected", [("2026-10-09", datetime(2026,10,10,18,tzinfo=BJ)),
    ("2026-10-09T10:00:00", datetime(2026,10,9,12,tzinfo=BJ)),
    ("2026-10-09T02:00:00+00:00", datetime(2026,10,9,12,tzinfo=BJ))])
def test_event_due_time(when, expected):
    assert due_for("event", when, NOW) == expected.timestamp()


@pytest.mark.parametrize("when,expected", [("tomorrow",datetime(2026,10,10,18,tzinfo=BJ)),
    ("明天",datetime(2026,10,10,18,tzinfo=BJ)),("tomorrow 17:00",datetime(2026,10,9,19,tzinfo=BJ)),
    ("后天 16:00",datetime(2026,10,10,18,tzinfo=BJ)),("today",datetime(2026,10,9,18,tzinfo=BJ))])
def test_relative_date_uses_server_clock(when,expected):
    assert due_for("event",when,NOW)==expected.timestamp()


@pytest.mark.parametrize("when", ["明天下午", "2026-10-06", "2026-12-12", "not-a-date"])
def test_ambiguous_or_out_of_range_due(when):
    with pytest.raises(ValueError):
        due_for("event", when, NOW)


def test_candidate_never_sends_and_expires(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    record(s, t, kind="event")
    assert SocialStore(tmp_path, NOW + DAY).claim() is None
    later = SocialStore(tmp_path, NOW + 8 * DAY)
    later.cleanup()
    assert later.operate(t, {"action": "list"})["followups"] == []


@pytest.mark.parametrize("hour", [0, 7, 23])
def test_quiet_hours(tmp_path, hour):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    record(s, t)
    now = datetime(2026, 10, 10, hour, tzinfo=BJ).timestamp()
    assert SocialStore(tmp_path, now).claim() is None


def test_recent_busy_and_48h_frequency(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    one = record(s, t)
    s, t = begin(tmp_path, msg="m2", now=NOW + DAY)
    record(s, t, summary="做手工")
    s.operate(t, {"action": "review", "id": one["id"]})
    assert SocialStore(tmp_path, NOW + DAY + 3600).claim() is None
    s = SocialStore(tmp_path, NOW + DAY + 7201)
    assert s.claim(lambda p,u: True) is None
    first = s.claim()
    assert first
    assert s.claim() is None
    s.finish(first["id"], "failed")
    assert SocialStore(tmp_path, NOW + 2 * DAY + 10000).claim() is None


def test_birthday_confirm_validation_leap_and_missed(tmp_path):
    s, t = begin(tmp_path)
    with pytest.raises(ValueError):
        birthday(s, t, confirmed=False)
    with pytest.raises(ValueError):
        birthday(s, t, month=2, day=30)
    with pytest.raises(ValueError):
        birthday(s,t,clock="23:00")
    leap = birthday(s, t, month=2, day=29)
    assert leap["next"].startswith("2027-03-01")
    assert datetime.fromtimestamp(birthday_next(2,29,"09:00", datetime(2028,1,1,tzinfo=BJ).timestamp()),BJ).day == 29
    birthday(s, t, month=10, day=8, clock="09:00")
    assert s.operate(t, {"action": "list"})["birthdays"][0]["due"] > NOW + 300 * DAY


def test_subscription_route_refreshes_after_new_session(tmp_path):
    s,t=begin(tmp_path)
    birthday(s,t)
    s.note_inbound("qqbot","A","new-session-msg")
    new=s.bind(GatewayUserScope("qqbot","A","dm","chat-A"),"new-session","new-session-msg")
    assert s.operate(new,{"action":"list"})["birthdays"][0]["session_id"]=="new-session"


def test_birthdays_merge_and_restart_no_duplicate(tmp_path):
    s, t = begin(tmp_path)
    birthday(s, t)
    birthday(s, t, subject="朋友", text="也祝你朋友生日快乐")
    later = SocialStore(tmp_path, NOW + DAY)
    item = later.claim()
    assert item["text"].count("生日快乐") == 2
    later.recover()
    assert later.claim() is None
    with later.tx() as db:
        assert db.execute("SELECT status FROM deliveries").fetchone()[0] == "unknown"
        assert db.execute("SELECT min(due) FROM birthdays").fetchone()[0] > NOW + 300 * DAY


def test_no_birthday_backfill_and_retention(tmp_path):
    s, t = begin(tmp_path)
    birthday(s, t)
    later = SocialStore(tmp_path, NOW + 2 * DAY)
    later.cleanup()
    assert later.claim() is None
    s.seed("qqbot", "A")
    record(s, t)
    s = SocialStore(tmp_path, NOW + DAY)
    item = s.claim()
    s.finish(item["id"], "sent")
    later = SocialStore(tmp_path, NOW + 95 * DAY)
    later.cleanup()
    with later.tx() as db:
        assert db.execute("SELECT count(*) FROM followups").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM deliveries").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM birthdays").fetchone()[0] == 1


def test_lock_error_does_not_rewrite_logic(tmp_path):
    s, t = begin(tmp_path)
    lock = sqlite3.connect(s.path)
    lock.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            s.operate(t, {"action": "list"})
    finally:
        lock.rollback()
        lock.close()


def test_registry_direct_denied():
    from tools.social_tool import denied
    assert json.loads(denied({"action": "settings", "enabled": True}))["success"] is False


def test_inline_requires_current_verified_session(tmp_path, monkeypatch):
    s, t = begin(tmp_path)
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(runtime, "configured", lambda home: True)
    agent = NS(_social_turn=t, _session_db=NS(get_session=lambda sid: {"source":"qqbot", "user_id":"B", "chat_type":"dm", "chat_id":"chat-A"}),
               session_id="s1", platform="qqbot", _user_id="A", _chat_type="dm", _chat_id="chat-A")
    assert not json.loads(runtime.tool(agent, {"action":"list"}))["success"]
    agent._session_db.get_session = lambda sid: {"source":"qqbot", "user_id":"A", "chat_type":"dm", "chat_id":"chat-A"}
    assert json.loads(runtime.tool(agent, {"action":"list"}))["success"]
    # 压缩后的当前会话归属相同即可；token 不允许更换平台/用户。
    agent.session_id = "compressed"
    assert json.loads(runtime.tool(agent, {"action":"list"}))["success"]
    agent._user_id = "B"
    assert not json.loads(runtime.tool(agent, {"action":"list"}))["success"]


@pytest.mark.asyncio
@pytest.mark.parametrize("success,message_id,raises,expected", [(True,"ack",False,"sent"), (True,None,False,"unknown"),
    (False,None,False,"failed"), (False,None,True,"unknown")])
async def test_runtime_sends_saved_text_without_model(tmp_path, monkeypatch, success, message_id, raises, expected):
    s, t = begin(tmp_path, now=NOW-DAY)
    s.seed("qqbot", "A")
    record(s, t)
    state_db(tmp_path, [("s1","qqbot","A","dm","chat-A")])
    monkeypatch.setattr(runtime, "SocialStore", lambda home: SocialStore(home, NOW))
    monkeypatch.setattr(runtime.time, "time", lambda: NOW)
    sent = []
    async def send(adapter,platform,chat,text):
        sent.append((chat,text))
        if raises:
            raise TimeoutError()
        return NS(success=success, message_id=message_id)
    from gateway.config import Platform
    monkeypatch.setattr(runtime,"send_text_once",send)
    adapter = NS(_is_dm_allowed=lambda uid: True)
    runner = NS(adapters={Platform.QQBOT: adapter}, _running_agents={})
    r = runtime.SocialRuntime(tmp_path, runner, asyncio.get_running_loop())
    await r.send_one()
    await r.send_one()
    assert sent == [("chat-A","今天画得怎么样？")]
    with s.tx() as db:
        assert db.execute("SELECT status FROM deliveries").fetchone()[0] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_row,allowed", [(True,True),(False,False)])
async def test_runtime_rejects_bad_session_or_removed_whitelist(tmp_path, monkeypatch, wrong_row, allowed):
    s, t = begin(tmp_path, now=NOW-DAY)
    s.seed("qqbot", "A")
    record(s, t)
    state_db(tmp_path, [("s1","qqbot","B" if wrong_row else "A","dm","chat-A")])
    monkeypatch.setattr(runtime, "SocialStore", lambda home: SocialStore(home, NOW))
    async def send(*args):
        pytest.fail("不应投递")
    from gateway.config import Platform
    runner = NS(adapters={Platform.QQBOT:NS(send=send,_is_dm_allowed=lambda uid:allowed)}, _running_agents={})
    await runtime.SocialRuntime(tmp_path, runner, asyncio.get_running_loop()).send_one()
    with s.tx() as db:
        assert db.execute("SELECT status FROM deliveries").fetchone()[0] == "denied"


def test_claim_atomic_under_two_workers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    record(s, t)
    a, b = SocialStore(tmp_path, NOW + DAY), SocialStore(tmp_path, NOW + DAY)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda st: st.claim(), [a, b]))
    assert sum(bool(r) for r in results) == 1


def test_changes_and_cancellation_prevent_old_text(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    item = record(s, t)
    s, latest = begin(tmp_path, msg="changed", now=NOW+60)
    s.operate(latest, {"action":"update", "id":item["id"], "kind":"event", "when":"2026-10-10",
                       "summary":"改到后天画画", "text":"后来画得顺利吗？"})
    assert SocialStore(tmp_path, NOW+DAY).claim() is None
    s.operate(latest, {"action":"cancel", "id":item["id"]})
    assert SocialStore(tmp_path, NOW+3*DAY).claim() is None


def test_stale_turn_cannot_review_new_inbound(tmp_path):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    item = record(s, t)
    s.note_inbound("qqbot", "A", "later")
    with pytest.raises(ValueError):
        s.operate(t, {"action":"review", "id":item["id"]})
    assert SocialStore(tmp_path, NOW+DAY).claim() is None


@pytest.mark.asyncio
async def test_storage_failure_latches_pause(tmp_path, monkeypatch):
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(runtime, "configured", lambda home: True)
    def broken(home):
        raise sqlite3.OperationalError("locked")
    monkeypatch.setattr(runtime, "SocialStore", broken)
    source = NS(platform="qqbot", user_id="A", chat_type="dm")
    await runtime.note_inbound(source, NS(message_id="message"))
    assert (tmp_path / "social.pause").exists()
    assert (str(tmp_path), "qqbot", "A") in runtime.BLOCKED
    runtime.BLOCKED.clear()


def test_dynamic_binding_refreshes_cached_agent_without_cross_user_context(tmp_path, monkeypatch):
    s, t = begin(tmp_path)
    s.seed("qqbot", "A")
    item = record(s, t)
    begin(tmp_path, uid="B")
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda:tmp_path)
    monkeypatch.setattr(runtime,"configured",lambda home:True)
    rows = {"s1":{"source":"qqbot","user_id":"A","chat_type":"dm","chat_id":"chat-A"},
            "sB":{"source":"qqbot","user_id":"B","chat_type":"dm","chat_id":"chat-B"}}
    agent = NS(_session_db=NS(get_session=lambda sid:rows.get(sid)),session_id="s1")
    def ctx(uid):
        return NS(source=NS(platform="qqbot",user_id=uid,chat_type="dm",chat_id="chat-"+uid),inbound_message_id="m1",persist_user_display_kind=None)
    assert item["id"] in runtime.bind_turn(agent,ctx("A"))
    agent.session_id="sB"
    assert item["id"] not in runtime.bind_turn(agent,ctx("B"))
    assert agent._social_turn.user_id=="B"
    agent.session_id="s1"
    assert item["id"] in runtime.bind_turn(agent,ctx("A"))
    group=ctx("A");group.source.chat_type="group"
    assert runtime.bind_turn(agent,group)==""
    assert agent._social_turn is None


@pytest.mark.asyncio
async def test_new_message_after_claim_blocks_network_send(tmp_path,monkeypatch):
    s,t=begin(tmp_path,now=NOW-DAY)
    s.seed("qqbot","A");record(s,t)
    state_db(tmp_path,[("s1","qqbot","A","dm","chat-A")])
    monkeypatch.setattr(runtime,"SocialStore",lambda home:SocialStore(home,NOW))
    monkeypatch.setattr(runtime.time,"time",lambda:NOW)
    original=runtime.verify_session
    def verify(home,item):
        SocialStore(home,NOW).note_inbound("qqbot","A","arrived-after-claim")
        return original(home,item)
    monkeypatch.setattr(runtime,"verify_session",verify)
    async def send(*args):
        pytest.fail("新消息后不应发送旧关心")
    monkeypatch.setattr(runtime,"send_text_once",send)
    from gateway.config import Platform
    runner=NS(adapters={Platform.QQBOT:NS(send=send,_is_dm_allowed=lambda u:True)},_running_agents={})
    await runtime.SocialRuntime(tmp_path,runner,asyncio.get_running_loop()).send_one()
    with s.tx() as db:
        assert db.execute("SELECT status FROM deliveries").fetchone()[0]=="denied"


@pytest.mark.asyncio
async def test_qq_plain_text_single_request_and_real_ack():
    requests=[]
    async def api(method,path,body):
        requests.append(body)
        return {"id":"server-ack"}
    adapter=NS(is_connected=True,_next_msg_seq=lambda chat:1,_messages_path=lambda kind,chat:"/c2c",_api_request=api)
    text="MEDIA:/private/secret.txt 这只是文字"
    result=await runtime.send_text_once(adapter,"qqbot","A",text)
    assert result.success and result.message_id=="server-ack"
    assert requests==[{"content":text,"msg_type":0,"msg_seq":1}]
    async def no_ack(*args):return {}
    adapter._api_request=no_ack
    result=await runtime.send_text_once(adapter,"qqbot","A",text)
    assert result.message_id is None


@pytest.mark.asyncio
async def test_weixin_plain_text_single_request_no_files_or_retry(monkeypatch):
    from gateway.platforms import weixin
    calls=[]
    async def request(session,**kwargs):
        calls.append(kwargs)
        return {"ret":0}
    monkeypatch.setattr(weixin,"_send_message",request)
    adapter=NS(_send_session=object(),_token="fake-token",_base_url="https://example.invalid",
               _account_id="fake",_token_store=NS(get=lambda account,chat:"fake-context"))
    result=await runtime.send_text_once(adapter,"weixin","A","MEDIA:/secret.txt")
    assert result.success and len(calls)==1 and calls[0]["text"]=="MEDIA:/secret.txt"
    async def timeout(session,**kwargs):
        calls.append(kwargs);raise TimeoutError()
    monkeypatch.setattr(weixin,"_send_message",timeout)
    with pytest.raises(TimeoutError):await runtime.send_text_once(adapter,"weixin","A","test")
    assert len(calls)==2


def test_cli_catalog_platform_restrictions_and_model_schema():
    from hermes_cli.tools_config import CONFIGURABLE_TOOLSETS,_get_platform_tools
    from hermes_cli.toolset_scope import toolset_allowed_for_platform
    from model_tools import get_tool_definitions
    assert "social" in {k for k,_,_ in CONFIGURABLE_TOOLSETS}
    assert toolset_allowed_for_platform("social","qqbot")
    assert toolset_allowed_for_platform("social","weixin")
    assert not toolset_allowed_for_platform("social","cli")
    cfg={"platform_toolsets":{"qqbot":["memory","social"],"weixin":["memory","social"],"cli":["memory"]}}
    for platform in ("qqbot","weixin"):
        enabled=_get_platform_tools(cfg,platform,include_default_mcp_servers=False)
        assert "social" in enabled
        defs=get_tool_definitions(enabled_toolsets=list(enabled),quiet_mode=True)
        assert any(d.get("function",{}).get("name")=="social_manage" for d in defs)
        assert not any(d.get("function",{}).get("name") in {"tool_call","tool_search","tool_describe"} for d in defs)
    assert "social" not in _get_platform_tools(cfg,"cli",include_default_mcp_servers=False)
