"""Clinician actions and the audit trail. MedSync records decisions; it never makes them."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session, select

from app import config
from app.l1_data.models import AuditLog, KeyIssue, Prescription, Product
from app.l2_classify import taxonomy as tx
from app.l3_resolve import pipeline
from app.l4_insight.recommend import Recommendation, SplitCheck, recommend, split_check


class InstructionResult(BaseModel):
    prescription_id: int
    instruction_text: str
    times: list[str]
    key_line_en: str
    key_line_de: str
    split: SplitCheck
    saved: bool


def log(session: Session, action: str, patient_id: Optional[int] = None, ref: str = "", detail: str = "") -> None:
    session.add(AuditLog(at=datetime.now(timezone.utc), patient_id=patient_id, action=action, ref=ref, detail=detail))
    session.commit()


def audit_entries(session: Session, patient_id: Optional[int] = None) -> list[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.id.desc())
    if patient_id is not None:
        q = q.where(AuditLog.patient_id == patient_id)
    return list(session.exec(q).all())


def dismissed_ids(session: Session, patient_id: int) -> set[str]:
    rows = session.exec(select(AuditLog.ref).where(AuditLog.patient_id == patient_id,
                                                   AuditLog.action == "recommendation_dismissed")).all()
    return set(rows)


def key_last_issued(session: Session, patient_id: int) -> Optional[date]:
    row = session.exec(select(KeyIssue).where(KeyIssue.patient_id == patient_id)
                       .order_by(KeyIssue.issued_at.desc(), KeyIssue.id.desc())).first()
    return row.issued_at if row else None


def recommendations_for(session: Session, patient_id: int, today: Optional[date] = None,
                        meds: Optional[list[pipeline.PatientMedication]] = None) -> list[Recommendation]:
    today = today or config.today()
    meds = meds if meds is not None else pipeline.resolve_patient(session, patient_id, today)
    return recommend(meds, today, key_last_issued(session, patient_id), dismissed_ids(session, patient_id))


def respond(session: Session, patient_id: int, rec_id: str, accepted: bool) -> None:
    """Record that a prompt was acted on or dismissed. Dismissed prompts stay hidden."""
    log(session, "recommendation_accepted" if accepted else "recommendation_dismissed", patient_id, rec_id)


def override_product(session: Session, prescription_id: int, product_id: Optional[int]) -> Prescription:
    """Clinician picks the product by hand. Only products of the same substance and strength are allowed."""
    rx = session.get(Prescription, prescription_id)
    if rx is None:
        raise LookupError("Unknown prescription.")
    if product_id is None:
        rx.override_product_id = None
        detail = "override cleared"
    else:
        product = session.get(Product, product_id)
        if product is None or product.substance_id != rx.substance_id or product.strength != rx.strength:
            raise ValueError("That product is not the same medicine and strength as the prescription.")
        rx.override_product_id = product.id
        detail = f"PZN {product.pzn} {product.name}"
    session.add(rx)
    session.commit()
    log(session, "product_override", rx.patient_id, str(rx.id), detail)
    return rx


_SLOT = r"(\d+(?:[.,]\d+)?\s*[½¼¾]?|[½¼¾]|\d/\d)"
_SLOTS = re.compile(rf"^\s*{_SLOT}\s*-\s*{_SLOT}\s*-\s*{_SLOT}(?:\s*-\s*{_SLOT})?\s*$")


def dose_slots(instruction: str) -> Optional[list[str]]:
    """Split "1-0-½" into [morning, noon, evening, (night)]. None for free text."""
    m = _SLOTS.match(instruction or "")
    if not m:
        return None
    return [g.replace(" ", "").replace("1/2", "½").replace("1/4", "¼") for g in m.groups() if g is not None]


def times_from_instruction(instruction: str, fallback: list[str]) -> list[str]:
    slots = dose_slots(instruction)
    if not slots:
        return fallback
    return [t for t, s in zip(tx.TIMES_OF_DAY, slots) if s not in ("0", "0,0", "0.0")]


def key_line(instruction: str, times: list[str], lang: str) -> str:
    """How the instruction will read on the patient key."""
    idx = 0 if lang == "en" else 1
    slots = dose_slots(instruction)
    if slots:
        parts = [f"{tx.SCHEDULE_LABELS[t][idx]}: {s}" for t, s in zip(tx.TIMES_OF_DAY, slots) if s != "0"]
        return ", ".join(parts) if parts else instruction
    when = ", ".join(tx.SCHEDULE_LABELS[t][idx] for t in times)
    return f"{instruction} ({when})" if when else instruction


def record_instruction(session: Session, prescription_id: int, text: str, confirm: bool) -> InstructionResult:
    """Record an instruction the clinician has already decided on, and run the split check.

    With confirm=False nothing is saved: it only previews the key line and the check.
    """
    rx = session.get(Prescription, prescription_id)
    if rx is None:
        raise LookupError("Unknown prescription.")
    text = (text or "").strip()
    if not text:
        raise ValueError("Please type the instruction you decided on.")
    from app.l1_data import adapters
    patient = adapters.get_patient(session, rx.patient_id)
    res = pipeline.resolve(rx, patient, config.today(), adapters.mock_sources(session))
    times = times_from_instruction(text, [t for t in rx.times_of_day.split(",") if t])
    check = split_check(text, res.appearances)
    if confirm:
        old = rx.instruction_text
        rx.instruction_text = text
        rx.times_of_day = ",".join(times)
        session.add(rx)
        session.commit()
        log(session, "instruction_recorded", rx.patient_id, str(rx.id),
            f"“{old}” -> “{text}”; split check: {'ok' if check.ok else 'NOT possible'}")
    return InstructionResult(prescription_id=rx.id, instruction_text=text, times=times,
                             key_line_en=key_line(text, times, "en"), key_line_de=key_line(text, times, "de"),
                             split=check, saved=confirm)
