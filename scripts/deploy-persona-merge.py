"""合并小云人格重复规则；原子更新配置，逐轮生效，无需重启网关。"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

import yaml

HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME / 'hermes-agent'
SOURCE = Path('/var/lib/hermes/xiaoyun.json')
PATTERN = r'^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
sys.path.insert(0, str(REPO))
os.environ['HERMES_HOME'] = str(HOME)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True
from dotenv import load_dotenv
load_dotenv(HOME / '.env', override=False)
from hermes_cli.personality import render_personality_prompt


def entry(persona):
    result = {}
    for field in ('description', 'system_prompt', 'tone', 'style'):
        value = persona.get(field)
        if value is None and field in ('tone', 'style'):
            items = ((persona.get('personality') or {}).get('core_traits', []) if field == 'tone'
                     else (persona.get('speech_style') or {}).get('general', []))
            value = '；'.join(str(x).strip() for x in items if str(x).strip())
        result[field] = str(value or '').strip()
    return result


def pids():
    result = subprocess.run(['pgrep', '-f', PATTERN], capture_output=True, text=True)
    assert result.returncode in (0, 1), '无法核验进程'
    return [int(x) for x in result.stdout.split()]


def replace_atomic(path, content, mode):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.persona-merge-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def mapping_value(node, key):
    matches = [v for k, v in node.value if k.value == key]
    assert len(matches) == 1, '配置节点不唯一'
    return matches[0]


def render_channels(expected):
    # 只加载配置和解析方法，不构造 Agent、连接平台或调用模型。
    from gateway.config import Platform, load_gateway_config
    from gateway.run_config_loaders import GatewayConfigLoadersMixin
    obj = GatewayConfigLoadersMixin()
    obj.config = load_gateway_config()
    db = sqlite3.connect(f'file:{HOME / "state.db"}?mode=ro', uri=True)
    try:
        for platform in (Platform.QQBOT, Platform.WEIXIN):
            row = db.execute('SELECT chat_id FROM sessions WHERE source=? AND chat_type=\'dm\' '
                             'AND chat_id IS NOT NULL ORDER BY started_at DESC LIMIT 1',
                             (platform.value,)).fetchone()
            assert row, '缺少已验证的私聊路由'
            assert obj._get_system_prompt_for_channel(platform, row[0]) == expected, '实际频道人格不一致'
    finally:
        db.close()


def main():
    assert len(sys.argv) == 4 and sys.argv[1] in ('check', 'apply')
    old = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
    new_path = Path(sys.argv[3])
    new = json.loads(new_path.read_text(encoding='utf-8'))
    assert old['version'] == '1.2.2' and new['version'] == '1.2.3'
    assert new['tone'] == new['style'] == ''
    for key in ('id', 'name', 'nickname', 'description'):
        assert old[key] == new[key]
    old_sections = {s.splitlines()[0]: s for s in old['system_prompt'].split('\n\n')[1:]}
    for section in ('人格：', '关系熟悉度：', '犯错：', '任务处理：', '【定时提醒文案】'):
        assert old_sections[section] in new['system_prompt'], '发现不应改写的人格要求'
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == 'f97608f178d1ffeca59860195ab7da295f7c8e5f'
    found = pids()
    assert len(found) == 1, '必须只有一个网关'
    process_env = Path(f'/proc/{found[0]}/environ').read_bytes().split(b'\0')
    assert not any(x.startswith(b'HERMES_EPHEMERAL_SYSTEM_PROMPT=') and x.split(b'=', 1)[1] for x in process_env), '人格存在进程环境覆盖'
    assert not os.getenv('HERMES_EPHEMERAL_SYSTEM_PROMPT'), '检查进程存在人格环境覆盖'
    assert b'MALLOC_ARENA_MAX=2' in process_env and b'MALLOC_TRIM_THRESHOLD_=131072' in process_env
    state = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
    assert state.get('pid') == found[0] and state.get('gateway_state') == 'running'
    config = HOME / 'config.yaml'
    original_bytes = config.read_bytes()
    text = original_bytes.decode('utf-8')
    cfg = yaml.safe_load(text)
    assert cfg['display']['personality'] == 'xiaoyun'
    assert cfg['agent']['personalities']['xiaoyun'] == entry(old), '生产人格已变化，停止覆盖'
    if SOURCE.exists():
        assert entry(json.loads(SOURCE.read_text(encoding='utf-8'))) == entry(old), '远程人格源与现状不符，停止覆盖'
    render_channels(render_personality_prompt(entry(old)))
    tree = yaml.compose(text)
    personalities = mapping_value(mapping_value(tree, 'agent'), 'personalities')
    keys = [k for k, v in personalities.value if k.value == 'xiaoyun']
    assert len(keys) == 1
    start = keys[0].start_mark.line
    indent = keys[0].start_mark.column
    lines = text.splitlines(keepends=True)
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    block = yaml.safe_dump({'xiaoyun': entry(new)}, allow_unicode=True, sort_keys=False, width=10000)
    merged = ''.join(lines[:start]) + ''.join(' ' * indent + line + '\n' for line in block.splitlines()) + ''.join(lines[end:])
    candidate = yaml.safe_load(merged)
    expected = copy.deepcopy(cfg)
    expected['agent']['personalities']['xiaoyun'] = entry(new)
    assert candidate == expected, '存在非目标配置变更'
    expected_prompt = render_personality_prompt(entry(new))
    assert expected_prompt == new['system_prompt'] and len(expected_prompt) == 1644
    assert '[LOCAL PATCH] QQ group messages must be PASSIVE replies' in (REPO / 'gateway/platforms/qqbot/adapter.py').read_text(encoding='utf-8')
    patch = Path('/var/lib/hermes/social-v0.21.5.patch')
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == '11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f'
    subprocess.run(['git', 'apply', '-R', '--check', str(patch)], cwd=REPO, check=True, capture_output=True)
    report = {'before_chars': len(render_personality_prompt(entry(old))), 'after_chars': len(expected_prompt), 'pid': found[0]}
    if sys.argv[1] == 'check':
        print(json.dumps(dict(report, preflight_ok=True)), flush=True)
        return
    assert state.get('active_agents') == 0, '存在在途聊天，停止切换'
    subprocess.run([str(REPO / 'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'preflight'], check=True)
    os.umask(0o077)
    backup = HOME / 'backups' / ('persona-merge-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for name in ('config.yaml', '.env', 'cron/jobs.json'):
        path = HOME / name
        if path.exists():
            shutil.copy2(path, backup / Path(name).name)
    source_bytes = SOURCE.read_bytes() if SOURCE.exists() else None
    source_mode = SOURCE.stat().st_mode & 0o777 if SOURCE.exists() else 0o600
    if source_bytes is not None:
        (backup / 'xiaoyun-before.json').write_bytes(source_bytes)
    for name in ('state.db', 'social.db'):
        with sqlite3.connect(f'file:{HOME / name}?mode=ro', uri=True, timeout=3) as src, sqlite3.connect(backup / name) as dest:
            src.backup(dest)
    diff = subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO)
    (backup / 'source-before.patch').write_bytes(diff)
    with tarfile.open(backup / 'source-before.tar.gz', 'w:gz') as archive:
        for rel in ('hermes_cli/personality.py', 'gateway/run_config_loaders.py', 'gateway/platforms/qqbot/adapter.py', 'tools/gateway_user_scope.py', 'tools/qq_reminder.py', 'gateway/social_runtime.py', 'tools/social_tool.py', 'tools/social_store.py'):
            archive.add(REPO / rel, arcname=rel)
    for p in backup.iterdir():
        p.chmod(0o600)
    # 最后检查配置和网关状态，避免覆盖并行维护或在途聊天。
    current = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
    assert config.read_bytes() == original_bytes and current.get('active_agents') == 0 and pids() == found
    mode = config.stat().st_mode & 0o777
    try:
        replace_atomic(config, merged.encode('utf-8'), mode)
        replace_atomic(SOURCE, new_path.read_bytes(), source_mode)
        render_channels(expected_prompt)
        assert pids() == found
        assert subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO) == diff
        assert yaml.safe_load(config.read_text(encoding='utf-8')) == expected
        assert not (HOME / 'social.pause').exists()
        result = dict(report, backup=str(backup), qq_weixin_prompt_equal=True, no_restart=True,
                      other_config_unchanged=True, source_unchanged=True,
                      prompt_sha256=hashlib.sha256(expected_prompt.encode('utf-8')).hexdigest())
        (backup / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps(result), flush=True)
    except BaseException:
        replace_atomic(config, original_bytes, mode)
        if source_bytes is None:
            SOURCE.unlink(missing_ok=True)
        else:
            replace_atomic(SOURCE, source_bytes, source_mode)
        render_channels(render_personality_prompt(entry(old)))
        print('persona_merge_failed_original_config_restored_no_restart', flush=True)
        raise


if __name__ == '__main__':
    main()
