"""微信私聊对齐：仅增加 sticker 工具集和 emoji 配图平台，不开放群聊。"""
import argparse
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
from datetime import datetime, timezone

HOME = Path('/var/lib/hermes/.hermes')
REPO = HOME / 'hermes-agent'
COMMIT = 'f97608f178d1ffeca59860195ab7da295f7c8e5f'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    os.environ['HERMES_HOME'] = str(HOME)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    import yaml
    from dotenv import dotenv_values
    from utils import atomic_roundtrip_yaml_save
    from hermes_cli.config import load_config_readonly
    from hermes_cli.tools_config import _get_platform_tools
    from gateway import emoji_stickers
    from tools.sticker_tool import load_manifest

    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    cfg_path = HOME / 'config.yaml'
    original = cfg_path.read_bytes()
    before = yaml.safe_load(original.decode('utf-8'))
    after = copy.deepcopy(before)
    qq = list(before['platform_toolsets']['qqbot'])
    wx = list(before['platform_toolsets']['weixin'])
    assert set(qq) - set(wx) <= {'sticker'}, 'Other QQ-only tools require a separate review'
    if 'sticker' not in wx:
        insert_at = wx.index('tts') if 'tts' in wx else len(wx)
        wx.insert(insert_at, 'sticker')
    after['platform_toolsets']['weixin'] = wx
    platforms = list(after['display']['emoji_stickers']['platforms'])
    if 'weixin' not in platforms:
        platforms.append('weixin')
    after['display']['emoji_stickers']['platforms'] = platforms
    assert set(wx) == set(qq)
    assert dotenv_values(HOME / '.env').get('WEIXIN_GROUP_POLICY') == 'disabled'
    assert before.get('platforms', {}).get('weixin', {}).get('extra', {}).get('group_policy', 'disabled') == 'disabled'
    state = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
    pid = state['pid']
    assert state['gateway_state'] == 'running' and Path(f'/proc/{pid}').exists()
    command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    assert command[:4] == [str(REPO / 'venv/bin/python').encode(), str(REPO / 'hermes').encode(), b'gateway', b'run']
    instances = subprocess.check_output(['pgrep', '-f', r'^/var/lib/hermes/\.hermes/hermes-agent/venv/bin/python /var/lib/hermes/\.hermes/hermes-agent/hermes gateway run$'], text=True).split()
    assert instances == [str(pid)]
    assert len(load_manifest()) > 0
    assert _get_platform_tools(after, 'qqbot') == _get_platform_tools(after, 'weixin')
    print(json.dumps({'apply': args.apply, 'tools_before': before['platform_toolsets']['weixin'],
        'tools_after': wx, 'emoji_platforms_before': before['display']['emoji_stickers']['platforms'],
        'emoji_platforms_after': platforms, 'mapping_preserved': True, 'group_policy': 'disabled',
        'restart_required': False, 'pid': pid}, ensure_ascii=False), flush=True)
    if not args.apply or before == after:
        return
    subprocess.run([str(REPO / 'venv/bin/python'), '/var/lib/hermes/social-admin.py', 'preflight'], check=True)
    backup = HOME / 'backups' / ('weixin-parity-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    shutil.copy2(cfg_path, backup / 'config.yaml')
    shutil.copy2(HOME / '.env', backup / 'environment-before')
    for name in ('state.db', 'social.db'):
        with sqlite3.connect((HOME / name).as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(backup / name) as dest:
            src.backup(dest)
    with tarfile.open(backup / 'source-before.tar.gz', 'w:gz') as tar:
        for name in ('gateway/platforms/base.py', 'gateway/platforms/weixin.py', 'gateway/emoji_stickers.py', 'tools/sticker_tool.py'):
            tar.add(REPO / name, arcname=name)
    (backup / 'source-before.patch').write_bytes(subprocess.check_output(['git', 'diff', '--binary']))
    shutil.copy2(Path(__file__), backup / 'deploy-weixin-parity.py')
    protected = {str(p): sha(p) for p in (HOME / '.env', HOME / 'stickers/manifest.json',
        REPO / 'gateway/platforms/base.py', REPO / 'gateway/platforms/weixin.py',
        REPO / 'gateway/emoji_stickers.py', REPO / 'tools/sticker_tool.py')}
    for p in backup.iterdir():
        os.chmod(p, 0o600)
    # 防止备份窗口内并行素材维护改动配置，被本脚本覆盖。
    assert cfg_path.read_bytes() == original, 'Config changed during preflight; retry from current state'
    try:
        atomic_roundtrip_yaml_save(cfg_path, after)
        assert yaml.safe_load(cfg_path.read_text(encoding='utf-8')) == after
        assert cfg_path.stat().st_mode & 0o777 == 0o600
        live = load_config_readonly()
        assert _get_platform_tools(live, 'qqbot') == _get_platform_tools(live, 'weixin')
        for key, sid in before['display']['emoji_stickers']['mapping'].items():
            text, ids = emoji_stickers.prepare('测试' + key, 'weixin')
            assert (text, ids) == ('测试', [sid]), (key, sid, text, ids)
        for p, expected in protected.items():
            assert sha(Path(p)) == expected, 'Unexpected collateral change: ' + p
        current = json.loads((HOME / 'gateway_state.json').read_text(encoding='utf-8'))
        assert current['pid'] == pid and current['gateway_state'] == 'running'
        result = {'backup': str(backup), 'pid': pid, 'hot_reload': True,
            'weixin_toolsets': wx, 'emoji_platforms': platforms,
            'mapping_count': len(before['display']['emoji_stickers']['mapping']),
            'mapping_order_preserved': list(live['display']['emoji_stickers']['mapping']) == list(before['display']['emoji_stickers']['mapping']),
            'group_policy': 'disabled', 'config_sha256_before': hashlib.sha256(original).hexdigest(),
            'config_sha256_after': sha(cfg_path), 'sources_and_env_unchanged': True}
        (backup / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except BaseException:
        # 本次唯一生产写入是 config；只回滚目标两项，保留并行修改的其他配置。
        current = yaml.safe_load(cfg_path.read_text(encoding='utf-8'))
        current['platform_toolsets']['weixin'] = before['platform_toolsets']['weixin']
        current['display']['emoji_stickers']['platforms'] = before['display']['emoji_stickers']['platforms']
        atomic_roundtrip_yaml_save(cfg_path, current)
        print('ROLLED BACK TARGET KEYS', flush=True)
        raise


if __name__ == '__main__':
    main()
