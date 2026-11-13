"""View models: arrange what Layers 3–6 return for the templates. No rules are decided here."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlmodel import Session

from app import config
from app.l1_data import adapters
from app.l2_classify import taxonomy as tx
from app.l3_resolve import explain, pipeline
from app.l4_insight import actions, clusters
from app.l4_insight.recommend import split_badge
from app.l5_conversation import session as calls
from app.l7_api.common import Live
from app.l7_api.schemas import ContractPeriod, ExplorerOut, PatientOut, TrailOut


def age_of(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def patient_out(session: Session, patient, today: date) -> PatientOut:
    insurer = adapters.get_insurer(session, patient.insurer_id)
    return PatientOut(id=patient.id, name=patient.name, age=age_of(patient.birth_date, today),
                      insurer=insurer.short_name if insurer else None,
                      prescriptions=len(adapters.prescriptions_for(session, patient.id)))


def consult(session: Session, patient_id: int, call_id: Optional[int] = None) -> dict:
    """Everything the Consult screen shows for one patient."""
    today = config.today()
    patient = adapters.get_patient(session, patient_id)
    if patient is None:
        raise LookupError(f"There is no patient with number {patient_id}.")
    meds = pipeline.resolve_patient(session, patient_id, today)
    state = None
    if call_id:
        try:
            state = calls.get(session, call_id, meds)
            if state.patient_id != patient_id:
                state = None
        except LookupError:
            state = None
    groups = clusters.find_clusters(meds)
    cluster_of = {pid: c for c in groups for pid in c.prescription_ids}
    by_id = {c.prescription_id: c for c in state.narrowing.candidates} if state else {}
    filtering = bool(state and state.anchors)
    narrowed = bool(state and state.narrowing.remaining <= 3)
    cards = []
    for med in meds:
        res = med.resolution
        cand = by_id.get(med.prescription_id)
        kind, label = split_badge(med)
        switched = bool(res.previous_product and res.switch_date and res.confidence_code == "dispensing"
                        and (today - res.switch_date).days <= config.DOUBLE_PACK_DAYS)
        cards.append({
            "med": med, "res": res,
            "state": (("glow" if narrowed else "") if cand.matched else "dim") if filtering and cand else "",
            "reasons": cand.reasons if cand and filtering else [],
            "cluster": cluster_of.get(med.prescription_id),
            "split_kind": kind, "split_label": label, "switched": switched,
            "risk_label": tx.RISK_LABELS[med.risk_tier],
            "chain": [(s.name, s.status) for s in res.stages],
        })
    confirm_target = confirmed_target = None
    if filtering and state.narrowing.remaining == 1:
        only = next(m for m in meds if m.prescription_id == state.narrowing.matched_ids[0])
        if only.resolution.confidence_code == "manual":
            confirmed_target = only
        elif only.resolution.product is not None:
            confirm_target = only
    return {
        "confirm_target": confirm_target, "confirmed_target": confirmed_target,
        "patient": patient_out(session, patient, today), "patients": [patient_out(session, p, today)
                                                                     for p in adapters.list_patients(session)],
        "cards": cards, "meds": meds, "recs": actions.recommendations_for(session, patient_id, today, meds),
        "call": state, "today": today, "version": Live.version,
        "key_issued": actions.key_last_issued(session, patient_id),
    }


def trail(session: Session, prescription_id: int) -> tuple[TrailOut, pipeline.PatientMedication]:
    from app.l1_data.models import Prescription
    rx = session.get(Prescription, prescription_id)
    if rx is None:
        raise LookupError("That prescription does not exist.")
    med = next(m for m in pipeline.resolve_patient(session, rx.patient_id, config.today())
               if m.prescription_id == prescription_id)
    res = med.resolution
    return TrailOut(prescription_id=prescription_id, headline=explain.headline(res),
                    lines=explain.explain_lines(res), read_aloud=explain.explain(res), resolution=res), med


# Display names for the Explorer tab only. The contracts behind them are invented demo data.
EXPLORER_INSURERS = {"Kasse Nord": "Techniker Krankenkasse (TK)", "Kasse Süd": "BARMER", "Kasse West": "DAK-Gesundheit",
                     "Kasse Ost": "Debeka", "Kasse Mitte": "DKV", "Kasse Küste": "Allianz"}


def explorer(session: Session, insurer_id: Optional[int], substance_id: Optional[int]) -> ExplorerOut:
    """The chain for one insurer and one drug: contracts on a timeline, and who holds what today."""
    today = config.today()
    insurers = adapters.list_insurers(session)
    substances = adapters.list_substances(session)
    insurer = next((i for i in insurers if i.id == insurer_id), insurers[0])
    substance = next((s for s in substances if s.id == substance_id), substances[0])
    sources = adapters.mock_sources(session)
    options = sources.appearance.products_for(substance.id, "")
    strengths = {p.strength for p in _products(session, substance.id)}
    strength = sorted(strengths)[0] if strengths else ""
    contracts = sources.contracts.contracts_for(insurer.id, substance.id, strength)
    periods, rotation, today_pct = [], None, 50.0
    if contracts:
        start = min(c.valid_from for c in contracts)
        end = max(c.valid_to for c in contracts)
        span = max((end - start).days, 1)
        today_pct = min(max((today - start).days / span * 100, 0), 100)
        for c in contracts:
            status = "active" if c.valid_from <= today <= c.valid_to else "past" if c.valid_to < today else "next"
            if status == "next" and rotation is None:
                rotation = c.valid_from
            periods.append(ContractPeriod(
                contract_id=c.contract_id, valid_from=c.valid_from, valid_to=c.valid_to, status=status,
                left_pct=round((c.valid_from - start).days / span * 100, 2),
                width_pct=round(max((c.valid_to - c.valid_from).days, 1) / span * 100, 2),
                products=[a.model_dump() for a in (sources.appearance.appearance(pid) for pid in c.product_ids) if a]))
    holders = []
    for patient in adapters.list_patients(session):
        if patient.insurer_id != insurer.id:
            continue
        for med in pipeline.resolve_patient(session, patient.id, today):
            if med.substance_id == substance.id:
                holders.append({"patient": patient.name, "patient_id": patient.id,
                                "confidence": med.resolution.confidence,
                                "headline": explain.headline(med.resolution),
                                "products": [a.model_dump() for a in med.resolution.appearances]})
    del options
    return ExplorerOut(insurer_id=insurer.id, insurer=EXPLORER_INSURERS.get(insurer.short_name, insurer.short_name), substance_id=substance.id,
                       substance=substance.inn_name, strength=strength, risk_tier=substance.risk_tier,
                       aliases=[a for a in substance.aliases.split(",") if a], today_pct=round(today_pct, 2),
                       rotation_date=rotation, periods=periods, holders=holders)


def _products(session: Session, substance_id: int):
    from sqlmodel import select
    from app.l1_data.models import Product
    return session.exec(select(Product).where(Product.substance_id == substance_id)).all()


def host(session: Session, patient_id: int) -> dict:
    """The mock practice-software screen: a text-only table built from the same prescriptions."""
    today = config.today()
    patient = adapters.get_patient(session, patient_id)
    if patient is None:
        raise LookupError(f"There is no patient with number {patient_id}.")
    rows = []
    for rx in adapters.prescriptions_for(session, patient_id):
        sub = adapters.get_substance(session, rx.substance_id)
        rows.append({"wirkstoff": sub.inn_name_de, "staerke": rx.strength.replace(".", ","),
                     "dosierung": rx.instruction_text,
                     "verordnet": rx.prescribed_on.strftime("%d.%m.%Y") if rx.prescribed_on else "–",
                     "status": "aktiv"})
    return {"patient": patient_out(session, patient, today), "rows": rows, "today": today,
            "patients": [patient_out(session, p, today) for p in adapters.list_patients(session)]}


def story(session: Session) -> dict:
    """Real seed values for the How We Work page: one prescription, two insurers, two different tablets."""
    today = config.today()
    sources = adapters.mock_sources(session)
    substance = adapters.list_substances(session)[0]                 # metoprolol succinate
    strength = sorted({p.strength for p in _products(session, substance.id)})[0]
    pair = []
    for insurer in adapters.list_insurers(session)[:2]:
        for c in sources.contracts.contracts_for(insurer.id, substance.id, strength):
            if c.valid_from <= today <= c.valid_to:
                pair.append({"insurer": insurer.short_name, "product": sources.appearance.appearance(c.product_ids[0])})
    return {"substance": substance, "strength": strength, "pair": pair,
            "pzn": pair[0]["product"].pzn if pair else "", "insurer_id": adapters.list_insurers(session)[0].id}
