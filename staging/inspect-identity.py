"""Read-only: does the per-session system prompt carry user identity or the memory block?

Answers, with evidence, whether the model itself can tell who it is talking to.
Note: sessions PK column is `id`, not `session_id`.
"""
import sqlite3

DB = "/var/lib/hermes/.hermes/state.db"
con = sqlite3.connect(DB)

PROBES = [
    "Current Session Context",
    "Source:",
    "Qqbot",
    "A729C39060FB65742B0C808249E36326",
    "56B2E66590BD2ED9A098C5D8B0123D68",
    "Memory",
    "MEMORY.md",
    "USER.md",
    "user profile",
    "nickname",
]

rows = con.execute(
    "SELECT id, source, chat_type, user_id, length(COALESCE(system_prompt,'')), system_prompt "
    "FROM sessions ORDER BY started_at DESC"
).fetchall()
print("=== sessions (newest first) ===")
print("rows:", len(rows))
for sid, src, ct, uid, n, sp in rows:
    p = sp or ""
    print(f"--- {sid}  source={src} chat_type={ct} user={uid} prompt_chars={n}")
    if not p:
        print("      (system_prompt empty)")
        continue
    for probe in PROBES:
        print(f"      contains {probe!r:<48} {probe in p}")
