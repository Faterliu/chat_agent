"""固定版本图片清理增量部署；失败还原本次源码，不回写旧业务数据库。"""
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
import tempfile
from datetime import datetime, timezone

HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME / 'hermes-agent'
WORK = Path(__file__).resolve().parent
PATCH = WORK / 'hermes-v0.21.5-image-retention.patch'
MANIFEST = WORK / 'hermes-v0.21.5-image-retention.json'
PYTHON = REPO / 'venv/bin/python'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def staged_checks(manifest):
    """只在临时目录应用补丁；通过实际入站缓存函数验证触发点。"""
    with tempfile.TemporaryDirectory(prefix='hermes-image-staging-') as name:
        stage = Path(name)
        for rel, hashes in manifest['files'].items():
            if hashes['before'] is not None:
                target = stage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, target)
        subprocess.run(['git', 'apply', str(PATCH)], cwd=stage, check=True)
        for rel, hashes in manifest['files'].items():
            assert digest(stage / rel) == hashes['after']
            compile((stage / rel).read_text(encoding='utf-8'), rel, 'exec')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   IMAGE_POLICY_SOURCE=str(stage / 'gateway/image_cache_policy.py'))
        result = subprocess.run([str(PYTHON), str(WORK / 'hermes-test-image-cache-policy.py')],
                                env=env, capture_output=True, text=True)
        print(result.stdout + result.stderr, flush=True)
        assert result.returncode == 0
        # 单独进程，真实 gateway.platforms.base 依赖，合成 HERMES_HOME，无 API 请求。
        script = '''
import os, sys, json, time, importlib.util
from pathlib import Path
home, repo, stage = map(Path, sys.argv[1:])
os.environ['HERMES_HOME'] = str(home)
os.chdir(repo); sys.path.insert(0, str(repo))
spec = importlib.util.spec_from_file_location('gateway.image_cache_policy', stage/'gateway/image_cache_policy.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module; spec.loader.exec_module(module)
import gateway.platforms.base as base
exec(compile((stage/'gateway/platforms/base.py').read_text(encoding='utf-8'), 'base.staged.py', 'exec'), base.__dict__)
(home/'sessions').mkdir(parents=True, exist_ok=True)
(home/'sessions/sessions.json').write_text('{}', encoding='utf-8')
cache = base.get_image_cache_dir()
for i in range(49):
    p=cache/f'img_{i:03}.jpg'; p.write_bytes(b'\\xff\\xd8\\xfftest')
    os.utime(p, (time.time()-200000+i, time.time()-200000+i))
assert base.cleanup_image_cache(max_age_hours=24) == 0
assert len(list(cache.glob('*.jpg'))) == 49
fresh=Path(base.cache_image_from_bytes(b'\\xff\\xd8\\xfffresh'))
assert fresh.exists() and len(list(cache.glob('*.jpg'))) == 30
assert not (cache/'img_019.jpg').exists() and (cache/'img_020.jpg').exists()
print('INTEGRATION OK: 24h expiry replaced; actual cache write 49->50->30')
'''
        test_home = stage / 'test-home'
        test_home.mkdir()
        result = subprocess.run([str(PYTHON), '-c', script, str(test_home), str(REPO), str(stage)],
                                env=env, capture_output=True, text=True)
        print(result.stdout + result.stderr, flush=True)
        assert result.returncode == 0


def main():
    os.umask(0o077)
    os.chdir(REPO)
    spec = importlib.util.spec_from_file_location('deploy_common', WORK / 'deploy-deepseek-endpoint.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert digest(PATCH) == manifest['patch_sha256']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == manifest['commit']
    for rel, hashes in manifest['files'].items():
        path = REPO / rel
        assert (digest(path) if path.exists() else None) == hashes['before'], 'Source changed: ' + rel
    assert '[LOCAL PATCH] QQ group messages must be PASSIVE replies' in (REPO / 'gateway/platforms/qqbot/adapter.py').read_text(encoding='utf-8')
    subprocess.run(['git', 'apply', '--check', str(PATCH)], check=True)
    for patch_name, expected in (
        ('/var/lib/hermes/user-scope-v0.21.5.patch', 'db2f6f68328faf55a94f026a7eb727875a9714aab5f369025a011fc57117cd7d'),
        ('/var/lib/hermes/token-v0.21.5.patch', 'e4cd9c316eb97d7f4415b7ab78f93b12a18bc4cea6e7a2e1e02040bd0b2b3888')):
        assert digest(Path(patch_name)) == expected
        # 文件已叠加后续修补，不把旧补丁无法整份反向套用误判成当前代码故障。
    staged_checks(manifest)
    subprocess.run([str(PYTHON), '/var/lib/hermes/social-admin.py', 'preflight'], check=True)
    found = helper.pids()
    state = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
    assert len(found) == 1 and state['pid'] == found[0] and state['gateway_state'] == 'running' and state['active_agents'] == 0
    sessions = json.loads((HOME / 'sessions/sessions.json').read_text(encoding='utf-8'))
    assert not any(isinstance(v, dict) and v.get('active_turn_token') for v in sessions.values())
    backup = HOME / 'backups' / ('image-retention-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    print('BACKUP ' + str(backup), flush=True)
    original = {rel: (REPO / rel).read_bytes() for rel, h in manifest['files'].items() if h['before'] is not None}
    protected = {rel: digest(HOME / rel) for rel in ('config.yaml', '.env')}
    for rel in ('config.yaml', '.env', 'sessions/sessions.json'):
        shutil.copy2(HOME / rel, backup / Path(rel).name)
    for name in ('state.db', 'social.db'):
        with sqlite3.connect((HOME / name).as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(backup / name) as dest:
            src.backup(dest)
    (backup / 'source-before.patch').write_bytes(subprocess.check_output(['git', 'diff', '--binary']))
    changed = subprocess.check_output(['git', 'ls-files', '-m', '-o', '--exclude-standard', '-z']).decode('utf-8').split('\0')
    with tarfile.open(backup / 'source-before.tar.gz', 'w:gz') as tar:
        for rel in sorted(set(p for p in changed if p)):
            if (REPO / rel).is_file():
                tar.add(REPO / rel, arcname=rel)
    shutil.copy2(PATCH, backup / PATCH.name)
    shutil.copy2(MANIFEST, backup / MANIFEST.name)
    # 不备份媒体副本，避免被清理图片仍永久残留在备份；当前生产图片目录为空。
    before_images = len(list((HOME / 'cache/images').iterdir()))
    for p in backup.iterdir():
        os.chmod(p, 0o600)
    offset = (HOME / 'logs/agent.log').stat().st_size
    helper.stop()
    applied = False
    try:
        for rel, data in original.items():
            assert (REPO / rel).read_bytes() == data, 'Source changed during backup'
        subprocess.run(['git', 'apply', str(PATCH)], check=True)
        applied = True
        for rel, hashes in manifest['files'].items():
            assert digest(REPO / rel) == hashes['after']
        # 初始化本月标记，不等下一次小时维护；策略本身只处理图片。
        sys.path.insert(0, str(REPO))
        from gateway.image_cache_policy import maintain_image_cache
        maintain_image_cache(HOME / 'cache/images', HOME)
        helper.start(backup)
        helper.connections(offset)
        assert {rel: digest(HOME / rel) for rel in protected} == protected
        subprocess.run(['git', 'apply', '-R', '--check', str(PATCH)], check=True)
        result = {'backup': str(backup), 'old_pid': found[0], 'pid': helper.pids()[0],
                  'qq_connected': True, 'weixin_connected': True, 'regression_tests': 11,
                  'integration': 'actual cache write 49->50->30; no 24h image expiry',
                  'images_before': before_images, 'images_after': len(list((HOME / 'cache/images').iterdir())),
                  'config_and_env_unchanged': True, 'patch_sha256': manifest['patch_sha256']}
        (backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
    except BaseException:
        if applied:
            if helper.pids():
                helper.stop()
            for rel, data in original.items():
                helper.atomic(REPO / rel, data, (REPO / rel).stat().st_mode & 0o777)
            (REPO / 'gateway/image_cache_policy.py').unlink(missing_ok=True)
        if not helper.pids():
            helper.start(backup, rollback=True)
        print('ROLLED BACK SOURCE; kept current business data', flush=True)
        raise


if __name__ == '__main__':
    main()
