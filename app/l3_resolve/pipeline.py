"""Layer 3: walk the chain insurer -> drug -> contract -> product -> appearance.

The result is a best estimate with an honest trail. Dispensing records beat prediction.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel
from sqlmodel import Session

from app import config
from app.l1_data import adapters
from app.l1_data.adapters import Appearance, ContractRecord, Sources
from app.l1_data.models import Patient, Prescription
from app.l2_classify import taxonomy as tx

CONFIDENCE = {
    "dispensing": "Confirmed by dispensing record",
    "prescription": "Confirmed by prescription",
    "contract": "Predicted from insurer contract",
    "contract_multi": "Predicted – one of {n} possible",
    "manual": "Selected manually by clinician",
    "unresolved": "Unresolved",
}


class StageResult(BaseModel):
    stage: int
    name: str
    status: str          # ok | warning | failed
    detail: str
    evidence: dict[str, Any] = {}


class Resolution(BaseModel):
    prescription_id: int
    patient_id: int
    substance_id: int
    substance_name: str
    strength: str
    insurer_name: Optional[str] = None
    product: Optional[Appearance] = None
    candidates: list[Appearance] = []
    confidence: str
    confidence_code: str
    stages: list[StageResult]
    warnings: list[str] = []
    contract_valid_from: Optional[date] = None
    contract_valid_to: Optional[date] = None
    days_until_rotation: Optional[int] = None
    rotation_date: Optional[date] = None
    next_products: list[Appearance] = []
    previous_product: Optional[Appearance] = None
    switch_date: Optional[date] = None
    switch_reason: Optional[str] = None
    last_dispensed_at: Optional[date] = None
    shortage_active: bool = False
    shortage_since: Optional[date] = None
    manual_override_allowed: bool = False
    manual_options: list[Appearance] = []

    @property
    def appearances(self) -> list[Appearance]:
        """The product in hand, or every candidate if it is not certain."""
        return [self.product] if self.product else list(self.candidates)


class PatientMedication(BaseModel):
    """One prescription with everything the upper layers need to show or reason about it."""
    prescription_id: int
    patient_id: int
    substance_id: int
    substance_name: str
    substance_name_de: str
    aliases: list[str]
    class_label: str
    strength: str
    instruction_text: str
    times: list[str]
    with_meal: bool
    aut_idem_excluded: bool
    purpose_key: str
    purpose_en: str
    purpose_de: str
    risk_tier: str
    narrow_therapeutic_index: bool
    otc_caution: bool
    resolution: Resolution

    @property
    def label(self) -> str:
        return f"{self.substance_name} {self.strength}"


def fmt_date(d: Optional[date], year: bool = False) -> str:
    if d is None:
        return "–"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{d.day} {months[d.month - 1]}" + (f" {d.year}" if year else "")


def _current(contracts: list[ContractRecord], today: date) -> Optional[ContractRecord]:
    valid = [c for c in contracts if c.valid_from <= today <= c.valid_to]
    return valid[-1] if valid else None


def _successor(contracts: list[ContractRecord], today: date) -> Optional[ContractRecord]:
    future = sorted([c for c in contracts if c.valid_from > today], key=lambda c: c.valid_from)
    return future[0] if future else None


def resolve(prescription: Prescription, patient: Patient, today: Optional[date] = None,
            sources: Optional[Sources] = None) -> Resolution:
    """Resolve which product the patient most likely holds for one prescription."""
    today = today or config.today()
    if sources is None:
        from app import db
        with Session(db.get_engine()) as session:
            return resolve(prescription, patient, today, adapters.mock_sources(session))

    warnings: list[str] = []
    stages: list[StageResult] = []

    # Stage 1 – insurer ------------------------------------------------------------------------
    insurer = sources.directory.insurer(patient.insurer_id)
    if insurer:
        stages.append(StageResult(stage=1, name="insurer", status="ok",
                                  detail=f"{patient.name} is insured with {insurer.short_name}.",
                                  evidence={"insurer_id": insurer.id, "insurer": insurer.short_name}))
    else:
        stages.append(StageResult(stage=1, name="insurer", status="failed",
                                  detail=f"No insurer is on record for {patient.name}."))
        warnings.append("Insurer unknown – contract prediction is not possible.")

    # Stage 2 – drug ---------------------------------------------------------------------------
    substance = sources.directory.substance(prescription.substance_id)
    sub_name = substance.inn_name if substance else "Unknown medicine"
    options = sources.appearance.products_for(prescription.substance_id, prescription.strength)
    if substance and options:
        stages.append(StageResult(stage=2, name="drug", status="ok",
                                  detail=f"The prescription is {sub_name} {prescription.strength}.",
                                  evidence={"substance": sub_name, "atc": substance.atc_code,
                                            "strength": prescription.strength,
                                            "aliases": [a for a in substance.aliases.split(",") if a]}))
    else:
        stages.append(StageResult(stage=2, name="drug", status="failed",
                                  detail=f"No product is known for {sub_name} {prescription.strength}.",
                                  evidence={"substance": sub_name, "strength": prescription.strength}))
        warnings.append(f"Strength {prescription.strength} does not match any known product – check the prescription.")

    # Stage 3 – contract -----------------------------------------------------------------------
    contracts = (sources.contracts.contracts_for(insurer.id, prescription.substance_id, prescription.strength)
                 if insurer else [])
    contract = _current(contracts, today)
    successor = _successor(contracts, today)
    days_left = (contract.valid_to - today).days if contract else None
    if contract:
        soon = days_left is not None and days_left <= config.ROTATION_WARN_DAYS
        stages.append(StageResult(
            stage=3, name="contract", status="warning" if soon else "ok",
            detail=(f"{insurer.short_name}'s contract is valid until {fmt_date(contract.valid_to, True)}"
                    f" ({days_left} days left) and covers {len(contract.product_ids)} product"
                    f"{'s' if len(contract.product_ids) != 1 else ''}."),
            evidence={"contract_id": contract.contract_id, "valid_from": contract.valid_from.isoformat(),
                      "valid_to": contract.valid_to.isoformat(), "days_until_rotation": days_left,
                      "product_ids": contract.product_ids}))
    else:
        past = [c for c in contracts if c.valid_to < today]
        if not insurer:
            detail = "Skipped – no insurer, so no contract can be looked up."
        elif past:
            detail = f"The last contract expired on {fmt_date(past[-1].valid_to, True)}. No valid contract today."
            warnings.append("Contract expired – the pharmacy may hand over any product.")
        else:
            detail = "No rebate contract is on record for this medicine."
        stages.append(StageResult(stage=3, name="contract", status="failed", detail=detail,
                                  evidence={"expired": [c.valid_to.isoformat() for c in past]}))

    # Stage 4 – product ------------------------------------------------------------------------
    events = sources.dispensing.events_for(prescription.id)
    latest = events[-1] if events else None
    recent = latest if latest and (today - latest.dispensed_at).days <= config.DISPENSING_WINDOW_DAYS else None
    product: Optional[Appearance] = None
    candidates: list[Appearance] = []
    code = "unresolved"
    status4, detail4, evidence4 = "failed", "", {}

    if prescription.override_product_id:
        product = sources.appearance.appearance(prescription.override_product_id)
    if product:
        code, status4 = "manual", "ok"
        detail4 = f"The clinician selected {product.name} by hand after checking with the patient or pharmacy."
        evidence4 = {"rule": "manual override", "pzn": product.pzn}
    elif recent and (product := sources.appearance.appearance(recent.product_id)):
        code, status4 = "dispensing", "ok"
        detail4 = (f"The pharmacy record from {fmt_date(recent.dispensed_at)} shows {product.name} was handed over. "
                   f"A dispensing record overrides prediction.")
        evidence4 = {"rule": "a) dispensing record within 120 days", "pzn": product.pzn,
                     "dispensed_at": recent.dispensed_at.isoformat(), "reason": recent.reason}
        if contract and product.product_id not in contract.product_ids:
            detail4 += " It differs from the current contract product."
            evidence4["conflict_with_contract"] = True
        if product.strength != prescription.strength:
            status4 = "warning"
            warnings.append(f"Dispensed pack is {product.strength}, the prescription says {prescription.strength}.")
    elif prescription.aut_idem_excluded and (product := sources.appearance.appearance(prescription.prescribed_product_id)):
        code, status4 = "prescription", "ok"
        detail4 = f"Substitution is excluded on the prescription (aut idem), so it is {product.name}."
        evidence4 = {"rule": "b) aut-idem exclusion", "pzn": product.pzn}
    elif contract and contract.product_ids:
        found = [a for a in (sources.appearance.appearance(pid) for pid in contract.product_ids) if a]
        if len(found) == 1:
            product, code, status4 = found[0], "contract", "ok"
            detail4 = f"No recent pharmacy record, so we show the contract product: {product.name}."
            evidence4 = {"rule": "c) single contract product", "pzn": product.pzn}
        elif found:
            candidates, code, status4 = found, "contract_multi", "warning"
            detail4 = (f"The contract has {len(found)} partners. The pharmacy picks one depending on stock: "
                       + " or ".join(a.name for a in found) + ".")
            evidence4 = {"rule": "c) several contract products", "pzns": [a.pzn for a in found]}
    if code == "unresolved":
        detail4 = "The product cannot be worked out. Ask the patient to read the box, or ask the pharmacy."
        evidence4 = {"rule": "d) unresolved"}
    stages.append(StageResult(stage=4, name="product", status=status4, detail=detail4, evidence=evidence4))

    # Stage 5 – appearance ---------------------------------------------------------------------
    if product:
        stages.append(StageResult(stage=5, name="appearance", status="ok", detail=describe(product),
                                  evidence={"color": product.color, "shape": product.shape,
                                            "size_mm": product.size_mm, "score_line": product.score_line,
                                            "imprint": product.imprint, "divisible_parts": product.divisible_parts}))
    elif candidates:
        stages.append(StageResult(stage=5, name="appearance", status="warning",
                                  detail="It could look like any of these: " + " / ".join(
                                      describe(c, short=True) for c in candidates) + ".",
                                  evidence={"candidates": [c.pzn for c in candidates]}))
    else:
        stages.append(StageResult(stage=5, name="appearance", status="failed",
                                  detail="Appearance unknown until the product is confirmed."))

    # After the stages: rotation outlook, switch history, shortage check --------------------------
    next_products: list[Appearance] = []
    rotation_date = None
    if successor and not prescription.aut_idem_excluded:
        held = {a.product_id for a in ([product] if product else candidates)}
        nxt = [a for a in (sources.appearance.appearance(pid) for pid in successor.product_ids) if a]
        if nxt and {a.product_id for a in nxt} != held:
            next_products, rotation_date = nxt, successor.valid_from

    previous, switch_date, switch_reason = None, None, None
    if latest and len(events) >= 2 and events[-2].product_id != latest.product_id:
        previous = sources.appearance.appearance(events[-2].product_id)
        switch_date, switch_reason = latest.dispensed_at, latest.reason

    shortages = sources.shortages.active(prescription.substance_id, prescription.strength, today)
    if shortages:
        warnings.append(f"Supply shortage reported for {sub_name} {prescription.strength} – "
                        f"the pharmacy may substitute another product.")

    confidence = CONFIDENCE[code].format(n=len(candidates))
    return Resolution(
        prescription_id=prescription.id, patient_id=patient.id, substance_id=prescription.substance_id,
        substance_name=sub_name, strength=prescription.strength,
        insurer_name=insurer.short_name if insurer else None, product=product, candidates=candidates,
        confidence=confidence, confidence_code=code, stages=stages, warnings=warnings,
        contract_valid_from=contract.valid_from if contract else None,
        contract_valid_to=contract.valid_to if contract else None,
        days_until_rotation=days_left, rotation_date=rotation_date, next_products=next_products,
        previous_product=previous, switch_date=switch_date, switch_reason=switch_reason,
        last_dispensed_at=latest.dispensed_at if latest else None,
        shortage_active=bool(shortages), shortage_since=shortages[0].active_from if shortages else None,
        manual_override_allowed=bool(shortages) or code in ("unresolved", "contract_multi", "manual"),
        manual_options=options)


def describe(a: Appearance, short: bool = False) -> str:
    """Plain words for what a tablet looks like."""
    noun = "capsule" if a.shape == "capsule" else "tablet"
    shape = "" if a.shape == "capsule" else f" {a.shape}"
    text = f"{tx.size_band(a.size_mm)} {a.color}{shape} {noun}"
    if short:
        return text
    text = f"A {text}"
    if a.score_line != "none":
        text += " with a line across it"
    if a.imprint:
        text += f", marked {a.imprint}"
    return f"{text}. {tx.split_label(a.divisible_parts)}."


def resolve_patient(session: Session, patient_id: int, today: Optional[date] = None) -> list[PatientMedication]:
    """Resolve every prescription of a patient."""
    patient = adapters.get_patient(session, patient_id)
    if patient is None:
        raise LookupError(f"Unknown patient {patient_id}")
    today = today or config.today()
    sources = adapters.mock_sources(session)
    out = []
    for rx in adapters.prescriptions_for(session, patient_id):
        sub = adapters.get_substance(session, rx.substance_id)
        out.append(PatientMedication(
            prescription_id=rx.id, patient_id=patient_id, substance_id=sub.id, substance_name=sub.inn_name,
            substance_name_de=sub.inn_name_de, aliases=[a for a in sub.aliases.split(",") if a],
            class_label=sub.class_label, strength=rx.strength, instruction_text=rx.instruction_text,
            times=[t for t in rx.times_of_day.split(",") if t], with_meal=rx.with_meal,
            aut_idem_excluded=rx.aut_idem_excluded, purpose_key=sub.purpose_key, purpose_en=sub.plain_purpose_en,
            purpose_de=sub.plain_purpose_de, risk_tier=sub.risk_tier,
            narrow_therapeutic_index=sub.narrow_therapeutic_index, otc_caution=sub.otc_caution,
            resolution=resolve(rx, patient, today, sources)))
    return out


def find_substances(session: Session, query: str) -> list:
    """Find substances by active ingredient, German name or (fictional) brand alias."""
    q = query.strip().lower()
    hits = []
    for sub in adapters.list_substances(session):
        names = [sub.inn_name, sub.inn_name_de] + [a for a in sub.aliases.split(",") if a]
        if not q or any(q in n.lower() for n in names):
            hits.append(sub)
    return hits
