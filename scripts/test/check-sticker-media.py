#!/usr/bin/env python3
"""验证放行后投递层接受表情包路径（模拟网关启动时的环境桥接）。"""

import os
import sys

sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

from hermes_cli.config import load_config  # noqa: E402
from gateway.media_policy import apply_media_policy_env  # noqa: E402
from gateway.platforms.base import BasePlatformAdapter  # noqa: E402

apply_media_policy_env(load_config())
print("HERMES_MEDIA_ALLOW_DIRS:", os.environ.get("HERMES_MEDIA_ALLOW_DIRS"))
for path in (
    "/var/lib/hermes/.hermes/stickers/packs/doro/doro_12.gif",
    "/var/lib/hermes/.hermes/stickers/packs/doro/doro_13.gif",
    "/var/lib/hermes/.hermes/config.yaml",
):
    print(os.path.basename(path), "->", BasePlatformAdapter.validate_media_delivery_path(path))
