"""Look-alike groups: medicines of one patient that share colour and shape."""
from __future__ import annotations

from itertools import combinations

from pydantic import BaseModel

from app.l2_classify import taxonomy as tx
from app.l3_resolve.pipeline import PatientMedication

# Attributes a patient can report, easiest first. Ties are broken in this order.
ATTRIBUTES = ["time of day", "score line", "size", "purpose", "imprint"]
CANNOT_SEPARATE = "These two cannot be told apart by appearance – ask the patient to read the box or blister."


class ClusterMember(BaseModel):
    prescription_id: int
    name: str
    values: dict[str, str]


class Cluster(BaseModel):
    id: str
    color: str
    shape: str
    members: list[ClusterMember]
    separating_attributes: list[str]
    separable: bool
    inseparable_pairs: list[tuple[str, str]] = []
    hint: str

    @property
    def prescription_ids(self) -> list[int]:
        return [m.prescription_id for m in self.members]


def _values(med: PatientMedication) -> dict[str, str]:
    p = med.resolution.product
    times = " and ".join(tx.SCHEDULE_LABELS[t][0] for t in med.times) or "when needed"
    return {
        "time of day": times,
        "score line": "with a line" if p.score_line != "none" else "no line",
        "size": tx.size_band(p.size_mm),
        "purpose": tx.PURPOSE_LABELS[med.purpose_key][0],
        "imprint": f"marked {p.imprint}" if p.imprint else "no marking",
    }


def _separates(members: list[ClusterMember], attrs: tuple[str, ...]) -> bool:
    seen = {tuple(m.values[a] for a in attrs) for m in members}
    return len(seen) == len(members)


def find_clusters(meds: list[PatientMedication]) -> list[Cluster]:
    """Group medicines whose product is known and that share colour and shape."""
    groups: dict[tuple[str, str], list[PatientMedication]] = {}
    for med in meds:
        p = med.resolution.product
        if p:
            groups.setdefault((p.color, p.shape), []).append(med)

    clusters = []
    for (color, shape), group in groups.items():
        if len(group) < 2:
            continue
        members = [ClusterMember(prescription_id=m.prescription_id, name=m.substance_name, values=_values(m))
                   for m in group]
        chosen: tuple[str, ...] = ()
        for size in range(1, len(ATTRIBUTES) + 1):
            chosen = next((c for c in combinations(ATTRIBUTES, size) if _separates(members, c)), ())
            if chosen:
                break
        pairs = []
        if not chosen:
            for a, b in combinations(members, 2):
                if all(a.values[k] == b.values[k] for k in ATTRIBUTES):
                    pairs.append((a.name, b.name))
        if chosen:
            parts = "; ".join(f"{m.name}: " + ", ".join(m.values[a] for a in chosen) for m in members)
            hint = f"Tell them apart by {' and '.join(chosen)}. {parts}."
        else:
            names = " and ".join(f"{a} / {b}" for a, b in pairs)
            hint = f"{CANNOT_SEPARATE} ({names})"
        clusters.append(Cluster(id=f"{color}-{shape}", color=color, shape=shape, members=members,
                                separating_attributes=list(chosen), separable=bool(chosen),
                                inseparable_pairs=pairs, hint=hint))
    return clusters
