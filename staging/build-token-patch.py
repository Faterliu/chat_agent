"""从服务器快照生成说明去重、时间展示和紧凑返回的增量补丁。"""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / 'token-work'
FILES = ['tools/social_tool.py', 'gateway/social_runtime.py', 'tools/qq_reminder.py',
         'tools/memory_tool.py', 'tools/session_search_tool.py']

SOCIAL = (
    '本人私聊主动关心与公历生日。可信状态提供当前北京时间、enabled、revision、pending；相对日期以当前时间为准，不沿用历史日期。'
    '每轮依据真实消息复核所有 pending：仍有效 review、变化 update、结束 complete、拒绝 cancel；不复核暂停发送。'
    'pending 的 due_bj/expires_bj 是北京时间，调度由服务端负责；review 只传 id，无需换算时间戳或重算问候时间。'
    '优先一次 batch 完成全部复核及最多一项新增；直接用 pending，无需先 list，成功后不再查询；无维护事项不调用。'
    'enabled=true 可从自然聊天记录本人具体未来事件 event 或未结束日常话题 topic，无需刻意设置提醒；'
    '禁止模糊愿望、第三方事件、健康/财务/创伤/私密关系。普通候选静默维护，只自然接话，不宣告记住了、记下来了、记录了、'
    '加入跟进、会提醒，不展示存储/调度、问候时间、工具参数、后台变化或历史测试故障。显式提醒、生日订阅或管理查询才确认。'
    'list 仅明确查询：默认 followups，生日 birthdays，全部 all；不检查无关生日。'
    'when 支持 today/tomorrow/day_after_tomorrow，可加结束时间 HH:MM（tomorrow 17:00），或结束时间 ISO/YYYY-MM-DD。'
    '日期不明省略 when 仅存 event 候选不发送；topic 省略 when。事件结束2小时后或次日18点，topic 24小时后。'
    'text 是当前人格的最终正文，后台不调模型，不假装知道结果、不强求回复。失败不反复猜日期，不以 cronjob/memory 代替；Cron 仅显式提醒。'
    '拒绝关心立即 settings enabled=false，新用户同意后开启；关闭不影响生日/Cron。'
    '生日须明确确认 confirmed=true；subject 简称，month/day 公历月日，不存出生年，只通知订阅本人；'
    'text≤160字，默认北京时间09:00，可选08:00–22:59；非闰年2月29日按3月1日并告知。'
)
MEMORY = (
    'Store compact, durable cross-session facts; injected each turn. Prefer ONE atomic operations batch for all changes; '
    'budget checks the final result. If full, batch shorten/remove stale entries with additions. Do not repeat a successful update. '
    'Single changes may use action/content/old_text. Task procedures, pitfalls and task-specific preferences belong in the relevant skill, '
    'not memory. Skip trivial/recoverable facts, raw dumps, progress, completed logs and temporary TODOs; use session_search for history.\n'
    "TARGETS: 'user' = who the user is (name, role, preferences, style). 'memory' = your "
    'notes (environment, conventions, tool quirks, lessons). '
    "QQ/Weixin private chat: read with target='group' only on request, without copying to private memory. Group chat cannot read private memory."
)
MEM_PARAMS = {
    'action': "Single change; read only target=group in private chat. Omit for batch.",
    'target': 'memory/user: current chat scope; group: read own shared group memory from private chat.',
    'content': 'Required for add/replace. Replace overwrites the WHOLE matched entry: include everything to keep.',
    'old_text': 'Required for replace/remove: unique substring locating the entry, not a text patch.',
    'new_text': 'Alias of content (content wins); full replacement entry.',
    'operations': 'Preferred atomic batch of action/content?/old_text?; budget checked on final state.',
}
SEARCH = (
    'Recall DB history without LLM: query searches (top result hydrated); no args browses recent sessions; '
    'session_id reads a session; session_id+around_message_id scrolls. Resolve @session:<profile>/<id> via profile and session_id. '
    'Messaging callers may only access verified user scope/current profile. Use result link verbatim inline. '
    'Search covers history only: inspect any user-provided direct source first; history misses do not establish source absence.'
)
SEARCH_PARAMS = {
    'query': 'Keywords, phrases or boolean query; omit to browse. Ignored for scrolling.',
    'limit': 'Discovery sessions: default 3, max 10; increase for topics spanning sessions.',
    'sort': 'Discovery ranking bias: omit=relevance; newest=latest progress; oldest=origins. Not a time bound.',
    'detail': 'Discovery: adaptive hydrates top hit, anchor only for others; full gives every hit bookends and complete anchor window.',
    'after': 'Discovery inclusive session-start lower bound: ISO date/time or 7d/24h/2w. Only if user specifies timeframe.',
    'before': 'Discovery exclusive session-start upper bound: ISO date/time (date=UTC midnight) or 7d (older than week). Only if user specifies timeframe.',
    'exclude_session_ids': 'Discovery: exclude inspected sessions and lineage; max 20.',
    'session_id': 'Read returned session ID; add around_message_id to scroll.',
    'around_message_id': 'Scroll anchor: match_message_id or an ID from a prior window.',
    'window': 'Scroll messages each side, anchor included; clamp 1–20, default 5.',
    'role_filter': 'Comma-separated roles; default user,assistant; add tool for tool output or use tool alone.',
    'profile': 'CLI: read-only alternate profile from session link; omit=current. Messaging: cross-profile denied.',
}


def schema_descriptions(text, variable, main, params):
    tree = ast.parse(text)
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets))
    edits = []
    lines = text.splitlines(keepends=True)
    # AST columns count UTF-8 bytes.
    def offset(line, col):
        return sum(map(len, lines[:line-1])) + len(lines[line-1].encode('utf-8')[:col].decode('utf-8'))
    def walk(d, path=()):
        if not isinstance(d, ast.Dict):
            return
        for k, v in zip(d.keys, d.values):
            key = ast.literal_eval(k)
            if key == 'description':
                value = main if not path else params.get(path[-1]) if path == ('parameters', 'properties', path[-1]) else None
                if value:
                    edits.append((offset(v.lineno, v.col_offset), offset(v.end_lineno, v.end_col_offset), json.dumps(value, ensure_ascii=False)))
            walk(v, path+(key,))
    walk(node)
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start]+value+text[end:]
    return text


def compact_json(text):
    # 仅 json.dumps 返回表示；不改变任何字段或数据。
    return text.replace('ensure_ascii=False)', 'ensure_ascii=False, separators=(",", ":"))').replace('json.dumps(target_error)', 'json.dumps(target_error, separators=(",", ":"))')


def main():
    patch = []
    manifest = {'commit': 'f97608f178d1ffeca59860195ab7da295f7c8e5f', 'files': {}}
    for rel in FILES:
        src = ROOT/'before'/rel
        old = src.read_text(encoding='utf-8')
        new = old
        if rel == 'tools/social_tool.py':
            new = schema_descriptions(new, 'SCHEMA', SOCIAL, {})
            new = new.replace('"operations": {"type": "array",', '"operations": {"description": "batch 顶层仅 action、operations；其他参数放在各操作内，勿带 clock。", "type": "array",')
            new = new.replace('"clock": {"type": "string"}', '"clock": {"type": "string", "description": "仅 birthday_add 的北京时间 HH:MM，默认09:00；不是服务器当前时间。"}')
        elif rel == 'gateway/social_runtime.py':
            new = new.replace('            context = store.context(turn)\n',
                '            context = store.context(turn)\n'
                '            # 保留原始字段，附北京时间，避免模型自行换算 Unix 秒。\n'
                '            for item in context["pending"]:\n'
                '                for key in ("due", "expires"):\n'
                '                    value = item.get(key)\n'
                '                    item[key + "_bj"] = datetime.fromtimestamp(value, BJ).isoformat() if value is not None else None\n')
            start = new.index('                + "\\n普通聊天的候选记录')
            end = new.index('\n            )', start)
            new = new[:start]+new[end:]
            new = new.replace('；相对日期以此为准，不沿用历史对话日期。', '')
        elif rel == 'tools/memory_tool.py':
            new = schema_descriptions(new, 'MEMORY_SCHEMA', MEMORY, MEM_PARAMS)
        elif rel == 'tools/session_search_tool.py':
            new = schema_descriptions(new, 'SESSION_SEARCH_SCHEMA', SEARCH, SEARCH_PARAMS)
        elif rel == 'tools/qq_reminder.py':
            new = new.replace('提醒已保存，将通过当前网关投递；发送结果仍受当前平台权限和会话有效期限制。', '已保存；投递受平台权限及会话有效期限制。')
            new = new.replace('当前平台私聊文字提醒：create 创建，list 查看自己的提醒，remove 按 job_id 取消。', '本人私聊提醒：create 创建，list 查看，remove 按 job_id 取消。')
        new = compact_json(new)
        assert new != old
        compile(new, rel, 'exec')
        dest = ROOT/'after'/rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new, encoding='utf-8', newline='\n')
        manifest['files'][rel] = {'before': hashlib.sha256(src.read_bytes()).hexdigest(), 'after': hashlib.sha256(dest.read_bytes()).hexdigest()}
        patch.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile='a/'+rel, tofile='b/'+rel))
    target = ROOT.parent.parent/'patches/hermes-v0.21.5-token.patch'
    target.write_text(''.join(patch), encoding='utf-8', newline='\n')
    manifest['patch_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    (ROOT/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
