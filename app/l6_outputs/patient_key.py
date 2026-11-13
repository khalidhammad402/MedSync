"""The patient key: a one-page, large-print picture list. German and English, PDF and plain text."""
from __future__ import annotations

import io
from datetime import date
from typing import Optional

from pydantic import BaseModel
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from sqlmodel import Session

from app import config
from app.l1_data import adapters, pills
from app.l1_data.adapters import Appearance
from app.l1_data.models import KeyIssue
from app.l2_classify import taxonomy as tx
from app.l3_resolve import pipeline
from app.l4_insight import actions
from app.l4_insight.recommend import required_parts

BODY = 18            # smallest body text size in points
TEXT = {
    "de": {"title": "Ihre Medikamente in Bildern", "new": "Was ist neu",
           "same": "Gleiches Medikament, neues Aussehen – nicht beide einnehmen.",
           "times": ["morgens", "mittags", "abends", "nachts"], "meal": "zum Essen", "old": "alt", "now": "neu",
           "unknown": "Aussehen bitte auf der Packung prüfen", "date": "Stand", "look": "Aussehen", "take": "Einnahme",
           "one_of": "eine von diesen", "plan": "MEDIKAMENTENPLAN"},
    "en": {"title": "Your medicines in pictures", "new": "What is new",
           "same": "Same medicine, new look – do not take both.",
           "times": ["morning", "noon", "evening", "night"], "meal": "with a meal", "old": "old", "now": "new",
           "unknown": "Please check the look on the box", "date": "Date", "look": "Looks like", "take": "Take",
           "one_of": "one of these", "plan": "MEDICINE LIST"},
}
SIZE_DE = {"small": "kleine", "medium": "mittelgroße", "large": "große"}
COLOR_DE = {"white": "weiße", "yellow": "gelbe", "orange": "orange", "pink": "rosa", "red": "rote", "brown": "braune",
            "green": "grüne", "blue": "blaue", "purple": "lila", "grey": "graue"}
SHAPE_DE = {"round": "runde", "oval": "ovale", "oblong": "längliche", "shield": "schildförmige", "capsule": ""}


class KeyRow(BaseModel):
    name: str
    strength: str
    purpose: str
    pill: Optional[Appearance] = None
    candidates: list[Appearance] = []
    slots: Optional[list[str]] = None      # doses for morning, noon, evening, night
    times: list[str] = []
    instruction: str
    with_meal: bool = False
    show_half: bool = False
    half_svg: str = ""
    look: str = ""


class KeyChange(BaseModel):
    name: str
    old: Appearance
    new: Appearance
    changed_on: date


class KeyData(BaseModel):
    patient_id: int
    patient_name: str
    lang: str
    issued_on: date
    rows: list[KeyRow]
    changes: list[KeyChange]
    text: dict


def look_text(a: Appearance, lang: str) -> str:
    if lang == "en":
        return pipeline.describe(a, short=True) + (" with a line" if a.score_line != "none" else "") + (
            f", marked {a.imprint}" if a.imprint else "")
    noun = "Kapsel" if a.shape == "capsule" else "Tablette"
    words = [SIZE_DE[tx.size_band(a.size_mm)], COLOR_DE[a.color], SHAPE_DE[a.shape], noun]
    text = " ".join(w for w in words if w)
    if a.score_line != "none":
        text += " mit Kerbe"
    if a.imprint:
        text += f", Aufdruck {a.imprint}"
    return text


def build_key(session: Session, patient_id: int, lang: str = "de", today: Optional[date] = None) -> KeyData:
    lang = lang if lang in TEXT else "de"
    today = today or config.today()
    patient = adapters.get_patient(session, patient_id)
    if patient is None:
        raise LookupError("Unknown patient.")
    rows, changes = [], []
    for med in pipeline.resolve_patient(session, patient_id, today):
        res = med.resolution
        slots = actions.dose_slots(med.instruction_text)
        need = required_parts(med.instruction_text)
        pill = res.product
        show_half = bool(pill and need and pill.divisible_parts >= need)
        strength = med.strength.replace(".", ",") if lang == "de" else med.strength
        purpose = med.purpose_de if lang == "de" else med.purpose_en
        rows.append(KeyRow(
            name=med.substance_name_de if lang == "de" else med.substance_name, strength=strength,
            purpose=purpose[0].upper() + purpose[1:], pill=pill, candidates=res.candidates, slots=slots,
            times=med.times, instruction=med.instruction_text, with_meal=med.with_meal, show_half=show_half,
            half_svg=pills.pill_svg(pill.color, pill.shape, pill.size_mm, pill.score_line, pill.imprint,
                                    pill.divisible_parts, half=True) if show_half else "",
            look=look_text(pill, lang) if pill else TEXT[lang]["unknown"]))
        if (res.previous_product and res.switch_date and res.product and res.confidence_code == "dispensing"
                and (today - res.switch_date).days <= config.DOUBLE_PACK_DAYS):
            changes.append(KeyChange(name=rows[-1].name, old=res.previous_product, new=res.product,
                                     changed_on=res.switch_date))
    changes.sort(key=lambda c: c.changed_on, reverse=True)
    return KeyData(patient_id=patient_id, patient_name=patient.name, lang=lang, issued_on=today, rows=rows,
                   changes=changes, text=TEXT[lang])


def record_issue(session: Session, patient_id: int, lang: str) -> None:
    session.add(KeyIssue(patient_id=patient_id, issued_at=config.today(), lang=lang))
    session.commit()
    actions.log(session, "patient_key_issued", patient_id, lang)


# ---------------------------------------------------------------------------------------------
# Plain text (for a letter)
# ---------------------------------------------------------------------------------------------
def render_text(key: KeyData) -> str:
    t = key.text
    lines = [f"{t['plan']} – {key.patient_name}", f"{t['date']}: {key.issued_on.strftime('%d.%m.%Y')}", ""]
    for i, row in enumerate(key.rows, start=1):
        lines.append(f"{i}. {row.name} {row.strength} – {row.purpose}")
        lines.append(f"   {t['look']}: {row.look}")
        take = actions.key_line(row.instruction, row.times, key.lang)
        if row.with_meal:
            take += f" ({t['meal']})"
        lines.append(f"   {t['take']}: {take}")
        lines.append("")
    if key.changes:
        lines.append(f"{t['new'].upper()}")
        for ch in key.changes:
            lines.append(f"- {ch.name}: {t['old']}: {look_text(ch.old, key.lang)} -> {t['now']}: "
                         f"{look_text(ch.new, key.lang)}")
        lines.append(t["same"])
        lines.append("")
    lines.append(config.FOOTER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------------------------
def draw_pill(c: canvas.Canvas, cx: float, cy: float, box: float, a: Appearance, half: bool = False) -> None:
    """Draw a pill with the same geometry as the on-screen SVG."""
    k = box / 120.0
    w, h = (v * k for v in pills.geometry(a.shape, a.size_mm))
    fill, stroke = HexColor(pills.COLOR_HEX[a.color]), HexColor(pills.STROKE_HEX[a.color])
    c.saveState()
    if half:
        clip = c.beginPath()
        clip.rect(cx - box / 2, cy - box / 2, box / 2 - 0.5, box)
        c.clipPath(clip, stroke=0, fill=0)
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(max(0.8, 2.2 * k))
    if a.shape == "round":
        c.circle(cx, cy, w, stroke=1, fill=1)
    elif a.shape == "oval":
        c.ellipse(cx - w, cy - h, cx + w, cy + h, stroke=1, fill=1)
    elif a.shape == "shield":
        p = c.beginPath()
        p.moveTo(cx - w, cy + h)
        p.lineTo(cx + w, cy + h)
        p.lineTo(cx + w, cy - h * 0.15)
        p.curveTo(cx + w, cy - h * 0.75, cx + w * 0.4, cy - h, cx, cy - h)
        p.curveTo(cx - w * 0.4, cy - h, cx - w, cy - h * 0.75, cx - w, cy - h * 0.15)
        p.close()
        c.drawPath(p, stroke=1, fill=1)
    else:
        c.roundRect(cx - w, cy - h, 2 * w, 2 * h, h, stroke=1, fill=1)
        if a.shape == "capsule":
            c.setFillColor(stroke)
            c.setFillAlpha(0.35)
            clip = c.beginPath()
            clip.rect(cx, cy - h, w, 2 * h)
            c.saveState()
            c.clipPath(clip, stroke=0, fill=0)
            c.roundRect(cx - w, cy - h, 2 * w, 2 * h, h, stroke=0, fill=1)
            c.restoreState()
            c.setFillAlpha(1)
    vertical = a.shape in ("oval", "oblong")
    has_line = a.score_line != "none" and a.shape != "capsule"
    if has_line:
        c.setLineWidth(max(0.6, (3 if a.score_line == "functional" else 1.6) * k))
        reach = 1.0 if a.score_line == "functional" else 0.62
        if vertical:
            c.line(cx, cy - h * reach * 0.92, cx, cy + h * reach * 0.92)
        else:
            c.line(cx - w * reach * 0.96, cy, cx + w * reach * 0.96, cy)
            if a.divisible_parts == 4:
                c.line(cx, cy - h * 0.96, cx, cy + h * 0.96)
    if a.imprint and not (has_line and a.divisible_parts == 4) and box >= 40 and not half:
        size = max(4.0, min(h * 0.6, w * (0.8 if vertical and has_line else 1.5) / max(len(a.imprint), 2) * 1.5))
        tx_, ty = cx, cy - size * 0.35
        if has_line and vertical:
            tx_ = cx - w * 0.5
        elif has_line:
            size = min(size, h * 0.46)
            ty = cy + h * 0.45 - size * 0.35
        c.setFillColor(stroke)
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(tx_, ty, a.imprint)
    c.restoreState()


def _time_icon(c: canvas.Canvas, cx: float, cy: float, index: int) -> None:
    """0 morning (rising sun), 1 noon (full sun), 2 evening (setting sun), 3 night (moon)."""
    import math
    sun = HexColor("#f2a900") if index != 2 else HexColor("#e2711d")
    c.saveState()
    c.setLineWidth(1.6)
    if index == 3:
        c.setFillColor(HexColor("#3b4a6b"))
        c.circle(cx, cy, 9, stroke=0, fill=1)
        c.setFillColor(white)
        c.circle(cx + 5, cy + 3, 8, stroke=0, fill=1)
    else:
        c.setFillColor(sun)
        c.setStrokeColor(sun)
        base = cy - 5 if index != 1 else cy
        if index == 1:
            c.circle(cx, base, 6, stroke=0, fill=1)
            angles = range(0, 360, 45)
        else:
            p = c.beginPath()
            p.arc(cx - 7, base - 7, cx + 7, base + 7, 0, 180)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
            angles = range(0, 181, 45)
            c.setStrokeColor(HexColor("#5b6b7f"))
            c.line(cx - 14, base, cx + 14, base)
            c.setStrokeColor(sun)
        for ang in angles:
            r = math.radians(ang)
            c.line(cx + math.cos(r) * 9, base + math.sin(r) * 9, cx + math.cos(r) * 13, base + math.sin(r) * 13)
    c.restoreState()


def _fit(text: str, font: str, size: float, width: float) -> str:
    """Never shrink below the body size: shorten with an ellipsis instead."""
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split(" "):
        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    return lines + ([current] if current else [])


def render_pdf(key: KeyData) -> bytes:
    """One A4 page, body text at least 18 pt."""
    t = key.text
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{t['title']} – {key.patient_name}")
    W, H = A4
    left, right = 36, W - 36
    ink, soft, accent = HexColor("#14263d"), HexColor("#5b6b7f"), HexColor("#1d5fa8")
    col_w = 72
    ncols = 4 if any("night" in r.times or (r.slots and len(r.slots) == 4) for r in key.rows) else 3
    cols_x = [right - col_w * (ncols - i) + col_w / 2 for i in range(ncols)]
    pill_w = 78

    y = H - 40
    c.setFillColor(ink)
    c.setFont("Helvetica-Bold", 25)
    c.drawString(left, y - 20, t["title"])
    y -= 36
    c.setFont("Helvetica", BODY)
    c.setFillColor(soft)
    c.drawString(left, y - 36, _fit(f"{key.patient_name} · {key.issued_on.strftime('%d.%m.%Y')}", "Helvetica", BODY,
                                    cols_x[0] - col_w / 2 - left - 6))
    for i, cx in enumerate(cols_x):
        _time_icon(c, cx, y - 8, i)
        c.setFillColor(ink)
        c.setFont("Helvetica", BODY)
        c.drawCentredString(cx, y - 36, _fit(t["times"][i], "Helvetica", BODY, col_w))
    y -= 46

    changes = key.changes[:3]
    same_lines = _wrap(t["same"], "Helvetica-Bold", BODY, right - left - 24)
    new_h = (30 + 54 * len(changes) + 22 * len(same_lines) + 10) if changes else 0
    footer_h = 34
    n = max(len(key.rows), 1)
    row_h = max(48.0, min(66.0, (y - 36 - footer_h - new_h - (12 if changes else 0)) / n))

    for row in key.rows:
        top = y
        c.setStrokeColor(HexColor("#c9d6e6"))
        c.setLineWidth(0.8)
        c.line(left, top, right, top)
        mid = top - row_h / 2
        box = min(84.0, row_h * 1.3)
        if row.pill:
            draw_pill(c, left + pill_w / 2, mid, box, row.pill)
        elif row.candidates:
            for j, cand in enumerate(row.candidates[:2]):
                draw_pill(c, left + 20 + j * 38, mid, box * 0.6, cand)
        else:
            c.setFillColor(soft)
            c.setFont("Helvetica-Bold", 26)
            c.drawCentredString(left + pill_w / 2, mid - 9, "?")
        text_x = left + pill_w + 10
        line1, line2 = mid + 4, mid - 18
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", BODY)
        c.drawString(text_x, line1, _fit(row.purpose, "Helvetica-Bold", BODY, cols_x[0] - col_w / 2 - text_x - 4))
        c.setFillColor(ink)
        name = f"{row.name} {row.strength}"
        if row.slots:
            for i, slot in enumerate(row.slots[:ncols]):
                if slot == "0":
                    c.setFillColor(HexColor("#b6c2d1"))
                    c.setFont("Helvetica", BODY)
                    c.drawCentredString(cols_x[i], line1, "–")
                    continue
                c.setFillColor(ink)
                c.setFont("Helvetica-Bold", 22)
                is_half = slot in ("½", "¼") and row.show_half and row.pill
                c.drawCentredString(cols_x[i] - (12 if is_half else 0), line1 - 1, slot)
                if is_half:
                    draw_pill(c, cols_x[i] + 22, line1 + 7, 50, row.pill, half=True)
            extra = f" · {t['meal']}" if row.with_meal else ""
            c.setFont("Helvetica", BODY)
            c.setFillColor(ink)
            c.drawString(text_x, line2, _fit(name + extra, "Helvetica", BODY, right - text_x))
        else:
            c.setFont("Helvetica", BODY)
            c.drawString(text_x, line2, _fit(f"{name}: {row.instruction}", "Helvetica", BODY, right - text_x))
        y -= row_h
    c.setStrokeColor(HexColor("#c9d6e6"))
    c.line(left, y, right, y)

    if changes:
        y -= 12
        c.setFillColor(HexColor("#fff4d6"))
        c.setStrokeColor(HexColor("#d99a00"))
        c.setLineWidth(1.5)
        c.roundRect(left, y - new_h, right - left, new_h, 10, stroke=1, fill=1)
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(left + 12, y - 24, t["new"])
        cy = y - 30
        for ch in changes:
            cy -= 54
            mid = cy + 27
            draw_pill(c, left + 46, mid, 70, ch.old)
            c.setLineWidth(2.5)
            c.setStrokeColor(ink)
            c.line(left + 88, mid, left + 108, mid)
            c.line(left + 108, mid, left + 101, mid + 6)
            c.line(left + 108, mid, left + 101, mid - 6)
            draw_pill(c, left + 150, mid, 70, ch.new)
            c.setFillColor(ink)
            c.setFont("Helvetica", BODY)
            c.drawString(left + 196, mid - 6, _fit(ch.name, "Helvetica", BODY, right - left - 208))
        c.setFont("Helvetica-Bold", BODY)
        for line in same_lines:
            cy -= 22
            c.drawString(left + 12, cy + 4, line)

    c.setFillColor(soft)
    c.setFont("Helvetica", BODY)
    c.drawCentredString(W / 2, 30, _fit(config.FOOTER, "Helvetica", BODY, right - left))
    c.showPage()
    c.save()
    return buf.getvalue()
