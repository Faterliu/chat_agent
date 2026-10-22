"""验收通过才切换单网关；仅还原源码与压缩字段，保留最新业务数据和密钥。"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

import yaml

WORK = Path('/var/lib/hermes/token-work-20261009')
HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME/'hermes-agent'
spec = importlib.util.spec_from_file_location('gateway_maintenance', WORK/'deploy-deepseek-endpoint.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def replace_cap(data, expected, replacement):
    text = data.decode('utf-8')
    cfg = yaml.safe_load(text)
    assert cfg['compression']['threshold_tokens'] == expected
    target = copy.deepcopy(cfg)
    target['compression']['threshold_tokens'] = replacement
    tree = yaml.compose(text)
    node = next(v for k, v in tree.value if k.value == 'compression')
    nodes = [v for k, v in node.value if k.value == 'threshold_tokens']
    assert len(nodes) == 1
    node = nodes[0]
    text = text[:node.start_mark.index]+str(replacement)+text[node.end_mark.index:]
    assert yaml.safe_load(text) == target
    return text.encode('utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    os.umask(0o077)
    manifest = json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    report = json.loads((WORK/'model-report-verified.json').read_text(encoding='utf-8'))
    assert report['passed'] is True and report['paired_complete'] is True and report['patch_sha256'] == manifest['patch_sha256']
    assert report['cumulative_tokens'] <= 100000 and report['cumulative_calls'] <= report['authorized_max_calls']
    assert '218 tests passed, 0 failed' in (WORK/'tests-final.log').read_text(encoding='utf-8')
    patch = WORK/'hermes-v0.21.5-token.patch'
    assert digest(patch) == manifest['patch_sha256']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == manifest['commit']
    for rel, hashes in manifest['files'].items():
        assert digest(REPO/rel) == hashes['before'], '源码已变化，停止覆盖'
    assert '[LOCAL PATCH] QQ group messages must be PASSIVE replies' in (REPO/'gateway/platforms/qqbot/adapter.py').read_text(encoding='utf-8')
    subprocess.run(['git', 'apply', '-R', '--check', '/var/lib/hermes/social-v0.21.5.patch'], cwd=REPO, check=True, capture_output=True)
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=REPO, check=True, capture_output=True)
    subprocess.run([str(REPO/'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'preflight'], check=True)
    found = helper.pids()
    state = json.loads((HOME/'gateway_state.json').read_text(encoding='utf-8'))
    assert len(found) == 1 and state['pid'] == found[0] and state['gateway_state'] == 'running' and state['active_agents'] == 0
    original_cfg = (HOME/'config.yaml').read_bytes()
    original_env = (HOME/'.env').read_bytes()
    cfg_mode = (HOME/'config.yaml').stat().st_mode & 0o777
    new_cfg = replace_cap(original_cfg, 256000, 64000)
    cfg = yaml.safe_load(new_cfg.decode('utf-8'))
    assert cfg['agent']['reasoning_effort'] == 'medium' and cfg['model']['default'] == 'cn:deepseek-v4.1-flash'
    original_source = {rel: (REPO/rel).read_bytes() for rel in manifest['files']}
    modes = {rel: (REPO/rel).stat().st_mode & 0o777 for rel in manifest['files']}
    backup = HOME/'backups'/('token-optimization-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for name in ('config.yaml', '.env'):
        shutil.copy2(HOME/name, backup/name)
    if (HOME/'cron/jobs.json').exists():
        shutil.copy2(HOME/'cron/jobs.json', backup/'jobs.json')
    for name in ('state.db', 'social.db'):
        with sqlite3.connect(f'file:{HOME/name}?mode=ro', uri=True, timeout=3) as src, sqlite3.connect(backup/name) as dest:
            src.backup(dest)
    with tarfile.open(backup/'source-before.tar.gz', 'w:gz') as archive:
        for rel in list(manifest['files'])+['gateway/platforms/qqbot/adapter.py', 'tools/gateway_user_scope.py', 'tools/social_store.py']:
            archive.add(REPO/rel, arcname=rel)
    (backup/'source-before.patch').write_bytes(subprocess.check_output(['git', 'diff', '--binary'], cwd=REPO))
    for name in ('manifest.json', 'hermes-v0.21.5-token.patch', 'tests-final.log', 'model-report-verified.json'):
        shutil.copy2(WORK/name, backup/name)
    for path in backup.iterdir():
        path.chmod(0o600)
    assert (HOME/'config.yaml').read_bytes() == original_cfg and (HOME/'.env').read_bytes() == original_env
    assert all((REPO/rel).read_bytes() == data for rel, data in original_source.items())
    assert helper.pids() == found and json.loads((HOME/'gateway_state.json').read_text(encoding='utf-8'))['active_agents'] == 0
    offset = (HOME/'logs/agent.log').stat().st_size
    helper.stop()
    try:
        subprocess.run(['git', 'apply', str(patch)], cwd=REPO, check=True, capture_output=True)
        helper.atomic(HOME/'config.yaml', new_cfg, cfg_mode)
        for rel, hashes in manifest['files'].items():
            assert digest(REPO/rel) == hashes['after']
        helper.start(backup)
        helper.connections(offset)
        subprocess.run([str(REPO/'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'verify'], check=True)
        subprocess.run(['git', 'apply', '-R', '--check', str(patch)], cwd=REPO, check=True, capture_output=True)
        assert (HOME/'.env').read_bytes() == original_env
        assert (HOME/'config.yaml').read_bytes() == new_cfg
        current = helper.pids()
        assert len(current) == 1
        env = Path(f'/proc/{current[0]}/environ').read_bytes().split(b'\0')
        assert b'MALLOC_ARENA_MAX=2' in env and b'MALLOC_TRIM_THRESHOLD_=131072' in env
        status = dict(line.split(':', 1) for line in Path(f'/proc/{current[0]}/status').read_text(encoding='utf-8').splitlines() if ':' in line)
        shutil.copy2(patch, '/var/lib/hermes/token-v0.21.5.patch')
        shutil.copy2(WORK/'manifest.json', '/var/lib/hermes/token-v0.21.5-manifest.json')
        result = {'backup': str(backup), 'old_pid': found[0], 'pid': current[0], 'qq_connected': True, 'weixin_connected': True,
                  'compression_threshold_tokens': 64000, 'reasoning_effort': 'medium', 'env_unchanged': True,
                  'rss_mib': round(int(status['VmRSS'].split()[0])/1024, 2), 'patch_sha256': manifest['patch_sha256']}
        (backup/'result.json').write_text(json.dumps(result), encoding='utf-8')
        (WORK/'deployment-result.json').write_text(json.dumps(result), encoding='utf-8')
        print(json.dumps(result), flush=True)
    except BaseException:
        if len(helper.pids()) == 1:
            helper.stop()
        assert not helper.pids(), '仍存在网关，拒绝启动重复实例'
        for rel, data in original_source.items():
            helper.atomic(REPO/rel, data, modes[rel])
        current_cfg = (HOME/'config.yaml').read_bytes()
        if yaml.safe_load(current_cfg.decode('utf-8'))['compression']['threshold_tokens'] == 64000:
            helper.atomic(HOME/'config.yaml', replace_cap(current_cfg, 64000, 256000), cfg_mode)
        restore_offset = (HOME/'logs/agent.log').stat().st_size
        helper.start(backup, rollback=True)
        helper.connections(restore_offset)
        print(json.dumps({'rollback': True, 'backup': str(backup), 'pid': helper.pids()[0]}), flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        print(json.dumps({'success': False, 'error_class': type(exc).__name__}), flush=True)
        sys.exit(1)
