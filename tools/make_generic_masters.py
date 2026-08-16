# -*- coding: utf-8 -*-
"""One-time: build GENERIC master DOCX set (all client data = blank lines) from
the volume template. These masters let the dashboard mint a client-specific,
overlay-stamped set on Linux (no Word needed) — the manager self-service flow.

Blanks minted later by the server: client name, ח.פ, rate, date, emails, phone.
Run locally, convert to PDF with Word, then measure anchors (make_master_spec.py).
"""
import io
import os
import re
import zipfile

TEMPLATE_DIR = r"C:\Users\PC\OneDrive\Desktop\my-aios\outputs\documents\2026-08-02-volume-construction-signing-set"
OUT = r"C:\Users\PC\OneDrive\Desktop\pisgat-liam-dashboard\agreements\sign-masters"

T_CLIENT = 'ווליום בנייה וביצוע בע"מ'
T_HP = "517152443"
T_ADDR = "משאבים 19, הוד השרון"
T_NAME = "נדב וולינץ"
T_TZ = "037969201"
NAME_B = "______________________________"   # client name blank (wide)
HP_B = "___________"
RATE_B = "_____"
BLANK = "____________________"
NBLANK = "______________"

PARA = ('<w:p><w:pPr><w:bidi/><w:spacing w:after="30" w:before="40" w:line="276"/>'
        '<w:ind w:start="400"/><w:jc w:val="right"/></w:pPr><w:r><w:rPr>'
        '<w:rFonts w:ascii="Arial" w:cs="Arial" w:eastAsia="Arial" w:hAnsi="Arial"/>'
        '<w:b w:val="false"/><w:bCs w:val="false"/><w:i w:val="false"/><w:iCs w:val="false"/>'
        '<w:color w:val="000000"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:rtl/></w:rPr>'
        '<w:t xml:space="preserve">{}</w:t></w:r></w:p>')

FILES = {
    1: "1 - הסכם מסגרת",
    2: "2 - נספח א - תנאים מסחריים",
    3: "3 - נספח ב - טופס הזמנת עובדים",
    4: "4 - ערבויות ובטוחות",
}

errors = []


def rep(xml, old, new, expected, label):
    n = xml.count(old)
    if n != expected:
        errors.append(f"{label}: expected {expected}, found {n}")
        return xml
    return xml.replace(old, new)


def rep_re(xml, pattern, new, expected, label):
    found = re.findall(pattern, xml)
    if len(found) != expected:
        errors.append(f"{label}: expected {expected}, found {len(found)}")
        return xml
    return re.sub(pattern, new, xml)


os.makedirs(OUT, exist_ok=True)
for num, base in FILES.items():
    src = os.path.join(TEMPLATE_DIR, f"{base} - ווליום בנייה וביצוע.docx")
    zin = zipfile.ZipFile(src, "r")
    xml = zin.read("word/document.xml").decode("utf-8")

    xml = rep(xml, T_CLIENT, NAME_B, {1: 1, 2: 1, 3: 1, 4: 4}[num], f"doc{num} client")
    xml = rep(xml, T_HP, HP_B, {1: 1, 2: 1, 3: 1, 4: 4}[num], f"doc{num} hp")

    if num == 1:
        xml = rep(xml, "ביום 2 בחודש אוגוסט שנת 2026",
                  "ביום ____ בחודש __________ שנת ______", 1, "doc1 date")
        xml = rep(xml, f"מטעמו: {T_NAME} ת.ז. {T_TZ},",
                  "מטעמו: ________________ ת.ז. ______________,", 1, "doc1 signatory")
        xml = rep(xml, f"מרח' {T_ADDR}", "מרח' " + BLANK, 1, "doc1 addr")
        anchor = f"מרח' {BLANK}</w:t></w:r></w:p>"
        i = xml.find(anchor)
        assert i != -1
        xml = (xml[:i + len(anchor)]
               + PARA.format('דוא"ל: ________________________________________')
               + PARA.format("טלפון: ________________________________________")
               + xml[i + len(anchor):])

    if num == 2:
        xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", "___ / ___ / ______", 1, "doc2 date")
        xml = rep(xml, "80 ₪ לשעה בחודש הראשון להתקשרות; 85 ₪ לשעה החל מהחודש השני ואילך",
                  f"{RATE_B} ₪ לשעה", 1, "doc2 price main")
        xml = rep_re(xml, r"(<w:t[^>]*>)—(</w:t>)", rf"\g<1>{RATE_B} ₪ לשעה\g<2>", 2, "doc2 dashes")

    if num == 3:
        xml = rep(xml, "<w:t>5</w:t>", '<w:t xml:space="preserve"> </w:t>', 1, "doc3 qty")
        xml = rep(xml, "<w:t>אוזבקיסטן</w:t>", '<w:t xml:space="preserve"> </w:t>', 1, "doc3 origin")
        xml = rep(xml, "<w:t>עבודות שלד (כולל ברזלנות לפי צורכי האתר)</w:t>",
                  '<w:t xml:space="preserve"> </w:t>', 1, "doc3 notes")
        xml = rep(xml, "תאריך: 02/08/2026", "תאריך: ______________", 1, "doc3 date")
        xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", "___ / ___ / ______", 1, "doc3 header date")
        xml = rep_re(xml, r"כמות שאושרה: 5(\s+)מדינות מוצא: אוזבקיסטן",
                     r"כמות שאושרה: ________\1מדינות מוצא: ________________", 1, "doc3 approved")
        xml = rep_re(xml, rf"שם החותם: {T_NAME}(\s+)תפקיד: בעלים ומנהל",
                     r"שם החותם: ______________\1תפקיד: ______________", 1, "doc3 signer")

    if num == 4:
        xml = rep(xml, "יום 2 חודש אוגוסט שנת 2026",
                  "יום ____ חודש __________ שנת ______", 1, "doc4 note date")
        xml = rep(xml, T_ADDR, BLANK, 3, "doc4 addresses")
        xml = rep(xml, T_NAME, NBLANK, 3, "doc4 names")
        xml = rep(xml, T_TZ, NBLANK, 3, "doc4 tz")
        xml = rep(xml, "<w:t>בעלים ומנהל</w:t>", f"<w:t>{NBLANK}</w:t>", 1, "doc4 role")
        xml = rep(xml, "תאריך: 02/08/2026", "תאריך: ______________", 1, "doc4 g-date")
        xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", "___ / ___ / ______", 1, "doc4 header date")
        xml = rep(xml, 'סך של 150,000 ש"ח (במילים: מאה וחמישים אלף ש"ח)',
                  'סך של ______________ ש"ח (במילים: ________________________ ש"ח)', 1, "doc4 sum")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    zin.close()
    with open(os.path.join(OUT, f"{num}.docx"), "wb") as f:
        f.write(buf.getvalue())
    print(f"master doc{num} written")

if errors:
    print("!! ERRORS:")
    for e in errors:
        print("  ", e)
    raise SystemExit(1)
print("GENERIC MASTERS OK ->", OUT)
