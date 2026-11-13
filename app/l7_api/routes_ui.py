"""Pages and live-update partials for the four tabs."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session

from app import db
from app.demo import scenario, simulator
from app.l1_data import adapters
from app.l3_resolve import pipeline
from app.l4_insight import actions
from app.l6_outputs import impact
from app.l7_api import views
from app.l7_api.common import Live, templates, wants_html
from app.l7_api.routes_api import impact_result

router = APIRouter()


@router.get("/")
def home():
    return RedirectResponse("/consult")


@router.get("/consult")
def consult(request: Request, patient_id: int = 1, session_id: Optional[int] = None, launched: int = 0,
            session: Session = Depends(db.get_session)):
    ctx = views.consult(session, patient_id, session_id)
    return templates.TemplateResponse(request, "consult.html", {**ctx, "tab": "consult", "launched": bool(launched)})


@router.get("/host")
def host(request: Request, patient_id: int = 1, session: Session = Depends(db.get_session)):
    """A generic mock of the practice software MedSync would open from. Not a real product."""
    return templates.TemplateResponse(request, "host.html", {**views.host(session, patient_id), "tab": ""})


@router.get("/ui/launch-context")
def launch_context(request: Request, patient_id: int = 1, session: Session = Depends(db.get_session)):
    import json
    from app.l7_api.routes_api import fhir
    bundle = fhir(patient_id, session)
    context = {"launch": "illustrative-demo-launch", "patient": f"Patient/medsync-{patient_id}",
               "encounter": "Encounter/demo-phone-consultation", "practitioner": "Practitioner/demo-hf-nurse"}
    return templates.TemplateResponse(request, "_launch_context.html", {
        "context": json.dumps(context, indent=2), "entries": len(bundle["entry"]),
        "bundle": json.dumps({**bundle, "entry": bundle["entry"][:2]}, indent=2, ensure_ascii=False)})


@router.get("/how-we-work")
def how_we_work(request: Request, session: Session = Depends(db.get_session)):
    return templates.TemplateResponse(request, "how_we_work.html", {**views.story(session), "tab": "how"})


@router.get("/ui/poll")
def poll(request: Request, patient_id: int = 1, v: int = 0, session_id: str = "",
         session: Session = Depends(db.get_session)):
    """Open Consult pages ask once a second. Nothing is sent unless something changed."""
    if v == Live.version:
        return Response(status_code=204)
    call_id = int(session_id) if session_id.isdigit() else None
    ctx = views.consult(session, patient_id, call_id)
    return templates.TemplateResponse(request, "_poll.html", {**ctx, "message": Live.message})


@router.get("/explorer")
def explorer(request: Request, insurer_id: Optional[int] = None, substance_id: Optional[int] = None,
             q: str = "", session: Session = Depends(db.get_session)):
    data = views.explorer(session, insurer_id, substance_id)
    if not wants_html(request):
        return data
    ctx = {"x": data, "insurers": adapters.list_insurers(session), "substances": adapters.list_substances(session),
           "q": q, "tab": "explorer"}
    return templates.TemplateResponse(request, "explorer.html", ctx)


@router.get("/explorer/search")
def explorer_search(request: Request, q: str = "", insurer_id: Optional[int] = None,
                    session: Session = Depends(db.get_session)):
    hits = pipeline.find_substances(session, q) if q.strip() else []
    return templates.TemplateResponse(request, "_explorer_suggest.html",
                                      {"hits": hits, "q": q, "insurer_id": insurer_id})


def _sim_context(session: Session) -> dict:
    ctx = views.consult(session, scenario.DEMO_PATIENT_ID)
    ctx["log"] = actions.audit_entries(session)[:5]
    return ctx


@router.get("/simulator")
def simulator_page(request: Request, session: Session = Depends(db.get_session)):
    return templates.TemplateResponse(request, "simulator.html",
                                      {**_sim_context(session), "sim_actions": simulator.ACTIONS, "tab": "simulator"})


@router.get("/ui/sim-preview")
def sim_preview(request: Request, v: int = 0, session: Session = Depends(db.get_session)):
    if v == Live.version:
        return Response(status_code=204)
    return templates.TemplateResponse(request, "_sim_preview.html", {**_sim_context(session), "changed": True})


@router.get("/impact")
def impact_page(request: Request):
    result = impact_result(request)
    if not wants_html(request):
        return result
    name = "_impact_result.html" if request.headers.get("hx-request") else "impact.html"
    from app.l6_outputs import evidence
    return templates.TemplateResponse(request, name, {"r": result, "fields": impact.Assumptions.model_fields,
                                                      "tab": "impact", "evidence": evidence})


@router.get("/demo/scenario")
def demo_scenario():
    return {"steps": scenario.STEPS, "total_seconds": scenario.TOTAL_SECONDS,
            "patient_id": scenario.DEMO_PATIENT_ID}
