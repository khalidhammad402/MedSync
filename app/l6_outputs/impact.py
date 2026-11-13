"""A transparent impact model. Every number comes from the assumptions shown next to it."""
from __future__ import annotations

from pydantic import BaseModel, Field

LABEL = "Modelled from stated assumptions, not measured outcomes"
PILOT_METRICS = [
    "Call duration (minutes per medication call)",
    "Callback rate (calls that need a second call)",
    "Refill-request loops (back-and-forth with the pharmacy)",
    "Patient-reported confidence (short phone survey)",
    "Reported medication mix-ups",
]


class Assumptions(BaseModel):
    calls_per_week: int = Field(default=120, ge=0, le=1000, description="Medication phone calls per week")
    share_with_identification_problem: float = Field(default=0.30, ge=0, le=1,
                                                     description="Share of calls where a tablet must be identified")
    minutes_without: float = Field(default=6.0, ge=0, le=30, description="Minutes spent identifying, today")
    minutes_with: float = Field(default=2.0, ge=0, le=30, description="Minutes spent identifying, with MedSync")
    callback_share_without: float = Field(default=0.25, ge=0, le=1, description="Problem calls needing a callback, today")
    callback_share_with: float = Field(default=0.10, ge=0, le=1, description="Problem calls needing a callback, with MedSync")
    minutes_per_callback: float = Field(default=8.0, ge=0, le=60, description="Minutes per callback")


class ImpactResult(BaseModel):
    assumptions: Assumptions
    problem_calls_per_week: float
    identification_minutes_without: float
    identification_minutes_with: float
    callbacks_without: float
    callbacks_with: float
    callbacks_avoided_per_week: float
    minutes_saved_per_week: float
    hours_saved_per_year: float
    label: str = LABEL
    pilot_metrics: list[str] = PILOT_METRICS


def compute(a: Assumptions) -> ImpactResult:
    problem = a.calls_per_week * a.share_with_identification_problem
    without = problem * a.minutes_without
    with_ = problem * a.minutes_with
    cb_without = problem * a.callback_share_without
    cb_with = problem * a.callback_share_with
    avoided = max(cb_without - cb_with, 0)
    saved = max(without - with_, 0) + avoided * a.minutes_per_callback
    return ImpactResult(assumptions=a, problem_calls_per_week=round(problem, 1),
                        identification_minutes_without=round(without, 1), identification_minutes_with=round(with_, 1),
                        callbacks_without=round(cb_without, 1), callbacks_with=round(cb_with, 1),
                        callbacks_avoided_per_week=round(avoided, 1), minutes_saved_per_week=round(saved),
                        hours_saved_per_year=round(saved * 46 / 60))
