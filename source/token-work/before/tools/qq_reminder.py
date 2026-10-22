"""QQ／微信私聊的一次性文字提醒；复用调度器，不启动后台模型。"""

import base64
from datetime import datetime, timedelta, timezone
import json
import re
import threading
from uuid import uuid4

from hermes_constants import get_hermes_home

_CREATE_LOCK = threading.Lock()
MAX_REMINDERS = 20


def _result(**values):
    return json.dumps(values, ensure_ascii=False)


def _owned(job, scope):
    # 保留 qq_reminder 标记与脚本目录以兼容已保存的 QQ 任务；归属始终校验平台。
    origin = job.get("origin") or {}
    return (origin.get("qq_reminder") is True
            and origin.get("platform") == scope.platform
            and origin.get("user_id") == scope.user_id
            and origin.get("chat_id") == scope.chat_id
            and origin.get("chat_type") == "dm")


def _view(job):
    return {"job_id": job["id"], "name": job.get("name"),
            "text": job.get("prompt"), "next_run_at": job.get("next_run_at"),
            "state": job.get("state"), "last_status": job.get("last_status"),
            "delivery_failed": bool(job.get("last_delivery_error"))}


def reminder_schema():
    return {"description": "当前平台私聊文字提醒：create 创建，list 查看自己的提醒，remove 按 job_id 取消。"
            "仅一次性提醒，不运行模型。prompt 必须是届时直接发送的提醒正文，不是给模型的指令。"
            "schedule 使用 'in 10m' 或带 +08:00 的 ISO 时间，最长 30 天；每用户最多 20 条，"
            "含已完成记录，移除后释放额度。群聊不支持。不接受脚本、技能或其他收件人。",
            "parameters": {"type": "object", "additionalProperties": False,
                           "required": ["action"], "properties": {
                               "action": {"type": "string", "enum": ["create", "list", "remove"]},
                               "prompt": {"type": "string", "description": "提醒正文，最多 1000 字"},
                               "schedule": {"type": "string", "description": "一次性延迟或北京时间 ISO 时间"},
                               "name": {"type": "string"}, "job_id": {"type": "string"}}}}


def qq_reminder(scope, args):
    if not scope or scope.platform not in ("qqbot", "weixin") or scope.chat_type != "dm":
        return _result(success=False, error="提醒仅支持身份已核实的 QQ／微信私聊。")
    from cron import jobs

    action = args.get("action", "").strip().lower()
    allowed = {"action", "prompt", "schedule", "name", "job_id", "include_disabled", "repeat", "deliver"}
    if set(args) - allowed:
        return _result(success=False, error="仅支持一次性文字提醒，不接受脚本、技能、模型或上下文参数。")
    if args.get("deliver") not in (None, "", "origin", f"{scope.platform}:{scope.chat_id}"):
        return _result(success=False, error="提醒只能发送给当前私聊用户。")
    if args.get("repeat") not in (None, 1):
        return _result(success=False, error="目前仅支持一次性提醒。")
    own = [job for job in jobs.list_jobs(include_disabled=True) if _owned(job, scope)]
    if action == "list":
        return _result(success=True, count=len(own), jobs=[_view(job) for job in own])
    if action == "remove":
        ref = args.get("job_id")
        matches = [job for job in own if job["id"] == ref or job.get("name") == ref]
        if len(matches) != 1:
            return _result(success=False, error="未找到提醒；请先查看自己的提醒并使用其 ID。")
        job = matches[0]
        if not jobs.remove_job(job["id"]):
            return _result(success=False, error="未找到提醒。")
        # 只删除本功能产生的随机脚本，不接收用户提供的路径。
        script = job.get("script", "")
        if re.fullmatch(r"qq_reminders/[0-9a-f]{32}\.py", script):
            (get_hermes_home() / "scripts" / script).unlink(missing_ok=True)
        from tools.cronjob_tools import _notify_provider_jobs_changed_safe
        _notify_provider_jobs_changed_safe()
        return _result(success=True, message="提醒已取消或记录已移除。", job_id=job["id"])
    if action != "create":
        return _result(success=False, error="仅支持 create、list、remove。")
    text = args.get("prompt")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        return _result(success=False, error="请提供 1–1000 字的提醒正文。")
    name = str(args.get("name") or text.strip()[:40])[:80]
    if re.search(r"MEDIA\s*:|\[\[(?:audio_as_voice|as_document)\]\]|\[SILENT\]|NO_REPLY", text + name, re.I):
        return _result(success=False, error="纯文字提醒不支持附件或调度控制标记。")
    schedule = args.get("schedule")
    if not isinstance(schedule, str) or not schedule.strip():
        return _result(success=False, error="请提供提醒时间。")
    schedule = schedule.strip()
    if re.fullmatch(r"\d+[mhdw]", schedule):
        schedule = "in " + schedule
    try:
        # 无时区的绝对时间明确按北京时间解释，不依赖服务器 UTC。
        if "T" in schedule or re.match(r"^\d{4}-\d{2}-\d{2}", schedule):
            absolute = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
            if absolute.tzinfo is None:
                schedule = absolute.replace(tzinfo=timezone(timedelta(hours=8))).isoformat()
        parsed = jobs.parse_schedule(schedule)
        if parsed["kind"] != "once":
            raise ValueError("目前仅支持一次性提醒，请使用 in 10m 或具体日期时间。")
        delay = datetime.fromisoformat(parsed["run_at"]) - datetime.now(timezone.utc)
        if delay.total_seconds() < 30 or delay > timedelta(days=30):
            raise ValueError("提醒须在 30 秒至 30 天之后。")
    except (ValueError, TypeError) as exc:
        return _result(success=False, error=str(exc))
    with _CREATE_LOCK:
        own = [job for job in jobs.list_jobs(include_disabled=True) if _owned(job, scope)]
        if len(own) >= MAX_REMINDERS:
            return _result(success=False, error="已达到 20 条提醒记录上限，请移除旧记录后再创建。")
        relative = f"qq_reminders/{uuid4().hex}.py"
        path = get_hermes_home() / "scripts" / relative
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # 正文编码为数据字面量；即使包含 Python/Shell 代码，也只会被打印。
        payload = base64.b64encode(("提醒：" + text.strip()).encode("utf-8")).decode("ascii")
        path.write_text(f"import base64\nprint(base64.b64decode('{payload}').decode('utf-8'))\n", encoding="utf-8")
        path.chmod(0o600)
        from cron.scheduler import create_job_with_scheduler_registration
        try:
            job = create_job_with_scheduler_registration(
                prompt=text.strip(), schedule=parsed["run_at"],
                name=name, repeat=1,
                deliver=f"{scope.platform}:{scope.chat_id}", failure_deliver="local",
                origin={"qq_reminder": True, "platform": scope.platform,
                        "user_id": scope.user_id, "chat_id": scope.chat_id, "chat_type": "dm"},
                script=relative, no_agent=True, attach_to_session=False,
                enabled_toolsets=["no_mcp"],
            )
        except Exception:
            # 注册失败也可能留下持久化任务，清除本次记录，避免报错后仍然发送。
            for candidate in jobs.list_jobs(include_disabled=True):
                if _owned(candidate, scope) and candidate.get("script") == relative:
                    jobs.remove_job(candidate["id"])
            path.unlink(missing_ok=True)
            return _result(success=False, error="提醒调度注册失败，未保留此次提醒。")
        return _result(success=True, **_view(job), message="提醒已保存，将通过当前网关投递；发送结果仍受当前平台权限和会话有效期限制。")
