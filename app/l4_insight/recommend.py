"""Rules-based prompts for the clinician. Communication and safety prompts only – never dosing advice."""
from __future__ import annotations

import re
from datetime import date
from typing import Iterable, Optional

from pydantic import BaseModel

from app import config
from app.l1_data.adapters import Appearance
from app.l2_classify import taxonomy as tx
from app.l3_resolve.pipeline import PatientMedication, describe, fmt_date
from app.l4_insight.clusters import find_clusters

SEVERITY_RANK = {"important": 0, "attention": 1, "info": 2}
SEVERITY_LABEL = {"important": "Important", "attention": "Attention", "info": "Info"}

_QUARTER = re.compile(r"[¼¾]|\b[13]/4\b|\b0[.,][27]5\b|quarter|viertel", re.I)
_HALF = re.compile(r"½|\b1/2\b|\b\d*[.,]5\b|\bhalf\b|\bhalbe?\b|hälfte", re.I)


class Recommendation(BaseModel):
    id: str
    rule: str
    severity: str
    title: str
    why: str
    action_label: str
    action_code: str
    prescription_id: Optional[int] = None
    sort_days: int = 0     # smaller = more recent or more urgent


class SplitCheck(BaseModel):
    needs_split: bool
    required_parts: Optional[int] = None
    ok: bool = True
    message: str = ""


def required_parts(instruction: str) -> Optional[int]:
    """2 if the instruction needs half a tablet, 4 for a quarter, None if no fraction."""
    if _QUARTER.search(instruction or ""):
        return 4
    if _HALF.search(instruction or ""):
        return 2
    return None


def split_check(instruction: str, appearances: Iterable[Appearance]) -> SplitCheck:
    """Can the instruction be carried out with the product the patient holds?"""
    need = required_parts(instruction)
    if need is None:
        return SplitCheck(needs_split=False, message="No tablet splitting needed.")
    word = "half a tablet" if need == 2 else "a quarter tablet"
    products = list(appearances)
    if not products:
        return SplitCheck(needs_split=True, required_parts=need, ok=True,
                          message=f"Needs {word}. Product not confirmed yet – check once it is known.")
    bad = [a for a in products if a.divisible_parts < need]
    if not bad:
        return SplitCheck(needs_split=True, required_parts=need, ok=True,
                          message=f"Needs {word}. {products[0].name} can be split this way.")
    a = bad[0]
    reason = ("its line is decorative" if a.score_line == "decorative" else
              "it can only be halved" if a.divisible_parts == 2 else "it has no break line")
    return SplitCheck(needs_split=True, required_parts=need, ok=False,
                      message=f"Needs {word}, but {a.name} must not be split this way ({reason}).")


def recommend(meds: list[PatientMedication], today: date, key_last_issued: Optional[date] = None,
              dismissed: Iterable[str] = ()) -> list[Recommendation]:
    """Ranked prompts: by severity, then by recency."""
    recs: list[Recommendation] = []
    latest_change: Optional[date] = None

    for med in meds:
        res, pid, name = med.resolution, med.prescription_id, med.substance_name

        # R1 – appearance change ahead
        if (res.next_products and res.rotation_date and res.days_until_rotation is not None
                and 0 <= res.days_until_rotation <= config.ROTATION_WARN_DAYS):
            recs.append(Recommendation(
                id=f"R1-{pid}", rule="R1", severity="attention", prescription_id=pid,
                title=f"Appearance change ahead – {name}",
                why=(f"The {res.insurer_name} contract rotates in {res.days_until_rotation} days. From "
                     f"{fmt_date(res.rotation_date)} the next pack will be a "
                     f"{describe(res.next_products[0], short=True)}."),
                action_label="Prepare updated key", action_code="open_key", sort_days=res.days_until_rotation))

        switched = bool(res.previous_product and res.switch_date and res.confidence_code == "dispensing")
        if switched:
            age = (today - res.switch_date).days
            latest_change = max(latest_change, res.switch_date) if latest_change else res.switch_date
            reason = {"shortage_substitution": "a supply shortage", "contract_switch": "a contract change"}.get(
                res.switch_reason or "", "a pharmacy substitution")
            # R2 – recent switch
            recs.append(Recommendation(
                id=f"R2-{pid}", rule="R2", severity="info", prescription_id=pid,
                title=f"Recent switch – {name}",
                why=(f"On {fmt_date(res.switch_date)} the pharmacy handed over {res.product.name} instead of "
                     f"{res.previous_product.name} because of {reason}."),
                action_label="Tell patient, refresh key", action_code="open_key", sort_days=age))
            # R3 – possible double pack
            if age <= config.DOUBLE_PACK_DAYS:
                recs.append(Recommendation(
                    id=f"R3-{pid}", rule="R3", prescription_id=pid,
                    severity="important" if med.risk_tier == "red" else "attention",
                    title=f"Possible double pack – {name}",
                    why=(f"The product changed {age} days ago. Old and new packs may both be at home: they look "
                         f"different but are the same medicine."),
                    action_label="Ask about both packs", action_code="ask_packs", sort_days=age))

        # R4 – supply shortage (only while no pack has been dispensed since it started)
        if res.shortage_active and not (res.last_dispensed_at and res.shortage_since
                                        and res.last_dispensed_at >= res.shortage_since):
            recs.append(Recommendation(
                id=f"R4-{pid}", rule="R4", severity="attention", prescription_id=pid,
                title=f"Supply shortage – {name}",
                why="A shortage is reported, so the pharmacy is likely to substitute another product.",
                action_label="Choose product by hand", action_code="override", sort_days=0))

        # R5 – unresolved or several candidates
        if res.confidence_code in ("unresolved", "contract_multi"):
            why = ("The product could not be worked out." if res.confidence_code == "unresolved" else
                   f"The contract allows {len(res.candidates)} products that look different.")
            recs.append(Recommendation(
                id=f"R5-{pid}", rule="R5", severity="attention", prescription_id=pid,
                title=f"Confirm product – {name}",
                why=f"{why} Ask the patient to read the box, or ask the pharmacy.",
                action_label="Confirm product", action_code="override", sort_days=0))

        # R7 – split instruction not possible (re-checked on whatever product is held now)
        check = split_check(med.instruction_text, res.appearances)
        if check.needs_split and not check.ok:
            recs.append(Recommendation(
                id=f"R7-{pid}", rule="R7", severity="important", prescription_id=pid,
                title=f"Split instruction not possible – {'new ' if switched else ''}product must not be split",
                why=f"{name}, instruction “{med.instruction_text}”: {check.message}",
                action_label="Contact prescriber or pharmacy", action_code="contact", sort_days=0))

    # R6 – look-alike groups
    for cluster in find_clusters(meds):
        recs.append(Recommendation(
            id=f"R6-{cluster.id}", rule="R6", severity="attention",
            title=f"Look-alike group – {len(cluster.members)} {cluster.color} {cluster.shape} tablets",
            why=cluster.hint, action_label="Ask before discussing changes", action_code="ask_separator",
            sort_days=0))

    # R8 – stale patient key
    if key_last_issued and latest_change and key_last_issued < latest_change:
        recs.append(Recommendation(
            id="R8-key", rule="R8", severity="info", title="Patient key is out of date",
            why=(f"The last key was issued on {fmt_date(key_last_issued)}, before the latest appearance change on "
                 f"{fmt_date(latest_change)}."),
            action_label="Create new key", action_code="open_key", sort_days=(today - latest_change).days))

    hidden = set(dismissed)
    recs = [r for r in recs if r.id not in hidden]
    recs.sort(key=lambda r: (SEVERITY_RANK[r.severity], r.sort_days, r.id))
    return recs


def split_badge(med: PatientMedication) -> tuple[str, str]:
    """(kind, label) for the card badge."""
    apps = med.resolution.appearances
    if not apps:
        return "unknown", "Splitting unknown"
    if all(tx.can_split(a.divisible_parts) for a in apps):
        return "ok", tx.split_label(max(a.divisible_parts for a in apps))
    if len(apps) > 1 and any(tx.can_split(a.divisible_parts) for a in apps):
        return "no", "Do not split (depends on product)"
    return "no", "Do not split"
