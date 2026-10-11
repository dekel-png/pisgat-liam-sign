# -*- coding: utf-8 -*-
"""Smoke test for the signing service - no network, no secrets, no real packages.

Run:  python tests/smoke_test.py   (from the repo root; exits 1 on any failure)

What it guards:
- the app imports and boots with no env at all (no PACKAGES_KEY, no DASH_URL,
  no Telegram) - exactly how CI and a fresh Render boot see it;
- a signing link is the ONLY credential of /s/<token>, so a well-formed token
  that is not a package must 404 on every route (page, document, submit) -
  including tokens with a real client prefix and a guessed suffix;
- path-traversal tokens never resolve;
- an unknown path 404s;
- a fixture package proves the 200 path works, so the 404s above are real
  "not found" answers and not a broken app.
"""
import io
import json
import os
import secrets
import shutil
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

# Isolation before any import of the app: no dashboard fetch, no Telegram,
# no encrypted bundle, and a private temp dir for the remote-package cache.
for var in ("DASH_URL", "DASH_OPS_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "PACKAGES_KEY"):
    os.environ.pop(var, None)
TMP = tempfile.mkdtemp(prefix="plsign-smoke-")
tempfile.tempdir = TMP

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    mark = "OK  " if cond else "FAIL"
    print(f"{mark} {name}{(' - ' + str(extra)) if (extra and not cond) else ''}")


def tiny_pdf():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "smoke fixture")
    c.save()
    return buf.getvalue()


def main():
    import app as signapp

    c = signapp.app.test_client()

    check("app boots: /healthz is 200", c.get("/healthz").status_code == 200)
    r = c.get("/")
    check("home redirects to the public site", r.status_code == 302
          and r.headers.get("Location", "").startswith("https://pisgat-liam.co.il"))

    # A fixture package under a fresh packages dir (the real ones are never in git).
    pkgs = os.path.join(TMP, "packages")
    known = "smk-" + secrets.token_urlsafe(18)
    pdir = os.path.join(pkgs, known)
    os.makedirs(pdir)
    with open(os.path.join(pdir, "doc1.pdf"), "wb") as f:
        f.write(tiny_pdf())
    with open(os.path.join(pdir, "package.json"), "w", encoding="utf-8") as f:
        json.dump({"client": "Smoke Fixture Ltd",
                   "docs": [{"name": "Doc 1", "file": "doc1.pdf"}],
                   "fields": [{"key": "full_name", "label": "Name", "required": True}]},
                  f, ensure_ascii=False)
    signapp.PACKAGES_DIR = pkgs

    r = c.get(f"/s/{known}")
    check("fixture token: signing page is 200", r.status_code == 200)
    check("fixture token: page shows the client", "Smoke Fixture Ltd" in r.get_data(as_text=True))
    r = c.get(f"/s/{known}/doc/0")
    check("fixture token: document served as PDF", r.status_code == 200 and r.mimetype == "application/pdf")
    check("fixture token: out-of-range document is 404", c.get(f"/s/{known}/doc/7").status_code == 404)

    # Well-formed tokens that are not packages - same shape as real links
    # ("<prefix>-<token_urlsafe(18)>"), including real client prefixes.
    for prefix in ("sal", "tla", "ahr", "smk"):
        t = f"{prefix}-{secrets.token_urlsafe(18)}"
        check(f"unknown token ({prefix}-...): page 404", c.get(f"/s/{t}").status_code == 404)
        check(f"unknown token ({prefix}-...): document 404", c.get(f"/s/{t}/doc/0").status_code == 404)
        check(f"unknown token ({prefix}-...): submit 404",
              c.post(f"/s/{t}/submit", json={"consent": True}).status_code == 404)

    for bad in ("..", "..%2F" + known, "%2e%2e", known + "%2F..", "a\\..\\b"):
        check(f"traversal token never resolves: {bad.replace(known, '<fixture>')!r}",
              c.get(f"/s/{bad}").status_code == 404)
    check("load_package refuses traversal", signapp.load_package("../" + known) is None
          and signapp.load_package("..") is None)

    check("unknown path is 404", c.get("/definitely-not-a-route").status_code == 404)
    check("bare /s/ is 404", c.get("/s/").status_code == 404)

    print()
    print(f"=== {len(PASS)} passed - {len(FAIL)} failed ===")
    for name in FAIL:
        print("  FAIL", name)
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
