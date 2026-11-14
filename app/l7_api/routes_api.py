"""Data routes. Thin: each one calls a lower layer and returns typed JSON or an HTMX partial."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlmodel import Session

from app import config, db
from app.demo import simulator
from app.l1_data import adapters
from app.l1_data.models import Prescription
from app.l3_resolve import pipeline
from app.l4_insight import actions
from app.l5_conversation import session as calls
from app.l6_outputs import fhir_export, patient_key
from app.l7_api import views
from app.l7_api.common import Live, payload, templates, truthy, wants_html
from app.l7_api.schemas import ActionResult, Health

router = APIRouter()


def _int(value, what: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Please give a valid {what}.") from None


def _require_patient(session: Session, patient_id: int):
    patient = adapters.get_patient(session, patient_id)
    if patient is None:
        raise LookupError(f"There is no patient with number {patient_id}.")
    return patient


@router.get("/health", response_model=Health)
def health():
    return Health(today=config.today(), llm_extractor=config.use_llm())


@router.get("/patients")
def patients(session: Session = Depends(db.get_session)):
    today = config.today()
    return [views.patient_out(session, p, today) for p in adapters.list_patients(session)]


@router.get("/patients/{patient_id}/medications")
def medications(patient_id: int, request: Request, session_id: Optional[int] = None,
                session: Session = Depends(db.get_session)):
    if wants_html(request):
        return templates.TemplateResponse(request, "_cards.html", views.consult(session, patient_id, session_id))
    _require_patient(session, patient_id)
    return pipeline.resolve_patient(session, patient_id, config.today())


@router.get("/patients/{patient_id}/recommendations")
def recommendations(patient_id: int, request: Request, session: Session = Depends(db.get_session)):
    if wants_html(request):
        return templates.TemplateResponse(request, "_warnings.html", views.consult(session, patient_id))
    _require_patient(session, patient_id)
    return actions.recommendations_for(session, patient_id, config.today())


@router.post("/recommendations/{rec_id}/respond")
async def respond(rec_id: str, request: Request, session: Session = Depends(db.get_session)):
    data = await payload(request)
    patient_id = _int(data.get("patient_id"), "patient")
    _require_patient(session, patient_id)
    accepted = truthy(data.get("accepted", "false"))
    actions.respond(session, patient_id, rec_id, accepted)
    if wants_html(request):
        return templates.TemplateResponse(request, "_warnings.html", views.consult(session, patient_id))
    return ActionResult(message="Noted in the audit trail." if accepted else "Dismissed and noted in the audit trail.")


# Call sessions --------------------------------------------------------------------------------
def _copilot(request: Request, session: Session, state) -> Response:
    if not wants_html(request):
        return state
    ctx = views.consult(session, state.patient_id, state.id)
    response = templates.TemplateResponse(request, "_copilot_response.html", ctx)
    response.headers["HX-Replace-Url"] = f"/consult?patient_id={state.patient_id}&session_id={state.id}"
    return response


@router.post("/sessions")
async def start_session(request: Request, session: Session = Depends(db.get_session)):
    data = await payload(request)
    return _copilot(request, session, calls.start(session, _int(data.get("patient_id"), "patient")))


@router.post("/sessions/{call_id}/utterance")
async def utterance(call_id: int, request: Request, session: Session = Depends(db.get_session)):
    data = await payload(request)
    state = calls.add_utterance(session, call_id, str(data.get("text", "")), str(data.get("lang", "auto")))
    return _copilot(request, session, state)


@router.delete("/sessions/{call_id}/anchors/{anchor_id}")
def delete_anchor(call_id: int, anchor_id: str, request: Request, session: Session = Depends(db.get_session)):
    return _copilot(request, session, calls.remove_anchor(session, call_id, anchor_id))


@router.post("/sessions/{call_id}/box")
async def box_available(call_id: int, request: Request, session: Session = Depends(db.get_session)):
    data = await payload(request)
    return _copilot(request, session, calls.set_box_available(session, call_id, truthy(data.get("available", ""))))


# Prescriptions --------------------------------------------------------------------------------
@router.get("/prescriptions/{prescription_id}/trail")
def trail(prescription_id: int, request: Request, session: Session = Depends(db.get_session)):
    out, med = views.trail(session, prescription_id)
    if wants_html(request):
        return templates.TemplateResponse(request, "_trail.html", {"trail": out, "med": med, "res": out.resolution})
    return out


@router.post("/prescriptions/{prescription_id}/override-product")
async def override_product(prescription_id: int, request: Request, session: Session = Depends(db.get_session)):
    data = await payload(request)
    raw = data.get("product_id")
    product_id = None if raw in (None, "", "clear") else _int(raw, "product")
    rx = actions.override_product(session, prescription_id, product_id)
    Live.bump("Product selection recorded." if product_id else "Manual selection removed.")
    if wants_html(request):
        out, med = views.trail(session, rx.id)
        return templates.TemplateResponse(request, "_trail.html", {"trail": out, "med": med, "res": out.resolution})
    return ActionResult(message=Live.message)


@router.post("/prescriptions/{prescription_id}/confirm")
def confirm(prescription_id: int, request: Request, session: Session = Depends(db.get_session)):
    """The clinician's click: 'I confirmed this tablet with the patient'. Recorded in the audit trail."""
    rx = actions.confirm_product(session, prescription_id)
    Live.bump("Confirmed with patient. Recorded in the audit trail.")
    if not wants_html(request):
        return ActionResult(message=Live.message)
    call_id = request.query_params.get("session_id", "")
    if call_id.isdigit():
        return templates.TemplateResponse(request, "_copilot_response.html",
                                          views.consult(session, rx.patient_id, int(call_id)))
    out, med = views.trail(session, rx.id)
    return templates.TemplateResponse(request, "_trail.html", {"trail": out, "med": med, "res": out.resolution})


@router.post("/prescriptions/{prescription_id}/instruction")
async def instruction(prescription_id: int, request: Request, session: Session = Depends(db.get_session)):
    """Record an instruction the clinician has decided on, and run the split check. Never suggests a dose."""
    if session.get(Prescription, prescription_id) is None:
        raise LookupError("That prescription does not exist.")
    data = await payload(request)
    confirm = truthy(data.get("confirm", "false"))
    result = actions.record_instruction(session, prescription_id, str(data.get("text", "")), confirm)
    if confirm:
        Live.bump("Instruction recorded in the audit trail.")
    if wants_html(request):
        response = templates.TemplateResponse(request, "_instruction_preview.html", {"preview": result})
        if confirm:
            response.headers["HX-Trigger"] = "close-modal"
        return response
    return result


# Patient key ----------------------------------------------------------------------------------
@router.get("/patients/{patient_id}/key.pdf")
def key_pdf(patient_id: int, lang: str = "en", session: Session = Depends(db.get_session)):
    key = patient_key.build_key(session, patient_id, lang)
    pdf = patient_key.render_pdf(key)
    patient_key.record_issue(session, patient_id, key.lang)
    Live.bump("Patient key issued.")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="medsync-key-{patient_id}-{key.lang}.pdf"'})


@router.get("/patients/{patient_id}/key.txt", response_class=PlainTextResponse)
def key_txt(patient_id: int, lang: str = "en", session: Session = Depends(db.get_session)):
    return PlainTextResponse(patient_key.render_text(patient_key.build_key(session, patient_id, lang)),
                             media_type="text/plain; charset=utf-8")


@router.get("/patients/{patient_id}/key.html")
def key_html(patient_id: int, request: Request, lang: str = "en", session: Session = Depends(db.get_session)):
    key = patient_key.build_key(session, patient_id, lang)
    return templates.TemplateResponse(request, "_key_preview.html", {"key": key, "t": key.text})


# Simulator, FHIR -------- -------------------------------------------------------------------------
@router.post("/simulator/{action}")
def simulate(action: str, request: Request, session: Session = Depends(db.get_session)):
    message = simulator.run(session, action)
    Live.bump(message)
    if wants_html(request):
        return templates.TemplateResponse(request, "_toast.html", {"message": message})
    return ActionResult(message=message)


@router.get("/fhir/MedicationStatement")
def fhir(patient_id: int = 1, session: Session = Depends(db.get_session)):
    _require_patient(session, patient_id)
    today = config.today()
    statements = [fhir_export.medication_statement(m, adapters.get_substance(session, m.substance_id).atc_code, today)
                  for m in pipeline.resolve_patient(session, patient_id, today)]
    return fhir_export.bundle(statements)
