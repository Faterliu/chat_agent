#!/usr/bin/env python3
"""Exercise the gateway failure-copy mapping under the active config."""
import os

from gateway import persona_errors as pe
from gateway.run import (
    _gateway_provider_error_reply,
    _normalize_empty_agent_response,
    _rate_limit_reply,
)

SAMPLES = {
    "rate_limit": "429 Too Many Requests: rate limit exceeded, retry after 30s",
    "auth": "401 Unauthorized: invalid api key (provider authentication failed)",
    "policy": "400 Bad Request: request rejected by content policy",
    "conn_interrupted": "Connection reset by peer mid-request",
    "endpoint": "Connection refused: endpoint unreachable",
    "conn_error": "APIConnectionError: Connection error.",
    "generic": "the model melted",
}

print("enabled =", pe.enabled())
print("rate_limit ->", _rate_limit_reply(SAMPLES["rate_limit"]))
for key, text in SAMPLES.items():
    print(f"{key} -> {_gateway_provider_error_reply(text)}")
print("failed_turn ->", _normalize_empty_agent_response(
    {"failed": True, "error": "boom"}, "", history_len=0))
print("failed_429 ->", _normalize_empty_agent_response(
    {"failed": True, "error": "429 rate limit"}, "", history_len=0))
print("failed_storage ->", _normalize_empty_agent_response(
    {"failed": True, "error": "session storage disk full",
     "failure_reason": "session_persistence_failed:disk"}, "", history_len=0))
print("timeout ->", pe.timeout(5))
print("no_model ->", pe.no_model())
