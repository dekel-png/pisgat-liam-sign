# -*- coding: utf-8 -*-
"""Delivery of a signed pack into the Pisgat Liam management dashboard.

Fail-open by design: the dashboard being down must never block a client's
signing — Telegram remains the archive of record either way."""
import json
import os

import requests


def push_signed_pack(pkg, audit, signed_docs, signature_png_b64):
    """POST the signed set to the dashboard's /ops/signed-pack intake.

    Returns True (stored), False (tried and failed), or None (not configured).
    """
    url = os.environ.get("DASH_URL", "").rstrip("/")
    key = os.environ.get("DASH_OPS_KEY", "")
    if not url or not key:
        return None

    fields = audit.get("fields", {})
    docs_meta, files = [], {}
    for i, (name, data) in enumerate(signed_docs):
        k = f"doc{i}"
        docs_meta.append({
            "key": k,
            "doc_type": pkg["docs"][i].get("dash_doc_type", "אחר"),
            "orig_name": name,
        })
        files[k] = (name, data, "application/pdf")

    meta = {
        "client_name": pkg["client"],
        "client_hp": pkg.get("client_hp", ""),
        "submission_id": audit["submission_id"],
        "signed_at_sql": audit.get("signed_at_sql", ""),
        "ip": audit.get("ip", ""),
        "user_agent": audit.get("user_agent", ""),
        "signature_png_b64": signature_png_b64,
        "signer": {
            "name": fields.get("full_name", ""),
            "id": fields.get("id_number", ""),
            "role": fields.get("role", ""),
            "phone": fields.get("phone", ""),
            "email": fields.get("email", ""),
        },
        "docs": docs_meta,
    }
    try:
        r = requests.post(f"{url}/ops/signed-pack",
                          data={"meta": json.dumps(meta, ensure_ascii=False)},
                          files=files, headers={"X-Ops-Key": key}, timeout=120)
        return bool(r.ok and r.json().get("ok"))
    except Exception:
        return False
