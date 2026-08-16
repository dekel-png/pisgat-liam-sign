# -*- coding: utf-8 -*-
"""Build a client's 4-doc signing set (DOCX) from the volume master template.

All replacements are exact-count-verified — any template drift fails loudly
instead of producing a wrong contract. Contact details (emails/phones) go on
the CLIENT side of the framework agreement (lesson from the Salhov set).

Usage:
  python make_client_docx_set.py --name "מאיר סלהוב אינסטלציה בע\"מ" --hp 514328541 \
      --rate 85 --emails "a@x.co.il,b@x.co.il" --phones "משרד: 03-1111111 · נייד: 052-2222222" \
      --date 16/08/2026 --out "C:\\...\\2026-08-16-client-signing-set"

Then: convert to PDF with Word COM (see the client-signing-pack skill).
"""
import argparse
import io
import os
import re
import zipfile

TEMPLATE_DIR = r"C:\Users\PC\OneDrive\Desktop\my-aios\outputs\documents\2026-08-02-volume-construction-signing-set"

T_CLIENT = 'ווליום בנייה וביצוע בע"מ'
T_HP = "517152443"
T_ADDR = "משאבים 19, הוד השרון"
T_NAME = "נדב וולינץ"
T_TZ = "037969201"
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


def rep(xml, old, new, expected, label, errors):
    n = xml.count(old)
    if n != expected:
        errors.append(f"{label}: expected {expected}, found {n}")
        return xml
    return xml.replace(old, new)


def rep_re(xml, pattern, new, expected, label, errors):
    found = re.findall(pattern, xml)
    if len(found) != expected:
        errors.append(f"{label}: expected {expected}, found {len(found)}")
        return xml
    return re.sub(pattern, new, xml)


def drop_paragraph_with(xml, needle):
    i = xml.find(needle)
    if i == -1:
        return xml, False
    return xml[:xml.rfind("<w:p>", 0, i)] + xml[xml.find("</w:p>", i) + len("</w:p>"):], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="client legal name incl. בע\"מ")
    ap.add_argument("--short", help="short name for filenames (default: name)")
    ap.add_argument("--hp", required=True)
    ap.add_argument("--rate", required=True, help="₪/hour before VAT, e.g. 85")
    ap.add_argument("--emails", default="", help="comma-separated client emails")
    ap.add_argument("--phones", default="", help='client phone line, e.g. "טל\' משרד: 03-... · נייד: 052-..."')
    ap.add_argument("--date", required=True, help="DD/MM/YYYY")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    short = a.short or a.name
    day, month, year = a.date.split("/")
    day_i, month_i = int(day), int(month)
    MONTHS = {1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל", 5: "מאי", 6: "יוני",
              7: "יולי", 8: "אוגוסט", 9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר"}
    month_he = MONTHS[month_i]
    os.makedirs(a.out, exist_ok=True)
    all_errors = []

    for num, base in FILES.items():
        src = os.path.join(TEMPLATE_DIR, f"{base} - ווליום בנייה וביצוע.docx")
        dst = os.path.join(a.out, f"{base} - {short}.docx")
        zin = zipfile.ZipFile(src, "r")
        xml = zin.read("word/document.xml").decode("utf-8")
        errors = []

        xml = rep(xml, T_CLIENT, a.name, {1: 1, 2: 1, 3: 1, 4: 4}[num], "client name", errors)
        xml = rep(xml, T_HP, a.hp, {1: 1, 2: 1, 3: 1, 4: 4}[num], "hp", errors)

        if num == 1:
            xml = rep(xml, "ביום 2 בחודש אוגוסט שנת 2026",
                      f"ביום {day_i} בחודש {month_he} שנת {year}", 1, "date", errors)
            xml = rep(xml, f"מטעמו: {T_NAME} ת.ז. {T_TZ},",
                      "מטעמו: ________________ ת.ז. ______________,", 1, "signatory", errors)
            xml = rep(xml, f"מרח' {T_ADDR}", "מרח' " + BLANK, 1, "client addr", errors)
            # client-side contact lines (emails + phones), inserted under the blank address
            anchor = f"מרח' {BLANK}</w:t></w:r></w:p>"
            i = xml.find(anchor)
            if i == -1:
                errors.append("client addr anchor for contacts not found")
            else:
                extra = ""
                if a.emails:
                    extra += PARA.format('דוא"ל: ' + " / ".join(
                        e.strip() for e in a.emails.split(",") if e.strip()))
                if a.phones:
                    extra += PARA.format(a.phones)
                xml = xml[:i + len(anchor)] + extra + xml[i + len(anchor):]

        if num == 2:
            xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", f"{day} / {month} / {year}", 1, "date", errors)
            xml = rep(xml, "80 ₪ לשעה בחודש הראשון להתקשרות; 85 ₪ לשעה החל מהחודש השני ואילך",
                      f"{a.rate} ₪ לשעה", 1, "price main", errors)
            xml = rep_re(xml, r"(<w:t[^>]*>)—(</w:t>)", rf"\g<1>{a.rate} ₪ לשעה\g<2>", 2, "price dashes", errors)

        if num == 3:
            xml = rep(xml, "<w:t>5</w:t>", '<w:t xml:space="preserve"> </w:t>', 1, "qty cell", errors)
            xml = rep(xml, "<w:t>אוזבקיסטן</w:t>", '<w:t xml:space="preserve"> </w:t>', 1, "origin cell", errors)
            xml = rep(xml, "<w:t>עבודות שלד (כולל ברזלנות לפי צורכי האתר)</w:t>",
                      '<w:t xml:space="preserve"> </w:t>', 1, "notes cell", errors)
            xml = rep(xml, "תאריך: 02/08/2026", "תאריך: ______________", 1, "sig date blank", errors)
            xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", f"{day} / {month} / {year}", 1, "header date", errors)
            xml = rep_re(xml, r"כמות שאושרה: 5(\s+)מדינות מוצא: אוזבקיסטן",
                         r"כמות שאושרה: ________\1מדינות מוצא: ________________", 1, "approved qty", errors)
            xml = rep_re(xml, rf"שם החותם: {T_NAME}(\s+)תפקיד: בעלים ומנהל",
                         r"שם החותם: ______________\1תפקיד: ______________", 1, "signer line", errors)

        if num == 4:
            xml = rep(xml, "יום 2 חודש אוגוסט שנת 2026",
                      f"יום {day_i} חודש {month_he} שנת {year}", 1, "note date", errors)
            xml = rep(xml, T_ADDR, BLANK, 3, "addresses", errors)
            xml = rep(xml, T_NAME, NBLANK, 3, "names", errors)
            xml = rep(xml, T_TZ, NBLANK, 3, "tz", errors)
            xml = rep(xml, "<w:t>בעלים ומנהל</w:t>", f"<w:t>{NBLANK}</w:t>", 1, "role cell", errors)
            xml = rep(xml, "תאריך: 02/08/2026", f"תאריך: {a.date}", 1, "guarantee date", errors)
            xml = rep_re(xml, r"02\s*/\s*08\s*/\s*2026", f"{day} / {month} / {year}", 1, "header date", errors)
            xml = rep(xml, 'סך של 150,000 ש"ח (במילים: מאה וחמישים אלף ש"ח)',
                      'סך של ______________ ש"ח (במילים: ________________________ ש"ח)', 1, "note sum", errors)

        if errors:
            all_errors += [f"doc{num} {e}" for e in errors]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/document.xml":
                    data = xml.encode("utf-8")
                zout.writestr(item, data)
        zin.close()
        with open(dst, "wb") as f:
            f.write(buf.getvalue())
        print(f"doc{num}: {dst}")

    if all_errors:
        print("!! TEMPLATE DRIFT — FIX BEFORE USE:")
        for e in all_errors:
            print("  ", e)
        raise SystemExit(1)
    print("ALL OK — convert to PDF (Word COM), then build the signing package.")


if __name__ == "__main__":
    main()
