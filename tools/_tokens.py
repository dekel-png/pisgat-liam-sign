"""Signing-link tokens live ONLY in a tokens file outside git AND outside OneDrive (11/10/2026):
%LOCALAPPDATA%\\my-aios\\secrets\\pisgat-liam-sign.tokens.json (override: PISGAT_SIGN_TOKENS_FILE).
The legacy gitignored .tokens.json at the repo root is still read if it exists.
A token is the sole credential of /s/<token> — never a literal in code (the
three leaked in 08/2026 were rotated 09/10). A new client gets a fresh one."""
import json
import os
import secrets

_SECRETS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "my-aios", "secrets", "pisgat-liam-sign.tokens.json")
_LEGACY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".tokens.json")


def _resolve():
    explicit = os.environ.get("PISGAT_SIGN_TOKENS_FILE")
    if explicit:
        return explicit
    if os.path.exists(_SECRETS) or not os.path.exists(_LEGACY):
        return _SECRETS
    return _LEGACY


_PATH = _resolve()


def token_for(client, prefix=None):
    data = json.load(open(_PATH, encoding="utf-8")) if os.path.exists(_PATH) else {}
    if client not in data:
        data[client] = f"{prefix or client[:3]}-{secrets.token_urlsafe(18)}"
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    return data[client]
