"""部署引导与元数据核验；不打印身份、凭据或私聊正文。"""
import json
import os
from pathlib import Path
import sqlite3
import sys

HOME = Path("/var/lib/hermes/.hermes")
REPO = HOME / "hermes-agent"
os.environ["HERMES_HOME"] = str(HOME)
sys.path.insert(0, str(REPO))
from dotenv import load_dotenv
load_dotenv(HOME / ".env", override=False)
from gateway.config import load_gateway_config, Platform
from gateway.platforms.qqbot.adapter import QQAdapter
from gateway.platforms.weixin import WeixinAdapter


def verified_owners():
    cfg = load_gateway_config()
    adapters = {"qqbot": QQAdapter(cfg.platforms[Platform.QQBOT]),
                "weixin": WeixinAdapter(cfg.platforms[Platform.WEIXIN])}
    db = sqlite3.connect(f"file:{HOME / 'state.db'}?mode=ro", uri=True, timeout=3)
    result = []
    try:
        for p, adapter in adapters.items():
            rows = db.execute("SELECT id,user_id,chat_id FROM sessions WHERE source=? AND chat_type='dm' "
                              "AND user_id IS NOT NULL AND chat_id IS NOT NULL ORDER BY started_at DESC", (p,)).fetchall()
            found = {}
            for sid, uid, chat in rows:
                if uid and chat and adapter._is_dm_allowed(uid):
                    found.setdefault(uid, (sid, chat))
            if len(found) != 1:
                raise RuntimeError("当前每平台应只有一个已验证白名单用户，实际计数不符合部署条件")
            uid, (sid, chat) = next(iter(found.items()))
            result.append((p, uid, sid, chat))
    finally:
        db.close()
    return result


action = sys.argv[1]
if action in ("preflight", "seed"):
    owners = verified_owners()
    for name in ("USER.md", "MEMORY.md"):
        p = HOME / "memories" / name
        if p.exists() and p.read_text(encoding="utf-8").strip():
            raise RuntimeError("发现未归属全局记忆，停止部署")
    # 与既有审批模块一致地核查未归属待审批；不输出内容。
    from tools import write_approval
    pending = write_approval.list_pending("memory")
    if pending:
        raise RuntimeError("发现全局待审批记录，停止部署并核查归属")
    print("verified_private_whitelist_owners=2; unowned_memory=0; unowned_pending=0")
    if action == "seed":
        from tools.social_store import SocialStore
        store = SocialStore(HOME)
        for platform, uid, sid, chat in owners:
            store.seed(platform, uid)
        print("social_enabled_existing_owners=2")
elif action == "enable":
    import yaml
    path = HOME / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg["social"] = {"enabled": True}
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
elif action == "verify":
    import yaml
    from tools.social_store import SocialStore
    from tools.social_tool import SCHEMA
    from gateway.social_runtime import verify_session
    cfg = yaml.safe_load((HOME / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["social"]["enabled"] is True
    from hermes_cli.tools_config import _get_platform_tools
    from model_tools import get_tool_definitions
    for platform in ("qqbot", "weixin"):
        enabled = _get_platform_tools(cfg, platform, include_default_mcp_servers=False)
        assert "social" in enabled, "新工具集未实际启用"
        definitions = get_tool_definitions(enabled_toolsets=list(enabled), quiet_mode=True)
        assert any(d.get("function", {}).get("name") == "social_manage" for d in definitions), "模型侧缺少 social 工具"
    assert "social" not in _get_platform_tools(cfg, "cli", include_default_mcp_servers=False)
    assert SCHEMA["name"] == "social_manage"
    store = SocialStore(HOME)
    with store.tx() as db:
        print("social_user_settings_count=" + str(db.execute("SELECT count(*) FROM user_settings WHERE enabled=1").fetchone()[0]))
        print("social_followups_count=" + str(db.execute("SELECT count(*) FROM followups").fetchone()[0]))
        print("social_birthdays_count=" + str(db.execute("SELECT count(*) FROM birthdays").fetchone()[0]))
        print("social_delivery_status=" + json.dumps(dict(db.execute("SELECT status,count(*) FROM deliveries GROUP BY status").fetchall())))
        print("social_journal=" + db.execute("PRAGMA journal_mode").fetchone()[0])
    for platform, uid, sid, chat in verified_owners():
        assert verify_session(HOME, {"platform":platform,"user_id":uid,"session_id":sid,"chat_id":chat})
    print("private_route_checks=2; db_mode=" + oct((HOME / "social.db").stat().st_mode & 0o777))
elif action in ("probe_test_birthdays", "clean_test_records", "confirm_test_receipt"):
    from datetime import datetime
    import time
    from tools.social_store import SocialStore, BJ
    store = SocialStore(HOME)
    owners = verified_owners()
    with store.tx() as db:
        for platform, uid, sid, chat in owners:
            row = db.execute("SELECT id FROM birthdays WHERE platform=? AND user_id=? AND subject='测试对象'", (platform, uid)).fetchone()
            if action == "probe_test_birthdays":
                if not row:
                    raise RuntimeError("两个平台的测试生日尚未全部创建，停止测试安排")
                target = datetime.fromtimestamp(time.time() + 180, BJ).replace(second=0, microsecond=0)
                db.execute("UPDATE birthdays SET month=?,day=?,clock=?,due=?,chat_id=?,session_id=? WHERE id=?",
                           (target.month, target.day, target.strftime("%H:%M"), target.timestamp(), chat, sid, row[0]))
            elif action == "confirm_test_receipt":
                if not row:
                    raise RuntimeError("未找到已确认的测试订阅")
                for delivery in db.execute("SELECT id,item_keys FROM deliveries WHERE platform=? AND user_id=? AND kind='birthday' AND status IN ('failed','unknown')",(platform,uid)).fetchall():
                    if row[0] in json.loads(delivery["item_keys"]):
                        db.execute("UPDATE deliveries SET status='sent',finished=? WHERE id=?",(time.time(),delivery["id"]))
            else:
                if row:
                    db.execute("DELETE FROM birthdays WHERE id=?", (row[0],))
                db.execute("DELETE FROM followups WHERE platform=? AND user_id=? AND (summary LIKE '%书桌%' OR summary LIKE '%拍照%' OR summary LIKE '%面包%') AND status='pending'", (platform, uid))
        print({"probe_test_birthdays":"test_birthdays_scheduled=2","clean_test_records":"test_subscriptions_and_candidates_removed","confirm_test_receipt":"test_delivery_marked_sent_by_explicit_user_confirmation"}[action])
else:
    raise ValueError("无效维护操作")
