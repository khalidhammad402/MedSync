"""The scripted demo on Herr Müller. One definition drives both the browser and the headless test.

Actions are small verbs. The browser (static/app.js) performs them on the real UI; `run_headless`
performs the same verbs over HTTP so the scenario can be checked without a browser.
"""
from __future__ import annotations

from typing import Any

DEMO_PATIENT_ID = 1
SAY_1 = "Ich nehme drei weiße Tabletten, eine blaue und zwei gelbe."
SAY_2 = "Is that the one for the heart or the yellow one?"
SAY_3 = "Ja, mit einer Kerbe in der Mitte."

STEPS: list[dict[str, Any]] = [
    {"n": 1, "page": "consult", "seconds": 10, "title": "Eight medicines, as pictures",
     "say": "Herr Müller, 82, takes eight medicines. Four are small white tablets: the look-alike group is outlined.",
     "actions": [{"do": "spotlight", "sel": ".card.lookalike"}]},
    {"n": 2, "page": "consult", "seconds": 20, "title": "The patient describes the tablets",
     "say": "The clinician types what the patient says. Anchors appear and the list narrows.",
     "actions": [{"do": "start_call"}, {"do": "utter", "text": SAY_1}]},
    {"n": 3, "page": "consult", "seconds": 20, "title": "“The one for the heart?”",
     "say": "Two white heart tablets remain. MedSync suggests the best next question: the line across the tablet.",
     "actions": [{"do": "utter", "text": SAY_2}, {"do": "spotlight", "sel": "#next-question"},
                 {"do": "wait", "ms": 7000}, {"do": "utter", "text": SAY_3}]},
    {"n": 4, "page": "consult", "seconds": 15, "title": "How do we know?",
     "say": "Every result has a plain-language trail: insurer, drug, contract, product, appearance.",
     "actions": [{"do": "open_trail", "prescription_id": 1}]},
    {"n": 5, "page": "simulator", "seconds": 10, "title": "The pharmacy substitutes",
     "say": "Metoprolol is short, so the pharmacy hands over another product. Watch the picture change.",
     "actions": [{"do": "wait", "ms": 1500}, {"do": "simulate", "action": "shortage_substitution"}]},
    {"n": 5, "page": "consult", "seconds": 15, "title": "Two warnings, straight away",
     "say": "Confirmed by dispensing record. Possible double pack, and the new tablet must not be split.",
     "actions": [{"do": "spotlight", "sel": "#card-1, #warnings .rec.important"}]},
    {"n": 6, "page": "consult", "seconds": 15, "title": "The patient key",
     "say": "A large-print picture key for the patient: same medicine, new look, do not take both.",
     "actions": [{"do": "open_key", "lang": "de"}]},
    {"n": 7, "page": "impact", "seconds": 15, "title": "Measurable value",
     "say": "Modelled minutes saved per week, and the pilot metrics that would replace the assumptions.",
     "actions": []},
]
TOTAL_SECONDS = sum(s["seconds"] for s in STEPS)


def run_headless(client: Any) -> dict:
    """Play the scenario over HTTP (after a reset) and return a summary of what the audience would see."""
    json_h = {"accept": "application/json"}
    assert client.post("/simulator/reset", headers=json_h).status_code == 200
    summary: dict[str, Any] = {"steps": []}
    call_id = None
    for step in STEPS:
        page = client.get(f"/{step['page']}", params={"patient_id": DEMO_PATIENT_ID})
        assert page.status_code == 200, step["title"]
        seen: dict[str, Any] = {"n": step["n"], "title": step["title"]}
        for action in step["actions"]:
            if action["do"] == "start_call":
                call_id = client.post("/sessions", data={"patient_id": DEMO_PATIENT_ID}, headers=json_h).json()["id"]
            elif action["do"] == "utter":
                state = client.post(f"/sessions/{call_id}/utterance", data={"text": action["text"]},
                                    headers=json_h).json()
                seen["sequence"] = state["narrowing"]["sequence"]
                seen["anchors"] = [f'{a["facet"]}={a["value"]}' for a in state["anchors"]]
                question = state["narrowing"]["question"]
                seen.setdefault("questions", []).append(question["text_en"] if question else None)
                seen["matched"] = [c["name"] for c in state["narrowing"]["candidates"] if c["matched"]]
            elif action["do"] == "open_trail":
                trail = client.get(f"/prescriptions/{action['prescription_id']}/trail", headers=json_h).json()
                seen["trail_stages"] = [s["name"] for s in trail["resolution"]["stages"]]
                seen["confidence_before"] = trail["resolution"]["confidence"]
            elif action["do"] == "simulate":
                seen["message"] = client.post(f"/simulator/{action['action']}", headers=json_h).json()["message"]
            elif action["do"] == "open_key":
                key = client.get(f"/patients/{DEMO_PATIENT_ID}/key.txt", params={"lang": action["lang"]})
                seen["key_has_new_box"] = "WAS IST NEU" in key.text and "nicht beide einnehmen" in key.text
        if step["page"] == "consult":
            meds = client.get(f"/patients/{DEMO_PATIENT_ID}/medications", headers=json_h).json()
            recs = client.get(f"/patients/{DEMO_PATIENT_ID}/recommendations", headers=json_h).json()
            seen["metoprolol"] = [meds[0]["resolution"]["confidence"], meds[0]["resolution"]["product"]["color"]]
            seen["top_warnings"] = [r["title"] for r in recs[:2]]
        if step["page"] == "impact":
            seen["minutes_saved"] = client.get("/impact", headers=json_h).json()["minutes_saved_per_week"]
        summary["steps"].append(seen)
    summary["total_seconds"] = TOTAL_SECONDS
    return summary
