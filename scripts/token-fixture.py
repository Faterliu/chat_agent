"""隔离构造实际工具定义与合成用户状态；禁止网络和实际投递。"""
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace as NS
from datetime import datetime

repo, home, target = map(Path, sys.argv[1:4])
os.environ['HERMES_HOME'] = str(home)
sys.path.insert(0, str(repo))
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline'))
import yaml
cfg = yaml.safe_load(Path('/var/lib/hermes/.hermes/config.yaml').read_text(encoding='utf-8'))
home.mkdir(mode=0o700, exist_ok=True)
# 只复制工具配置；人格由本地已核验源提供，没有凭据或真实用户身份。
safe = {'platform_toolsets': cfg['platform_toolsets'], 'tool_search': cfg.get('tool_search', {}), 'social': {'enabled': True},
        'model': {'provider': 'deepseek', 'default': 'cn:deepseek-v4.1-flash', 'context_length': 1000000}}
(home/'config.yaml').write_text(yaml.safe_dump(safe, allow_unicode=True), encoding='utf-8')
from hermes_cli.tools_config import _get_platform_tools
import model_tools
model_tools._resolve_active_context_length = lambda: 1000000
# 合成提供方能力；仅保留生产已经存在的 Vision schema，不调用视觉接口。
from tools.registry import registry
registry._tools['vision_analyze'].check_fn = lambda: True
enabled = list(_get_platform_tools(safe, 'qqbot', include_default_mcp_servers=False))
defs = model_tools.get_tool_definitions(enabled_toolsets=enabled, quiet_mode=True)
from tools.social_store import SocialStore, BJ
from tools.gateway_user_scope import GatewayUserScope
from gateway import social_runtime as rt
class Clock(datetime):
    @staticmethod
    def now(zone):
        return datetime(2026, 10, 9, 12, tzinfo=BJ)
rt.datetime = Clock
s = SocialStore(home, Clock.now(BJ).timestamp())
s.seed('qqbot', 'A')
s.note_inbound('qqbot', 'A', 'm1')
scope = GatewayUserScope('qqbot', 'A', 'dm', 'chat-A')
turn = s.bind(scope, 'session-A', 'm1')
rows = {'session-A': {'source': 'qqbot', 'user_id': 'A', 'chat_type': 'dm', 'chat_id': 'chat-A'}}
agent = NS(_session_db=NS(get_session=lambda sid: rows.get(sid)), session_id='session-A',
           platform='qqbot', _user_id='A', _chat_type='dm', _chat_id='chat-A')
ctx = NS(source=NS(platform='qqbot', user_id='A', chat_type='dm', chat_id='chat-A'), inbound_message_id='m1')
rt.SocialStore = lambda h: SocialStore(h, Clock.now(BJ).timestamp())
empty = rt.bind_turn(agent, ctx)
item = s.operate(turn, {'action': 'record', 'kind': 'topic', 'summary': '练习水彩，还在继续', 'text': '水彩画得怎么样？'})
# 两个版本用相同合成 ID，严格成对比较输入。
with s.tx() as db:
    db.execute('UPDATE followups SET id=? WHERE id=?', ('pending-test', item['id']))
s.note_inbound('qqbot', 'A', 'm2'); ctx.inbound_message_id = 'm2'
pending = rt.bind_turn(agent, ctx)
batch_result = rt.tool(agent, {'action': 'batch', 'operations': [{'action': 'review', 'id': 'pending-test'}]})
from tools.qq_reminder import reminder_schema
from tools.session_search_tool import SESSION_SEARCH_SCHEMA
target.write_text(json.dumps({'tools': defs, 'empty': empty, 'pending': pending, 'batch_result': batch_result,
    'reminder': reminder_schema(), 'search': SESSION_SEARCH_SCHEMA}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'tools': [t['function']['name'] for t in defs], 'schema_chars': len(json.dumps(defs, ensure_ascii=False)),
                  'empty_chars': len(empty), 'pending_chars': len(pending)}))
