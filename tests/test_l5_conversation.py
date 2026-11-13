import json
import time

import pytest
from sqlmodel import select

from app.l1_data.models import Patient
from app.l3_resolve import pipeline
from app.l5_conversation import llm_extractor, session as calls
from app.l5_conversation.anchors import Anchor, build_lexicon, extract
from app.l5_conversation.narrowing import narrow


def _pairs(anchors):
    return {(a.facet, a.value) for a in anchors.items}


def _muller(session):
    return session.exec(select(Patient).where(Patient.name == "Herr Müller")).one()


def _numbered(anchors, n=1):
    for i, a in enumerate(anchors.items):
        a.id, a.utterance = f"a{n}{i}", n
    return anchors.items


def test_organizer_dialogue_english():
    a = extract("I take three white tablets, one blue and two yellow ones", "en")
    assert _pairs(a) == {("color", "white"), ("color", "blue"), ("color", "yellow")}
    assert a.quantities == {"white": 3, "blue": 1, "yellow": 2}


def test_organizer_dialogue_german():
    a = extract("Ich nehme drei weiße Tabletten, eine blaue und zwei gelbe.", "de")
    assert a.quantities == {"white": 3, "blue": 1, "yellow": 2}
    assert a.negations == []


def test_heart_or_yellow_question_in_both_languages():
    en = extract("Is that the one for the heart or the yellow one?")
    assert _pairs(en) == {("purpose", "heart"), ("color", "yellow")} and not en.quantities
    de = extract("Ist das die für das Herz oder die gelbe?")
    assert _pairs(de) == {("purpose", "heart"), ("color", "yellow")}


def test_common_phrasing_schedule_size_purpose():
    a = extract("the small yellow one in the evening")
    assert _pairs(a) == {("size", "small"), ("color", "yellow"), ("schedule", "evening")}
    b = extract("Die Wassertablette nehme ich morgens zum Essen, die kleine runde")
    assert {("purpose", "water"), ("schedule", "morning"), ("schedule", "with_meal"), ("size", "small"),
            ("shape", "round")} <= _pairs(b)
    assert _pairs(extract("my blood thinner and the one for blood pressure")) == {
        ("purpose", "blood_thinner"), ("purpose", "blood_pressure")}


def test_negations_english_and_german():
    en = extract("not the round one, the oval one")
    assert [(a.value, a.negated) for a in en.items] == [("round", True), ("oval", False)]
    de = extract("nicht die runde, sondern die längliche")
    assert [(a.value, a.negated) for a in de.items] == [("round", True), ("oblong", False)]


def test_score_line_yes_and_no():
    assert _pairs(extract("Ja, mit einer Kerbe in der Mitte")) == {("score_line", "yes")}
    assert _pairs(extract("it has a line across the middle")) == {("score_line", "yes")}
    assert _pairs(extract("ohne Kerbe")) == {("score_line", "no")}
    assert _pairs(extract("there is no line on it")) == {("score_line", "no")}


def test_box_anchors_from_box_or_blister(session):
    lex = build_lexicon(session)
    a = extract("Auf der Packung steht Metoprolol Nordlicht 47,5 mg, PZN 99900037", "de", lex)
    assert ("box_name", "Metoprolol succinate") in _pairs(a)
    assert ("box_name", "Nordlicht Generika") in _pairs(a)
    assert ("box_strength", "47.5 mg") in _pairs(a) and ("box_pzn", "99900037") in _pairs(a)
    assert ("box_name", "Torasemide") in _pairs(extract("it says Torasemid on the box", "en", lex))
    assert ("box_name", "Metoprolol succinate") in _pairs(extract("Metoprolool", "en", lex))   # misspelt
    assert _pairs(extract("it says M 47 on it")) == {("imprint", "M47")}


def test_narrowing_sequence_on_demo_patient(session, today):
    meds = pipeline.resolve_patient(session, _muller(session).id, today)
    anchors = _numbered(extract("Ich nehme drei weiße Tabletten, eine blaue und zwei gelbe."), 1)
    r1 = narrow(meds, anchors)
    assert r1.sequence == [8, 7] and r1.remaining == 7
    assert r1.count_notes == ["Patient mentions 3 white, the list has 4."]
    anchors += _numbered(extract("Is that the one for the heart or the yellow one?"), 2)
    r2 = narrow(meds, anchors)
    assert r2.sequence == [8, 7, 2]
    assert {c.name for c in r2.candidates if c.matched} == {"Metoprolol succinate 47.5 mg", "Dapagliflozin 10 mg"}
    assert r2.question.attribute == "score_line"
    assert r2.question.text_en == "Does the tablet have a line across the middle?"
    anchors += _numbered(extract("Ja, mit einer Kerbe in der Mitte"), 3)
    r3 = narrow(meds, anchors)
    assert r3.sequence == [8, 7, 2, 1] and r3.question is None
    assert r3.candidates[0].name == "Metoprolol succinate 47.5 mg" and r3.candidates[0].matched
    assert r3.candidates[0].reasons


def test_box_anchor_overrides_visual_anchors(session, today):
    meds = pipeline.resolve_patient(session, _muller(session).id, today)
    lex = build_lexicon(session)
    anchors = _numbered(extract("the blue one", "en", lex), 1)
    assert narrow(meds, anchors).candidates[0].name.startswith("Apixaban")
    anchors += _numbered(extract("the box says Torasemid", "en", lex), 2)
    r = narrow(meds, anchors)
    assert r.remaining == 1 and r.candidates[0].name.startswith("Torasemide")       # blue is ignored
    assert r.box_mode and r.overridden_anchor_ids == [anchors[0].id]


def test_next_question_prefers_box_when_possible_or_needed(session, today):
    meds = pipeline.resolve_patient(session, _muller(session).id, today)
    anchors = _numbered(extract("the white ones"), 1)
    assert narrow(meds, anchors).question.attribute == "score_line"                 # 2 with a line, 2 without
    assert narrow(meds, anchors, box_available=True).question.attribute == "box"
    twins = [meds[1], meds[1].model_copy(update={"prescription_id": 999})]
    q = narrow(twins, anchors).question
    assert q.attribute == "box" and q.text_en == "Can you read me the name on the box?"
    assert narrow(meds, _numbered(extract("the green one"), 1)).remaining == 0


def test_removing_an_anchor_widens_the_list(session):
    pid = _muller(session).id
    state = calls.start(session, pid)
    state = calls.add_utterance(session, state.id, "the yellow one")
    assert state.narrowing.remaining == 2 and state.anchors[0].source == "rule"
    state = calls.add_utterance(session, state.id, "it is round")
    assert state.narrowing.sequence == [8, 2, 1]
    state = calls.remove_anchor(session, state.id, state.anchors[0].id)
    assert state.narrowing.remaining == 6
    with pytest.raises(ValueError):
        calls.add_utterance(session, state.id, "   ")
    with pytest.raises(LookupError):
        calls.remove_anchor(session, state.id, "a99")


class _FakeBedrock:
    def __init__(self, text=None, error=None, delay=0.0):
        self.text, self.error, self.delay, self.sent = text, error, delay, []

    def converse(self, **kwargs):
        self.sent.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def test_llm_anchors_are_validated_merged_and_labelled(session):
    reply = json.dumps({"anchors": [
        {"facet": "color", "value": "gelblich", "negated": False, "quantity": None},
        {"facet": "shape", "value": "round"},
        {"facet": "color", "value": "turquoise"},                 # outside the vocabulary: dropped
        {"facet": "dose", "value": "take two"},                   # not a facet: dropped
        {"facet": "purpose", "value": "Herz"}]})
    client = _FakeBedrock("Here you go: " + reply)
    result = llm_extractor.extract_merged("the yellowish one for my ticker", client=client, enabled=True)
    assert result.llm_used and not result.fell_back
    by_key = {(a.facet, a.value): a.source for a in result.anchors.items}
    assert by_key == {("color", "yellow"): "rule", ("shape", "round"): "AI", ("purpose", "heart"): "AI"}


def test_llm_fallback_on_error_invalid_output_and_timeout(monkeypatch):
    text = "the small white one"
    rule = _pairs(extract(text))
    for client in (_FakeBedrock(error=RuntimeError("network down")), _FakeBedrock("sorry, I cannot"),
                   _FakeBedrock('{"anchors": "nope"}')):
        result = llm_extractor.extract_merged(text, client=client, enabled=True)
        assert result.fell_back and not result.llm_used and _pairs(result.anchors) == rule
    monkeypatch.setattr(llm_extractor, "TIMEOUT_SECONDS", 0.2)
    slow = llm_extractor.extract_merged(text, client=_FakeBedrock('{"anchors": []}', delay=0.6), enabled=True)
    assert slow.fell_back and _pairs(slow.anchors) == rule
    off = llm_extractor.extract_merged(text, client=_FakeBedrock(error=RuntimeError("must not be called")))
    assert not off.fell_back and not off.llm_used                # flag is off by default


def test_text_is_deidentified_before_it_is_sent(session):
    patient = _muller(session)
    born = patient.birth_date
    said = (f"Hier ist Karl Müller, geboren am {born.day:02d}.{born.month:02d}.{born.year}, Musterweg 12 in Erlangen, "
            f"Telefon 09131 5550101. Meine Frau Erika Beispiel sagt, die gelbe Tablette.")
    client = _FakeBedrock('{"anchors": []}')
    llm_extractor.extract_merged(said, patient=patient, client=client, enabled=True)
    sent = client.sent[0]["messages"][0]["content"][0]["text"]
    for secret in ("Müller", "Karl", str(born.year), "Musterweg", "5550101", "Beispiel"):
        assert secret not in sent
    assert "gelbe Tablette" in sent
    assert Anchor(facet="color", value="yellow").label == "yellow"
