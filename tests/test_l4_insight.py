from datetime import timedelta

import pytest
from sqlmodel import select

from app.l1_data.models import AuditLog, DispensingEvent, KeyIssue, Patient, Prescription, Product, Substance
from app.l3_resolve import pipeline
from app.l4_insight import actions, clusters
from app.l4_insight.recommend import recommend, required_parts, split_check


def _pid(session, name):
    return session.exec(select(Patient).where(Patient.name == name)).one().id


def _rx(session, patient_id, inn_prefix):
    sub = session.exec(select(Substance).where(Substance.inn_name.startswith(inn_prefix))).one()
    return session.exec(select(Prescription).where(Prescription.patient_id == patient_id,
                                                   Prescription.substance_id == sub.id)).one()


def _rules(recs):
    return {r.rule for r in recs}


def _substitute_metoprolol(session, today):
    pid = _pid(session, "Herr Karl Müller")
    rx = _rx(session, pid, "Metoprolol")
    orange = session.exec(select(Product).where(Product.imprint == "RG")).one()
    session.add(DispensingEvent(patient_id=pid, prescription_id=rx.id, product_id=orange.id,
                                dispensed_at=today, reason="shortage_substitution"))
    session.commit()
    return pid, rx


def test_white_look_alike_group_with_minimal_separators(session, today):
    meds = pipeline.resolve_patient(session, _pid(session, "Herr Karl Müller"), today)
    found = clusters.find_clusters(meds)
    assert len(found) == 1
    c = found[0]
    assert (c.color, c.shape, len(c.members)) == ("white", "round", 4)
    assert c.separable and c.separating_attributes == ["time of day", "score line"]
    assert "Tell them apart by time of day and score line" in c.hint


def test_inseparable_pair_is_stated_plainly(session, today):
    meds = pipeline.resolve_patient(session, _pid(session, "Herr Karl Müller"), today)
    a, b = meds[1].model_copy(deep=True), meds[1].model_copy(deep=True)   # two identical tablets
    b.prescription_id, b.substance_name = 999, "Twin medicine"
    c = clusters.find_clusters([a, b])[0]
    assert not c.separable and c.separating_attributes == []
    assert "cannot be told apart by appearance" in c.hint and "read the box or blister" in c.hint


def test_baseline_rules_for_demo_patient(session, today):
    pid = _pid(session, "Herr Karl Müller")
    recs = actions.recommendations_for(session, pid, today)
    assert _rules(recs) == {"R1", "R2", "R3", "R6", "R8"}
    r1 = next(r for r in recs if r.rule == "R1")
    assert "Ramipril" in r1.title and "20 days" in r1.why
    r3 = next(r for r in recs if r.rule == "R3")
    assert "Torasemide" in r3.title and r3.severity == "attention"      # amber-tier drug


def test_rules_do_not_fire_without_cause(session, today):
    recs = actions.recommendations_for(session, _pid(session, "Frau Helga Schneider"), today)
    assert "R1" not in _rules(recs) and "R2" not in _rules(recs) and "R3" not in _rules(recs)
    assert "R7" not in _rules(recs) and "R8" not in _rules(recs)
    yilmaz = actions.recommendations_for(session, _pid(session, "Herr Mehmet Yilmaz"), today)
    assert "R6" not in _rules(yilmaz)                 # three yellow tablets, but three different shapes


def test_r4_shortage_and_r5_candidates_and_unresolved(session, today):
    schneider = actions.recommendations_for(session, _pid(session, "Frau Helga Schneider"), today)
    assert any(r.rule == "R4" and "Atorvastatin" in r.title for r in schneider)
    assert any(r.rule == "R5" and "Spironolactone" in r.title and "2 products" in r.why for r in schneider)
    yilmaz = actions.recommendations_for(session, _pid(session, "Herr Mehmet Yilmaz"), today)
    assert sum(1 for r in yilmaz if r.rule == "R5") == 2                # ibuprofen unresolved, pantoprazole 1 of 2
    muller = actions.recommendations_for(session, _pid(session, "Herr Karl Müller"), today)
    assert "R4" not in _rules(muller) and "R5" not in _rules(muller)


def test_substitution_triggers_double_pack_and_split_warning(session, today):
    pid, rx = _substitute_metoprolol(session, today)
    recs = actions.recommendations_for(session, pid, today)
    top = recs[:2]
    assert {r.rule for r in top} == {"R7", "R3"} and all(r.severity == "important" for r in top)
    r7 = next(r for r in recs if r.rule == "R7")
    assert r7.title == "Split instruction not possible – new product must not be split"
    assert "decorative" in r7.why
    assert any(r.id == f"R3-{rx.id}" and r.title.startswith("Possible double pack") for r in recs)


def test_r3_stops_after_90_days_but_r2_stays(session, today):
    pid = _pid(session, "Herr Karl Müller")
    rx = _rx(session, pid, "Torasemide")
    ev = session.exec(select(DispensingEvent).where(DispensingEvent.prescription_id == rx.id,
                                                    DispensingEvent.reason == "contract_switch")).one()
    ev.dispensed_at = today - timedelta(days=100)
    first = session.exec(select(DispensingEvent).where(DispensingEvent.prescription_id == rx.id,
                                                       DispensingEvent.reason == "normal")).one()
    first.dispensed_at = today - timedelta(days=200)
    session.add(ev)
    session.add(first)
    session.commit()
    recs = actions.recommendations_for(session, pid, today)
    assert any(r.id == f"R2-{rx.id}" for r in recs) and not any(r.id == f"R3-{rx.id}" for r in recs)


def test_r8_clears_when_a_new_key_is_issued(session, today):
    pid = _pid(session, "Herr Karl Müller")
    assert "R8" in _rules(actions.recommendations_for(session, pid, today))
    session.add(KeyIssue(patient_id=pid, issued_at=today, lang="de"))
    session.commit()
    assert "R8" not in _rules(actions.recommendations_for(session, pid, today))


def test_ordering_is_severity_then_recency(session, today):
    pid, _ = _substitute_metoprolol(session, today)
    recs = actions.recommendations_for(session, pid, today)
    ranks = [{"important": 0, "attention": 1, "info": 2}[r.severity] for r in recs]
    assert ranks == sorted(ranks)
    for a, b in zip(recs, recs[1:]):
        if a.severity == b.severity:
            assert a.sort_days <= b.sort_days
    infos = [r for r in recs if r.rule == "R2"]
    assert infos[0].sort_days == 0 and infos[1].sort_days == 30       # newest switch first


def test_dismissal_hides_and_is_audited(session, today):
    pid = _pid(session, "Herr Karl Müller")
    target = actions.recommendations_for(session, pid, today)[0]
    actions.respond(session, pid, target.id, accepted=False)
    assert target.id not in {r.id for r in actions.recommendations_for(session, pid, today)}
    actions.respond(session, pid, "R8-key", accepted=True)
    logged = {(a.action, a.ref) for a in session.exec(select(AuditLog)).all()}
    assert ("recommendation_dismissed", target.id) in logged and ("recommendation_accepted", "R8-key") in logged


@pytest.mark.parametrize("text,parts", [("1-0-½", 2), ("1/2 tablet in the evening", 2), ("eine halbe Tablette", 2),
                                        ("half a tablet", 2), ("0,5-0-0", 2), ("¼ Tablette", 4), ("1-0-1", None),
                                        ("1 tablet when needed", None)])
def test_fraction_detection(text, parts):
    assert required_parts(text) == parts


def test_split_check_and_instruction_recording(session, today):
    pid = _pid(session, "Herr Karl Müller")
    rx = _rx(session, pid, "Apixaban")                                  # blue tablet, must not be split
    preview = actions.record_instruction(session, rx.id, "1-0-½", confirm=False)
    assert preview.split.needs_split and not preview.split.ok and not preview.saved
    assert session.get(Prescription, rx.id).instruction_text == "1-0-1"
    assert preview.key_line_de == "morgens: 1, abends: ½"
    saved = actions.record_instruction(session, rx.id, "1-0-½", confirm=True)
    assert saved.saved and session.get(Prescription, rx.id).instruction_text == "1-0-½"
    assert any(r.rule == "R7" and r.prescription_id == rx.id for r in actions.recommendations_for(session, pid, today))
    assert any(a.action == "instruction_recorded" for a in session.exec(select(AuditLog)).all())
    meto = pipeline.resolve_patient(session, pid, today)[0]
    assert split_check("1-0-½", meto.resolution.appearances).ok
    with pytest.raises(ValueError):
        actions.record_instruction(session, rx.id, "   ", confirm=True)


def test_override_rejects_other_medicines(session, today):
    pid = _pid(session, "Herr Mehmet Yilmaz")
    rx = _rx(session, pid, "Ibuprofen")
    wrong = session.exec(select(Product).where(Product.imprint == "M47")).one()
    with pytest.raises(ValueError):
        actions.override_product(session, rx.id, wrong.id)
    right = session.exec(select(Product).where(Product.imprint == "IBU")).one()
    actions.override_product(session, rx.id, right.id)
    med = [m for m in pipeline.resolve_patient(session, pid, today) if m.prescription_id == rx.id][0]
    assert med.resolution.confidence_code == "manual"
