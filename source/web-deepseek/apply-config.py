"""Apply DeepSeek search provider config — idempotent, prints a diff summary only."""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import yaml

HOME = Path("/var/lib/hermes/.hermes")
CONFIG = HOME / "config.yaml"
ENV = HOME / ".env"

KEY_LINE = "DEEPSEEK_SEARCH_API_KEY=sk-DEEPSEEK_SEARCH_API_KEY"
BASE_LINE = "DEEPSEEK_SEARCH_API_BASE=https://api.deepseek.com/v1/tools"

text = CONFIG.read_text(encoding="utf-8")
changes = []

# 1) web.backend: deepseek
if re.search(r"^web:\s*$", text, re.M):
    if re.search(r"^web:\s*\n(?:[ \t]+.*\n)*?[ \t]+backend:\s*\S+", text, re.M):
        text = re.sub(r"(^web:\s*\n(?:[ \t]+.*\n)*?[ \t]+backend:\s*)\S+", r"\1deepseek", text, count=1, flags=re.M)
        changes.append("web.backend updated")
    else:
        text = re.sub(r"(^web:\s*\n)", r"\1  backend: deepseek\n", text, count=1, flags=re.M)
        changes.append("web.backend inserted")
else:
    if not text.endswith("\n"):
        text += "\n"
    text += "\nweb:\n  backend: deepseek\n"
    changes.append("web: section appended")

# 2) add `search` to qqbot / weixin toolset lists (after - memory)
for platform in ("qqbot", "weixin"):
    pattern = re.compile(
        r"(^  %s:\n(?:    - [^\n]+\n)*)" % re.escape(platform), re.M
    )
    m = pattern.search(text)
    if not m:
        sys.exit(f"platform block not found: {platform}")
    block = m.group(0)
    if re.search(r"^    - search$", block, re.M):
        changes.append(f"{platform}: already has search")
        continue
    new_block = block.replace("    - memory\n", "    - memory\n    - search\n", 1)
    if new_block == block:
        sys.exit(f"memory entry not found in {platform} block")
    text = text[: m.start()] + new_block + text[m.end():]
    changes.append(f"{platform}: search added")

# validate before writing
data = yaml.safe_load(text)
assert (data.get("web") or {}).get("backend") == "deepseek", "web.backend validation failed"
for platform in ("qqbot", "weixin"):
    assert "search" in (data["platform_toolsets"][platform] or []), f"{platform} validation failed"
assert "web" not in (data["platform_toolsets"]["cli"] or []), "cli must stay untouched"

CONFIG.write_text(text, encoding="utf-8")

# 3) .env keys
env_text = ENV.read_text(encoding="utf-8")
added = []
for line in (KEY_LINE, BASE_LINE):
    name = line.split("=", 1)[0]
    if re.search(rf"^{re.escape(name)}=", env_text, re.M):
        env_text = re.sub(rf"^{re.escape(name)}=.*$", line, env_text, count=1, flags=re.M)
    else:
        if not env_text.endswith("\n"):
            env_text += "\n"
        env_text += line + "\n"
        added.append(name)
ENV.write_text(env_text, encoding="utf-8")
ENV.chmod(0o600)

print("changes:")
for c in changes:
    print("  -", c)
print("env added:", added or "none (updated in place)")
print("effective qqbot:", data["platform_toolsets"]["qqbot"])
print("effective weixin:", data["platform_toolsets"]["weixin"])
print("web:", data.get("web"))
