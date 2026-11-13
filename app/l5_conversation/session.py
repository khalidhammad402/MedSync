"""Call sessions: what was said, which anchors are active, and the current narrowing."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from sqlmodel import Session

from app import config
from app.l1_data import adapters
from app.l1_data.models import CallSession
from app.l3_resolve import pipeline
from app.l4_insight import actions
from app.l5_conversation import llm_extractor
from app.l5_conversation.anchors import Anchor, build_lexicon
from app.l5_conversation.narrowing import NarrowingResult, narrow


class SessionState(BaseModel):
    id: int
    patient_id: int
    started_at: datetime
    utterances: list[str]
    anchors: list[Anchor]
    box_available: bool
    narrowing: NarrowingResult
    ai_enabled: bool = False
    last_fell_back: bool = False


def _load(session: Session, call_id: int) -> CallSession:
    call = session.get(CallSession, call_id)
    if call is None:
        raise LookupError("Unknown call session.")
    return call


def _state(session: Session, call: CallSession, meds: Optional[list] = None, fell_back: bool = False) -> SessionState:
    anchors = [Anchor(**a) for a in json.loads(call.anchors_json)]
    meds = meds if meds is not None else pipeline.resolve_patient(session, call.patient_id, config.today())
    return SessionState(id=call.id, patient_id=call.patient_id, started_at=call.started_at,
                        utterances=json.loads(call.utterances_json), anchors=anchors,
                        box_available=call.box_available,
                        narrowing=narrow(meds, anchors, call.box_available),
                        ai_enabled=config.use_llm(), last_fell_back=fell_back)


def start(session: Session, patient_id: int) -> SessionState:
    if adapters.get_patient(session, patient_id) is None:
        raise LookupError("Unknown patient.")
    call = CallSession(patient_id=patient_id, started_at=datetime.now(timezone.utc))
    session.add(call)
    session.commit()
    session.refresh(call)
    actions.log(session, "call_started", patient_id, str(call.id))
    return _state(session, call)


def get(session: Session, call_id: int, meds: Optional[list] = None) -> SessionState:
    return _state(session, _load(session, call_id), meds)


def add_utterance(session: Session, call_id: int, text: str, lang: str = "auto", client: Any = None) -> SessionState:
    """Extract anchors from what the patient said and add them to the session."""
    call = _load(session, call_id)
    text = (text or "").strip()
    if not text:
        raise ValueError("Type or paste what the patient said first.")
    patient = adapters.get_patient(session, call.patient_id)
    result = llm_extractor.extract_merged(text, lang, build_lexicon(session), patient, client)
    utterances = json.loads(call.utterances_json)
    utterances.append(text)
    anchors = [Anchor(**a) for a in json.loads(call.anchors_json)]
    next_id = max([int(a.id[1:]) for a in anchors] + [0]) + 1
    keys = {a.key: a for a in anchors}
    for new in result.anchors.items:
        if new.key in keys:
            keys[new.key].quantity = keys[new.key].quantity or new.quantity
            continue
        new.id, new.utterance = f"a{next_id}", len(utterances)
        next_id += 1
        anchors.append(new)
        keys[new.key] = new
    call.utterances_json = json.dumps(utterances, ensure_ascii=False)
    call.anchors_json = json.dumps([a.model_dump() for a in anchors], ensure_ascii=False)
    session.add(call)
    session.commit()
    return _state(session, call, fell_back=result.fell_back)


def remove_anchor(session: Session, call_id: int, anchor_id: str) -> SessionState:
    call = _load(session, call_id)
    anchors = [Anchor(**a) for a in json.loads(call.anchors_json)]
    kept = [a for a in anchors if a.id != anchor_id]
    if len(kept) == len(anchors):
        raise LookupError("That anchor is no longer there.")
    call.anchors_json = json.dumps([a.model_dump() for a in kept], ensure_ascii=False)
    session.add(call)
    session.commit()
    return _state(session, call)


def set_box_available(session: Session, call_id: int, available: bool) -> SessionState:
    call = _load(session, call_id)
    call.box_available = available
    session.add(call)
    session.commit()
    return _state(session, call)
