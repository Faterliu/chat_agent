"""更换已验证的 DeepSeek 中转配置；密钥只从标准输入读取，不写入源码。"""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone

import yaml

HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME / 'hermes-agent'
PATTERN = r'^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'
STARTER = Path('/var/lib/hermes/start-chat-agent.sh')
MODEL = 'cn:deepseek-v4-flash'
BASE = 'https://wb.yinxingye.space/v1'


def pids():
    result = subprocess.run(['pgrep', '-f', PATTERN], capture_output=True, text=True)
    assert result.returncode in (0, 1)
    return [int(p) for p in result.stdout.split()]


def atomic(path, data, mode):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.api-change-')
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def stop():
    found = pids()
    assert len(found) == 1, '只允许停止单个项目网关'
    os.kill(found[0], signal.SIGTERM)
    for _ in range(45):
        if not pids():
            return
        time.sleep(1)
    raise RuntimeError('网关没有正常退出，不强杀或启动重复实例')


def start(backup, rollback=False):
    assert not pids()
    env = dict(os.environ, HERMES_HOME=str(HOME))
    # 由 .env 和低内存启动器提供配置，避免维护进程的旧环境覆盖。
    for name in ('DEEPSEEK_API_KEY', 'DEEPSEEK_BASE_URL'):
        env.pop(name, None)
    with (backup / ('gateway-rollback.log' if rollback else 'gateway.log')).open('ab') as out:
        subprocess.Popen(['/usr/bin/nohup', str(STARTER)], cwd='/var/lib/hermes', env=env,
                         stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)


def connections(offset):
    log = HOME / 'logs/agent.log'
    for _ in range(45):
        with log.open('rb') as stream:
            stream.seek(offset)
            recent = stream.read().decode('utf-8', errors='replace')
        if 'qqbot connected' in recent and 'Connected account=' in recent and len(pids()) == 1:
            return
        time.sleep(1)
    raise RuntimeError('两平台未在验证窗口内连接')


def env_updated(text, name, value):
    assert re.fullmatch(r'[A-Za-z0-9_:/\.\-]+', value), '配置值格式不符合本次维护条件'
    lines = text.splitlines(keepends=True)
    active = [i for i, line in enumerate(lines) if re.match(r'^\s*(?:export\s+)?' + re.escape(name) + r'\s*=', line)]
    assert len(active) <= 1, '存在重复环境变量，停止覆盖'
    replacement = name + '=' + value + '\n'
    if active:
        lines[active[0]] = replacement
    else:
        if lines and not lines[-1].endswith('\n'):
            lines[-1] += '\n'
        lines.append(replacement)
    return ''.join(lines)


def main():
    os.umask(0o077)
    supplied = json.load(sys.stdin)
    key = supplied['api_key']
    assert supplied['base_url'].rstrip('/') == BASE
    assert key and re.fullmatch(r'[A-Za-z0-9_\-]+', key)
    original_pids = pids()
    assert len(original_pids) == 1
    state = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
    assert state.get('pid') == original_pids[0] and state.get('gateway_state') == 'running' and state.get('active_agents') == 0
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == 'f97608f178d1ffeca59860195ab7da295f7c8e5f'
    assert '[LOCAL PATCH] QQ group messages must be PASSIVE replies' in (REPO / 'gateway/platforms/qqbot/adapter.py').read_text(encoding='utf-8')
    subprocess.run(['git', 'apply', '-R', '--check', '/var/lib/hermes/social-v0.21.5.patch'], cwd=REPO, check=True, capture_output=True)
    assert STARTER.is_file()
    subprocess.run(['bash', '-n', str(STARTER)], check=True)
    subprocess.run([str(REPO / 'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'preflight'], check=True)
    paths = [HOME / 'config.yaml', HOME / '.env']
    original = [p.read_bytes() for p in paths]
    modes = [p.stat().st_mode & 0o777 for p in paths]
    cfg = yaml.safe_load(original[0].decode('utf-8'))
    assert cfg['model']['provider'] == 'deepseek'
    expected = copy.deepcopy(cfg)
    expected['model']['base_url'] = BASE
    expected['model']['default'] = MODEL
    tree = yaml.compose(original[0].decode('utf-8'))
    model_nodes = [v for k, v in tree.value if k.value == 'model']
    assert len(model_nodes) == 1
    updates = []
    for name, value in [('base_url', BASE), ('default', MODEL)]:
        nodes = [v for k, v in model_nodes[0].value if k.value == name]
        assert len(nodes) == 1
        updates.append((nodes[0].start_mark.index, nodes[0].end_mark.index, json.dumps(value)))
    new_cfg = original[0].decode('utf-8')
    for start_at, end_at, value in sorted(updates, reverse=True):
        new_cfg = new_cfg[:start_at] + value + new_cfg[end_at:]
    assert yaml.safe_load(new_cfg) == expected, '配置有非目标变更'
    new_env = env_updated(original[1].decode('utf-8'), 'DEEPSEEK_API_KEY', key)
    new_env = env_updated(new_env, 'DEEPSEEK_BASE_URL', BASE)
    from dotenv import dotenv_values
    before_env = dict(dotenv_values(stream=__import__('io').StringIO(original[1].decode('utf-8'))))
    after_env = dict(dotenv_values(stream=__import__('io').StringIO(new_env)))
    before_env.update(DEEPSEEK_API_KEY=key, DEEPSEEK_BASE_URL=BASE)
    assert after_env == before_env, '环境有非目标变更'
    backup = HOME / 'backups' / ('api-change-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for p in paths:
        shutil.copy2(p, backup / p.name)
    if (HOME / 'cron/jobs.json').is_file():
        shutil.copy2(HOME / 'cron/jobs.json', backup / 'jobs.json')
    for name in ('state.db', 'social.db'):
        with sqlite3.connect(f'file:{HOME / name}?mode=ro', uri=True, timeout=3) as src, sqlite3.connect(backup / name) as dest:
            src.backup(dest)
    diff = subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO)
    (backup / 'source-before.patch').write_bytes(diff)
    with tarfile.open(backup / 'source-before.tar.gz', 'w:gz') as archive:
        for rel in ('gateway/platforms/qqbot/adapter.py', 'tools/gateway_user_scope.py', 'tools/qq_reminder.py', 'gateway/social_runtime.py', 'tools/social_tool.py', 'tools/social_store.py'):
            archive.add(REPO / rel, arcname=rel)
    for p in backup.iterdir():
        p.chmod(0o600)
    assert [p.read_bytes() for p in paths] == original and pids() == original_pids
    assert json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8')).get('active_agents') == 0
    offset = (HOME / 'logs/agent.log').stat().st_size
    stop()
    try:
        atomic(paths[0], new_cfg.encode('utf-8'), modes[0])
        atomic(paths[1], new_env.encode('utf-8'), 0o600)
        start(backup)
        connections(offset)
        sys.path.insert(0, str(REPO))
        sys.dont_write_bytecode = True
        os.environ['HERMES_HOME'] = str(HOME)
        from dotenv import load_dotenv
        load_dotenv(HOME / '.env', override=True)
        from hermes_cli.runtime_provider import resolve_runtime_provider
        runtime = resolve_runtime_provider(requested='deepseek', target_model=MODEL)
        assert runtime['api_key'] == key and runtime['base_url'].rstrip('/') == BASE
        # 通过 Hermes 解析的路由与 OpenAI 客户端验证流式文本通路。
        from openai import OpenAI
        began = time.monotonic()
        with OpenAI(api_key=runtime['api_key'], base_url=runtime['base_url'], timeout=30, max_retries=0) as client:
            with client.chat.completions.create(model=MODEL, messages=[{'role': 'user', 'content': 'Reply only: OK'}], max_tokens=128, stream=True) as stream:
                parts = []
                for chunk in stream:
                    for choice in chunk.choices:
                        if choice.delta.content:
                            parts.append(choice.delta.content)
            assert ''.join(parts).strip(), '流式测试没有回复'
        subprocess.run([str(REPO / 'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'verify'], check=True)
        current = pids()
        assert len(current) == 1
        process_env = Path(f'/proc/{current[0]}/environ').read_bytes().split(b'\0')
        assert b'MALLOC_ARENA_MAX=2' in process_env and b'MALLOC_TRIM_THRESHOLD_=131072' in process_env
        assert subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO) == diff
        assert yaml.safe_load(paths[0].read_text(encoding='utf-8')) == expected
        status = dict(x.split(':', 1) for x in Path(f'/proc/{current[0]}/status').read_text(encoding='utf-8').splitlines() if ':' in x)
        result = {'backup': str(backup), 'old_pid': original_pids[0], 'pid': current[0], 'model': MODEL,
                  'base_url': BASE, 'qq_connected': True, 'weixin_connected': True,
                  'streaming_test_passed': True, 'stream_and_route_verification_seconds': round(time.monotonic() - began, 2),
                  'rss_mib': round(int(status['VmRSS'].split()[0]) / 1024, 2), 'source_unchanged': True}
        (backup / 'result.json').write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps(result), flush=True)
    except BaseException:
        if len(pids()) == 1:
            stop()
        assert not pids(), '存在网关，停止恢复以避免重复实例'
        for p, content, mode in zip(paths, original, modes):
            atomic(p, content, mode)
        restore_offset = (HOME / 'logs/agent.log').stat().st_size
        start(backup, rollback=True)
        connections(restore_offset)
        print(json.dumps({'rollback': True, 'backup': str(backup), 'pid': pids()[0]}), flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        # 网络异常可能包含敏感请求信息，仅报告类型。
        print(json.dumps({'success': False, 'error_class': type(exc).__name__}), flush=True)
        sys.exit(1)
