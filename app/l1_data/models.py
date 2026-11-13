"""Layer 1 tables. Everything here is mock data."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Insurer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    short_name: str
    full_name: str


class Substance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    inn_name: str
    inn_name_de: str
    atc_code: str
    class_label: str
    purpose_key: str            # Layer 2 purpose vocabulary
    plain_purpose_en: str
    plain_purpose_de: str
    risk_tier: str              # red | amber | green
    narrow_therapeutic_index: bool = False
    otc_caution: bool = False
    aliases: str = ""           # comma separated fictional brand names


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    pzn: str = Field(index=True)
    substance_id: int = Field(foreign_key="substance.id")
    name: str
    strength: str
    form: str
    manufacturer: str
    color: str
    shape: str
    size_mm: float
    score_line: str             # none | functional | decorative
    divisible_parts: int        # 1 = must not be split, 2, 4
    coating: str
    imprint: str = ""
    image_svg: str = ""


class Contract(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    insurer_id: int = Field(foreign_key="insurer.id")
    substance_id: int = Field(foreign_key="substance.id")
    strength: str
    valid_from: date
    valid_to: date


class ContractProduct(SQLModel, table=True):
    __tablename__ = "contract_product"
    contract_id: int = Field(foreign_key="contract.id", primary_key=True)
    product_id: int = Field(foreign_key="product.id", primary_key=True)


class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    first_name: str
    last_name: str
    salutation: str
    birth_date: date
    insurer_id: Optional[int] = Field(default=None, foreign_key="insurer.id")
    address: str = ""
    phone: str = ""


class Prescription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    substance_id: int = Field(foreign_key="substance.id")
    strength: str
    instruction_text: str
    times_of_day: str           # comma separated: morning,noon,evening,night
    with_meal: bool = False
    aut_idem_excluded: bool = False
    prescribed_product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    override_product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    prescribed_on: Optional[date] = None


class DispensingEvent(SQLModel, table=True):
    __tablename__ = "dispensing_event"
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    prescription_id: int = Field(foreign_key="prescription.id")
    product_id: int = Field(foreign_key="product.id")
    dispensed_at: date
    reason: str = "normal"      # normal | shortage_substitution | contract_switch


class Shortage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    substance_id: int = Field(foreign_key="substance.id")
    strength: str
    active_from: date
    active_to: date


class CallSession(SQLModel, table=True):
    __tablename__ = "call_session"
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    started_at: datetime
    utterances_json: str = "[]"
    anchors_json: str = "[]"
    box_available: bool = False


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: Optional[int] = Field(default=None, primary_key=True)
    at: datetime
    patient_id: Optional[int] = None
    action: str
    ref: str = ""
    detail: str = ""


class KeyIssue(SQLModel, table=True):
    __tablename__ = "key_issue"
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    issued_at: date
    lang: str = "de"
