"""Turn what the patient says into anchors. Rule-based, German and English, runs offline."""
from __future__ import annotations

import difflib
import re
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Session

from app.l1_data import adapters
from app.l1_data.models import Product
from app.l2_classify import taxonomy as tx
from app.l2_classify import vocab

BOX_FACETS = ["box_name", "box_strength", "box_pzn"]
VISUAL_FACETS = ["color", "shape", "size", "score_line", "imprint"]
ALL_FACETS = BOX_FACETS + VISUAL_FACETS + ["schedule", "purpose"]
FACET_TITLES = {"box_name": "box", "box_strength": "box", "box_pzn": "box", "color": "colour", "shape": "shape",
                "size": "size", "score_line": "line", "imprint": "imprint", "schedule": "time", "purpose": "for"}


class Anchor(BaseModel):
    id: str = ""
    facet: str
    value: str
    negated: bool = False
    quantity: Optional[int] = None
    source: str = "rule"          # "rule" or "AI"
    utterance: int = 0

    @property
    def key(self) -> tuple[str, str, bool]:
        return (self.facet, self.value, self.negated)

    @property
    def label(self) -> str:
        value = self.value
        if self.facet == "purpose":
            value = tx.PURPOSE_LABELS[value][0]
        elif self.facet == "schedule":
            value = tx.SCHEDULE_LABELS[value][0]
        elif self.facet == "score_line":
            value = "has a line" if value == "yes" else "no line"
        elif self.facet == "box_pzn":
            value = f"PZN {value}"
        text = f"{self.quantity}× {value}" if self.quantity else value
        return f"not {text}" if self.negated else text


class Anchors(BaseModel):
    items: list[Anchor] = []

    @property
    def box(self) -> list[Anchor]:
        return [a for a in self.items if a.facet in BOX_FACETS]

    @property
    def visual(self) -> list[Anchor]:
        return [a for a in self.items if a.facet in VISUAL_FACETS]

    @property
    def schedule(self) -> list[Anchor]:
        return [a for a in self.items if a.facet == "schedule"]

    @property
    def purpose(self) -> list[Anchor]:
        return [a for a in self.items if a.facet == "purpose"]

    @property
    def negations(self) -> list[Anchor]:
        return [a for a in self.items if a.negated]

    @property
    def quantities(self) -> dict[str, int]:
        return {a.value: a.quantity for a in self.items if a.quantity}

    def get(self, facet: str) -> list[str]:
        return [a.value for a in self.items if a.facet == facet and not a.negated]


class Lexicon(BaseModel):
    """Names that can be read off a box: active ingredients, brand aliases, manufacturers."""
    names: dict[str, str] = {}      # lower-case word -> canonical substance or manufacturer name

    def find(self, word: str) -> Optional[str]:
        w = word.lower()
        if w in self.names:
            return self.names[w]
        if len(w) >= 6:
            close = difflib.get_close_matches(w, list(self.names), n=1, cutoff=0.84)
            if close:
                return self.names[close[0]]
        return None


def build_lexicon(session: Session) -> Lexicon:
    names: dict[str, str] = {}
    for sub in adapters.list_substances(session):
        for raw in [sub.inn_name, sub.inn_name_de] + sub.aliases.split(","):
            for word in re.split(r"[\s/]+", raw):
                if len(word) >= 5 and word.lower() not in ("succinate",):
                    names[word.lower()] = sub.inn_name
    from sqlmodel import select
    for manufacturer in session.exec(select(Product.manufacturer).distinct()).all():
        names[manufacturer.split(" ")[0].lower()] = manufacturer
    return Lexicon(names=names)


_WORD = re.compile(r"[A-Za-zÄÖÜäöüß0-9½¼'’\-]+")
_CLAUSE_BREAK = re.compile(r"[,.;:!?]|\bbut\b|\baber\b|\bsondern\b|\bor\b|\boder\b|\band\b|\bund\b")
_STRENGTH = re.compile(r"(\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?)\s*(mg|µg|mcg|mikrogramm|milligramm|microgram(?:s|me)?)\b", re.I)
_PZN = re.compile(r"\b(?:pzn\D{0,3})?(\d{7,8})\b|\bpzn\D{0,3}(\d{4,8})\b", re.I)
_IMPRINT = re.compile(r"(?:imprint|marked|marking|letters?|says|written|stamped|aufdruck|prägung|aufschrift|"
                      r"buchstaben?|steht|beschriftung)\s+(?:is\s+|ist\s+|it\s+|on\s+it\s+|drauf\s+|darauf\s+)?"
                      r"[\"'„“]?([A-Z]{1,3}\s?\d{1,3}|[A-Z]{1,3}|\d{1,3})\b")


def _negated(text: str, start: int) -> bool:
    """True if a negation word sits in the same clause, at most three words before the match."""
    before = text[:start]
    breaks = list(_CLAUSE_BREAK.finditer(before))
    clause = before[breaks[-1].end():] if breaks else before
    words = [w.lower() for w in _WORD.findall(clause)][-3:]
    return any(w in vocab.NEGATION_WORDS for w in words)


def _phrase_hits(text: str, table: dict[str, list[str]], facet: str) -> list[tuple[int, int, str, str]]:
    """Find multi-word or compound synonyms. Longest phrases win; overlaps are dropped."""
    phrases = sorted(((p, key) for key, plist in table.items() for p in plist), key=lambda x: -len(x[0]))
    taken: list[tuple[int, int]] = []
    hits = []
    for phrase, key in phrases:
        for m in re.finditer(rf"(?<![a-zäöüß]){re.escape(phrase)}(?:en|n|e|s)?(?![a-zäöüß])", text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append((m.start(), m.end(), facet, key))
    return hits


def normalise_strength(raw: str) -> str:
    m = _STRENGTH.search(raw if re.search(r"[a-zµ]", raw, re.I) else raw + " mg")
    if not m:
        return raw.strip().lower()
    number = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    unit = "µg" if unit in ("mcg", "mikrogramm") or unit.startswith("microgram") else "mg" if unit.startswith("m") else unit
    return f"{number} {unit}"


def extract(text: str, lang: str = "auto", lexicon: Optional[Lexicon] = None) -> Anchors:
    """Extract anchors from one utterance. `lang` may be "de", "en" or "auto" (both vocabularies apply)."""
    found: list[tuple[int, Anchor]] = []
    lower = text.lower()

    # Box anchors: strongest, read off the box or blister
    for m in _PZN.finditer(text):
        found.append((m.start(), Anchor(facet="box_pzn", value=m.group(1) or m.group(2))))
    for m in _STRENGTH.finditer(text):
        found.append((m.start(), Anchor(facet="box_strength", value=normalise_strength(m.group(0)))))
    words = [(m.start(), m.group(0)) for m in _WORD.finditer(text)]
    if lexicon:
        for pos, word in words:
            name = lexicon.find(word)
            if name:
                found.append((pos, Anchor(facet="box_name", value=name)))

    # Visual anchors: colour, shape, size (single words, inflected forms allowed) with quantities
    visual_at: dict[int, Anchor] = {}
    for i, (pos, word) in enumerate(words):
        for facet, fn in (("color", vocab.normalise_color), ("shape", vocab.normalise_shape),
                          ("size", vocab.normalise_size)):
            value = fn(word)
            if value:
                visual_at[i] = Anchor(facet=facet, value=value, negated=_negated(lower, pos))
                found.append((pos, visual_at[i]))
                break
    for i in sorted(visual_at):
        if i - 1 in visual_at:
            continue                                   # not the start of a run of visual words
        qty = vocab.normalise_number(words[i - 1][1]) if i > 0 else None
        if qty:
            run = []
            j = i
            while j in visual_at:
                run.append(visual_at[j])
                j += 1
            target = next((a for a in run if a.facet == "color"), run[-1])
            target.quantity = qty

    # Score line: "no line" / "ohne Kerbe" becomes the value "no"
    for start, _end, _f, _k in _phrase_hits(lower, {"yes": vocab.SCORE_WORDS}, "score_line"):
        found.append((start, Anchor(facet="score_line", value="no" if _negated(lower, start) else "yes")))

    for m in _IMPRINT.finditer(text):
        found.append((m.start(1), Anchor(facet="imprint", value=vocab.normalise_imprint(m.group(1)))))

    for table, facet in ((vocab.SCHEDULE_SYNONYMS, "schedule"), (vocab.PURPOSE_SYNONYMS, "purpose")):
        for start, _end, _f, key in _phrase_hits(lower, table, facet):
            found.append((start, Anchor(facet=facet, value=key, negated=_negated(lower, start))))

    items: list[Anchor] = []
    for _pos, anchor in sorted(found, key=lambda x: x[0]):
        same = next((a for a in items if a.key == anchor.key), None)
        if same:
            same.quantity = same.quantity or anchor.quantity
        else:
            items.append(anchor)
    return Anchors(items=items)
