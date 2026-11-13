"""Optional AI extractor: Claude on Amazon Bedrock. OFF by default (USE_LLM_EXTRACTOR=false).

When enabled, DE-IDENTIFIED transcript text is sent to AWS. Any error, timeout or invalid
output falls back silently to the rule-based parser. The model must be enabled for the AWS
account in an EU region (default region: eu-central-1).
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from pydantic import BaseModel, ValidationError

from app import config
from app.l1_data.models import Patient
from app.l2_classify import vocab
from app.l5_conversation.anchors import ALL_FACETS, Anchor, Anchors, Lexicon, extract, normalise_strength

log = logging.getLogger("medsync.llm")
TIMEOUT_SECONDS = 3.0

SYSTEM_PROMPT = (
    "You extract structured anchors from one sentence a patient said on the phone about their tablets. "
    "The text may be German or English. Reply with ONE JSON object and nothing else, in this shape: "
    '{"anchors": [{"facet": "...", "value": "...", "negated": false, "quantity": null}]}. '
    "Allowed facets and values: "
    "color (white, yellow, orange, pink, red, brown, green, blue, purple, grey); "
    "shape (round, oval, oblong, shield, capsule); size (small, medium, large); score_line (yes, no); "
    "imprint (letters or digits on the tablet); schedule (morning, noon, evening, night, with_meal); "
    "purpose (heart, water, blood_thinner, thyroid, stomach, cholesterol, blood_pressure, pain, sugar); "
    "box_name (a medicine or manufacturer name read off the box); box_strength (for example 47.5 mg). "
    "Set negated to true when the patient rules a value out. Set quantity when a count is given. "
    "Never add medical advice, doses or anything that is not in the sentence."
)


class _LLMAnchor(BaseModel):
    facet: str
    value: str
    negated: bool = False
    quantity: Optional[int] = None


class _LLMOutput(BaseModel):
    anchors: list[_LLMAnchor]


class ExtractionResult(BaseModel):
    anchors: Anchors
    llm_used: bool = False
    fell_back: bool = False


def deidentify(text: str, patient: Optional[Patient] = None) -> str:
    """Remove names, dates of birth, addresses and phone numbers before anything leaves the laptop."""
    out = text
    if patient is not None:
        known = [patient.name, f"{patient.first_name} {patient.last_name}", patient.last_name, patient.first_name]
        b = patient.birth_date
        known += [b.isoformat(), f"{b.day:02d}.{b.month:02d}.{b.year}", f"{b.day}.{b.month}.{b.year}",
                  f"{b.day:02d}/{b.month:02d}/{b.year}"]
        known += [patient.address, patient.phone, patient.phone.replace(" ", "")]
        known += [part.strip() for part in patient.address.split(",")]
        for value in sorted({k for k in known if k and len(k) >= 3}, key=len, reverse=True):
            out = re.sub(re.escape(value), "[REMOVED]", out, flags=re.I)
    out = re.sub(r"\b(Herr|Frau|Mr|Mrs|Ms|Dr)\.?\s+[A-ZÄÖÜ][\wäöüß\-]+", "[NAME]", out)
    out = re.sub(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b", "[DATE]", out)
    out = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "[DATE]", out)
    out = re.sub(r"\b[A-ZÄÖÜ][a-zäöüß]+(?:straße|strasse|weg|allee|platz|gasse|ring)\s+\d+\s?[a-z]?\b", "[ADDRESS]", out)
    out = re.sub(r"(?<!\d)\+?\d[\d\s/\-]{6,}\d(?!\d)", "[NUMBER]", out)     # phone numbers (also hides PZNs)
    out = re.sub(r"\b\d{5}\b", "[POSTCODE]", out)
    return out


def _default_client() -> Any:
    import boto3  # optional dependency, only needed when the flag is on
    from botocore.config import Config
    return boto3.client("bedrock-runtime", region_name=config.aws_region(),
                        config=Config(connect_timeout=2, read_timeout=TIMEOUT_SECONDS, retries={"max_attempts": 1}))


def _call(client: Any, text: str) -> str:
    response = client.converse(
        modelId=config.bedrock_model_id(),
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": text}]}],
        inferenceConfig={"maxTokens": 400},
    )
    return "".join(block.get("text", "") for block in response["output"]["message"]["content"])


def validate(raw: str, lexicon: Optional[Lexicon] = None) -> list[Anchor]:
    """Parse the model's reply and drop every value that is outside the Layer 2 vocabulary."""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    parsed = _LLMOutput.model_validate(json.loads(match.group(0)))
    anchors = []
    for item in parsed.anchors:
        facet, value = item.facet.strip().lower(), item.value.strip()
        if facet not in ALL_FACETS or facet == "box_pzn":
            continue
        if facet in vocab.NORMALISERS:
            value = vocab.normalise(facet, value)
        elif facet == "imprint":
            value = vocab.normalise_imprint(value)
            value = value if 1 <= len(value) <= 6 else None
        elif facet == "box_name":
            value = lexicon.find(value.split(" ")[0]) if lexicon else None
        elif facet == "box_strength":
            value = normalise_strength(value) if re.search(r"\d", value) else None
        if not value:
            continue
        negated = item.negated
        if facet == "score_line" and negated:
            value, negated = ("no" if value == "yes" else "yes"), False
        qty = item.quantity if item.quantity and 0 < item.quantity <= 20 else None
        anchors.append(Anchor(facet=facet, value=value, negated=negated, quantity=qty, source="AI"))
    return anchors


def llm_anchors(text: str, patient: Optional[Patient] = None, lexicon: Optional[Lexicon] = None,
                client: Any = None) -> Optional[list[Anchor]]:
    """Ask the model. Returns None on any error, timeout or invalid output."""
    try:
        client = client or _default_client()
        safe_text = deidentify(text, patient)
        with ThreadPoolExecutor(max_workers=1) as pool:
            raw = pool.submit(_call, client, safe_text).result(timeout=TIMEOUT_SECONDS)
        return validate(raw, lexicon)
    except (Exception, ValidationError) as exc:  # noqa: BLE001 – every failure means "use the rules"
        log.warning("AI extractor unavailable, using the rule-based parser (%s)", type(exc).__name__)
        return None


def merge(rule: Anchors, ai: list[Anchor]) -> Anchors:
    """Rule-based result plus validated AI anchors. Each anchor keeps its source."""
    items = [a.model_copy() for a in rule.items]
    keys = {a.key for a in items}
    for anchor in ai:
        if anchor.key not in keys:
            items.append(anchor)
            keys.add(anchor.key)
    return Anchors(items=items)


def extract_merged(text: str, lang: str = "auto", lexicon: Optional[Lexicon] = None,
                   patient: Optional[Patient] = None, client: Any = None,
                   enabled: Optional[bool] = None) -> ExtractionResult:
    """The entry point used by the app: rules always run, the AI only adds to them when enabled."""
    rule = extract(text, lang, lexicon)
    enabled = config.use_llm() if enabled is None else enabled
    if not enabled:
        return ExtractionResult(anchors=rule)
    ai = llm_anchors(text, patient, lexicon, client)
    if ai is None:
        return ExtractionResult(anchors=rule, fell_back=True)
    return ExtractionResult(anchors=merge(rule, ai), llm_used=True)
