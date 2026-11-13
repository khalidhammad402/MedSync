"""Simulator actions: change the mock world the way real life does, on the demo patient."""
from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from app import config
from app.l1_data import adapters, seed
from app.l1_data.models import (Contract, DispensingEvent, Patient, Prescription, Product, Shortage,
                                Substance)
from app.l4_insight import actions

ACTIONS = {
    "shortage_substitution": ("Pharmacy substitutes due to shortage",
                              "Metoprolol is short. The pharmacy hands Herr Müller a different product."),
    "contract_rotates": ("Insurer contract rotates",
                         "Kasse Nord's ramipril contract switches to its successor today."),
    "contract_expires": ("Contract expires",
                         "Kasse Nord's pantoprazole contract ends with no successor."),
    "reset": ("Reset demo", "Restore the original demo data."),
}


def _demo_rx(session: Session, inn_prefix: str) -> tuple[Patient, Prescription, Substance]:
    patient = adapters.list_patients(session)[0]
    sub = session.exec(select(Substance).where(Substance.inn_name.startswith(inn_prefix))).one()
    rx = session.exec(select(Prescription).where(Prescription.patient_id == patient.id,
                                                 Prescription.substance_id == sub.id)).one()
    return patient, rx, sub


def _current_contract(session: Session, patient: Patient, rx: Prescription, today):
    return session.exec(select(Contract).where(Contract.insurer_id == patient.insurer_id,
                                               Contract.substance_id == rx.substance_id,
                                               Contract.strength == rx.strength, Contract.valid_from <= today,
                                               Contract.valid_to >= today)).first()


def run(session: Session, action: str) -> str:
    """Apply one action and return a short message for the toast."""
    if action not in ACTIONS:
        raise LookupError(f"Unknown simulator action: {action}")
    today = config.today()

    if action == "reset":
        session.close()
        seed.reset()
        return "Demo data restored."

    if action == "shortage_substitution":
        patient, rx, sub = _demo_rx(session, "Metoprolol")
        substitute = session.exec(select(Product).where(Product.substance_id == sub.id,
                                                        Product.divisible_parts == 1)).first()
        last = session.exec(select(DispensingEvent).where(DispensingEvent.prescription_id == rx.id)
                            .order_by(DispensingEvent.dispensed_at.desc(), DispensingEvent.id.desc())).first()
        if last and last.product_id == substitute.id:
            return "The substitution is already recorded."
        if not adapters.mock_sources(session).shortages.active(sub.id, rx.strength, today):
            session.add(Shortage(substance_id=sub.id, strength=rx.strength, active_from=today,
                                 active_to=today + timedelta(days=30)))
        session.add(DispensingEvent(patient_id=patient.id, prescription_id=rx.id, product_id=substitute.id,
                                    dispensed_at=today, reason="shortage_substitution"))
        rx.override_product_id = None      # a newer pack supersedes an earlier confirmation
        session.add(rx)
        session.commit()
        actions.log(session, "simulator", patient.id, action, f"dispensed {substitute.name}")
        return f"Pharmacy handed over {substitute.name} instead of the contract product."

    if action == "contract_rotates":
        patient, rx, _ = _demo_rx(session, "Ramipril")
        current = _current_contract(session, patient, rx, today)
        successor = session.exec(select(Contract).where(Contract.insurer_id == patient.insurer_id,
                                                        Contract.substance_id == rx.substance_id,
                                                        Contract.valid_from > today)
                                 .order_by(Contract.valid_from)).first()
        if not successor:
            return "The ramipril contract has already rotated."
        if current:
            current.valid_to = today - timedelta(days=1)
            session.add(current)
        successor.valid_from = today
        session.add(successor)
        session.commit()
        actions.log(session, "simulator", patient.id, action)
        return "Ramipril contract rotated: the predicted tablet looks different now."

    patient, rx, _ = _demo_rx(session, "Pantoprazole")
    current = _current_contract(session, patient, rx, today)
    if not current:
        return "The pantoprazole contract has already expired."
    current.valid_to = today - timedelta(days=1)
    session.add(current)
    session.commit()
    actions.log(session, "simulator", patient.id, action)
    return "Pantoprazole contract expired: the product is now unresolved."
