from sqlmodel import select

from app.l1_data import adapters
from app.l1_data.models import DispensingEvent, KeyIssue, Prescription, Product, Substance
from app.l3_resolve import pipeline
from app.l6_outputs import fhir_export, impact, patient_key


def test_keys_generate_for_all_patients_in_both_languages(session, today):
    for patient in adapters.list_patients(session):
        for lang in ("de", "en"):
            key = patient_key.build_key(session, patient.id, lang, today)
            pdf = patient_key.render_pdf(key)
            assert pdf[:5] == b"%PDF-" and len(pdf) > 3000
            assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type /Page>") <= 1
            text = patient_key.render_text(key)
            assert patient.name in text and "SYNTHETIC DEMO DATA" in text
            assert len(key.rows) == len(adapters.prescriptions_for(session, patient.id))


def test_text_key_has_expected_names_times_and_changes(session, today):
    de = patient_key.render_text(patient_key.build_key(session, 1, "de", today))
    for expected in ("Metoprololsuccinat 47,5 mg", "Für das Herz", "morgens: 1, abends: ½", "Levothyroxin 75 µg",
                     "Wassertablette", "Was ist neu".upper(), "Torasemid",
                     "Gleiches Medikament, neues Aussehen – nicht beide einnehmen."):
        assert expected in de
    en = patient_key.render_text(patient_key.build_key(session, 1, "en", today))
    for expected in ("Metoprolol succinate 47.5 mg", "For your heart", "morning: 1, evening: ½", "noon: 1",
                     "Same medicine, new look – do not take both."):
        assert expected in en


def test_half_pill_and_whats_new_follow_a_substitution(session, today):
    key = patient_key.build_key(session, 1, "de", today)
    assert key.rows[0].show_half and key.rows[0].half_svg.startswith("<svg")
    assert [c.name for c in key.changes] == ["Torasemid"]
    rx = session.exec(select(Prescription).where(Prescription.patient_id == 1)).first()
    orange = session.exec(select(Product).where(Product.imprint == "RG")).one()
    session.add(DispensingEvent(patient_id=1, prescription_id=rx.id, product_id=orange.id, dispensed_at=today,
                                reason="shortage_substitution"))
    session.commit()
    key = patient_key.build_key(session, 1, "de", today)
    assert [c.name for c in key.changes] == ["Metoprololsuccinat", "Torasemid"]
    assert not key.rows[0].show_half                       # the new product must not be split
    assert patient_key.render_pdf(key)[:5] == b"%PDF-"
    before = len(session.exec(select(KeyIssue)).all())
    patient_key.record_issue(session, 1, "de")
    assert len(session.exec(select(KeyIssue)).all()) == before + 1


def test_fhir_statement_carries_the_pzn(session, today):
    med = pipeline.resolve_patient(session, 1, today)[0]
    atc = session.get(Substance, med.substance_id).atc_code
    st = fhir_export.medication_statement(med, atc, today)
    assert st["resourceType"] == "MedicationStatement"
    coding = st["contained"][0]["code"]["coding"][0]
    assert coding["system"].endswith("/pzn") and coding["code"] == med.resolution.product.pzn
    assert fhir_export.bundle([st])["entry"][0]["resource"]["id"] == st["id"]


def test_impact_changes_with_assumptions():
    base = impact.compute(impact.Assumptions())
    assert base.minutes_saved_per_week == 187              # 36 calls x 4 min + 5.4 callbacks x 8 min
    assert base.callbacks_avoided_per_week == 5.4
    more = impact.compute(impact.Assumptions(calls_per_week=240))
    assert more.minutes_saved_per_week == 2 * base.minutes_saved_per_week
    none = impact.compute(impact.Assumptions(minutes_with=6.0, callback_share_with=0.25))
    assert none.minutes_saved_per_week == 0
    assert base.label == "Modelled from stated assumptions, not measured outcomes"
    assert len(base.pilot_metrics) == 5
