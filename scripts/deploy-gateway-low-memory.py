"""仅替换网关启动参数，备份、单实例检查与失败恢复均在服务器执行。"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import time
from datetime import datetime, timezone

HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME/'hermes-agent'
WRAPPER = Path('/var/lib/hermes/start-chat-agent.sh')
LAUNCHER = Path('/var/lib/hermes/.local/bin/hermes')
PATTERN = '^/var/lib/hermes/\\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\\.hermes/hermes-agent/hermes gateway run$'

def pids():
    result = subprocess.run(['pgrep','-f',PATTERN], capture_output=True, text=True)
    if result.returncode not in (0,1):
        raise RuntimeError('进程核验失败')
    return [int(x) for x in result.stdout.split()]

def stop():
    found = pids()
    if len(found) != 1:
        raise RuntimeError('只能停止一个已验证项目网关')
    os.kill(found[0], signal.SIGTERM)
    for _ in range(45):
        if not pids():
            return
        time.sleep(1)
    raise RuntimeError('网关未完成退出，停止部署，不强杀')

def start(optimized):
    assert not pids()
    env = dict(os.environ, HERMES_HOME=str(HOME),
               UV_DEFAULT_INDEX='https://pypi.tuna.tsinghua.edu.cn/simple',
               UV_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple',
               PIP_INDEX_URL='https://pypi.tuna.tsinghua.edu.cn/simple')
    for key in ('MALLOC_ARENA_MAX','MALLOC_TRIM_THRESHOLD_'):
        env.pop(key, None)
    if not optimized:
        env.update(old_allocator)
    command = [str(WRAPPER)] if optimized else [str(LAUNCHER),'gateway','run']
    with (backup/('gateway-optimized.log' if optimized else 'gateway-rollback.log')).open('ab') as log:
        subprocess.Popen(['/usr/bin/nohup',*command], cwd='/var/lib/hermes', env=env,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)

def sample(pid):
    status = dict(x.split(':',1) for x in Path(f'/proc/{pid}/status').read_text(encoding='utf-8').splitlines() if ':' in x)
    smaps = dict(x.split(':',1) for x in Path(f'/proc/{pid}/smaps_rollup').read_text(encoding='utf-8').splitlines() if ':' in x)
    return {'pid':pid,'rss_mib':round(int(status['VmRSS'].split()[0])/1024,2),
            'pss_mib':round(int(smaps['Pss'].split()[0])/1024,2),
            'threads':int(status['Threads'])}

os.umask(0o077)
found = pids()
assert len(found) == 1
state = json.loads((HOME/'gateway_state.json').read_text(encoding='utf-8'))
assert state.get('pid') == found[0] and state.get('gateway_state') == 'running' and state.get('active_agents') == 0, '网关忙碌或运行状态未核实，停止切换'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip() == 'f97608f178d1ffeca59860195ab7da295f7c8e5f'
assert not WRAPPER.exists(), '已有启动器，禁止覆盖'
patch = Path('/var/lib/hermes/social-v0.21.5.patch')
assert hashlib.sha256(patch.read_bytes()).hexdigest() == '11525fa3f197f953b24e860186c5fc2dfe0eb6e0c5a6b72d099049b3a130823f'
subprocess.run(['git','apply','-R','--check',str(patch)],cwd=REPO,check=True,capture_output=True)
assert '[LOCAL PATCH] QQ group messages must be PASSIVE replies' in (REPO/'gateway/platforms/qqbot/adapter.py').read_text(encoding='utf-8')
old_allocator = {}
for value in Path(f'/proc/{found[0]}/environ').read_bytes().split(b'\0'):
    for key in ('MALLOC_ARENA_MAX','MALLOC_TRIM_THRESHOLD_'):
        if value.startswith((key+'=').encode()):
            old_allocator[key] = value.decode().split('=',1)[1]
subprocess.run([str(REPO/'venv/bin/python'),'/var/lib/hermes/social-admin.py','preflight'],check=True)
backup = HOME/'backups'/('low-memory-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
before = sample(found[0])
for name in ('config.yaml','.env','cron/jobs.json'):
    path = HOME/name
    if path.is_file():
        shutil.copy2(path,backup/Path(name).name)
for name in ('state.db','social.db'):
    with sqlite3.connect(HOME/name,timeout=3) as src, sqlite3.connect(backup/name) as dest:
        src.backup(dest)
diff = subprocess.check_output(['git','diff','--binary'],cwd=REPO)
(backup/'source-before.patch').write_bytes(diff)
changed = subprocess.check_output(['git','diff','--name-only'],cwd=REPO,text=True).splitlines()
extras = ['gateway/social_runtime.py','tools/social_store.py','tools/social_tool.py','tools/gateway_user_scope.py','tools/qq_reminder.py']
with tarfile.open(backup/'source-before.tar.gz','w:gz') as archive:
    for name in sorted(set(changed+extras)):
        if (REPO/name).is_file():
            archive.add(REPO/name,arcname=name)
(backup/'before.json').write_text(json.dumps({'memory':before,'allocator':old_allocator}),encoding='utf-8')
for path in backup.iterdir():
    path.chmod(0o600)
log = HOME/'logs/agent.log'
offset = log.stat().st_size
subprocess.run(['bash','-n','/var/lib/hermes/start-chat-agent-low-memory.sh'],check=True)
stop()
try:
    WRAPPER.write_bytes(Path('/var/lib/hermes/start-chat-agent-low-memory.sh').read_bytes())
    WRAPPER.chmod(0o700)
    subprocess.run(['bash','-n',str(WRAPPER)],check=True)
    start(True)
    connected = False
    for _ in range(45):
        time.sleep(1)
        with log.open('rb') as stream:
            stream.seek(offset)
            text = stream.read().decode('utf-8',errors='replace')
        if 'qqbot connected' in text and 'Connected account=' in text:
            connected = True
            break
    assert connected and len(pids()) == 1, '两平台未连接或网关数量异常'
    subprocess.run([str(REPO/'venv/bin/python'),'/var/lib/hermes/social-admin.py','verify'],check=True)
    current = pids()[0]
    env = Path(f'/proc/{current}/environ').read_bytes().split(b'\0')
    assert b'MALLOC_ARENA_MAX=2' in env and b'MALLOC_TRIM_THRESHOLD_=131072' in env
    assert (HOME/'config.yaml').read_bytes() == (backup/'config.yaml').read_bytes()
    assert subprocess.check_output(['git','diff','--binary'],cwd=REPO) == diff
    after = sample(current)
    result = {'backup':str(backup),'before':before,'after_startup':after,'qq_connected':True,'weixin_connected':True,'source_and_config_unchanged':True}
    (backup/'result.json').write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps(result),flush=True)
except BaseException:
    if len(pids()) == 1:
        stop()
    if not pids():
        start(False)
        print('optimization_failed_original_allocator_restarted',flush=True)
    raise
