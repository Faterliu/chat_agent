#!/usr/bin/env python3
"""Apply the 云白-voice failure-copy patch to gateway/run.py and gateway/run_turn.py.

Idempotent: refuses when the markers are already present. Backs both files up,
asserts every replacement matched exactly once, compiles the results, and writes
a unified diff for the repository patch record.

Usage: HERMES_SOURCE=/var/lib/hermes/.hermes/hermes-agent python3 apply-persona-errors.py
"""
import datetime
import hashlib
import os
import py_compile
import shutil
import sys
from pathlib import Path

SRC = Path(os.environ.get("HERMES_SOURCE", "/var/lib/hermes/.hermes/hermes-agent"))
RUN = SRC / "gateway" / "run.py"
TURN = SRC / "gateway" / "run_turn.py"
MODULE = SRC / "gateway" / "persona_errors.py"
BACKUP_ROOT = SRC.parent / "backups" / ("persona-errors-" + datetime.datetime.now(
    datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))

RUN_EDITS = [
    (
        "    from agent.retry_utils import format_reset_window, reset_delay_from_message\n"
        "    seconds = reset_delay_from_message(text) or 0\n"
        "    if seconds < 120:\n",
        "    from agent.retry_utils import format_reset_window, reset_delay_from_message\n"
        "    seconds = reset_delay_from_message(text) or 0\n"
        "    from gateway import persona_errors as _persona\n"
        "    if _persona.enabled():\n"
        "        return _persona.rate_limit(seconds)\n"
        "    if seconds < 120:\n",
    ),
    (
        "    for pattern, reply in _PROVIDER_ERROR_REPLIES:\n"
        "        if pattern.search(text):\n"
        "            return _rate_limit_reply(text) if pattern is _GATEWAY_RATE_LIMIT_RE else reply\n"
        "    return (\n"
        "        \"⚠️ The AI model service kept failing. Use /retry to try again, or /model to switch \"\n",
        "    _provider_kinds = (\"auth\", \"policy\", \"connection_interrupted\",\n"
        "                       \"endpoint_unreachable\", \"connection_error\")\n"
        "    for index, (pattern, reply) in enumerate(_PROVIDER_ERROR_REPLIES):\n"
        "        if pattern.search(text):\n"
        "            if pattern is _GATEWAY_RATE_LIMIT_RE:\n"
        "                return _rate_limit_reply(text)\n"
        "            from gateway import persona_errors as _persona\n"
        "            if _persona.enabled():\n"
        "                kind = _provider_kinds[index - 1] if 0 < index <= len(_provider_kinds) else \"generic\"\n"
        "                return _persona.provider(kind)\n"
        "            return reply\n"
        "    from gateway import persona_errors as _persona\n"
        "    if _persona.enabled():\n"
        "        return _persona.provider(\"generic\")\n"
        "    return (\n"
        "        \"⚠️ The AI model service kept failing. Use /retry to try again, or /model to switch \"\n",
    ),
    (
        "        if failure_reason.startswith(\"session_persistence_failed\") or \"session storage\" in error_str:\n"
        "            if failure_reason.endswith(\":disk\") or \"disk\" in error_str:\n",
        "        if failure_reason.startswith(\"session_persistence_failed\") or \"session storage\" in error_str:\n"
        "            from gateway import persona_errors as _persona\n"
        "            if _persona.enabled():\n"
        "                return _persona.storage()\n"
        "            if failure_reason.endswith(\":disk\") or \"disk\" in error_str:\n",
    ),
    (
        "        logger.warning(\"Agent turn failed; reply sanitized for chat. Detail: %s\", str(error_detail)[:500])\n"
        "        return (\n"
        "            \"⚠️ Something went wrong and I couldn't finish this reply. Use /retry to try again, \"\n"
        "            \"or /new to start a fresh conversation. Technical details are in the gateway log \"\n"
        "            \"(`hermes logs`).\")\n",
        "        logger.warning(\"Agent turn failed; reply sanitized for chat. Detail: %s\", str(error_detail)[:500])\n"
        "        from gateway import persona_errors as _persona\n"
        "        if _persona.enabled():\n"
        "            return _persona.failed_turn()\n"
        "        return (\n"
        "            \"⚠️ Something went wrong and I couldn't finish this reply. Use /retry to try again, \"\n"
        "            \"or /new to start a fresh conversation. Technical details are in the gateway log \"\n"
        "            \"(`hermes logs`).\")\n",
    ),
]

TURN_EDITS = [
    (
        "        return self._hmwa_add_failed_turn_notice(\n"
        "            f\"⚠️ Something went wrong and I couldn't finish this reply.{status_hint}\\n\"\n"
        "            \"Use /retry to try again, or /new to start a fresh conversation. \"\n"
        "            \"Technical details are in the gateway log (`hermes logs`).\",\n"
        "            PARTIAL_FAILED_TURN_NOTICE,\n"
        "        )\n",
        "        from gateway import persona_errors as _persona\n"
        "        if _persona.enabled():\n"
        "            return self._hmwa_add_failed_turn_notice(\n"
        "                _persona.failed_turn(status_code, status_hint), PARTIAL_FAILED_TURN_NOTICE)\n"
        "        return self._hmwa_add_failed_turn_notice(\n"
        "            f\"⚠️ Something went wrong and I couldn't finish this reply.{status_hint}\\n\"\n"
        "            \"Use /retry to try again, or /new to start a fresh conversation. \"\n"
        "            \"Technical details are in the gateway log (`hermes logs`).\",\n"
        "            PARTIAL_FAILED_TURN_NOTICE,\n"
        "        )\n",
    ),
    (
        "        _diag_lines = [\n"
        "            f\"⏱️ Agent inactive for {_timeout_mins} min — no tool calls or API responses.\"\n"
        "        ]\n"
        "        if _cur_tool:\n"
        "            _diag_lines.append(\n"
        "                f\"The agent appears stuck on tool `{_cur_tool}` ({_secs_ago:.0f}s since last \"\n"
        "                f\"activity, {_iter_progress}).\"\n"
        "            )\n"
        "        else:\n"
        "            _diag_lines.append(\n"
        "                f\"Last activity: {_last_desc} ({_secs_ago:.0f}s ago, \"\n"
        "                f\"{_iter_progress}). \"\n"
        "                \"The agent may have been waiting on an API response.\"\n"
        "            )\n"
        "        _diag_lines.append(\n"
        "            \"To increase the limit, set agent.gateway_timeout in config.yaml (value in seconds, 0 \"\n"
        "            \"= no limit) and restart the gateway.\\nTry again, or use /reset to start fresh.\"\n"
        "        )\n",
        "        from gateway import persona_errors as _persona\n"
        "        if _persona.enabled():\n"
        "            _diag_lines = [_persona.timeout(_timeout_mins)]\n"
        "        else:\n"
        "            _diag_lines = [\n"
        "                f\"⏱️ Agent inactive for {_timeout_mins} min — no tool calls or API responses.\"\n"
        "            ]\n"
        "            if _cur_tool:\n"
        "                _diag_lines.append(\n"
        "                    f\"The agent appears stuck on tool `{_cur_tool}` ({_secs_ago:.0f}s since last \"\n"
        "                    f\"activity, {_iter_progress}).\"\n"
        "                )\n"
        "            else:\n"
        "                _diag_lines.append(\n"
        "                    f\"Last activity: {_last_desc} ({_secs_ago:.0f}s ago, \"\n"
        "                    f\"{_iter_progress}). \"\n"
        "                    \"The agent may have been waiting on an API response.\"\n"
        "                )\n"
        "            _diag_lines.append(\n"
        "                \"To increase the limit, set agent.gateway_timeout in config.yaml (value in seconds, 0 \"\n"
        "                \"= no limit) and restart the gateway.\\nTry again, or use /reset to start fresh.\"\n"
        "            )\n",
    ),
    (
        "                await adapter.send(\n"
        "                    source.chat_id,\n"
        "                    \"❌ The background task couldn't start because no AI model sign-in is \"\n"
        "                    \"configured. Use /login, or run `hermes setup` on the host.\",\n"
        "                    metadata=_thread_metadata,\n"
        "                )\n",
        "                from gateway import persona_errors as _persona\n"
        "                await adapter.send(\n"
        "                    source.chat_id,\n"
        "                    _persona.no_model() if _persona.enabled() else (\n"
        "                        \"❌ The background task couldn't start because no AI model sign-in is \"\n"
        "                        \"configured. Use /login, or run `hermes setup` on the host.\"),\n"
        "                    metadata=_thread_metadata,\n"
        "                )\n",
    ),
]


def apply(path: Path, edits, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    if marker in text:
        raise SystemExit(f"refusing: patch marker already present in {path}")
    for old, new in edits:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"refusing: expected 1 match in {path}, found {count}:\n{old[:120]}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=False)
    os.chmod(BACKUP_ROOT, 0o700)
    for path in (RUN, TURN):
        shutil.copy2(path, BACKUP_ROOT / path.name)
        os.chmod(BACKUP_ROOT / path.name, 0o600)

    apply(RUN, RUN_EDITS, "persona_errors as _persona")
    apply(TURN, TURN_EDITS, "persona_errors as _persona")

    for path in (RUN, TURN, MODULE):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        print("compiled", path.name, hashlib.sha256(path.read_bytes()).hexdigest())

    diff_path = BACKUP_ROOT / "persona-errors.patch"
    parts = []
    for path in (RUN, TURN):
        import subprocess
        out = subprocess.run(
            ["diff", "-u", str(BACKUP_ROOT / path.name), str(path)],
            cwd=str(SRC), capture_output=True, text=True).stdout
        rel = f"gateway/{path.name}"
        lines = []
        for line in out.splitlines():
            if line.startswith("--- "):
                lines.append(f"--- a/{rel}")
            elif line.startswith("+++ "):
                lines.append(f"+++ b/{rel}")
            else:
                lines.append(line)
        parts.append("\n".join(lines) + "\n")
    diff_path.write_text("".join(parts), encoding="utf-8")
    os.chmod(diff_path, 0o600)
    print("backup:", BACKUP_ROOT)
    print("diff:", diff_path, diff_path.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
