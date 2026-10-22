"""Verify DeepSeek provider wiring against the live HERMES_HOME config."""
from __future__ import annotations

import sys

sys.path.insert(0, "/var/lib/hermes/.hermes/hermes-agent")

from hermes_cli.config import load_config  # noqa: E402
from hermes_cli.plugins import discover_plugins  # noqa: E402
from hermes_cli.tools_config import _get_platform_tools  # noqa: E402
from model_tools import get_tool_definitions  # noqa: E402

discover_plugins()

from tools.web_tools import _get_backend  # noqa: E402

cfg = load_config()
print("web.backend =", (cfg.get("web") or {}).get("backend"))
print("resolved backend =", _get_backend())

for platform in ("qqbot", "weixin", "cli"):
    ts = sorted(_get_platform_tools(cfg, platform))
    defs = get_tool_definitions(enabled_toolsets=ts, quiet_mode=True)
    names = {d.get("function", {}).get("name") for d in defs}
    print(f"{platform:8s} toolsets={ts}")
    print(f"{'':8s} web_search={'web_search' in names} web_extract={'web_extract' in names} total={len(names)}")

# provider registry view
from agent.web_search_registry import get_provider  # noqa: E402
provider = get_provider("deepseek")
print("provider registered:", provider is not None,
      "| name:", getattr(provider, "name", None),
      "| available:", provider.is_available() if provider else None,
      "| extract:", provider.supports_extract() if provider else None)
