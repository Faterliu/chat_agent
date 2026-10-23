"""用临时 HERMES_HOME 验证图片容量、月清理和处理中保护，不调用模型。"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
POLICY_SOURCE = os.environ.get('IMAGE_POLICY_SOURCE')
if POLICY_SOURCE is None:
    POLICY_SOURCE = str(ROOT.parent.parent / 'source/image_cache_policy.py')
spec = importlib.util.spec_from_file_location(
    'image_cache_policy', POLICY_SOURCE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
NOW = datetime(2026, 10, 31, 23, 59, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
NEXT = NOW + 120


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.images = self.home / 'cache/images'
        self.images.mkdir(parents=True)
        (self.home / 'sessions').mkdir()
        self.sessions = self.home / 'sessions/sessions.json'
        self.sessions.write_text(json.dumps({'A': {}, 'B': {}}), encoding='utf-8')

    def create(self, count):
        for i in range(count):
            p = self.images / f'img_{i:03}.jpg'
            p.write_bytes(b'\xff\xd8\xfftest')
            os.utime(p, (NOW - 10000 + i, NOW - 10000 + i))

    def clean(self, now=NOW, **kwargs):
        return policy.maintain_image_cache(self.images, self.home, now=now, **kwargs)

    def names(self):
        return sorted(p.name for p in self.images.glob('*.jpg'))

    def test_below_threshold(self):
        self.create(49)
        self.assertEqual(self.clean(), 0)
        self.assertEqual(len(self.names()), 49)

    def test_threshold_removes_oldest_twenty(self):
        self.create(50)
        self.assertEqual(self.clean(), 20)
        self.assertEqual(self.names(), [f'img_{i:03}.jpg' for i in range(20, 50)])
        self.assertEqual(self.clean(), 0)

    def test_backlog_removes_batches(self):
        self.create(90)
        self.assertEqual(self.clean(), 60)
        self.assertEqual(len(self.names()), 30)

    def test_month_boundary_keeps_newest_twenty(self):
        self.create(49)
        self.clean()
        self.assertEqual(self.clean(NEXT), 29)
        self.assertEqual(self.names(), [f'img_{i:03}.jpg' for i in range(29, 49)])
        self.create(21)
        self.assertEqual(self.clean(NEXT + 100), 0)  # 同月不重复月清理。

    def test_monthly_empty_cache(self):
        self.clean()
        self.assertEqual(self.clean(NEXT), 0)
        self.assertEqual((self.home / 'cache/image-retention-month.txt').read_text(encoding='utf-8').strip(), '2026-11')

    def test_busy_and_unreadable_state_defer(self):
        self.create(50)
        self.sessions.write_text(json.dumps({'B': {'active_turn_token': 'busy'}}), encoding='utf-8')
        self.assertEqual(self.clean(), 0)
        self.sessions.write_text('broken', encoding='utf-8')
        self.assertEqual(self.clean(), 0)
        self.assertEqual(len(self.names()), 50)

    def test_recent_and_protected_files_defer(self):
        self.create(50)
        self.assertEqual(self.clean(protected=[self.images / 'img_000.jpg']), 0)
        p = self.images / 'img_049.jpg'
        os.utime(p, (NOW, NOW))
        self.assertEqual(self.clean(), 20)  # 新图不是删除目标，不阻塞旧图清理。

    def test_recent_burst_defers_then_retries(self):
        self.create(50)
        for p in self.images.iterdir():
            os.utime(p, (NOW, NOW))
        self.assertEqual(self.clean(), 0)
        self.assertEqual(self.clean(NOW + 301), 20)

    def test_monthly_busy_does_not_mark_complete(self):
        self.create(49)
        self.clean()
        self.sessions.write_text(json.dumps({'A': {'active_turn_token': 'busy'}}), encoding='utf-8')
        self.assertEqual(self.clean(NEXT), 0)
        self.sessions.write_text('{}', encoding='utf-8')
        self.assertEqual(self.clean(NEXT + 60), 29)

    def test_other_files_and_symlinks_untouched(self):
        self.create(50)
        outside = self.home / 'outside.jpg'
        outside.write_bytes(b'keep')
        (self.images / 'notes.txt').write_text('keep', encoding='utf-8')
        (self.images / 'nested').mkdir()
        try:
            (self.images / 'linked.jpg').symlink_to(outside)
        except OSError:
            pass
        self.assertEqual(self.clean(), 20)
        self.assertEqual(outside.read_bytes(), b'keep')
        self.assertTrue((self.images / 'notes.txt').exists())
        with self.assertRaises(ValueError):
            policy.maintain_image_cache(self.home, self.home, now=NOW)

    def test_legacy_cache_path(self):
        legacy = self.home / 'image_cache'
        legacy.mkdir()
        self.assertEqual(policy.maintain_image_cache(legacy, self.home, now=NOW), 0)


if __name__ == '__main__':
    unittest.main()
