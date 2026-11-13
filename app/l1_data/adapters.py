"""Interfaces a real deployment would implement, plus mock versions that read the demo database.

Nothing here is connected to a real system and no licensed vendor is integrated.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Protocol

from pydantic import BaseModel
from sqlmodel import Session, select

from app.l1_data.models import (Contract, ContractProduct, DispensingEvent, Insurer, Patient,
                                Prescription, Product, Shortage, Substance)


class Appearance(BaseModel):
    product_id: int
    pzn: str
    name: str
    substance_id: int
    strength: str
    form: str
    manufacturer: str
    color: str
    shape: str
    size_mm: float
    score_line: str
    divisible_parts: int
    coating: str
    imprint: str
    image_svg: str


class DispensingRecord(BaseModel):
    prescription_id: int
    product_id: int
    dispensed_at: date
    reason: str


class ContractRecord(BaseModel):
    contract_id: int
    insurer_id: int
    substance_id: int
    strength: str
    valid_from: date
    valid_to: date
    product_ids: list[int]


class ShortageRecord(BaseModel):
    substance_id: int
    strength: str
    active_from: date
    active_to: date


class DispensingFeed(Protocol):
    """What the pharmacy actually handed over.

    Real system category: dispensing data from the electronic medication list (eML) in the ePA.
    """
    def events_for(self, prescription_id: int) -> list[DispensingRecord]: ...


class ContractSource(Protocol):
    """Which products an insurer's rebate contract covers, and when.

    Real system category: rebate contract flags in pharmacy article master data.
    """
    def contracts_for(self, insurer_id: int, substance_id: int, strength: str) -> list[ContractRecord]: ...


class ShortageSource(Protocol):
    """Supply shortages. Real system category: official and wholesaler shortage feeds."""
    def active(self, substance_id: int, strength: str, today: date) -> list[ShortageRecord]: ...


class DrugAppearanceSource(Protocol):
    """What a product looks like. Real system category: a licensed drug appearance database."""
    def appearance(self, product_id: int) -> Optional[Appearance]: ...
    def products_for(self, substance_id: int, strength: str) -> list[Appearance]: ...


def to_appearance(p: Product) -> Appearance:
    return Appearance(product_id=p.id, pzn=p.pzn, name=p.name, substance_id=p.substance_id, strength=p.strength,
                      form=p.form, manufacturer=p.manufacturer, color=p.color, shape=p.shape, size_mm=p.size_mm,
                      score_line=p.score_line, divisible_parts=p.divisible_parts, coating=p.coating,
                      imprint=p.imprint, image_svg=p.image_svg)


class MockDispensingFeed:
    """Mock of the eML dispensing feed: reads `dispensing_event`."""
    def __init__(self, session: Session):
        self.session = session

    def events_for(self, prescription_id: int) -> list[DispensingRecord]:
        rows = self.session.exec(select(DispensingEvent).where(DispensingEvent.prescription_id == prescription_id)
                                 .order_by(DispensingEvent.dispensed_at, DispensingEvent.id)).all()
        return [DispensingRecord(prescription_id=r.prescription_id, product_id=r.product_id,
                                 dispensed_at=r.dispensed_at, reason=r.reason) for r in rows]


class MockContractSource:
    """Mock of article master data with rebate flags: reads `contract` and `contract_product`."""
    def __init__(self, session: Session):
        self.session = session

    def contracts_for(self, insurer_id: int, substance_id: int, strength: str) -> list[ContractRecord]:
        rows = self.session.exec(select(Contract).where(Contract.insurer_id == insurer_id,
                                                        Contract.substance_id == substance_id,
                                                        Contract.strength == strength)
                                 .order_by(Contract.valid_from)).all()
        out = []
        for c in rows:
            ids = self.session.exec(select(ContractProduct.product_id)
                                    .where(ContractProduct.contract_id == c.id)
                                    .order_by(ContractProduct.product_id)).all()
            out.append(ContractRecord(contract_id=c.id, insurer_id=c.insurer_id, substance_id=c.substance_id,
                                      strength=c.strength, valid_from=c.valid_from, valid_to=c.valid_to,
                                      product_ids=list(ids)))
        return out


class MockShortageSource:
    """Mock of a shortage feed: reads `shortage`."""
    def __init__(self, session: Session):
        self.session = session

    def active(self, substance_id: int, strength: str, today: date) -> list[ShortageRecord]:
        rows = self.session.exec(select(Shortage).where(Shortage.substance_id == substance_id,
                                                        Shortage.strength == strength,
                                                        Shortage.active_from <= today,
                                                        Shortage.active_to >= today)).all()
        return [ShortageRecord(substance_id=r.substance_id, strength=r.strength, active_from=r.active_from,
                               active_to=r.active_to) for r in rows]


class MockDrugAppearanceSource:
    """Mock of a licensed appearance database: reads `product` (pictures are generated in code)."""
    def __init__(self, session: Session):
        self.session = session

    def appearance(self, product_id: int) -> Optional[Appearance]:
        p = self.session.get(Product, product_id) if product_id else None
        return to_appearance(p) if p else None

    def products_for(self, substance_id: int, strength: str) -> list[Appearance]:
        rows = self.session.exec(select(Product).where(Product.substance_id == substance_id,
                                                       Product.strength == strength).order_by(Product.id)).all()
        return [to_appearance(p) for p in rows]


class MockDirectory:
    """Master data lookups (insurer and substance names). In production: the practice system."""
    def __init__(self, session: Session):
        self.session = session

    def insurer(self, insurer_id: Optional[int]) -> Optional[Insurer]:
        return self.session.get(Insurer, insurer_id) if insurer_id else None

    def substance(self, substance_id: int) -> Optional[Substance]:
        return self.session.get(Substance, substance_id)


class Sources:
    """The four adapters bundled together. Layer 3 only talks to these."""
    def __init__(self, dispensing: DispensingFeed, contracts: ContractSource, shortages: ShortageSource,
                 appearance: DrugAppearanceSource, directory: MockDirectory):
        self.dispensing = dispensing
        self.contracts = contracts
        self.shortages = shortages
        self.appearance = appearance
        self.directory = directory


def mock_sources(session: Session) -> Sources:
    return Sources(MockDispensingFeed(session), MockContractSource(session), MockShortageSource(session),
                   MockDrugAppearanceSource(session), MockDirectory(session))


# Small read helpers used by upper layers ------------------------------------------------------
def get_patient(session: Session, patient_id: int) -> Optional[Patient]:
    return session.get(Patient, patient_id)


def list_patients(session: Session) -> list[Patient]:
    return list(session.exec(select(Patient).order_by(Patient.id)).all())


def prescriptions_for(session: Session, patient_id: int) -> list[Prescription]:
    return list(session.exec(select(Prescription).where(Prescription.patient_id == patient_id)
                             .order_by(Prescription.id)).all())


def get_insurer(session: Session, insurer_id: Optional[int]) -> Optional[Insurer]:
    return session.get(Insurer, insurer_id) if insurer_id else None


def get_substance(session: Session, substance_id: int) -> Optional[Substance]:
    return session.get(Substance, substance_id)


def list_substances(session: Session) -> list[Substance]:
    return list(session.exec(select(Substance).order_by(Substance.id)).all())


def list_insurers(session: Session) -> list[Insurer]:
    return list(session.exec(select(Insurer).order_by(Insurer.id)).all())
