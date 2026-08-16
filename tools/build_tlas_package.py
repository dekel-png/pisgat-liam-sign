# -*- coding: utf-8 -*-
"""Build the Tlas Engineering signing package: copy PDFs + generate package.json
with signature/field spots located via pdfplumber anchors (Hebrew extracts in
visual order, so anchors are matched reversed).

Doc-4 fixed coordinates re-measured on the Tlas PDFs (page 2 sits 13.8pt higher
than the Salhov set — shorter client name reflows the intro paragraph)."""
import json
import os
import shutil
import sys

import pdfplumber

TOKEN = "tls-8LGTwS3wNBCZupWbWA-G68_M"
SET_DIR = r"C:\Users\PC\OneDrive\Desktop\my-aios\outputs\documents\2026-08-16-tlas-signing-set"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(REPO, "packages", TOKEN)

FILES = {
    1: ("1 - הסכם מסגרת - תלס הנדסה.pdf", "1 - הסכם מסגרת", "הסכם מסגרת"),
    2: ("2 - נספח א - תנאים מסחריים - תלס הנדסה.pdf", "2 - נספח א - תנאים מסחריים", "נספח א — תנאים מסחריים"),
    3: ("3 - נספח ב - טופס הזמנת עובדים - תלס הנדסה.pdf", "3 - נספח ב - טופס הזמנת עובדים", "נספח ב — טופס הזמנת עובדים"),
    4: ("4 - ערבויות ובטוחות - תלס הנדסה.pdf", "4 - ערבויות ובטוחות", "ערבויות ובטוחות"),
}

def words_of(path):
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                out.append({"page": pi, "text": w["text"], "x0": w["x0"], "x1": w["x1"],
                            "top": w["top"], "bottom": w["bottom"]})
    return out

def same_line(a, b, tol=3.0):
    return abs(a["top"] - b["top"]) < tol

def blanks_on_line(words, anchor, page):
    return sorted([w for w in words if w["page"] == page and set(w["text"]) == {"_"}
                   and same_line(w, anchor)], key=lambda w: -w["x1"])  # RTL: rightmost first

def find(words, rev_text, page=None):
    hits = [w for w in words if w["text"] == rev_text and (page is None or w["page"] == page)]
    return hits

def footer_spots(words, n_pages):
    """Small signature on the 'חתימת המזמין: ____' footer blank of every page."""
    spots = []
    for p in range(1, n_pages + 1):
        anchors = [w for w in words if w["page"] == p and w["text"] == ":ןימזמה" and w["top"] > 770]
        assert anchors, f"footer anchor missing on page {p}"
        blanks = blanks_on_line(words, anchors[0], p)
        assert blanks, f"footer blank missing on page {p}"
        b = blanks[0]
        spots.append({"type": "sig", "page": p, "x0": round(b["x0"], 1), "x1": round(b["x1"], 1),
                      "bottom": round(b["bottom"], 1), "h": 15})
    return spots

def final_sig_spot(words, page):
    """The big 'המזמין' signature box at the document end."""
    labels = [w for w in words if w["page"] == page and w["text"] == "ןימזמה" and w["top"] > 140]
    for lab in sorted(labels, key=lambda w: w["top"]):
        cands = [w for w in words if w["page"] == page and set(w["text"]) == {"_"}
                 and 4 < lab["top"] - w["bottom"] < 40
                 and not (w["x1"] < lab["x0"] - 60 or w["x0"] > lab["x1"] + 60)]
        if cands:
            b = cands[0]
            return {"type": "sig", "page": page, "x0": round(b["x0"], 1), "x1": round(b["x1"], 1),
                    "bottom": round(b["bottom"], 1), "h": 34}
    raise AssertionError(f"final signature box not found on page {page}")

os.makedirs(PKG_DIR, exist_ok=True)
docs_spec = []

for num, (fname, display, dash_type) in FILES.items():
    src = os.path.join(SET_DIR, fname)
    shutil.copy(src, os.path.join(PKG_DIR, f"{num}.pdf"))
    words = words_of(src)
    n_pages = max(w["page"] for w in words)
    spots = footer_spots(words, n_pages)

    if num == 1:
        # party block: address blank on the מרח' line
        mrh = [w for w in words if w["page"] == 1 and w["text"].endswith("'חרמ")]
        addr_line = None
        for m in mrh:
            bl = blanks_on_line(words, m, 1)
            if bl:
                addr_line = bl[0]
        assert addr_line, "client address blank not found"
        spots.append({"type": "text", "page": 1, "x0": round(addr_line["x0"], 1),
                      "x1": round(addr_line["x1"], 1), "bottom": round(addr_line["bottom"], 1),
                      "field": "company_address", "size": 9})
        # authorized signatory line: 'באמצעות מורשה להתקשרות מטעמו: ____ ת.ז. ____,'
        anchor = find(words, ":ומעטמ", page=1)
        assert anchor, "מטעמו anchor not found"
        bl = blanks_on_line(words, anchor[0], 1)
        assert len(bl) >= 2, f"signatory blanks: {len(bl)}"
        name_b, tz_b = bl[0], bl[1]  # rightmost = name, then t.z.
        spots.append({"type": "text", "page": 1, "x0": round(name_b["x0"], 1),
                      "x1": round(name_b["x1"], 1), "bottom": round(name_b["bottom"], 1),
                      "field": "full_name", "size": 9})
        spots.append({"type": "text", "page": 1, "x0": round(tz_b["x0"], 1),
                      "x1": round(tz_b["x1"], 1), "bottom": round(tz_b["bottom"], 1),
                      "field": "id_number", "size": 9})
        spots.append(final_sig_spot(words, n_pages))

    if num == 2:
        spots.append(final_sig_spot(words, n_pages))

    if num == 4:
        # part A table (page 1) — measured on the Tlas PDF
        for field, x0, x1, bottom in [
            ("full_name", 327.9, 404.0, 306.0),
            ("id_number", 327.9, 404.0, 329.3),
            ("company_address", 292.8, 403.9, 352.7),
            ("phone", 292.8, 403.9, 375.8),   # empty cell — same column band
            ("role", 327.9, 404.0, 405.7),
        ]:
            spots.append({"type": "text", "page": 1, "x0": x0, "x1": x1,
                          "bottom": bottom, "field": field, "size": 9})
        # 'שם הערב: ____ ת.ז.: ____' + signature line (page 1)
        spots.append({"type": "text", "page": 1, "x0": 174.0, "x1": 255.8, "bottom": 523.3,
                      "field": "full_name", "size": 9})
        spots.append({"type": "text", "page": 1, "x0": 55.2, "x1": 137.1, "bottom": 523.3,
                      "field": "id_number", "size": 9})
        spots.append({"type": "sig", "page": 1, "x0": 154.1, "x1": 306.0, "bottom": 540.2, "h": 26})
        # page 2 — note maker (address + signature); 13.8pt higher than the Salhov set
        spots.append({"type": "text", "page": 2, "x0": 61.0, "x1": 171.9, "bottom": 304.1,
                      "field": "company_address", "size": 9})
        spots.append({"type": "sig", "page": 2, "x0": 61.0, "x1": 253.8, "bottom": 320.9, "h": 26})
        # page 2 — aval guarantor #1 (rightmost column)
        spots.append({"type": "text", "page": 2, "x0": 437.7, "x1": 515.4, "bottom": 480.7,
                      "field": "full_name", "size": 8})
        spots.append({"type": "text", "page": 2, "x0": 434.8, "x1": 512.6, "bottom": 496.4,
                      "field": "id_number", "size": 8})
        spots.append({"type": "text", "page": 2, "x0": 403.5, "x1": 514.7, "bottom": 512.2,
                      "field": "company_address", "size": 7})
        spots.append({"type": "sig", "page": 2, "x0": 440.5, "x1": 501.5, "bottom": 527.9, "h": 18})

    docs_spec.append({"file": f"{num}.pdf", "name": display, "dash_doc_type": dash_type, "spots": spots})
    print(f"doc{num}: {len(spots)} spots ({n_pages} pages)")

package = {
    "token": TOKEN,
    "client": 'תלס הנדסה בע"מ',
    "client_hp": "513991463",
    "fields": [
        {"key": "full_name", "label": "שם מלא של החותם (מורשה החתימה ובעל השליטה)", "required": True},
        {"key": "id_number", "label": "מספר תעודת זהות", "required": True, "inputmode": "numeric"},
        {"key": "company_address", "label": "כתובת רשומה של החברה (רחוב, מספר, עיר)", "required": True},
        {"key": "phone", "label": "טלפון נייד של החותם", "required": True, "inputmode": "tel", "type": "tel"},
        {"key": "role", "label": "תפקיד בחברה", "required": True, "options": ["בעלים", "מנהל", "בעלים ומנהל"]},
        {"key": "email", "label": 'דוא"ל של החותם', "required": True, "type": "email"},
    ],
    "docs": docs_spec,
}

with open(os.path.join(PKG_DIR, "package.json"), "w", encoding="utf-8") as f:
    json.dump(package, f, ensure_ascii=False, indent=1)
print("package written:", PKG_DIR)
