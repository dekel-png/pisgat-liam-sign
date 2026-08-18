# -*- coding: utf-8 -*-
"""One-time: measure the generic master PDFs and emit agreements/sign_spots.json —
mint_spots (client details, stamped at pack creation) + sign_spots (signature/
fields, stamped at signing).

pdfplumber splits long underscore runs unpredictably, so adjacent blank words
are MERGED first; classification is context-driven (labels, ₪, date words),
with char-length only as a tolerant fallback. Hebrew extracts in visual order →
all anchors are reversed strings.
"""
import json
import os

import pdfplumber

MASTERS = r"C:\Users\PC\OneDrive\Desktop\pisgat-liam-dashboard\agreements\sign-masters"
OUT = r"C:\Users\PC\OneDrive\Desktop\pisgat-liam-dashboard\agreements\sign_spots.json"

DOCS = {
    1: ("1 - הסכם מסגרת", "הסכם מסגרת"),
    2: ("2 - נספח א - תנאים מסחריים", "נספח א — תנאים מסחריים"),
    3: ("3 - נספח ב - טופס הזמנת עובדים", "נספח ב — טופס הזמנת עובדים"),
    4: ("4 - ערבויות ובטוחות", "ערבויות ובטוחות"),
}

problems = []


def words_of(path):
    out = []
    with pdfplumber.open(path) as pdf:
        for pi, page in enumerate(pdf.pages, 1):
            for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
                out.append({"page": pi, "text": w["text"], "x0": round(w["x0"], 1),
                            "x1": round(w["x1"], 1), "top": round(w["top"], 1),
                            "bottom": round(w["bottom"], 1)})
    return out


def merged_blanks(words):
    """Underscore-run words (trailing ,/. tolerated) merged when adjacent on
    the same line. text is normalized to the underscores only."""
    pure = []
    for w in words:
        core = w["text"].strip(",.")
        if core and set(core) == {"_"}:
            pure.append({**w, "text": core})
    pure.sort(key=lambda w: (w["page"], round(w["top"]), w["x0"]))
    out = []
    for w in pure:
        if (out and out[-1]["page"] == w["page"]
                and abs(out[-1]["top"] - w["top"]) < 2.5
                and 0 <= w["x0"] - out[-1]["x1"] < 5):
            out[-1]["x1"] = w["x1"]
            out[-1]["text"] += w["text"]
            out[-1]["bottom"] = max(out[-1]["bottom"], w["bottom"])
        else:
            out.append(dict(w))
    return out


def same_line(a, b, tol=3.0):
    return abs(a["top"] - b["top"]) < tol


def on_line(words, blank, rev_text, contains=False):
    return [w for w in words
            if w["page"] == blank["page"] and same_line(w, blank)
            and ((rev_text in w["text"]) if contains else (w["text"] == rev_text))]


def left_adjacent(blanks_, label, max_gap=14):
    """Blank ending just left of a label (RTL value position)."""
    cands = [b for b in blanks_ if b["page"] == label["page"] and same_line(b, label)
             and -2 <= label["x0"] - b["x1"] <= max_gap]
    return sorted(cands, key=lambda b: -b["x1"])


def t_spot(b, field, size=9):
    return {"type": "text", "page": b["page"], "x0": b["x0"], "x1": b["x1"],
            "bottom": b["bottom"], "field": field, "size": size}


def s_spot(b, h):
    return {"type": "sig", "page": b["page"], "x0": b["x0"], "x1": b["x1"],
            "bottom": b["bottom"], "h": h}


spec_docs = []

for num, (display, dash_type) in DOCS.items():
    words = words_of(os.path.join(MASTERS, f"{num}.pdf"))
    n_pages = max(w["page"] for w in words)
    B = merged_blanks(words)
    mint, sign = [], []
    used = set()

    def take(b):
        used.add((b["page"], b["x0"], b["top"]))

    def free(b):
        return (b["page"], b["x0"], b["top"]) not in used

    def line_has(b, pred):
        return any(pred(w) for w in words
                   if w["page"] == b["page"] and same_line(w, b))

    # ── 1. header slash date (line contains שנחתם) — FIRST, it also
    #      contains 'ביום' which would confuse the hebrew-date rule ──
    for p in range(1, n_pages + 1):
        hdr = [w for w in words if w["page"] == p and w["text"] == "םתחנש"]
        if hdr:
            line = sorted([b for b in B if free(b) and same_line(b, hdr[0])
                           and b["page"] == p], key=lambda b: -b["x0"])
            if len(line) == 3:
                for b, f in zip(line, ("date_dd", "date_mm", "date_yyyy")):
                    mint.append(t_spot(b, f)); take(b)
            else:
                problems.append(f"doc{num} p{p}: header date blanks={len(line)}")

    # ── 2. doc2 v2: rate cells (2 lines ×3), housing (2 lines), payment (3) ──
    if num == 2:
        wide = sorted([b for b in B if free(b) and len(b["text"]) >= 70],
                      key=lambda b: (b["page"], b["top"]))
        if len(wide) != 5:
            problems.append(f"doc2: wide blanks={len(wide)} (expected 5)")
        else:
            for b, f in zip(wide, ("housing_l1", "housing_l2",
                                   "payment_l1", "payment_l2", "payment_l3")):
                mint.append(t_spot(b, f)); take(b)
        # שורות הטבלה לפי סדר המאסטר: תאילנד, אוזבקיסטן, סרי לנקה — כל
        # מדינה מקבלת שדה תעריף משלה (rate_th / rate_uz / rate_lk)
        rate_b = sorted([b for b in B if free(b) and 28 <= len(b["text"]) <= 40
                         and b["x0"] < 150],
                        key=lambda b: (b["page"], b["top"]))
        if len(rate_b) != 6:
            problems.append(f"doc2: rate blanks={len(rate_b)} (expected 6)")
        else:
            for i, origin in zip(range(0, 6, 2), ("th", "uz", "lk")):
                l1, l2 = rate_b[i], rate_b[i + 1]
                if l2["top"] - l1["top"] > 20:
                    problems.append(f"doc2: rate pair {origin} not adjacent")
                mint.append(t_spot(l1, f"rate_{origin}_l1")); take(l1)
                mint.append(t_spot(l2, f"rate_{origin}_l2")); take(l2)

    # ── 3. hebrew date words (skip שנחתם header + promissory לשלם) ─
    for rev_label, field in (("םויב", "date_day"), ("םוי", "date_day"),
                             ("שדוחב", "date_month_he"), ("שדוח", "date_month_he"),
                             ("תנש", "date_year")):
        for lab in [w for w in words if w["text"] == rev_label]:
            if line_has(lab, lambda w: w["text"] in ("םלשל", "םתחנש")):
                continue
            adj = [b for b in left_adjacent(B, lab) if free(b)]
            if adj:
                mint.append(t_spot(adj[0], field)); take(adj[0])

    # ── 4. client name / hp — length + line-context (avoids the long
    #      signature blanks of doc3 and date-month fragments) ────────
    for b in B:
        if not free(b):
            continue
        n = len(b["text"])
        near_hp = line_has(b, lambda w: ".פ.ח" in w["text"])
        if 27 <= n <= 33 and (near_hp or line_has(
                b, lambda w: w["text"] in (":םש", ":ןיבל") or "ןיבל" in w["text"])):
            mint.append(t_spot(b, "client_name")); take(b)
        elif 10 <= n <= 12 and near_hp:
            mint.append(t_spot(b, "client_hp")); take(b)

    if num == 1:
        # mint: emails/phones lines
        for b in B:
            if not free(b) or len(b["text"]) < 30:
                continue
            if on_line(words, b, ':ל"אוד'):
                mint.append(t_spot(b, "emails", size=8)); take(b)
            elif on_line(words, b, ":ןופלט"):
                mint.append(t_spot(b, "phones", size=8)); take(b)
        # sign: client address (מרח' line without יאיר)
        addr = [b for b in B if free(b) and b["page"] == 1
                and on_line(words, b, "'חרמ", contains=True)
                and not on_line(words, b, "ריאי", contains=True)]
        if len(addr) == 1:
            sign.append(t_spot(addr[0], "company_address")); take(addr[0])
        else:
            problems.append(f"doc1: client addr blanks={len(addr)}")
        # sign: signatory name + id on the מטעמו line
        mt = [w for w in words if w["page"] == 1 and ":ומעטמ" in w["text"]]
        if mt:
            line = sorted([b for b in B if free(b) and same_line(b, mt[0])],
                          key=lambda b: -b["x0"])
            if len(line) >= 2:
                sign.append(t_spot(line[0], "full_name")); take(line[0])
                sign.append(t_spot(line[1], "id_number")); take(line[1])
            else:
                problems.append(f"doc1: signatory blanks={len(line)}")
        else:
            problems.append("doc1: מטעמו anchor missing")

    if num == 4:
        # v2: note-sum blanks (digits + words) — optional mint fields; empty = open
        # note. The words blank can wrap to the line BELOW "במילים:", so the
        # search window extends a line down from the label.
        bl_labels = [w for w in words if "םילימב" in w["text"]]
        for lab in bl_labels[:1]:
            for b in list(B):
                if not free(b) or b["page"] != lab["page"]:
                    continue
                if not (-3 <= b["top"] - lab["top"] <= 22):
                    continue
                if len(b["text"]) >= 20:
                    mint.append(t_spot(b, "note_sum_words", size=8)); take(b)
                elif 10 <= len(b["text"]) <= 18 and same_line(b, lab):
                    mint.append(t_spot(b, "note_sum")); take(b)
        # part A table (p1): labels on the right, value band to the left
        for rev_label, field in (("אלמ", "full_name"), (".ז.ת", "id_number"),
                                 ("תבותכ", "company_address"), ("ןופלט", "phone"),
                                 ("דיקפת", "role")):
            labs = [w for w in words if w["page"] == 1 and w["text"] == rev_label
                    and w["x0"] > 400 and 280 < w["top"] < 420]
            if not labs:
                problems.append(f"doc4: table label {field} missing")
                continue
            lab = labs[0]
            bl = [b for b in B if free(b) and b["page"] == 1
                  and same_line(b, lab, 8) and b["x1"] < 412]
            if bl:
                sign.append(t_spot(bl[0], field)); take(bl[0])
            else:  # empty cell (phone row has no blank)
                sign.append({"type": "text", "page": 1, "x0": 292.8, "x1": 403.9,
                             "bottom": lab["bottom"] + 6, "field": field, "size": 9})
        # שם הערב / ת.ז line (p1)
        for rev_label, field in ((":ברעה", "full_name"), (":.ז.ת", "id_number")):
            labs = [w for w in words if w["page"] == 1 and w["text"] == rev_label
                    and w["top"] > 480]
            for lab in labs[:1]:
                near = [b for b in B if free(b) and b["page"] == 1
                        and same_line(b, lab) and b["x1"] <= lab["x0"] + 2]
                near = sorted(near, key=lambda b: -b["x1"])
                if near:
                    sign.append(t_spot(near[0], field)); take(near[0])
                else:
                    problems.append(f"doc4: ערב {field} blank missing")
        # p1 signature + mint date on the same line
        sig1 = [w for w in words if w["page"] == 1 and w["text"] == ":המיתח"
                and w["top"] > 500]
        if sig1:
            bl = [b for b in B if free(b) and b["page"] == 1 and same_line(b, sig1[0])
                  and b["x1"] <= sig1[0]["x0"] + 2]
            if bl:
                b = sorted(bl, key=lambda x: -x["x1"])[0]
                sign.append(s_spot(b, 26)); take(b)
        dt = [w for w in words if w["page"] == 1 and w["text"] == ":ךיראת"
              and w["top"] > 500]
        if dt:
            bl = [b for b in B if free(b) and b["page"] == 1 and same_line(b, dt[0])
                  and b["x1"] <= dt[0]["x0"] + 2]
            if bl:
                b = sorted(bl, key=lambda x: -x["x1"])[0]
                mint.append(t_spot(b, "date_full")); take(b)
        # p2: note maker מען + חתימה
        maen = [w for w in words if w["page"] == 2 and w["text"] == ":ןעמ"
                and 150 < w["x0"] < 220 and w["top"] < 350]
        if maen:
            bl = [b for b in B if free(b) and b["page"] == 2 and same_line(b, maen[0])]
            if bl:
                sign.append(t_spot(bl[0], "company_address")); take(bl[0])
        sig2 = [w for w in words if w["page"] == 2 and w["text"] == ":המיתח"
                and w["top"] < 360]
        if sig2:
            bl = [b for b in B if free(b) and b["page"] == 2 and same_line(b, sig2[0])]
            if bl:
                sign.append(s_spot(bl[0], 26)); take(bl[0])
        # p2: aval guarantor #1 — rightmost column (labels at x>500)
        for rev_label, field, size in ((":םש", "full_name", 8),
                                       (":.ז.ת", "id_number", 8),
                                       (":ןעמ", "company_address", 7)):
            labs = [w for w in words if w["page"] == 2 and w["text"] == rev_label
                    and w["x0"] > 500 and w["top"] > 460]
            for lab in labs[:1]:
                bl = [b for b in B if free(b) and b["page"] == 2 and same_line(b, lab)
                      and b["x0"] > 390 and b["x1"] <= lab["x0"] + 2]
                if bl:
                    sign.append(t_spot(bl[0], field, size=size)); take(bl[0])
                else:
                    problems.append(f"doc4 p2: aval {field} blank missing")
        sig3 = [w for w in words if w["page"] == 2 and w["text"] == ":המיתח"
                and w["x0"] > 495 and w["top"] > 500]
        if sig3:
            bl = [b for b in B if free(b) and b["page"] == 2 and same_line(b, sig3[0])
                  and b["x0"] > 400]
            if bl:
                sign.append(s_spot(bl[0], 18)); take(bl[0])

    # footers on every page
    for p in range(1, n_pages + 1):
        f_lab = [w for w in words if w["page"] == p and w["text"] == ":ןימזמה"
                 and w["top"] > 770]
        if not f_lab:
            problems.append(f"doc{num} p{p}: footer label missing")
            continue
        bl = [b for b in B if free(b) and b["page"] == p and same_line(b, f_lab[0])]
        if bl:
            sign.append(s_spot(bl[0], 15)); take(bl[0])
        else:
            problems.append(f"doc{num} p{p}: footer blank missing")

    # final signature box (docs 1-2)
    if num in (1, 2):
        labels = [w for w in words if w["page"] == n_pages and w["text"] == "ןימזמה"
                  and 140 < w["top"] < 770]
        placed = False
        for lab in sorted(labels, key=lambda w: w["top"]):
            cands = [b for b in B if free(b) and b["page"] == n_pages
                     and 4 < lab["top"] - b["bottom"] < 40
                     and not (b["x1"] < lab["x0"] - 60 or b["x0"] > lab["x1"] + 60)]
            if cands:
                sign.append(s_spot(cands[0], 34)); take(cands[0])
                placed = True
                break
        if not placed:
            problems.append(f"doc{num}: final signature box missing")

    spec_docs.append({"file": f"{num}.pdf", "name": display, "dash_doc_type": dash_type,
                      "mint_spots": mint, "sign_spots": sign})
    print(f"doc{num}: mint={len(mint)} sign={len(sign)}")

spec = {
    "fields": [
        {"key": "full_name", "label": "שם מלא של החותם (מורשה החתימה ובעל השליטה)", "required": True},
        {"key": "id_number", "label": "מספר תעודת זהות", "required": True, "inputmode": "numeric"},
        {"key": "company_address", "label": "כתובת רשומה של החברה (רחוב, מספר, עיר)", "required": True},
        {"key": "phone", "label": "טלפון נייד של החותם", "required": True, "inputmode": "tel", "type": "tel"},
        {"key": "role", "label": "תפקיד בחברה", "required": True, "options": ["בעלים", "מנהל", "בעלים ומנהל"]},
        {"key": "email", "label": 'דוא"ל של החותם', "required": True, "type": "email"},
    ],
    "docs": spec_docs,
}

# expected-count sanity per doc
EXPECT = {1: {"client_name": 1, "client_hp": 1, "emails": 1, "phones": 1,
              "date_day": 1, "date_month_he": 1, "date_year": 1},
          2: {"client_name": 1, "client_hp": 1,
              "rate_th_l1": 1, "rate_th_l2": 1, "rate_uz_l1": 1, "rate_uz_l2": 1,
              "rate_lk_l1": 1, "rate_lk_l2": 1,
              "housing_l1": 1, "housing_l2": 1,
              "payment_l1": 1, "payment_l2": 1, "payment_l3": 1,
              "date_dd": 1, "date_mm": 1, "date_yyyy": 1},
          3: {"client_name": 1, "client_hp": 1, "date_dd": 1, "date_mm": 1, "date_yyyy": 1},
          4: {"client_name": 4, "client_hp": 4, "date_dd": 1, "date_mm": 1, "date_yyyy": 1,
              "date_day": 1, "date_month_he": 1, "date_year": 1, "date_full": 1,
              "note_sum": 1, "note_sum_words": 1}}
for num, doc in zip(DOCS, spec_docs):
    got = {}
    for m in doc["mint_spots"]:
        got[m["field"]] = got.get(m["field"], 0) + 1
    if got != EXPECT[num]:
        problems.append(f"doc{num} mint mismatch: got {got} expected {EXPECT[num]}")

if problems:
    print("!! PROBLEMS:")
    for p in problems:
        print("  ", p)
    raise SystemExit(1)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(spec, f, ensure_ascii=False, indent=1)
print("spec written:", OUT)
