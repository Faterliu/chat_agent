"""入站图片缓存：满 50 张删最旧 20 张，每月保留最新 20 张。"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import stat
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
_LOCK = threading.RLock()
_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
_RECENT_SECONDS = 300


def _busy(home: Path) -> bool:
    """有未完成回合或无法确认会话状态时，延后清理。"""
    try:
        entries = json.loads((home / 'sessions/sessions.json').read_text(encoding='utf-8'))
        if not isinstance(entries, dict):
            return True
        return any(isinstance(v, dict) and v.get('active_turn_token') for v in entries.values())
    except (OSError, ValueError):
        return True


def _images(directory: Path):
    result = []
    for path in directory.iterdir():
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(info.st_mode) and path.suffix.lower() in _EXTENSIONS:
            result.append((info.st_mtime_ns, path.name, path, info))
    return sorted(result)


def maintain_image_cache(directory: Path, home: Path, *, now: float | None = None,
                         protected=()) -> int:
    """仅清理指定主目录的图片缓存；失败不删除，按北京时间判断月份。"""
    directory, home = Path(directory), Path(home).resolve()
    if directory.is_symlink() or directory.resolve() not in {home / 'cache/images', home / 'image_cache'}:
        raise ValueError('Refusing unexpected image cache directory')
    if not directory.exists():
        return 0
    now = time.time() if now is None else now
    month = datetime.fromtimestamp(now, ZoneInfo('Asia/Shanghai')).strftime('%Y-%m')
    marker = home / 'cache/image-retention-month.txt'
    protected = {Path(p).resolve() for p in protected}
    removed = 0
    with _LOCK:
        # No external cleaner is installed: the gateway owns all calls under this lock.
        if _busy(home):
            return 0
        try:
            last_month = marker.read_text(encoding='utf-8').strip()
            datetime.strptime(last_month, '%Y-%m')
        except FileNotFoundError:
            last_month = month  # 部署当月不额外触发月清理。
        items = _images(directory)
        monthly_due = last_month != month
        if monthly_due:
            targets = items[:-20] if len(items) > 20 else []
        else:
            count = len(items)
            batches = 0 if count < 50 else (count - 50) // 20 + 1
            targets = items[:batches * 20]
        # 整批延后，不能因为部分图片受保护而悄悄变成“删不足 20 张”。
        if any(path.resolve() in protected or now - info.st_mtime < _RECENT_SECONDS
               for _, _, path, info in targets):
            return 0
        for _, _, path, original in targets:
            if _busy(home):
                return removed
            try:
                current = path.lstat()
            except FileNotFoundError:
                continue
            if (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size) != (
                    original.st_dev, original.st_ino, original.st_mtime_ns, original.st_size):
                return removed
            if not stat.S_ISREG(current.st_mode):
                return removed
            path.unlink()
            removed += 1
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = marker.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(month + '\n')
        os.replace(temporary, marker)
        if removed:
            logger.info('Image retention: removed=%d remaining=%d mode=%s',
                        removed, len(_images(directory)), 'monthly' if monthly_due else 'capacity')
    return removed
