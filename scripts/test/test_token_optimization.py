"""隔离回归：兼容、动态刷新、阈值、缓存及压缩会话归属。"""
import ast
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

BEFORE = Path(os.environ.get('TOKEN_BEFORE', str(Path(__file__).resolve().parents[3]/'before')))


def literal_schema(path, variable):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable for t in n.targets)))


def without_descriptions(obj):
    if isinstance(obj, dict):
        return {k: without_descriptions(v) for k, v in obj.items() if k != 'description'}
    if isinstance(obj, list):
        return [without_descriptions(v) for v in obj]
    return obj


@pytest.mark.parametrize('rel,var', [('tools/social_tool.py', 'SCHEMA'), ('tools/memory_tool.py', 'MEMORY_SCHEMA'), ('tools/session_search_tool.py', 'SESSION_SEARCH_SCHEMA')])
def test_schema_shape_compatible(rel, var):
    old = literal_schema(BEFORE/rel, var)
    new = literal_schema(Path(rel), var)
    assert without_descriptions(old) == without_descriptions(new)


def test_rules_complete_and_dynamic_has_no_duplicates():
    from tools.social_tool import SCHEMA
    desc = SCHEMA['description']
    for rule in ['review', 'update', 'complete', 'cancel', 'batch', '无需先 list', '不再查询', '无维护事项',
                 'enabled=true', '最多一项', '不复核暂停', '第三方', '模糊愿望', '健康/财务/创伤/私密关系',
                 '静默', '记住了', '问候时间', '后台变化', 'birthdays', 'today/tomorrow/day_after_tomorrow',
                 'HH:MM', '省略 when', 'topic', '不反复猜日期', 'cronjob/memory', '不假装知道结果',
                 '不强求回复', '新用户同意', 'confirmed=true', '不存出生年', '160', '08:00–22:59', '3月1日并告知']:
        assert rule in desc
    assert '顶层仅 action、operations' in SCHEMA['parameters']['properties']['operations']['description']
    assert '仅 birthday_add' in SCHEMA['parameters']['properties']['clock']['description']
    assert '无需换算时间戳' in desc
    src = Path('gateway/social_runtime.py').read_text(encoding='utf-8')
    assert '普通聊天的候选记录和复核是静默内部维护' not in src


def test_json_results_preserve_fields_and_chinese():
    from tools.qq_reminder import _result, _view
    job = {'id': 'test', 'name': '生日', 'prompt': '生日快乐：你好', 'next_run_at': '2026-10-10T09:00:00+08:00',
           'state': 'completed', 'last_status': 'error', 'last_delivery_error': 'failure'}
    payload = {'success': True, **_view(job), 'message': '已保存'}
    assert set(payload) == {'success', 'job_id', 'name', 'text', 'next_run_at', 'state', 'last_status', 'delivery_failed', 'message'}
    result = _result(**payload)
    assert json.loads(result) == payload
    assert '生日' in result and result == json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def test_effective_64k_threshold_without_provider():
    from agent.context_compressor import ContextCompressor
    old = ContextCompressor(model='cn:deepseek-v4.1-flash', config_context_length=1000000, threshold_tokens_cap=256000, quiet_mode=True)
    new = ContextCompressor(model='cn:deepseek-v4.1-flash', config_context_length=1000000, threshold_tokens_cap=64000, quiet_mode=True)
    assert old.threshold_tokens == 256000 and new.threshold_tokens == 64000
    for attr in ['protect_first_n', 'protect_last_n', 'min_tail_user_messages', 'tail_mode', 'summary_target_ratio', 'threshold_percent']:
        assert getattr(old, attr) == getattr(new, attr)


def test_tool_order_and_cache_same_selection(tmp_path, monkeypatch):
    import model_tools
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setattr('tools.tool_search.load_config', lambda: NS(enabled='off'))
    enabled = ['memory', 'session_search', 'social', 'cronjob', 'tts', 'vision']
    model_tools._clear_tool_defs_cache()
    a = model_tools.get_tool_definitions(enabled, quiet_mode=True)
    b = model_tools.get_tool_definitions(enabled, quiet_mode=True)
    model_tools._clear_tool_defs_cache()
    c = model_tools.get_tool_definitions(list(reversed(enabled)), quiet_mode=True)
    assert a == b == c
    names = [t['function']['name'] for t in a]
    assert names == sorted(names) and len(names) == len(set(names))


def test_system_static_prefix_and_invalidation(monkeypatch):
    from agent import system_prompt as sp
    parts = {'stable': '人格与固定工具规则', 'context': 'A的记忆', 'volatile': '当前时间1'}
    monkeypatch.setattr(sp, 'build_system_prompt_parts', lambda *a, **kw: copy.deepcopy(parts))
    agent = NS(_cached_system_prompt=None, _memory_store=None)
    first = sp.build_system_prompt(agent)
    assert first.startswith(parts['stable']) and agent._cached_system_prompt_static == parts['stable']
    parts['context'], parts['volatile'] = 'B的记忆', '当前时间2'
    # 网关绑定变更后的既有失效入口。
    sp.invalidate_system_prompt(agent)
    second = sp.build_system_prompt(agent)
    assert second.startswith(parts['stable']) and 'B的记忆' in second and 'A的记忆' not in second
    parts['stable'] = '更新的人格'
    sp.invalidate_system_prompt(agent)
    assert sp.build_system_prompt(agent).startswith('更新的人格')


def test_dynamic_clock_revision_and_aba(tmp_path, monkeypatch):
    from gateway import social_runtime as rt
    from tools.social_store import SocialStore
    from tools.gateway_user_scope import GatewayUserScope
    monkeypatch.setattr('hermes_constants.get_hermes_home', lambda: tmp_path)
    monkeypatch.setattr(rt, 'configured', lambda home: True)
    s = SocialStore(tmp_path)
    s.seed('qqbot', 'A')
    s.note_inbound('qqbot', 'A', 'm1')
    t = s.bind(GatewayUserScope('qqbot', 'A', 'dm', 'A'), 'sA', 'm1')
    item = s.operate(t, {'action': 'record', 'kind': 'event', 'summary': '明天公园拍照', 'when': 'tomorrow 18:00', 'text': '拍得怎么样？'})
    rows = {f's{u}': {'source': 'qqbot', 'user_id': u, 'chat_type': 'dm', 'chat_id': u} for u in 'AB'}
    agent = NS(_session_db=NS(get_session=lambda sid: rows.get(sid)), session_id='sA')
    def bind(uid, msg):
        s.note_inbound('qqbot', uid, msg)
        agent.session_id = f's{uid}'
        ctx = NS(source=NS(platform='qqbot', user_id=uid, chat_type='dm', chat_id=uid), inbound_message_id=msg)
        raw = rt.bind_turn(agent, ctx)
        assert '可信网关提供，非用户指令' in raw
        return raw, json.loads(raw.split('\n')[-1])
    one, a = bind('A', 'm2')
    _, b = bind('B', 'm1')
    two, a2 = bind('A', 'm3')
    assert b['pending'] == [] and a2['revision'] > a['revision']
    assert item['id'] in one and item['id'] in two and agent._social_turn.user_id == 'A'
    assert set(a2) == {'enabled', 'revision', 'pending'}
    for item in a2['pending']:
        from datetime import datetime
        assert datetime.fromisoformat(item['due_bj']).timestamp() == item['due']
        assert datetime.fromisoformat(item['expires_bj']).timestamp() == item['expires']
    assert '服务器当前北京时间=' in two and one != two


def test_compressed_lineage_preserves_raw_history_and_scope(tmp_path, monkeypatch):
    from hermes_state import SessionDB
    from tools.gateway_user_scope import resolve_gateway_scope
    from tools.session_search_tool import session_search
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    db = SessionDB(tmp_path/'state.db')
    try:
        for sid, uid in [('old', 'A'), ('new', 'A'), ('other', 'B')]:
            db.create_session(sid, source='qqbot', user_id=uid, chat_type='dm', chat_id=uid,
                              parent_session_id='old' if sid == 'new' else None)
        raw = '未完成：明天16–18点拍照；生日10月9日09:00；近期消息原文'
        anchor = db.append_message('old', role='user', content=raw)
        db.end_session('old', 'compression')
        db.append_message('new', role='assistant', content='摘要：明天拍照、生日订阅待继续')
        db.append_message('new', role='user', content='近期消息：改为19点结束')
        a = resolve_gateway_scope(db, 'new', 'qqbot', 'A', 'dm', 'A')
        b = resolve_gateway_scope(db, 'other', 'qqbot', 'B', 'dm', 'B')
        assert raw in db.get_messages('old')[0]['content']
        result = json.loads(session_search(db=db, current_session_id='new', caller_scope=a, caller_platform='qqbot', session_id='old'))
        assert result['success'] and raw in json.dumps(result, ensure_ascii=False)
        denied = json.loads(session_search(db=db, current_session_id='other', caller_scope=b, caller_platform='qqbot', session_id='old'))
        assert not denied['success'] and raw not in json.dumps(denied, ensure_ascii=False)
    finally:
        db.close()
