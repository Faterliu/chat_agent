#!/usr/bin/env python3
"""直接调 QQ 机器人接口往指定私聊发一条「表情语法」测试消息。

目的：确认 QQ 客户端对 <face id="1"/> / [微笑] / /微笑 三种写法的渲染结果，
      以及 Unicode emoji 的对照效果。只发一条，不改配置、不进对话上下文。
凭据从 HERMES_HOME/.env 读取，不打印 token。
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path("/var/lib/hermes/.hermes/.env")
OPENID = sys.argv[1] if len(sys.argv) > 1 else "A729C39060FB65742B0C808249E36326"
CONTENT = (
    "表情测试（忽略这条即可）：\n"
    '1 <face id="1"/>\n'
    "2 [微笑]\n"
    "3 /微笑\n"
    "4 😄 对照"
)


def load_env() -> dict:
    env = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def post(url: str, body: dict, headers: dict) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


env = load_env()
app_id, secret = env["QQ_APP_ID"], env["QQ_CLIENT_SECRET"]

status, body = post("https://bots.qq.com/app/getAppAccessToken",
                    {"appId": app_id, "clientSecret": secret}, {})
if status != 200:
    print("token_failed", status, body[:300])
    raise SystemExit(1)
token = json.loads(body)["access_token"]
print("token_ok expires_in:", json.loads(body).get("expires_in"))

status, body = post(
    f"https://api.sgroup.qq.com/v2/users/{OPENID}/messages",
    {"content": CONTENT, "msg_type": 0, "msg_seq": 1},
    {"Authorization": f"QQBot {token}"},
)
print("send_status:", status)
print("send_body:", body[:500])
