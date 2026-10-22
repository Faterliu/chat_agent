"""离线测量分配器；只构造假客户端和合成数据，不启动网关。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path('/var/lib/hermes/.hermes/hermes-agent')
CODE = r'''
import concurrent.futures, contextlib, ctypes, gc, io, json, socket, threading, time
from pathlib import Path
socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline profiling'))
def rss():
    line = next(x for x in Path('/proc/self/status').read_text(encoding='utf-8').splitlines() if x.startswith('VmRSS:'))
    return round(int(line.split()[1])/1024, 2)
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    import gateway.run, run_agent
    from openai import OpenAI
    from openai.types.chat import ChatCompletion
clients = []
barrier = threading.Barrier(10)
def worker(i):
    client = OpenAI(api_key='offline-test-key', base_url='https://offline.invalid/v1', max_retries=0)
    for _ in range(3):
        response = ChatCompletion.model_validate({'id':'offline','object':'chat.completion','created':0,'model':'deepseek-flash','choices':[{'index':0,'message':{'role':'assistant','content':'测试'*5000},'finish_reason':'stop'}]})
        request = [{'role':'user','content':'合成文本'*3000} for _ in range(20)]
        scratch = [bytearray(65536) for _ in range(150)]
        del response, request, scratch
    clients.append(client)
    barrier.wait(timeout=15)
started = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    list(pool.map(worker, range(10)))
result = {'rss_mib':rss(),'activity_seconds':round(time.monotonic()-started,3)}
gc.collect()
fn = ctypes.CDLL(None).malloc_trim
fn.argtypes, fn.restype = [ctypes.c_size_t], ctypes.c_int
fn(0)
result['after_manual_trim_mib'] = rss()
for client in clients:
    client.close()
print(json.dumps(result))
'''

folder = Path(tempfile.mkdtemp(prefix='hermes-memory-probe-', dir='/var/lib/hermes'))
try:
    variants = {'default':{}, 'arena2':{'MALLOC_ARENA_MAX':'2'},
                'arena2_trim':{'MALLOC_ARENA_MAX':'2','MALLOC_TRIM_THRESHOLD_':'131072'}}
    for name, settings in variants.items():
        env = dict(os.environ, HERMES_HOME=str(folder), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        for key in ('MALLOC_ARENA_MAX','MALLOC_TRIM_THRESHOLD_'):
            env.pop(key, None)
        env.update(settings)
        result = subprocess.run([str(REPO/'venv/bin/python'), '-c', CODE], cwd=REPO,
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=40)
        if result.returncode:
            raise RuntimeError('离线测量失败，退出码=' + str(result.returncode))
        print(json.dumps({'variant':name, **json.loads(result.stdout)}), flush=True)
finally:
    assert folder.parent == Path('/var/lib/hermes') and folder.name.startswith('hermes-memory-probe-') and not folder.is_symlink()
    shutil.rmtree(folder)
