"""为固定版本 Hermes 扫码接入微信，只开放授权账号私聊；不启动网关。"""

import asyncio
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path("/var/lib/hermes/.hermes")
REPO = HOME / "hermes-agent"
os.environ["HERMES_HOME"] = str(HOME)
os.umask(0o077)
sys.path.insert(0, str(REPO))

from dotenv import dotenv_values
from gateway.platforms import weixin
from hermes_cli.config import save_env_value


def show_qr(value, url, *, report_render_error):
    if not url:
        raise RuntimeError("微信没有返回可扫描的登录链接")
    print("QR_URL=" + url, flush=True)


def main():
    if not weixin.check_weixin_requirements():
        raise RuntimeError("缺少微信依赖")
    env = dotenv_values(HOME / ".env")
    if env.get("WEIXIN_TOKEN") or env.get("WEIXIN_ACCOUNT_ID"):
        raise RuntimeError("已有微信账号，请先核实，不自动覆盖")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = HOME / "backups" / ("weixin-" + stamp)
    backup.mkdir(mode=0o700, parents=True)
    for name in (".env", "config.yaml"):
        shutil.copy2(HOME / name, backup / name)
        (backup / name).chmod(0o600)
    with sqlite3.connect(HOME / "state.db") as source:
        with sqlite3.connect(backup / "state.db") as target:
            source.backup(target)
    shutil.copy2(REPO / "gateway/platforms/weixin.py", backup / "weixin.py")
    print("BACKUP=" + str(backup), flush=True)
    weixin._print_qr = show_qr
    credentials = asyncio.run(weixin.qr_login(str(HOME), timeout_seconds=480))
    if not credentials:
        raise RuntimeError("登录未完成，生产配置未切换")
    if not credentials.get("user_id"):
        raise RuntimeError("授权响应缺少用户身份，不启用微信")
    settings = {
        "WEIXIN_ACCOUNT_ID": credentials["account_id"],
        "WEIXIN_TOKEN": credentials["token"],
        "WEIXIN_BASE_URL": credentials["base_url"],
        "WEIXIN_CDN_BASE_URL": weixin.WEIXIN_CDN_BASE_URL,
        "WEIXIN_DM_POLICY": "allowlist",
        "WEIXIN_ALLOWED_USERS": credentials["user_id"],
        "WEIXIN_ALLOW_ALL_USERS": "false",
        "WEIXIN_GROUP_POLICY": "disabled",
        "WEIXIN_GROUP_ALLOWED_USERS": "",
    }
    try:
        for key, value in settings.items():
            save_env_value(key, value)
        stored = dotenv_values(HOME / ".env")
        if any(stored.get(key) != value for key, value in settings.items()):
            raise RuntimeError("配置保存核验失败")
        (HOME / ".env").chmod(0o600)
    except Exception:
        shutil.copy2(backup / ".env", HOME / ".env")
        raise
    print("WEIXIN_CONFIGURED_OWNER_ONLY", flush=True)


if __name__ == "__main__":
    main()
