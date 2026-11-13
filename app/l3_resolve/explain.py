"""Turn a resolution trail into plain English that is short enough to read aloud."""
from __future__ import annotations

from app.l3_resolve.pipeline import Resolution, fmt_date


def explain_lines(res: Resolution) -> list[str]:
    """One short sentence per stage, in chain order, then the outlook."""
    lines = [s.detail for s in sorted(res.stages, key=lambda s: s.stage)]
    if res.previous_product and res.switch_date and res.product:
        lines.append(f"Until {fmt_date(res.switch_date)} the patient had {res.previous_product.name}, "
                     f"which looks different. Old packs may still be at home.")
    if res.next_products and res.rotation_date:
        lines.append(f"From {fmt_date(res.rotation_date)} the contract changes, so the next pack will look different.")
    lines.extend(res.warnings)
    return lines


def explain(res: Resolution) -> str:
    return " ".join(explain_lines(res))


def headline(res: Resolution) -> str:
    """A single sentence answer to "how do you know?"."""
    if res.product:
        return f"{res.confidence}: {res.product.name}."
    if res.candidates:
        return f"{res.confidence}: " + " or ".join(c.name for c in res.candidates) + "."
    return "Unresolved: ask the patient to read the box, or ask the pharmacy."
