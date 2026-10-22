"""基于本次生产源码快照生成独立增量补丁，保留原有本地补丁。"""
from pathlib import Path
import difflib
import hashlib

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "source/social-work"
BASE, UPDATED = WORK / "base", WORK / "updated"


def edit(name, old, new):
    text = (BASE / name).read_text(encoding="utf-8")
    assert text.count(old) == 1, name
    out = UPDATED / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


edit("toolsets.py", '    "memory": _ts(', '    "social": _ts("本人私聊主动关心与生日订阅", ["social_manage"]),\n    "memory": _ts(')
edit("hermes_cli/tools_config.py", 'CONFIGURABLE_TOOLSETS = [',
     'CONFIGURABLE_TOOLSETS = [\n    ("social", "🌱 主动关心与生日", "本人私聊 social_manage"),')
p = UPDATED / "hermes_cli/tools_config.py"
s = p.read_text(encoding="utf-8").replace('_DEFAULT_OFF_TOOLSETS = {', '_DEFAULT_OFF_TOOLSETS = {"social", ')
p.write_text(s, encoding="utf-8", newline="\n")
edit("hermes_cli/toolset_scope.py", '_TOOLSET_PLATFORM_RESTRICTIONS = {',
     '_TOOLSET_PLATFORM_RESTRICTIONS = {"social": {"qqbot", "weixin"}, ')
edit("tools/tool_search.py", '_DIRECT_SURFACE_TOOLSETS = frozenset({',
     '_DIRECT_SURFACE_TOOLSETS = frozenset({"social", ')
edit("agent/inline_tool_executors.py", '    "cronjob_manage": _cronjob,',
     '    "cronjob_manage": _cronjob,\n    "social_manage": _tool("gateway.social_runtime", "tool", agent=lambda agent, ctx: agent, args=lambda agent, ctx: ctx.args),')
# _tool 的参数规则需遵循现有接口；使用显式执行器避免任何参数映射歧义。
p = UPDATED / "agent/inline_tool_executors.py"
s = p.read_text(encoding="utf-8")
s = s.replace('def _memory(agent, args: dict, ctx: InlineToolContext) -> Any:',
              'def _social(agent, args: dict, ctx: InlineToolContext) -> Any:\n    from gateway.social_runtime import tool\n    return tool(agent, args)\n\n\ndef _memory(agent, args: dict, ctx: InlineToolContext) -> Any:')
s = s.replace('"social_manage": _tool("gateway.social_runtime", "tool", agent=lambda agent, ctx: agent, args=lambda agent, ctx: ctx.args),', '"social_manage": _social,')
p.write_text(s, encoding="utf-8", newline="\n")
edit("gateway/run_inbound.py", '        _quick_key = self._session_key_for_source(source)\n        _reply = await self._hm_pending_reply_intercepts',
     '        from gateway.social_runtime import note_inbound as _social_note_inbound\n        await _social_note_inbound(source, event, is_internal)\n\n        _quick_key = self._session_key_for_source(source)\n        _reply = await self._hm_pending_reply_intercepts')
edit("gateway/run_turn_runner.py", '            kwargs = {"conversation_history": agent_history, "task_id": ctx.session_id}',
     '            from gateway.social_runtime import bind_turn as _social_bind_turn\n            _social_context = _social_bind_turn(agent, ctx)\n            if _social_context:\n                if isinstance(api_message, str):\n                    api_message += _social_context\n                elif isinstance(api_message, list):\n                    api_message = [*api_message, {"type": "text", "text": _social_context}]\n                if persist_user_message_override is None:\n                    persist_user_message_override = ctx.message\n            kwargs = {"conversation_history": agent_history, "task_id": ctx.session_id}')
edit("gateway/run.py", '    chores += [\n        (5, "Channel directory refresh",',
     '    from gateway.social_runtime import SocialRuntime\n    _social_runtime = SocialRuntime(get_hermes_home(), runner, loop)\n    chores.append((1, "Social private followups", _social_runtime.tick))\n    chores += [\n        (5, "Channel directory refresh",')
p = UPDATED / "gateway/run.py"
s = p.read_text(encoding="utf-8").replace('    logger.info("Gateway housekeeping stopped")', '    _social_runtime.stop()\n    logger.info("Gateway housekeeping stopped")')
p.write_text(s, encoding="utf-8", newline="\n")

chunks = []
for file in sorted(UPDATED.rglob("*.py")):
    name = file.relative_to(UPDATED).as_posix()
    base = BASE / name
    before = base.read_text(encoding="utf-8").splitlines(keepends=True) if base.exists() else []
    after = file.read_text(encoding="utf-8").splitlines(keepends=True)
    chunks.append(f"diff --git a/{name} b/{name}\n")
    if not base.exists():
        chunks.append("new file mode 100644\n")
    chunks.extend(difflib.unified_diff(before, after, fromfile=f"a/{name}" if base.exists() else "/dev/null", tofile=f"b/{name}"))
patch = ROOT / "documents/patches/hermes-v0.21.5-social.patch"
patch.write_text("".join(chunks), encoding="utf-8", newline="\n")
print("patch_sha256=" + hashlib.sha256(patch.read_bytes()).hexdigest())
