# -*- coding: utf-8 -*-
"""PDF stamping engine — embeds signature image + form fields into PDFs at
pre-measured coordinates, and appends an electronic-signature audit page.

Coordinates in the package spec use pdfplumber's space (origin top-left,
y grows downward); converted here to reportlab space (origin bottom-left).
"""
import base64
import hashlib
import io
import os

from bidi.algorithm import get_display
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

BASE = os.path.dirname(os.path.abspath(__file__))
FONT = "Alef"
FONT_BOLD = "Alef-Bold"
INK = (0.10, 0.14, 0.42)  # dark blue ink

_registered = False


def _ensure_fonts():
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, os.path.join(BASE, "fonts", "Alef-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(BASE, "fonts", "Alef-Bold.ttf")))
        _registered = True


def heb(text):
    """Hebrew logical -> visual for reportlab."""
    return get_display(str(text))


def load_signature(data_url, max_bytes=800_000):
    """data:image/png;base64,... -> trimmed RGBA PIL image."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    if len(raw) > max_bytes:
        raise ValueError("signature image too large")
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("empty signature")
    return img.crop(bbox)


def _fit_text(c, text, width, size, min_size=6):
    while size > min_size and pdfmetrics.stringWidth(text, FONT, size) > width:
        size -= 0.5
    return size


def _draw_spot(c, spot, fields, sig_img, page_h):
    kind = spot["type"]
    if kind == "text":
        value = fields.get(spot["field"], "")
        if not value:
            return
        text = heb(value)
        x0, x1 = spot["x0"], spot["x1"]
        size = _fit_text(c, text, x1 - x0 - 2, spot.get("size", 9))
        # sit on the underline: baseline just above the blank's bottom
        y = page_h - spot["bottom"] + 1.5
        c.setFont(FONT, size)
        c.setFillColorRGB(*INK)
        c.drawCentredString((x0 + x1) / 2.0, y, text)
    elif kind == "sig":
        x0, x1 = spot["x0"], spot["x1"]
        box_w = x1 - x0
        box_h = spot.get("h", 24)
        iw, ih = sig_img.size
        scale = min(box_w / iw, box_h / ih)
        w, h = iw * scale, ih * scale
        y = page_h - spot["bottom"] + 1.0  # image bottom sits on the line
        x = x0 + (box_w - w) / 2.0
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(sig_img), x, y, width=w, height=h, mask="auto")


def _overlay_pdf(spec_doc, fields, sig_img, page_sizes):
    """Build a multi-page overlay PDF matching page_sizes with all spots drawn."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf)
    spots_by_page = {}
    for spot in spec_doc["spots"]:
        spots_by_page.setdefault(spot["page"], []).append(spot)
    for pi, (w, h) in enumerate(page_sizes, 1):
        c.setPageSize((w, h))
        for spot in spots_by_page.get(pi, []):
            _draw_spot(c, spot, fields, sig_img, h)
        c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def _audit_page(doc_name, audit, original_sha):
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    right = W - 50
    c.setFillColorRGB(0.176, 0.314, 0.086)  # brand green
    c.rect(0, H - 70, W, 70, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(FONT_BOLD, 16)
    c.drawRightString(right, H - 42, heb("נספח תיעוד חתימה אלקטרונית"))
    c.setFont(FONT, 10)
    c.drawRightString(right, H - 58, heb("פסגת ליאם כ\"א בע\"מ — מערכת החתימות"))

    rows = [
        ("מסמך", doc_name),
        ("מזהה הליך חתימה", audit["submission_id"]),
        ("נחתם על ידי", audit["fields"].get("full_name", "")),
        ("מספר זהות", audit["fields"].get("id_number", "")),
        ("תפקיד", audit["fields"].get("role", "")),
        ("דוא\"ל החותם", audit["fields"].get("email", "")),
        ("טלפון החותם", audit["fields"].get("phone", "")),
        ("כתובת החברה", audit["fields"].get("company_address", "")),
        ("מועד החתימה (שעון ישראל)", audit["signed_at_il"]),
        ("מועד החתימה (UTC)", audit["signed_at_utc"]),
        ("כתובת IP", audit["ip"]),
        ("דפדפן / מכשיר", audit["user_agent"][:95]),
        ("טביעת אצבע של המסמך המקורי (SHA-256)", original_sha),
    ]
    y = H - 110
    for label, value in rows:
        c.setFillColorRGB(0.176, 0.314, 0.086)
        c.setFont(FONT_BOLD, 10)
        c.drawRightString(right, y, heb(label))
        c.setFillColorRGB(0.09, 0.10, 0.07)
        # values that are technical (hash/ua/ip/id) stay LTR
        c.setFont(FONT, 9)
        val = str(value)
        if any("֐" <= ch <= "ת" for ch in val):
            c.drawRightString(right, y - 13, heb(val))
        else:
            c.drawRightString(right, y - 13, val)
        y -= 34
        if y < 120:
            break

    c.setFillColorRGB(0.35, 0.38, 0.33)
    c.setFont(FONT, 8.5)
    consent_lines = [
        "החותם אישר בעת ההליך: \"קראתי את המסמך במלואו, אני מוסמך/ת לחתום בשם המזמין, ואני",
        "מסכים/ה כי חתימתי האלקטרונית מחייבת כדין כחתימת ידי לכל דבר ועניין.\"",
        "החתימה צוירה בכתב ידו של החותם על גבי מסך המכשיר והוטבעה בכל מקומות החתימה במסמך.",
    ]
    yy = 95
    for line in consent_lines:
        c.drawRightString(right, yy, heb(line))
        yy -= 12
    c.showPage()
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def stamp_document(pdf_path, spec_doc, fields, sig_img, audit):
    """Return (signed_bytes, original_sha256)."""
    _ensure_fonts()
    with open(pdf_path, "rb") as f:
        original = f.read()
    original_sha = hashlib.sha256(original).hexdigest()

    reader = PdfReader(io.BytesIO(original))
    page_sizes = [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages]
    overlay = _overlay_pdf(spec_doc, fields, sig_img, page_sizes)

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)
    for page in _audit_page(spec_doc["name"], audit, original_sha).pages:
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), original_sha
