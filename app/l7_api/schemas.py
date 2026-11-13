"""Typed shapes returned by the JSON API (the lower layers' models are reused where they fit)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.l3_resolve.pipeline import Resolution


class Health(BaseModel):
    status: str = "ok"
    synthetic_data: bool = True
    today: date
    llm_extractor: bool


class PatientOut(BaseModel):
    id: int
    name: str
    age: int
    insurer: Optional[str]
    prescriptions: int


class TrailOut(BaseModel):
    prescription_id: int
    headline: str
    lines: list[str]
    read_aloud: str
    resolution: Resolution


class ActionResult(BaseModel):
    ok: bool = True
    message: str


class ErrorOut(BaseModel):
    error: str
    message: str


class ContractPeriod(BaseModel):
    contract_id: int
    valid_from: date
    valid_to: date
    status: str                  # past | active | next
    left_pct: float
    width_pct: float
    products: list[dict]


class ExplorerOut(BaseModel):
    insurer_id: int
    insurer: str
    substance_id: int
    substance: str
    strength: str
    aliases: list[str]
    today_pct: float
    rotation_date: Optional[date]
    periods: list[ContractPeriod]
    holders: list[dict]
