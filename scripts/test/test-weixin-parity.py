"""微信私聊对齐回归：真实工具、最终出口和媒体封装，假传输，无外部请求。"""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

SOURCE = Path(os.environ.get('HERMES_SOURCE', '/var/lib/hermes/.hermes/hermes-agent'))
TEMP = tempfile.TemporaryDirectory(prefix='weixin-parity-test-')
HOME = Path(TEMP.name)
os.environ['HERMES_HOME'] = str(HOME)
sys.dont_write_bytecode = True
sys.path.insert(0, str(SOURCE))

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
LIB = HOME / 'stickers/packs/test'
LIB.mkdir(parents=True)
(LIB / 'test_png.png').write_bytes(PNG)
(LIB / 'test_gif.gif').write_bytes(GIF)
(HOME / 'stickers/manifest.json').write_text(json.dumps({'version': 1, 'stickers': [
    {'id': 'test_png', 'file': 'packs/test/test_png.png', 'scene': '合成静图'},
    {'id': 'test_gif', 'file': 'packs/test/test_gif.gif', 'scene': '合成动图'},
]}, ensure_ascii=False), encoding='utf-8')
TOOLS = ['cronjob', 'memory', 'search', 'session_search', 'social', 'sticker', 'tts', 'vision']
CONFIG = {
    'platform_toolsets': {'qqbot': TOOLS, 'weixin': TOOLS, 'cli': ['memory', 'session_search', 'tts', 'vision']},
    'gateway': {'media_delivery_allow_dirs': [str(HOME / 'stickers/packs')]},
    'display': {'emoji_stickers': {'enabled': True, 'platforms': ['qqbot', 'weixin'],
        'mapping': {'😎': 'test_png', '😄': 'test_gif'}, 'max_per_turn': 1,
        'cooldown_seconds': 300, 'delay_ms': 1200, 'max_lines': 3, 'max_chars': 200}},
}
(HOME / 'config.yaml').write_text(json.dumps(CONFIG, ensure_ascii=False), encoding='utf-8')

from gateway import emoji_stickers as emoji
from gateway.platforms import weixin
from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.config import Platform
from tools import sticker_tool
from hermes_cli.tools_config import _get_platform_tools
from tools.registry import registry


class LedgerAdapter:
    send_final_ledgered = BasePlatformAdapter.send_final_ledgered
    platform = Platform.WEIXIN
    name = 'synthetic-weixin'

    def __init__(self):
        self.calls = []

    def _final_delivery_adapter(self, source):
        return self

    async def _record_delivery_obligation(self, *args):
        return None

    async def _send_with_retry(self, **kwargs):
        self.calls.append(('text', kwargs['content']))
        return SendResult(success=True, message_id='synthetic-text')

    async def send_image_file(self, **kwargs):
        self.calls.append(('image', kwargs['image_path']))
        return SendResult(success=True, message_id='synthetic-image')


class WeixinParityTests(unittest.TestCase):
    def setUp(self):
        sticker_tool._last_sent_at = 0

    def test_toolsets_equal(self):
        self.assertEqual(_get_platform_tools(CONFIG, 'qqbot'), _get_platform_tools(CONFIG, 'weixin'))
        self.assertIn('sticker', _get_platform_tools(CONFIG, 'weixin'))
        self.assertNotIn('sticker', _get_platform_tools(CONFIG, 'cli'))

    def test_tool_schema_contains_library(self):
        defs = registry.get_definitions({'send_sticker'})
        fn = defs[0].get('function', defs[0])
        self.assertEqual(set(fn['parameters']['properties']['sticker_id']['enum']), {'test_png', 'test_gif'})

    def test_sticker_result_and_path(self):
        result = sticker_tool.send_sticker('test_gif')
        self.assertIn('MEDIA:' + str(LIB / 'test_gif.gif'), result)
        self.assertIn('"success": true', result)

    def test_sticker_bad_id(self):
        self.assertFalse(json.loads(sticker_tool.send_sticker('../outside'))['success'])

    def test_sticker_shared_cooldown(self):
        self.assertIn('MEDIA:', sticker_tool.send_sticker('test_png'))
        self.assertFalse(json.loads(sticker_tool.send_sticker('test_gif'))['success'])

    def test_both_platforms_same_mapping(self):
        for p in ('qqbot', 'weixin'):
            self.assertEqual(emoji.prepare('开心😄', p), ('开心', ['test_gif']))

    def test_other_platform_unchanged(self):
        self.assertEqual(emoji.prepare('开心😄', 'cli'), ('开心😄', []))

    def test_mapping_priority_unchanged(self):
        self.assertEqual(emoji.prepare('开心😄😎', 'weixin'), ('开心', ['test_png']))

    def test_long_reply_unchanged(self):
        text = '第一行😄\n第二行\n第三行\n第四行'
        self.assertEqual(emoji.prepare(text, 'weixin'), (text, []))

    def test_fence_and_pure_emoji_unchanged(self):
        for text in ('```\n😄\n```', '😄'):
            self.assertEqual(emoji.prepare(text, 'weixin'), (text, []))

    def test_final_exit_text_then_one_image(self):
        adapter = LedgerAdapter()
        event = types.SimpleNamespace(source=types.SimpleNamespace(chat_id='synthetic-A'))
        with patch.object(emoji.asyncio, 'sleep', new=AsyncMock()) as sleep:
            asyncio.run(adapter.send_final_ledgered(event, 'synthetic-session', '开心😄', {}, reply_to=None))
        self.assertEqual(adapter.calls, [('text', '开心'), ('image', str(LIB / 'test_gif.gif'))])
        sleep.assert_awaited_once_with(1.2)

    def test_ephemeral_reply_no_image(self):
        adapter = LedgerAdapter()
        event = types.SimpleNamespace(source=types.SimpleNamespace(chat_id='synthetic-A'))
        asyncio.run(adapter.send_final_ledgered(event, 'synthetic-session', '开心😄', {}, reply_to=None, is_ephemeral_response=True))
        self.assertEqual(adapter.calls, [('text', '开心😄')])

    def test_direct_tool_cooldown_blocks_auto_image(self):
        sticker_tool.send_sticker('test_png')
        adapter = LedgerAdapter()
        event = types.SimpleNamespace(source=types.SimpleNamespace(chat_id='synthetic-A'))
        asyncio.run(emoji.deliver(adapter, event, ['test_gif'], None))
        self.assertEqual(adapter.calls, [])

    def test_weixin_chatty_lines_split(self):
        self.assertEqual(weixin._split_text_for_weixin_delivery('到啦\n今天怎么样', 2000, False), ['到啦', '今天怎么样'])

    def test_weixin_structured_text_preserved(self):
        for text in ('- first\n- second', '```python\nprint(1)\n```'):
            self.assertEqual(weixin._split_text_for_weixin_delivery(text, 2000, False), [text])

    def test_weixin_oversized_text_split(self):
        self.assertTrue(all(len(x) <= 2000 for x in weixin._split_text_for_weixin_delivery('甲' * 4500, 2000, False)))

    def test_weixin_media_upload_png_and_gif(self):
        for path, original in ((LIB / 'test_png.png', PNG), (LIB / 'test_gif.gif', GIF)):
            adapter = weixin.WeixinAdapter.__new__(weixin.WeixinAdapter)
            adapter._send_session = object()
            adapter._token = 'synthetic-token'
            adapter._account_id = 'synthetic-account'
            adapter._base_url = 'https://invalid.example'
            adapter._cdn_base_url = 'https://invalid.example'
            adapter._token_store = types.SimpleNamespace(get=lambda *args: 'synthetic-context')
            sent, uploaded = [], []

            async def get_upload(*args, **kwargs):
                self.assertEqual(kwargs['media_type'], weixin.MEDIA_IMAGE)
                self.assertEqual(kwargs['rawsize'], len(original))
                return {'upload_full_url': 'https://invalid.example/upload'}

            async def upload(*args, **kwargs):
                uploaded.append(kwargs['ciphertext'])
                return 'synthetic-encrypted-param'

            async def send_items(*args, **kwargs):
                sent.append(kwargs['item_list'])
                self.assertEqual(kwargs['context_token'], 'synthetic-context')
                return {'ret': 0, 'errcode': 0}

            with patch.object(weixin, '_get_upload_url', get_upload), patch.object(weixin, '_upload_ciphertext', upload), patch.object(weixin, '_send_items', send_items):
                asyncio.run(adapter._send_file('synthetic-A', str(path), '合成说明'))
            self.assertEqual(len(uploaded), 1)
            self.assertEqual([x[0]['type'] for x in sent], [weixin.ITEM_TEXT, weixin.ITEM_IMAGE])


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        TEMP.cleanup()
