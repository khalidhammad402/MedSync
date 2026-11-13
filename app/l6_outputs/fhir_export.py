"""A FHIR-shaped MedicationStatement, to show the data model is ready for ePA / eMP integration.

Shape only: there is no profile validation here.
"""
from __future__ import annotations

from datetime import date

from app.l3_resolve.pipeline import PatientMedication

PZN_SYSTEM = "http://fhir.de/CodeSystem/ifa/pzn"
ATC_SYSTEM = "http://fhir.de/CodeSystem/bfarm/atc"


def medication_statement(med: PatientMedication, atc_code: str, today: date) -> dict:
    res = med.resolution
    codings = [{"system": ATC_SYSTEM, "code": atc_code, "display": med.substance_name}]
    if res.product:
        codings.insert(0, {"system": PZN_SYSTEM, "code": res.product.pzn, "display": res.product.name})
    return {
        "resourceType": "MedicationStatement",
        "id": f"medsync-rx-{med.prescription_id}",
        "meta": {"tag": [{"system": "https://example.org/medsync", "code": "synthetic-demo-data"}]},
        "status": "active",
        "contained": [{
            "resourceType": "Medication",
            "id": "med",
            "code": {"coding": codings, "text": f"{med.substance_name} {med.strength}"},
            "form": {"text": res.product.form if res.product else "unknown"},
        }],
        "medicationReference": {"reference": "#med"},
        "subject": {"reference": f"Patient/medsync-{med.patient_id}"},
        "dateAsserted": today.isoformat(),
        "dosage": [{"text": med.instruction_text, "timing": {"code": {"text": ", ".join(med.times)}}}],
        "note": [{"text": f"Product identification: {res.confidence}. Synthetic demo data."}],
    }


def bundle(statements: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": s} for s in statements]}
