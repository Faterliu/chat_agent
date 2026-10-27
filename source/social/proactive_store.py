"""事件驱动主动关心：一次性候选存储（独立表，与 Social 共用 social.db）。

状态机：PENDING → PROCESSING → SENDING → SENT/FAILED/UNKNOWN；SKIPPED/EXPIRED/CANCELLED 为旁路终态。
终态一律不可重新领取；发送占用（SENDING + attempt_count=1）必须在调用平台接口前提交。
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

BJ = timezone(timedelta(hours=8))
DAY = 86400
TERMINAL = ("SENT", "FAILED", "UNKNOWN", "SKIPPED", "EXPIRED", "CANCELLED")
MAX_PENDING = 5
MAX_INTAKE = 20


class ProactiveStore:
    def __init__(self, home, now=None):
        self.home = str(Path(home).resolve())
        self.path = Path(self.home) / "social.db"
        self.now = time.time() if now is None else now
        if self.path.is_symlink():
            raise ValueError("数据库路径无效")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        if os.name != "nt":
            os.chmod(self.path, 0o600)
        with self.tx() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS proactive_intake(
                  id TEXT PRIMARY KEY, platform TEXT NOT NULL, user_id TEXT NOT NULL,
                  chat_id TEXT NOT NULL, message_key TEXT NOT NULL, text TEXT NOT NULL,
                  received REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                  UNIQUE(platform,user_id,message_key));
                CREATE TABLE IF NOT EXISTS proactive_tasks(
                  task_id TEXT PRIMARY KEY, platform TEXT NOT NULL, user_id TEXT NOT NULL,
                  chat_id TEXT NOT NULL, session_id TEXT, event_key TEXT NOT NULL,
                  event_summary TEXT NOT NULL, event_time REAL, trigger_at REAL NOT NULL,
                  expires_at REAL NOT NULL, status TEXT NOT NULL,
                  attempt_count INTEGER NOT NULL DEFAULT 0, decision_reason TEXT,
                  created_at REAL NOT NULL, updated_at REAL NOT NULL,
                  UNIQUE(platform,user_id,event_key));
                CREATE INDEX IF NOT EXISTS proactive_intake_state ON proactive_intake(state,received);
                CREATE INDEX IF NOT EXISTS proactive_due ON proactive_tasks(status,trigger_at);
                CREATE INDEX IF NOT EXISTS proactive_owner ON proactive_tasks(platform,user_id,status);
            """)

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=3000")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    # ── 事件识别排队（入站路径只做规则命中，不调模型） ──
    def intake(self, platform, user_id, chat_id, message_key, text):
        if platform not in ("qqbot", "weixin") or not (user_id and chat_id and message_key):
            return False
        with self.tx() as db:
            if db.execute("SELECT count(*) FROM proactive_intake WHERE state='pending'").fetchone()[0] >= MAX_INTAKE:
                return False
            return db.execute(
                "INSERT OR IGNORE INTO proactive_intake(id,platform,user_id,chat_id,message_key,text,received,state) "
                "VALUES(?,?,?,?,?,?,?,'pending')",
                (uuid.uuid4().hex, platform, user_id, chat_id, message_key, text, self.now)).rowcount == 1

    def next_intake(self):
        with self.tx() as db:
            row = db.execute("SELECT * FROM proactive_intake WHERE state='pending' ORDER BY received LIMIT 1").fetchone()
            return dict(row) if row else None

    def close_intake(self, ident, state="consumed"):
        if state not in ("consumed", "dropped"):
            raise ValueError("排队状态无效")
        with self.tx() as db:
            db.execute("UPDATE proactive_intake SET state=? WHERE id=? AND state='pending'", (state, ident))
            db.execute("DELETE FROM proactive_intake WHERE received<?", (self.now - 7 * DAY,))

    # ── 候选任务 ──
    def create(self, platform, user_id, chat_id, session_id, event_key, summary, event_time, trigger_at, expires_at):
        """返回 (task_id, action)：created / updated / ignored（终态或已存在同键）。"""
        pair = (platform, user_id)
        with self.tx() as db:
            old = db.execute("SELECT * FROM proactive_tasks WHERE platform=? AND user_id=? AND event_key=?",
                             (*pair, event_key)).fetchone()
            if old:
                if old["status"] != "PENDING":
                    return old["task_id"], "ignored"
                db.execute("UPDATE proactive_tasks SET event_summary=?,event_time=?,trigger_at=?,expires_at=?,"
                           "chat_id=?,session_id=?,updated_at=? WHERE task_id=?",
                           (summary, event_time, trigger_at, expires_at, chat_id, session_id, self.now, old["task_id"]))
                return old["task_id"], "updated"
            if db.execute("SELECT count(*) FROM proactive_tasks WHERE platform=? AND user_id=? AND status IN ('PENDING','PROCESSING','SENDING')",
                          pair).fetchone()[0] >= MAX_PENDING:
                return None, "ignored"
            ident = uuid.uuid4().hex
            db.execute("INSERT INTO proactive_tasks VALUES(?,?,?,?,?,?,?,?,?,?,'PENDING',0,NULL,?,?)",
                       (ident, *pair, chat_id, session_id, event_key, summary, event_time, trigger_at,
                        expires_at, self.now, self.now))
            return ident, "created"

    def cancel(self, platform, user_id, event_key=None, summary=None):
        with self.tx() as db:
            if event_key:
                rows = db.execute("SELECT task_id FROM proactive_tasks WHERE platform=? AND user_id=? AND event_key=? "
                                  "AND status IN ('PENDING','PROCESSING')", (platform, user_id, event_key)).fetchall()
            elif summary:
                rows = db.execute("SELECT task_id FROM proactive_tasks WHERE platform=? AND user_id=? AND event_summary=? "
                                  "AND status IN ('PENDING','PROCESSING')", (platform, user_id, summary)).fetchall()
            else:
                return 0
            for row in rows:
                db.execute("UPDATE proactive_tasks SET status='CANCELLED',decision_reason='user_cancelled',updated_at=? "
                           "WHERE task_id=? AND status IN ('PENDING','PROCESSING')", (self.now, row["task_id"]))
            return len(rows)

    # ── GATE + 领取 ──
    def pick(self):
        """DB 侧准入通过才把 PENDING 原子转 PROCESSING；静默时段直接返回 None。"""
        local = datetime.fromtimestamp(self.now, BJ)
        if local.hour >= 23 or local.hour < 8:
            return None
        with self.tx() as db:
            db.execute("UPDATE proactive_tasks SET status='EXPIRED',decision_reason='expired',updated_at=? "
                       "WHERE status='PENDING' AND expires_at<=?", (self.now, self.now))
            rows = db.execute(
                "SELECT t.* FROM proactive_tasks t JOIN user_settings u "
                "  ON t.platform=u.platform AND t.user_id=u.user_id "
                "WHERE t.status='PENDING' AND t.trigger_at<=? AND t.expires_at>? AND u.enabled=1 "
                "  AND u.last_inbound<=? "
                "  AND NOT EXISTS(SELECT 1 FROM deliveries d WHERE d.platform=t.platform AND d.user_id=t.user_id "
                "                 AND d.kind IN ('followup','proactive') AND d.attempted>?) "
                "ORDER BY t.trigger_at LIMIT 20",
                (self.now, self.now, self.now - 7200, self.now - 2 * DAY)).fetchall()
            for row in rows:
                if db.execute("UPDATE proactive_tasks SET status='PROCESSING',updated_at=? WHERE task_id=? AND status='PENDING'",
                              (self.now, row["task_id"])).rowcount == 1:
                    item = dict(row)
                    item["status"] = "PROCESSING"
                    return item
        return None

    def settle(self, task_id, status, reason):
        """未发送即终结（决策跳过、复核失效、异常）。只允许从 PROCESSING 迁移。"""
        if status not in ("SKIPPED", "EXPIRED", "CANCELLED"):
            raise ValueError("结束状态无效")
        with self.tx() as db:
            return db.execute("UPDATE proactive_tasks SET status=?,decision_reason=?,updated_at=? "
                              "WHERE task_id=? AND status='PROCESSING'",
                              (status, reason, self.now, task_id)).rowcount == 1

    def begin_send(self, task):
        """发送占用：复核 + SENDING + attempt_count=1 + 投递台账，同一事务提交后才允许调平台接口。"""
        local = datetime.fromtimestamp(self.now, BJ)
        if local.hour >= 23 or local.hour < 8:
            return None
        with self.tx() as db:
            row = db.execute("SELECT t.*, u.enabled AS u_enabled, u.last_inbound AS u_last_inbound "
                             "FROM proactive_tasks t LEFT JOIN user_settings u "
                             "  ON t.platform=u.platform AND t.user_id=u.user_id WHERE t.task_id=?",
                             (task["task_id"],)).fetchone()
            if not row or row["status"] != "PROCESSING" or row["attempt_count"] != 0:
                return None
            if row["expires_at"] <= self.now or row["u_enabled"] != 1 or row["u_last_inbound"] > self.now - 7200:
                return None
            if db.execute("SELECT 1 FROM deliveries d WHERE d.platform=? AND d.user_id=? "
                          "AND d.kind IN ('followup','proactive') AND d.attempted>?",
                          (row["platform"], row["user_id"], self.now - 2 * DAY)).fetchone():
                return None
            if db.execute("UPDATE proactive_tasks SET status='SENDING',attempt_count=1,updated_at=? "
                          "WHERE task_id=? AND status='PROCESSING' AND attempt_count=0",
                          (self.now, row["task_id"])).rowcount != 1:
                return None
            ident = uuid.uuid4().hex
            db.execute("INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (ident, row["platform"], row["user_id"], "proactive", json.dumps([row["task_id"]]),
                        task.get("text") or "", row["chat_id"], row["session_id"], self.now, "attempted", None))
            return ident

    def finish(self, task_id, ledger_id, status, reason=None):
        """记录发送结果；成功/失败/未知都只落一次，不重发。"""
        if status not in ("SENT", "FAILED", "UNKNOWN"):
            raise ValueError("投递状态无效")
        with self.tx() as db:
            db.execute("UPDATE proactive_tasks SET status=?,decision_reason=?,updated_at=? WHERE task_id=? AND status='SENDING'",
                       (status, reason, self.now, task_id))
            db.execute("UPDATE deliveries SET status=?,finished=? WHERE id=? AND status='attempted'",
                       (status.lower(), self.now, ledger_id))

    def recover(self):
        """重启保守终结：PROCESSING 丢弃执行机会，SENDING 视为可能已发送。"""
        with self.tx() as db:
            db.execute("UPDATE proactive_tasks SET status='SKIPPED',decision_reason='crash_processing',updated_at=? "
                       "WHERE status='PROCESSING'", (self.now,))
            db.execute("UPDATE proactive_tasks SET status='UNKNOWN',decision_reason='crash_sending',updated_at=? "
                       "WHERE status='SENDING'", (self.now,))
            db.execute("UPDATE proactive_tasks SET status='EXPIRED',decision_reason='expired',updated_at=? "
                       "WHERE status='PENDING' AND expires_at<=?", (self.now, self.now))
            db.execute("UPDATE deliveries SET status='unknown',finished=? WHERE status='attempted' AND kind='proactive'",
                       (self.now,))

    def cleanup(self):
        with self.tx() as db:
            db.execute("DELETE FROM proactive_tasks WHERE updated_at<? AND status IN ('SENT','FAILED','UNKNOWN','SKIPPED','EXPIRED','CANCELLED')",
                       (self.now - 90 * DAY,))
            db.execute("DELETE FROM proactive_intake WHERE received<?", (self.now - 7 * DAY,))

    def pending_summary(self, platform, user_id):
        with self.tx() as db:
            return [{"summary": r["event_summary"],
                     "trigger_bj": datetime.fromtimestamp(r["trigger_at"], BJ).isoformat()}
                    for r in db.execute("SELECT * FROM proactive_tasks WHERE platform=? AND user_id=? "
                                        "AND status='PENDING' ORDER BY trigger_at LIMIT 5", (platform, user_id))]
