# -*- coding: utf-8 -*-
"""פסגת ליאם — מערכת חתימה דיגיטלית ללקוחות.

Each signing package lives under packages/<token>/ (package.json + PDFs).
The client opens /s/<token> on their phone, reviews the documents, fills the
required fields, draws one signature — the server stamps it into every
signature spot, appends an audit page, and delivers everything to Telegram.
Nothing persistent is stored on this server; Telegram is the archive.
"""
import base64
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file
import io

import dash_util
import stamp
import telegram_util

BASE = os.path.dirname(os.path.abspath(__file__))


def _resolve_packages_dir():
    """Local dev: plaintext packages/. Production (public repo): packages.enc
    decrypted at boot with PACKAGES_KEY into a runtime dir — contracts never
    sit in the repo in the clear."""
    plain = os.path.join(BASE, "packages")
    if os.path.isdir(plain) and os.listdir(plain):
        return plain
    enc = os.path.join(BASE, "packages.enc")
    key = os.environ.get("PACKAGES_KEY", "")
    if os.path.exists(enc) and key:
        import tarfile
        import tempfile
        from cryptography.fernet import Fernet
        target = os.path.join(tempfile.gettempdir(), "plsign-packages")
        with open(enc, "rb") as f:
            blob = Fernet(key.encode()).decrypt(f.read())
        os.makedirs(target, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            tar.extractall(target, filter="data")
        return target
    return plain


PACKAGES_DIR = _resolve_packages_dir()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

_submit_counts = {}
_lock = threading.Lock()


def _fetch_remote_package(token):
    """Dashboard-minted packs (manager self-service) live on the dashboard's
    persistent disk; fetch once and cache locally for this instance."""
    import base64
    import tempfile

    import requests

    url = os.environ.get("DASH_URL", "").rstrip("/")
    key = os.environ.get("DASH_OPS_KEY", "")
    if not url or not key:
        return None
    try:
        r = requests.get(f"{url}/ops/sign-package/{token}",
                         headers={"X-Ops-Key": key}, timeout=60)
        if r.status_code != 200:
            return None
        data = r.json()
        if not data.get("ok"):
            return None
    except Exception:
        return None
    cache = os.path.join(tempfile.gettempdir(), "plsign-remote", token)
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, "package.json"), "w", encoding="utf-8") as f:
        json.dump(data["package"], f, ensure_ascii=False)
    for fname, b64 in data.get("files", {}).items():
        if "/" in fname or "\\" in fname or ".." in fname:
            continue
        with open(os.path.join(cache, fname), "wb") as f:
            f.write(base64.b64decode(b64))
    return cache


def load_package(token):
    if not token or "/" in token or "\\" in token or ".." in token:
        return None
    pack_dir = os.path.join(PACKAGES_DIR, token)
    if not os.path.exists(os.path.join(pack_dir, "package.json")):
        import tempfile
        cached = os.path.join(tempfile.gettempdir(), "plsign-remote", token)
        if os.path.exists(os.path.join(cached, "package.json")):
            pack_dir = cached
        else:
            pack_dir = _fetch_remote_package(token)
            if not pack_dir:
                return None
    with open(os.path.join(pack_dir, "package.json"), encoding="utf-8") as f:
        pkg = json.load(f)
    pkg["_dir"] = pack_dir
    return pkg


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "?"


@app.get("/")
def home():
    return redirect("https://pisgat-liam.co.il", code=302)


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/s/<token>")
def sign_page(token):
    pkg = load_package(token)
    if not pkg:
        abort(404)
    return render_template("sign.html", pkg=pkg, token=token,
                           served_at=datetime.now(timezone.utc).isoformat())


@app.get("/s/<token>/doc/<int:idx>")
def view_doc(token, idx):
    pkg = load_package(token)
    if not pkg or idx < 0 or idx >= len(pkg["docs"]):
        abort(404)
    doc = pkg["docs"][idx]
    path = os.path.join(pkg["_dir"], doc["file"])
    return send_file(path, mimetype="application/pdf", as_attachment=False,
                     download_name=doc["name"] + ".pdf")


@app.post("/s/<token>/submit")
def submit(token):
    pkg = load_package(token)
    if not pkg:
        abort(404)

    with _lock:
        n = _submit_counts.get(token, 0) + 1
        _submit_counts[token] = n
    if n > 25:
        return jsonify({"ok": False, "error": "יותר מדי ניסיונות — פנו לפסגת ליאם"}), 429

    data = request.get_json(silent=True) or {}
    fields = data.get("fields") or {}
    fields = {k: str(v).strip()[:200] for k, v in fields.items()}
    if not data.get("consent"):
        return jsonify({"ok": False, "error": "יש לאשר את הצהרת ההסכמה"}), 400
    missing = [f["label"] for f in pkg["fields"]
               if f.get("required") and not fields.get(f["key"])]
    if missing:
        return jsonify({"ok": False, "error": "חסרים שדות: " + ", ".join(missing)}), 400

    try:
        sig_img = stamp.load_signature(data.get("signature", ""))
    except Exception:
        return jsonify({"ok": False, "error": "החתימה חסרה או לא תקינה — נסו לחתום שוב"}), 400
    if sig_img.width < 40 or sig_img.height < 12:
        return jsonify({"ok": False, "error": "החתימה קצרה מדי — חתמו שוב בבירור"}), 400

    now_utc = datetime.now(timezone.utc)
    audit = {
        "submission_id": uuid.uuid4().hex[:12].upper(),
        "package": token,
        "client": pkg["client"],
        "fields": fields,
        "signed_at_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "signed_at_sql": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "signed_at_il": now_utc.astimezone(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M:%S"),
        "ip": client_ip(),
        "user_agent": request.headers.get("User-Agent", "?"),
        "page_served_at": data.get("served_at", ""),
        "consent_text": "קראתי את המסמכים, אני מוסמך/ת לחתום בשם המזמין, וחתימתי האלקטרונית מחייבת כדין.",
    }

    signed_docs, doc_hashes = [], []
    for doc in pkg["docs"]:
        pdf_path = os.path.join(pkg["_dir"], doc["file"])
        signed_bytes, original_sha = stamp.stamp_document(pdf_path, doc, fields, sig_img, audit)
        signed_name = doc["name"] + " - חתום.pdf"
        signed_docs.append((signed_name, signed_bytes))
        doc_hashes.append({"doc": doc["name"], "original_sha256": original_sha,
                           "signed_sha256": hashlib.sha256(signed_bytes).hexdigest()})
    audit["documents"] = doc_hashes

    # file the signed set in the management dashboard (fail-open)
    sig_buf = io.BytesIO()
    sig_img.save(sig_buf, "PNG")
    dash_status = dash_util.push_signed_pack(
        pkg, audit, signed_docs, base64.b64encode(sig_buf.getvalue()).decode())
    audit["dashboard_filed"] = dash_status
    dash_line = {True: "📁 נקלט בתיק הלקוח בדשבורד ✓",
                 False: "⚠️ לא נקלט בדשבורד — להעלות לתיק ידנית",
                 None: "דשבורד: לא מוגדר"}[dash_status]

    # deliver to Telegram (the archive of record)
    telegram_util.send_message(
        "✍️ נחתם סט מסמכים — {client}\n"
        "חותם: {name} ({role}) · ת.ז {tz}\n"
        "מועד: {ts} · IP: {ip}\n"
        "מזהה הליך: {sid}\n{dash}".format(
            client=pkg["client"], name=fields.get("full_name", "?"),
            role=fields.get("role", "?"), tz=fields.get("id_number", "?"),
            ts=audit["signed_at_il"], ip=audit["ip"], sid=audit["submission_id"],
            dash=dash_line))
    delivered = all(
        telegram_util.send_document(name, bytes_) for name, bytes_ in signed_docs)
    telegram_util.send_document(
        "audit-{}.json".format(audit["submission_id"]),
        json.dumps(audit, ensure_ascii=False, indent=2).encode("utf-8"))

    return jsonify({
        "ok": True,
        "delivered": delivered,
        "submission_id": audit["submission_id"],
        "docs": [{"name": name, "b64": base64.b64encode(bytes_).decode()}
                 for name, bytes_ in signed_docs],
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5511, debug=False)
