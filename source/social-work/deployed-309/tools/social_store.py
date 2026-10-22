"""私聊主动关心的轻量存储；所有访问均绑定平台、用户和当前消息版本。"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
import calendar
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

BJ = timezone(timedelta(hours=8))
DAY = 86400


@dataclass(frozen=True)
class SocialTurn:
    home: str
    platform: str
    user_id: str
    chat_id: str
    session_id: str
    revision: int
    source_key: str


def source_key(message_id):
    return hashlib.sha256(str(message_id).encode("utf-8")).hexdigest() if message_id else ""


def birthday_next(month, day, clock, now):
    hour, minute = map(int, clock.split(":"))
    local = datetime.fromtimestamp(now, BJ)
    for year in (local.year, local.year + 1):
        m, d = (3, 1) if (month, day) == (2, 29) and not calendar.isleap(year) else (month, day)
        value = datetime(year, m, d, hour, minute, tzinfo=BJ).timestamp()
        if value > now:
            return value
    raise ValueError("生日日期无效")


def due_for(kind, when, now):
    if kind == "topic":
        if when:
            raise ValueError("日常话题无需指定时间")
        return now + DAY
    if kind != "event":
        raise ValueError("仅支持具体事件或未结束的日常话题")
    if not when:
        return None
    # 仅接受明确的 ISO 日期或日期时间；无时区按北京时间。
    if len(when) == 10:
        d = date.fromisoformat(when) + timedelta(days=1)
        due = datetime(d.year, d.month, d.day, 18, tzinfo=BJ).timestamp()
    else:
        dt = datetime.fromisoformat(when)
        due = (dt.replace(tzinfo=BJ) if dt.tzinfo is None else dt).timestamp() + 7200
    if not now < due <= now + 30 * DAY:
        raise ValueError("跟进时间必须在未来 30 天内")
    return due


class SocialStore:
    def __init__(self, home, now=None):
        self.home = str(Path(home).resolve())
        self.path = Path(self.home) / "social.db"
        self.now = time.time() if now is None else now
        # 不替换既有文件、不跟随数据库符号链接。
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
            db.execute("PRAGMA journal_mode=DELETE")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS user_settings(
                  platform TEXT, user_id TEXT, enabled INTEGER NOT NULL DEFAULT 0,
                  revision INTEGER NOT NULL DEFAULT 0, reviewed INTEGER NOT NULL DEFAULT 0,
                  last_inbound REAL NOT NULL DEFAULT 0, turns TEXT NOT NULL DEFAULT '[]',
                  PRIMARY KEY(platform,user_id));
                CREATE TABLE IF NOT EXISTS followups(
                  id TEXT PRIMARY KEY, platform TEXT, user_id TEXT, chat_id TEXT,
                  session_id TEXT, source_key TEXT, summary TEXT, text TEXT, kind TEXT,
                  due REAL, expires REAL, status TEXT, revision INTEGER, created REAL,
                  closed REAL, UNIQUE(platform,user_id,source_key));
                CREATE TABLE IF NOT EXISTS birthdays(
                  id TEXT PRIMARY KEY, platform TEXT, user_id TEXT, chat_id TEXT,
                  session_id TEXT, subject TEXT, month INTEGER, day INTEGER, clock TEXT,
                  text TEXT, due REAL, UNIQUE(platform,user_id,subject));
                CREATE TABLE IF NOT EXISTS deliveries(
                  id TEXT PRIMARY KEY, platform TEXT, user_id TEXT, kind TEXT,
                  item_keys TEXT, text TEXT, chat_id TEXT, session_id TEXT,
                  attempted REAL, status TEXT, finished REAL);
                CREATE INDEX IF NOT EXISTS followup_owner ON followups(platform,user_id,status);
                CREATE INDEX IF NOT EXISTS delivery_owner ON deliveries(platform,user_id,attempted);
                PRAGMA user_version=1;
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

    def note_inbound(self, platform, user_id, message_id):
        if platform not in ("qqbot", "weixin") or not user_id:
            return
        key = source_key(message_id)
        with self.tx() as db:
            db.execute("INSERT OR IGNORE INTO user_settings(platform,user_id) VALUES(?,?)", (platform, user_id))
            row = db.execute("SELECT * FROM user_settings WHERE platform=? AND user_id=?", (platform, user_id)).fetchone()
            turns = json.loads(row["turns"])
            if key and any(t[0] == key for t in turns):
                return
            rev = row["revision"] + 1
            turns = (turns + [[key, rev]])[-32:]
            db.execute("UPDATE user_settings SET revision=?,last_inbound=?,turns=? WHERE platform=? AND user_id=?",
                       (rev, self.now, json.dumps(turns), platform, user_id))

    def bind(self, scope, session_id, message_id):
        if not scope or scope.chat_type != "dm" or scope.platform not in ("qqbot", "weixin"):
            return None
        key = source_key(message_id)
        if not key:
            return None
        with self.tx() as db:
            row = db.execute("SELECT * FROM user_settings WHERE platform=? AND user_id=?", (scope.platform, scope.user_id)).fetchone()
            if row:
                for k, revision in json.loads(row["turns"]):
                    if k == key:
                        if revision == row["revision"]:
                            for table in ("birthdays", "followups"):
                                db.execute(f"UPDATE {table} SET chat_id=?,session_id=? WHERE platform=? AND user_id=?",
                                           (scope.chat_id, session_id, scope.platform, scope.user_id))
                        return SocialTurn(self.home, scope.platform, scope.user_id, scope.chat_id, session_id, revision, key)
        return None

    def seed(self, platform, user_id):
        with self.tx() as db:
            db.execute("INSERT INTO user_settings(platform,user_id,enabled) VALUES(?,?,1) "
                       "ON CONFLICT(platform,user_id) DO UPDATE SET enabled=1", (platform, user_id))

    def context(self, turn):
        with self.tx() as db:
            row = self._owner(db, turn)
            items = self._pending(db, turn)
        return {"enabled": bool(row["enabled"]), "revision": turn.revision,
                "pending": [{k: r[k] for k in ("id", "summary", "kind", "due", "expires", "revision")} for r in items]}

    def _owner(self, db, turn):
        if not isinstance(turn, SocialTurn) or str(Path(turn.home).resolve()) != self.home:
            raise ValueError("身份未核实")
        row = db.execute("SELECT * FROM user_settings WHERE platform=? AND user_id=?", (turn.platform, turn.user_id)).fetchone()
        if not row or row["revision"] != turn.revision or not turn.source_key:
            raise ValueError("聊天已更新，请在最新消息中操作")
        return row

    def _pending(self, db, turn):
        return db.execute("SELECT * FROM followups WHERE platform=? AND user_id=? AND status='pending' "
                          "AND expires>? ORDER BY created LIMIT 5", (turn.platform, turn.user_id, self.now)).fetchall()

    def _reviewed(self, db, turn):
        if all(r["revision"] == turn.revision for r in self._pending(db, turn)):
            db.execute("UPDATE user_settings SET reviewed=? WHERE platform=? AND user_id=? AND revision=?",
                       (turn.revision, turn.platform, turn.user_id, turn.revision))

    def operate(self, turn, args):
        fields = {
            "record": {"kind", "summary", "text", "when"},
            "update": {"id", "kind", "summary", "text", "when"},
            "review": {"id"}, "complete": {"id"}, "cancel": {"id"},
            "list": set(), "settings": {"enabled"},
            "birthday_add": {"subject", "month", "day", "clock", "text", "confirmed"},
            "birthday_remove": {"id"},
        }
        action = args.get("action")
        if action not in fields or set(args) - fields[action] - {"action"}:
            raise ValueError("操作或参数无效")
        with self.tx() as db:
            owner = self._owner(db, turn)
            pair = (turn.platform, turn.user_id)
            db.execute("UPDATE followups SET status='expired',closed=? WHERE platform=? AND user_id=? "
                       "AND status='pending' AND expires<=?", (self.now, *pair, self.now))
            if action == "list":
                return {"enabled": bool(owner["enabled"]), "followups": [dict(r) for r in self._pending(db, turn)],
                        "birthdays": [dict(r) for r in db.execute("SELECT * FROM birthdays WHERE platform=? AND user_id=?", pair)]}
            if action == "settings":
                if type(args.get("enabled")) is not bool:
                    raise ValueError("enabled 必须为布尔值")
                db.execute("UPDATE user_settings SET enabled=? WHERE platform=? AND user_id=?", (int(args["enabled"]), *pair))
                return {"enabled": args["enabled"], "note": "仅影响主动关心；生日订阅和明确提醒独立保留。"}
            if action.startswith("birthday_"):
                if action == "birthday_remove":
                    count = db.execute("DELETE FROM birthdays WHERE id=? AND platform=? AND user_id=?", (args.get("id"), *pair)).rowcount
                    if not count:
                        raise ValueError("未找到")
                    return {"removed": True}
                if args.get("confirmed") is not True:
                    raise ValueError("生日订阅须获得用户明确确认")
                subject = self._text(args.get("subject"), 40)
                text = self._text(args.get("text"), 160)
                month, day = args.get("month"), args.get("day")
                if type(month) is not int or type(day) is not int:
                    raise ValueError("生日须为公历月日")
                date(2000, month, day)
                clock = args.get("clock", "09:00")
                if not isinstance(clock, str) or len(clock) != 5 or clock[2] != ":":
                    raise ValueError("时间格式须为 HH:MM")
                hour, minute = map(int, clock.split(":"))
                if not 8 <= hour < 23 or not 0 <= minute < 60:
                    raise ValueError("生日发送时间须在北京时间 08:00–22:59，避开免打扰时段")
                due = birthday_next(month, day, clock, self.now)
                old = db.execute("SELECT id FROM birthdays WHERE platform=? AND user_id=? AND subject=?", (*pair, subject)).fetchone()
                if not old and db.execute("SELECT count(*) FROM birthdays WHERE platform=? AND user_id=?", pair).fetchone()[0] >= 20:
                    raise ValueError("生日订阅最多 20 条")
                ident = old[0] if old else uuid.uuid4().hex
                db.execute("INSERT OR REPLACE INTO birthdays VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (ident, *pair, turn.chat_id, turn.session_id, subject, month, day, clock, text, due))
                return {"id": ident, "next": datetime.fromtimestamp(due, BJ).isoformat(),
                        "note": "2 月 29 日在非闰年按 3 月 1 日；错过当天不补发。"}
            if action in ("review", "complete", "cancel", "update"):
                event = db.execute("SELECT * FROM followups WHERE id=? AND platform=? AND user_id=? AND status='pending'",
                                   (args.get("id"), *pair)).fetchone()
                if not event:
                    raise ValueError("未找到")
                if action != "update":
                    status = "pending" if action == "review" else action
                    db.execute("UPDATE followups SET revision=?,status=?,closed=? WHERE id=?",
                               (turn.revision, status, None if status == "pending" else self.now, event["id"]))
                    self._reviewed(db, turn)
                    return {"id": event["id"], "status": status}
            if not owner["enabled"]:
                raise ValueError("主动关心未启用；用户同意后可调整 settings")
            summary = self._text(args.get("summary"), 180)
            text = self._text(args.get("text"), 600)
            kind = args.get("kind")
            due = due_for(kind, args.get("when"), self.now)
            expires = due + 2 * DAY if due else self.now + 7 * DAY
            if action == "record":
                old = db.execute("SELECT id FROM followups WHERE platform=? AND user_id=? AND source_key=?",
                                 (*pair, turn.source_key)).fetchone()
                if old:
                    return {"id": old[0], "deduplicated": True}
                if len(self._pending(db, turn)) >= 5:
                    raise ValueError("待跟进事项最多 5 条")
                if db.execute("SELECT 1 FROM followups WHERE platform=? AND user_id=? AND status='pending' AND summary=?", (*pair, summary)).fetchone():
                    raise ValueError("已有同一事项，请更新或复核")
                ident = uuid.uuid4().hex
                db.execute("INSERT INTO followups VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (ident, *pair, turn.chat_id, turn.session_id, turn.source_key, summary, text, kind,
                            due, expires, "pending", turn.revision, self.now, None))
            else:
                ident = event["id"]
                db.execute("UPDATE followups SET summary=?,text=?,kind=?,due=?,expires=?,revision=?,chat_id=?,session_id=? WHERE id=?",
                           (summary, text, kind, due, expires, turn.revision, turn.chat_id, turn.session_id, ident))
            self._reviewed(db, turn)
            return {"id": ident, "due": datetime.fromtimestamp(due, BJ).isoformat() if due else None, "status": "pending"}

    @staticmethod
    def _text(value, maximum):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
            raise ValueError("文字为空或过长")
        return value.strip()

    def recover(self):
        with self.tx() as db:
            db.execute("UPDATE deliveries SET status='unknown',finished=? WHERE status='attempted'", (self.now,))

    def cleanup(self):
        with self.tx() as db:
            db.execute("UPDATE followups SET status='expired',closed=? WHERE status='pending' AND expires<=?", (self.now, self.now))
            db.execute("DELETE FROM followups WHERE closed<?", (self.now - 30 * DAY,))
            db.execute("DELETE FROM deliveries WHERE attempted<? AND status!='attempted'", (self.now - 90 * DAY,))
            # 跳过已错过的生日；每年独立，禁止重启后补发旧祝福。
            for row in db.execute("SELECT * FROM birthdays WHERE due<=?", (self.now,)).fetchall():
                if datetime.fromtimestamp(row["due"], BJ).date() < datetime.fromtimestamp(self.now, BJ).date():
                    db.execute("UPDATE birthdays SET due=? WHERE id=?",
                               (birthday_next(row["month"], row["day"], row["clock"], self.now), row["id"]))

    def claim(self, busy=lambda p, u: False):
        local = datetime.fromtimestamp(self.now, BJ)
        if local.hour >= 23 or local.hour < 8:
            return None
        with self.tx() as db:
            # 生日不受关心开关及 48 小时频率限制；同时间订阅合并投递。
            for birthday in db.execute("SELECT * FROM birthdays WHERE due<=? ORDER BY due LIMIT 40", (self.now,)).fetchall():
                p, u = birthday["platform"], birthday["user_id"]
                if busy(p, u):
                    continue
                if datetime.fromtimestamp(birthday["due"], BJ).date() != local.date():
                    continue
                rows = db.execute("SELECT * FROM birthdays WHERE platform=? AND user_id=? AND due=?", (p, u, birthday["due"])).fetchall()
                texts = []
                for r in rows:
                    texts.append(r["text"])
                    db.execute("UPDATE birthdays SET due=? WHERE id=?", (birthday_next(r["month"], r["day"], r["clock"], self.now), r["id"]))
                return self._delivery(db, birthday, "birthday", [r["id"] for r in rows], "\n\n".join(texts))
            rows = db.execute("SELECT f.* FROM followups f JOIN user_settings u ON f.platform=u.platform AND f.user_id=u.user_id "
                              "WHERE f.status='pending' AND f.due<=? AND f.expires>? AND u.enabled=1 "
                              "AND u.revision=u.reviewed AND f.revision=u.revision AND u.last_inbound<=? "
                              "AND NOT EXISTS(SELECT 1 FROM deliveries d WHERE d.platform=f.platform AND d.user_id=f.user_id "
                              "AND d.kind='followup' AND d.attempted>?) ORDER BY f.due LIMIT 40",
                              (self.now, self.now, self.now - 7200, self.now - 2 * DAY)).fetchall()
            for row in rows:
                if not busy(row["platform"], row["user_id"]):
                    db.execute("UPDATE followups SET status='attempted',closed=? WHERE id=?", (self.now, row["id"]))
                    return self._delivery(db, row, "followup", [row["id"]], row["text"])
        return None

    def _delivery(self, db, row, kind, keys, text):
        ident = uuid.uuid4().hex
        db.execute("INSERT INTO deliveries VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (ident, row["platform"], row["user_id"], kind, json.dumps(keys), text,
                    row["chat_id"], row["session_id"], self.now, "attempted", None))
        return dict(db.execute("SELECT * FROM deliveries WHERE id=?", (ident,)).fetchone())

    def finish(self, ident, status):
        if status not in ("sent", "failed", "unknown", "denied"):
            raise ValueError("投递状态无效")
        with self.tx() as db:
            db.execute("UPDATE deliveries SET status=?,finished=? WHERE id=? AND status='attempted'", (status, self.now, ident))
