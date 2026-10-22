"""最多八次真实请求；合成对话、隔离工具，无实际投递。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile

import httpx
from dotenv import dotenv_values

WORK = Path('/var/lib/hermes/token-work-20261009')
HOME = Path('/var/lib/hermes/.hermes')
MODEL = 'cn:deepseek-v4.1-flash'
BASE = 'https://wb.yinxingye.space/v1'
LIMIT = 100000
MAX_CALLS = 8
REPORT = WORK/'model-report-verified.json'


def execute_isolated(version, scenario, call):
    target = Path(tempfile.mkdtemp(prefix=f'execute-{version}-{scenario}-', dir=WORK))
    shutil.copytree(WORK/f'{version}-home', target, dirs_exist_ok=True)
    args = json.loads(call['function']['arguments'])
    assert call['function']['name'] == 'social_manage'
    code = '''import sys,json,os
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace as NS
repo,home,args=sys.argv[1:];sys.path.insert(0,repo);os.environ['HERMES_HOME']=home
from tools.social_store import SocialStore,BJ
from tools.gateway_user_scope import GatewayUserScope
from gateway import social_runtime as rt
now=datetime(2026,10,9,12,tzinfo=BJ).timestamp()
rt.SocialStore=lambda h:SocialStore(h,now)
rows={'session-A':{'source':'qqbot','user_id':'A','chat_type':'dm','chat_id':'chat-A'}}
agent=NS(_session_db=NS(get_session=lambda sid:rows.get(sid)),session_id='session-A',platform='qqbot',_user_id='A',_chat_type='dm',_chat_id='chat-A')
ctx=NS(source=NS(platform='qqbot',user_id='A',chat_type='dm',chat_id='chat-A'),inbound_message_id='m2')
rt.bind_turn(agent,ctx)
result=rt.tool(agent,json.loads(args));assert json.loads(result)['success'],result
print(result)
'''
    result = subprocess.check_output([str(WORK/'.venv/bin/python'), '-c', code, str(WORK/version), str(target), json.dumps(args)], text=True)
    return json.loads(result.splitlines()[-1])


def payloads(max_output=512):
    persona = json.loads((WORK/'xiaoyun.json').read_text(encoding='utf-8'))['system_prompt']
    fixtures = {v: json.loads((WORK/f'{v}-fixture.json').read_text(encoding='utf-8')) for v in ('before', 'after')}
    scenarios = [
        ('ordinary', '今天的晚霞挺好看，颜色像橘子汽水。', 'empty'),
        ('batch', '水彩还在继续练习。我明天下午16点去公园拍照，18点结束，回来再和你聊。', 'pending'),
        ('birthday', '订阅一个测试生日：测试对象，公历10月9日，每年北京时间9点发送“生日功能测试”，我确认订阅。', 'empty'),
        ('after_batch', '我明晚19点准备试着烤面包，20点结束，做好了再跟你分享。', 'empty'),
    ]
    batches = []
    for scenario, user, dynamic in scenarios:
        for version in ('before', 'after'):
            f = fixtures[version]
            messages = [{'role': 'system', 'content': persona}, {'role': 'user', 'content': user+f[dynamic]}]
            if scenario == 'after_batch':
                call = {'id': 'call-test', 'type': 'function', 'function': {'name': 'social_manage', 'arguments': json.dumps({
                    'action': 'batch', 'operations': [{'action': 'record', 'kind': 'event', 'summary': '明晚烤面包',
                    'when': 'tomorrow 20:00', 'text': '面包出炉怎么样？'}]}, ensure_ascii=False)}}
                # 真正在临时 SocialStore 中执行，结果作为假工具消息回放。
                result = execute_isolated(version, scenario, call)
                messages += [{'role': 'assistant', 'content': None, 'tool_calls': [call]},
                             {'role': 'tool', 'tool_call_id': 'call-test', 'content': json.dumps(result, ensure_ascii=False,
                                  separators=(',', ':')) if version == 'after' else json.dumps(result, ensure_ascii=False)}]
            p = {'model': MODEL, 'messages': messages, 'tools': f['tools'], 'max_tokens': max_output, 'reasoning_effort': 'medium', 'stream': False}
            batches.append((scenario, version, p))
    return batches


def validate(scenario, version, message):
    calls = message.get('tool_calls') or []
    text = message.get('content') or ''
    if scenario in ('ordinary', 'after_batch'):
        assert not calls, '不应追加工具'
        assert text.strip(), '没有自然回复'
        for word in ['记住了', '记好了', '记下来了', '记录了', '后台', '工具参数', '20点问', '22点问', '加入跟进']:
            assert word not in text, '静默维护泄露'
        return
    assert len(calls) == 1 and calls[0]['function']['name'] == 'social_manage', '应仅调用一次 social'
    args = json.loads(calls[0]['function']['arguments'])
    if scenario == 'batch':
        assert args['action'] == 'batch'
        ops = args['operations']
        assert len(ops) == 2
        assert any(o['action'] == 'review' and o['id'] == 'pending-test' for o in ops)
        records = [o for o in ops if o['action'] == 'record']
        assert len(records) == 1 and records[0]['kind'] == 'event'
        assert records[0]['when'] in ('tomorrow 18:00', '2026-10-10T18:00:00+08:00', '2026-10-10 18:00')
        for word in ['记住了', '记好了', '记下来了', '记录了', '后台', '问候']:
            assert word not in text
    else:
        assert args['action'] == 'birthday_add' and args['confirmed'] is True
        assert (args['subject'], args['month'], args['day']) == ('测试对象', 10, 9)
        assert args.get('clock', '09:00') == '09:00' and args['text'] == '生日功能测试'
    execute_isolated(version, scenario, calls[0])


def main():
    # 必须收到用户对这两项新测试上限的授权后，才以这组显式参数执行。
    assert sys.argv[1:] == ['--authorized-max-calls', '18', '--max-output', '1024']
    assert not REPORT.exists(), '已有最终真实请求记录，禁止自动重跑'
    prior = json.loads((WORK/'model-report-third.json').read_text(encoding='utf-8'))
    assert prior['cumulative_calls'] == 10 and prior['cumulative_tokens'] == 47993
    requests = payloads(max_output=1024)
    starting_total = prior['cumulative_tokens']
    # 已实测输入最高 before=4948/after=4282；预留场景、附加时间字段和格式余量。
    # 单次预留完整1024输出；每次仍按实际usage重新检查剩余预算。
    input_reservations = [5500 if v == 'before' else 5000 for _, v, _ in requests]
    bounds = [n+1024 for n in input_reservations]
    assert starting_total+sum(bounds) <= LIMIT, '预估超过累计十万预算'
    key = dotenv_values(HOME/'.env').get('DEEPSEEK_API_KEY')
    assert key
    report = {'model': MODEL, 'reasoning_effort': 'medium', 'max_output': 1024, 'budget': LIMIT,
              'preflight_conservative_estimate': sum(bounds), 'calls': [],
              'authorized_max_calls': 18, 'prior_calls': 10, 'prior_tokens': starting_total,
              'patch_sha256': json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))['patch_sha256']}
    total = starting_total
    with httpx.Client(timeout=httpx.Timeout(55, connect=10), follow_redirects=False) as client:
        for i, (scenario, version, p) in enumerate(requests):
            assert i < MAX_CALLS and len(report['calls'])+report['prior_calls'] < report['authorized_max_calls'] and total+sum(bounds[i:]) <= LIMIT
            began = time.monotonic()
            res = client.post(BASE+'/chat/completions', headers={'Authorization': 'Bearer '+key}, json=p)
            entry = {'scenario': scenario, 'version': version, 'http_status': res.status_code, 'seconds': round(time.monotonic()-began, 2)}
            report['calls'].append(entry)
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            assert res.status_code == 200, '提供方请求失败，停止预算内验证'
            body = res.json()
            usage = body.get('usage') or {}
            prompt = int(usage.get('prompt_tokens', 0))
            cached = int(usage.get('prompt_cache_hit_tokens', (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)))
            output = int(usage.get('completion_tokens', 0))
            assert prompt > 0 and output > 0, '缺失预算计数，停止'
            charged = max(prompt, cached+int(usage.get('prompt_cache_miss_tokens', 0)))+output
            total += charged
            message = body['choices'][0]['message']
            entry.update(input=prompt, cache_read=cached, output=output, usage=usage,
                         tool_calls=len(message.get('tool_calls') or []), message=message,
                         finish_reason=body['choices'][0]['finish_reason'])
            report['cumulative_tokens'] = total
            report['cumulative_calls'] = len(report['calls'])+report['prior_calls']
            try:
                assert prompt <= input_reservations[i] and output <= 1024, '提供方usage超过保守预留，停止'
                validate(scenario, version, message)
                entry['passed'] = True
            except Exception as exc:
                entry['passed'] = False
                entry['validation_error'] = str(exc)
                REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                raise
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k: v for k, v in entry.items() if k not in ('message', 'usage')}), flush=True)
    old = sum(c['input'] for c in report['calls'] if c['version'] == 'before')
    new = sum(c['input'] for c in report['calls'] if c['version'] == 'after')
    assert total <= LIMIT
    assert new < old and len(report['calls']) == 8
    report.update(passed=True, paired_complete=True, input_before=old, input_after=new, input_reduction_percent=round(100*(old-new)/old, 2))
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('calls', 'baseline_before')}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'passed': False, 'error_class': type(exc).__name__, 'reason': str(exc) if isinstance(exc, AssertionError) else '隔离验证失败'}), flush=True)
        sys.exit(1)
