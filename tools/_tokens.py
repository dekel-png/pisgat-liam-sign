"""Signing-link tokens live ONLY in the gitignored .tokens.json at the repo root.
A token is the sole credential of /s/<token> — never a literal in code (the
three leaked in 08/2026 were rotated 09/10). A new client gets a fresh one."""
import json
import os
import secrets

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tokens.json")


def token_for(client, prefix=None):
    data = json.load(open(_PATH, encoding="utf-8")) if os.path.exists(_PATH) else {}
    if client not in data:
        data[client] = f"{prefix or client[:3]}-{secrets.token_urlsafe(18)}"
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    return data[client]
