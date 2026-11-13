"""Filter and rank the patient's medicines by the anchors heard so far. The clinician decides."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.l2_classify import taxonomy as tx
from app.l2_classify import vocab
from app.l3_resolve.pipeline import PatientMedication
from app.l5_conversation.anchors import BOX_FACETS, Anchor, normalise_strength

BOX_QUESTION = ("Can you read me the name on the box?", "Können Sie mir den Namen auf der Packung vorlesen?")


class Candidate(BaseModel):
    prescription_id: int
    name: str
    matched: bool
    score: float
    reasons: list[str] = []
    ruled_out_by: list[str] = []


class Question(BaseModel):
    attribute: str
    text_en: str
    text_de: str
    why: str


class NarrowingResult(BaseModel):
    candidates: list[Candidate]
    total: int
    remaining: int
    sequence: list[int]
    question: Optional[Question] = None
    box_mode: bool = False
    overridden_anchor_ids: list[str] = []
    count_notes: list[str] = []

    @property
    def matched_ids(self) -> list[int]:
        return [c.prescription_id for c in self.candidates if c.matched]


def _match(med: PatientMedication, facet: str, value: str) -> Optional[bool]:
    """True / False, or None when the appearance is unknown and nothing can be said."""
    apps = med.resolution.appearances
    if facet == "purpose":
        return med.purpose_key == value
    if facet == "schedule":
        return med.with_meal if value == "with_meal" else value in med.times
    if facet == "box_strength":
        return normalise_strength(med.strength) == value
    if facet == "box_name":
        return med.substance_name == value or any(a.manufacturer == value for a in apps)
    if not apps:
        return None
    if facet == "box_pzn":
        return any(value in a.pzn for a in apps)
    if facet == "color":
        return any(a.color == value for a in apps)
    if facet == "shape":
        return any(a.shape == value for a in apps)
    if facet == "size":
        return any(tx.size_band(a.size_mm) == value for a in apps)
    if facet == "score_line":
        return any((a.score_line != "none") == (value == "yes") for a in apps)
    if facet == "imprint":
        return any(value in vocab.normalise_imprint(a.imprint) for a in apps if a.imprint)
    return None


def _active(anchors: list[Anchor]) -> tuple[list[Anchor], list[Anchor]]:
    """Box anchors are the strongest: when present they override everything else."""
    box = [a for a in anchors if a.facet in BOX_FACETS]
    if box:
        return box, [a for a in anchors if a.facet not in BOX_FACETS]
    return list(anchors), []


def _evaluate(meds: list[PatientMedication], anchors: list[Anchor]) -> list[Candidate]:
    active, _ = _active(anchors)
    facets: dict[str, list[Anchor]] = {}
    for a in active:
        facets.setdefault(a.facet, []).append(a)
    out = []
    for med in meds:
        reasons, ruled_out, hits, positives = [], [], 0, 0
        ok = True
        for facet, group in facets.items():
            pos = [a for a in group if not a.negated]
            neg = [a for a in group if a.negated]
            positives += 1 if pos else 0
            if pos:
                results = [(a, _match(med, facet, a.value)) for a in pos]
                yes = [a for a, r in results if r is True]
                if yes:
                    hits += 1
                    reasons.append(f"{facet.replace('_', ' ')}: {yes[0].label}")
                elif any(r is None for _, r in results):
                    reasons.append("appearance unknown – cannot be ruled out")
                else:
                    ok = False
                    ruled_out.append(" / ".join(a.label for a in pos))
            for a in neg:
                if _match(med, facet, a.value) is True:
                    ok = False
                    ruled_out.append(a.label)
        score = round(hits / positives, 2) if positives else (1.0 if ok else 0.0)
        out.append(Candidate(prescription_id=med.prescription_id, name=med.label, matched=ok,
                             score=score if ok else 0.0, reasons=reasons, ruled_out_by=ruled_out))
    return out


def _question(meds: list[PatientMedication], anchors: list[Anchor], box_available: bool) -> Optional[Question]:
    n = len(meds)
    if n == 0:
        return Question(attribute="box", text_en=BOX_QUESTION[0], text_de=BOX_QUESTION[1],
                        why="Nothing on the list matches. Remove an anchor or ask for the box.")
    if n == 1:
        return None
    box = Question(attribute="box", text_en=BOX_QUESTION[0], text_de=BOX_QUESTION[1],
                   why=f"{n} medicines remain. The name on the box settles it.")
    if box_available:
        return box
    asked = {a.facet for a in anchors}
    options: list[tuple[str, str, str, str]] = [("score_line", "yes", "Does the tablet have a line across the middle?",
                                                 "Hat die Tablette eine Kerbe in der Mitte?")]
    options += [("color", c, f"Is the tablet {c}?", f"Ist die Tablette {tx.COLOR_LABELS_DE[c]}?") for c in tx.COLORS]
    options += [("shape", s, "Is it a capsule?" if s == "capsule" else f"Is the tablet {s}?",
                 "Ist es eine Kapsel?" if s == "capsule" else f"Ist die Tablette {tx.SHAPE_LABELS_DE[s]}?")
                for s in tx.SHAPES]
    options += [("size", "small", "Is it a small tablet?", "Ist es eine kleine Tablette?"),
                ("size", "large", "Is it a large tablet?", "Ist es eine große Tablette?")]
    options += [("schedule", "evening", "Do you take it in the evening?", "Nehmen Sie sie abends?"),
                ("schedule", "morning", "Do you take it in the morning?", "Nehmen Sie sie morgens?"),
                ("schedule", "noon", "Do you take it at noon?", "Nehmen Sie sie mittags?")]
    best, best_even = None, 0
    for facet, value, en, de in options:
        if facet in asked:
            continue
        yes = sum(1 for m in meds if _match(m, facet, value) is True)
        even = min(yes, n - yes)
        if even > best_even:
            best, best_even = Question(attribute=facet, text_en=en, text_de=de,
                                       why=f"Splits the {n} remaining medicines {yes} / {n - yes}."), even
    return best or box


def narrow(meds: list[PatientMedication], anchors: list[Anchor], box_available: bool = False) -> NarrowingResult:
    """Rank the medicines, give the narrowing sequence and the best next question."""
    candidates = _evaluate(meds, anchors)
    order = {m.prescription_id: i for i, m in enumerate(meds)}
    candidates.sort(key=lambda c: (not c.matched, -c.score, order[c.prescription_id]))
    remaining = [m for m in meds if any(c.prescription_id == m.prescription_id and c.matched for c in candidates)]

    sequence = [len(meds)]
    for step in sorted({a.utterance for a in anchors}):
        upto = [a for a in anchors if a.utterance <= step]
        sequence.append(sum(1 for c in _evaluate(meds, upto) if c.matched))

    active, overridden = _active(anchors)
    notes = []
    if not overridden:
        for a in active:
            if a.facet == "color" and a.quantity and not a.negated:
                have = sum(1 for m in meds if _match(m, "color", a.value) is True)
                if have != a.quantity:
                    notes.append(f"Patient mentions {a.quantity} {a.value}, the list has {have}.")
    question = _question(remaining, anchors, box_available) if anchors or box_available else None
    return NarrowingResult(candidates=candidates, total=len(meds), remaining=len(remaining), sequence=sequence,
                           question=question, box_mode=bool(overridden) or any(a.facet in BOX_FACETS for a in anchors),
                           overridden_anchor_ids=[a.id for a in overridden], count_notes=notes)
