from datetime import timedelta

from sqlmodel import select

from app.l1_data import adapters
from app.l1_data.models import (Contract, DispensingEvent, Patient, Prescription, Product, Shortage,
                                Substance)
from app.l3_resolve import explain, pipeline


def _rx(session, patient_name, inn_prefix):
    patient = session.exec(select(Patient).where(Patient.name == patient_name)).one()
    sub = session.exec(select(Substance).where(Substance.inn_name.startswith(inn_prefix))).one()
    rx = session.exec(select(Prescription).where(Prescription.patient_id == patient.id,
                                                 Prescription.substance_id == sub.id)).one()
    return patient, rx


def _resolve(session, patient_name, inn_prefix, today):
    patient, rx = _rx(session, patient_name, inn_prefix)
    return pipeline.resolve(rx, patient, today, adapters.mock_sources(session))


def _product(session, imprint, color):
    return session.exec(select(Product).where(Product.imprint == imprint, Product.color == color)).first()


def test_rule_a_recent_dispensing_is_ground_truth(session, today):
    res = _resolve(session, "Herr Karl Müller", "Dapagliflozin", today)
    assert res.confidence == "Confirmed by dispensing record"
    assert res.product.color == "white"


def test_rule_b_aut_idem_uses_prescribed_product_not_contract(session, today):
    res = _resolve(session, "Herr Karl Müller", "Levothyroxine", today)
    assert res.confidence == "Confirmed by prescription"
    assert res.product.color == "pink"            # contract product would be white
    assert res.next_products == []


def test_rule_c_single_contract_product_is_prediction(session, today):
    res = _resolve(session, "Herr Karl Müller", "Metoprolol", today)   # last dispensing is older than 120 days
    assert res.confidence == "Predicted from insurer contract"
    assert res.product.imprint == "M47" and res.product.divisible_parts == 2


def test_rule_c_multi_product_contract_gives_candidates(session, today):
    res = _resolve(session, "Frau Helga Schneider", "Spironolactone", today)
    assert res.product is None and len(res.candidates) == 2
    assert res.confidence == "Predicted – one of 2 possible"
    assert res.manual_override_allowed
    assert res.stages[3].status == "warning" and res.stages[4].status == "warning"


def test_rule_d_unresolved_offers_same_substance_only(session, today):
    res = _resolve(session, "Herr Mehmet Yilmaz", "Ibuprofen", today)
    assert res.confidence == "Unresolved" and res.product is None and res.candidates == []
    assert res.manual_override_allowed
    assert len(res.manual_options) == 2
    assert {o.substance_id for o in res.manual_options} == {res.substance_id}


def test_dispensing_overrides_conflicting_contract(session, today):
    patient, rx = _rx(session, "Herr Karl Müller", "Metoprolol")
    other = _product(session, "RG", "orange")
    session.add(DispensingEvent(patient_id=patient.id, prescription_id=rx.id, product_id=other.id,
                                dispensed_at=today, reason="shortage_substitution"))
    session.commit()
    res = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert res.confidence == "Confirmed by dispensing record"
    assert res.product.product_id == other.id
    assert res.stages[3].evidence.get("conflict_with_contract") is True
    assert res.previous_product.imprint == "M47" and res.switch_reason == "shortage_substitution"


def test_expired_contract_fails_stage_three_but_dispensing_still_wins(session, today):
    res = _resolve(session, "Herr Mehmet Yilmaz", "Atorvastatin", today)
    assert res.stages[2].status == "failed" and "expired" in res.stages[2].detail
    assert res.confidence == "Confirmed by dispensing record"


def test_expired_contract_without_dispensing_is_unresolved(session, today):
    patient, rx = _rx(session, "Herr Mehmet Yilmaz", "Atorvastatin")
    for ev in session.exec(select(DispensingEvent).where(DispensingEvent.prescription_id == rx.id)).all():
        session.delete(ev)
    session.commit()
    res = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert res.confidence == "Unresolved"


def test_soon_expiring_contract_reports_next_product(session, today):
    res = _resolve(session, "Herr Karl Müller", "Ramipril", today)
    assert res.stages[2].status == "warning"
    assert res.days_until_rotation == 20
    assert res.rotation_date == today + timedelta(days=21)
    assert res.next_products and res.next_products[0].color != res.product.color


def test_aut_idem_plus_shortage_warns_but_never_changes_result(session, today):
    patient, rx = _rx(session, "Herr Karl Müller", "Levothyroxine")
    before = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    session.add(Shortage(substance_id=rx.substance_id, strength=rx.strength,
                         active_from=today - timedelta(days=2), active_to=today + timedelta(days=20)))
    session.commit()
    after = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert after.product.product_id == before.product.product_id
    assert after.confidence == "Confirmed by prescription"
    assert after.shortage_active and after.manual_override_allowed
    assert any("shortage" in w.lower() for w in after.warnings)


def test_strength_mismatch_fails_drug_stage(session, today):
    patient, rx = _rx(session, "Herr Karl Müller", "Ramipril")
    rx.strength = "7.5 mg"
    session.add(rx)
    session.commit()
    res = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert res.stages[1].status == "failed"
    assert res.confidence == "Unresolved"
    assert any("7.5 mg" in w for w in res.warnings)


def test_missing_insurer_fails_stage_one_and_skips_contract(session, today):
    patient, rx = _rx(session, "Herr Karl Müller", "Ramipril")
    patient.insurer_id = None
    session.add(patient)
    session.commit()
    res = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert res.stages[0].status == "failed" and res.stages[2].status == "failed"
    assert res.confidence == "Unresolved"
    # a dispensing record still resolves without an insurer
    _, rx2 = _rx(session, "Herr Karl Müller", "Apixaban")
    assert pipeline.resolve(rx2, patient, today, adapters.mock_sources(session)).confidence_code == "dispensing"


def test_manual_override_wins_and_is_labelled(session, today):
    patient, rx = _rx(session, "Herr Mehmet Yilmaz", "Ibuprofen")
    option = pipeline.resolve(rx, patient, today, adapters.mock_sources(session)).manual_options[0]
    rx.override_product_id = option.product_id
    session.add(rx)
    session.commit()
    res = pipeline.resolve(rx, patient, today, adapters.mock_sources(session))
    assert res.confidence == "Confirmed with patient" and res.product.product_id == option.product_id


def test_stage_order_is_always_one_to_five(session, today):
    for patient in adapters.list_patients(session):
        for med in pipeline.resolve_patient(session, patient.id, today):
            assert [s.stage for s in med.resolution.stages] == [1, 2, 3, 4, 5]
            assert [s.name for s in med.resolution.stages] == ["insurer", "drug", "contract", "product", "appearance"]
            assert all(s.status in ("ok", "warning", "failed") for s in med.resolution.stages)


def test_recorded_contract_switch_is_visible(session, today):
    res = _resolve(session, "Herr Karl Müller", "Torasemide", today)
    assert res.switch_reason == "contract_switch"
    assert res.switch_date == today - timedelta(days=30)
    assert res.previous_product.shape == "oblong" and res.product.shape == "round"


def test_different_insurers_resolve_to_different_products(session, today):
    a = _resolve(session, "Herr Karl Müller", "Metoprolol", today)
    b = _resolve(session, "Frau Helga Schneider", "Metoprolol", today)
    assert a.product.product_id != b.product.product_id


def test_explanation_is_plain_and_short(session, today):
    res = _resolve(session, "Herr Karl Müller", "Torasemide", today)
    text = explain.explain(res)
    assert "TK" in text and "Torasemide" in text
    assert len(text.split()) < 130
    assert len(explain.explain_lines(res)) >= 5
    assert explain.headline(res).startswith("Confirmed by dispensing record")


def test_find_substance_by_brand_alias(session):
    assert pipeline.find_substances(session, "cardimet")[0].inn_name.startswith("Metoprolol")
    assert pipeline.find_substances(session, "Torasemid")[0].inn_name == "Torasemide"
    assert session.exec(select(Contract)).first() is not None
