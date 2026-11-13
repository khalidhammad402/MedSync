import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402

from app.demo import scenario  # noqa: E402
from app.main import app  # noqa: E402

JSON = {"accept": "application/json"}
HTML = {"accept": "text/html"}
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client():
    with TestClient(app) as c:        # startup resets the demo data
        yield c


def test_smoke_every_route(client):
    assert client.get("/health").json()["status"] == "ok"
    patients = client.get("/patients").json()
    assert [p["name"] for p in patients] == ["Herr Müller", "Frau Schneider", "Herr Yilmaz"]

    meds = client.get("/patients/1/medications", headers=JSON).json()
    assert len(meds) == 8 and [s["stage"] for s in meds[0]["resolution"]["stages"]] == [1, 2, 3, 4, 5]
    recs = client.get("/patients/1/recommendations", headers=JSON).json()
    assert {r["rule"] for r in recs} == {"R1", "R2", "R3", "R6", "R8"}

    call = client.post("/sessions", json={"patient_id": 1}, headers=JSON).json()
    state = client.post(f"/sessions/{call['id']}/utterance", json={"text": "the yellow round one"}, headers=JSON).json()
    assert state["narrowing"]["remaining"] == 1 and len(state["anchors"]) == 2
    anchor = state["anchors"][0]["id"]
    state = client.delete(f"/sessions/{call['id']}/anchors/{anchor}", headers=JSON).json()
    assert len(state["anchors"]) == 1
    assert client.post(f"/sessions/{call['id']}/box", json={"available": "1"}, headers=JSON).json()[
        "narrowing"]["question"]["attribute"] == "box"

    trail = client.get("/prescriptions/1/trail", headers=JSON).json()
    assert trail["headline"].startswith("Predicted from insurer contract")
    result = client.post("/prescriptions/5/instruction", json={"text": "1-0-½"}, headers=JSON).json()
    assert result["saved"] is False and result["split"]["ok"] is False
    result = client.post("/prescriptions/5/instruction", json={"text": "1-0-½", "confirm": "true"}, headers=JSON).json()
    assert result["saved"] is True
    ibuprofen = client.get("/patients/3/medications", headers=JSON).json()[4]
    option = ibuprofen["resolution"]["manual_options"][0]["product_id"]
    rx = ibuprofen["prescription_id"]
    assert client.post(f"/prescriptions/{rx}/override-product", json={"product_id": option}, headers=JSON).json()["ok"]
    assert client.post("/recommendations/R8-key/respond", json={"patient_id": 1, "accepted": "false"},
                       headers=JSON).status_code == 200

    pdf = client.get("/patients/1/key.pdf?lang=en")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:5] == b"%PDF-"
    assert "Metoprololsuccinat" in client.get("/patients/1/key.txt").text
    assert client.get("/explorer", headers=JSON).json()["periods"]
    assert client.get("/impact", headers=JSON).json()["minutes_saved_per_week"] == 187
    assert client.get("/impact?calls_per_week=240", headers=JSON).json()["minutes_saved_per_week"] == 374
    bundle = client.get("/fhir/MedicationStatement").json()
    assert bundle["resourceType"] == "Bundle" and len(bundle["entry"]) == 8
    for action in ("shortage_substitution", "contract_rotates", "contract_expires", "reset"):
        assert client.post(f"/simulator/{action}", headers=JSON).json()["ok"] is True
    assert len(client.get("/demo/scenario").json()["steps"]) == 8


def test_every_tab_and_partial_renders_with_the_footer(client):
    for url in ("/consult", "/consult?patient_id=2", "/consult?patient_id=3", "/explorer", "/explorer?insurer_id=3&substance_id=9",
                "/explorer?substance_id=12", "/simulator", "/impact"):
        page = client.get(url, headers=HTML)
        assert page.status_code == 200, url
        assert "SYNTHETIC DEMO DATA – NOT FOR CLINICAL USE" in page.text
        assert page.text.count('class="tab ') == 4                       # four tabs only
        assert "Traceback" not in page.text
    hx = {"hx-request": "true"}
    for url in ("/patients/1/medications", "/patients/1/recommendations", "/prescriptions/1/trail",
                "/prescriptions/1/instruction-form", "/patients/1/key.html", "/explorer/search?q=cardimet",
                "/ui/poll?patient_id=1&v=0", "/ui/sim-preview?v=0"):
        assert client.get(url, headers=hx).status_code == 200, url
    assert "Records your decision. MedSync does not suggest doses." in client.get(
        "/prescriptions/1/instruction-form", headers=hx).text
    assert client.get("/", follow_redirects=False).status_code in (302, 307)


def test_live_update_reaches_open_consult_pages(client):
    page = client.get("/consult", headers=HTML).text
    version = int(page.split('id="poll-v" name="v" value="')[1].split('"')[0])
    assert client.get(f"/ui/poll?patient_id=1&v={version}").status_code == 204       # nothing changed
    client.post("/simulator/shortage_substitution", headers=JSON)
    update = client.get(f"/ui/poll?patient_id=1&v={version}")
    assert update.status_code == 200
    assert "Confirmed by dispensing record" in update.text and "Possible double pack" in update.text
    assert "Split instruction not possible – new product must not be split" in update.text


def test_errors_are_clear_json_without_stack_traces(client):
    unknown = client.get("/patients/999/medications", headers=JSON)
    assert unknown.status_code == 404 and unknown.json()["error"] == "not_found" and "999" in unknown.json()["message"]
    assert client.get("/patients/999/key.pdf").status_code == 404
    call = client.post("/sessions", json={"patient_id": 1}, headers=JSON).json()
    empty = client.post(f"/sessions/{call['id']}/utterance", json={"text": "  "}, headers=JSON)
    assert empty.status_code == 422 and empty.json()["error"] == "invalid_input"
    bad = client.post("/prescriptions/1/override-product", json={"product_id": 30}, headers=JSON)     # another medicine
    assert bad.status_code == 422 and "not the same medicine" in bad.json()["message"]
    assert client.post("/prescriptions/1/override-product", json={"product_id": "abc"}, headers=JSON).status_code == 422
    assert client.post("/simulator/explode", headers=JSON).status_code == 404
    assert client.post("/sessions", json={"patient_id": 999}, headers=JSON).status_code == 404
    assert client.get("/impact?calls_per_week=-5", headers=JSON).status_code == 422
    friendly = client.get("/consult?patient_id=999", headers=HTML)
    assert friendly.status_code == 404 and "That did not work" in friendly.text and "Traceback" not in friendly.text
    for response in (unknown, empty, bad):
        assert "Traceback" not in response.text and set(response.json()) == {"error", "message"}


def test_demo_scenario_is_repeatable_and_short(client):
    first = scenario.run_headless(client)
    second = scenario.run_headless(client)
    assert first == second
    assert first["total_seconds"] <= 135                                  # under 2 min 15 s
    steps = first["steps"]
    assert steps[1]["sequence"] == [8, 7]
    assert steps[2]["sequence"] == [8, 7, 2, 1]
    assert steps[2]["questions"][0] == "Does the tablet have a line across the middle?"
    assert steps[2]["matched"] == ["Metoprolol succinate 47.5 mg"]
    assert steps[3]["trail_stages"] == ["insurer", "drug", "contract", "product", "appearance"]
    assert steps[3]["metoprolol"] == ["Predicted from insurer contract", "white"]
    assert steps[5]["metoprolol"] == ["Confirmed by dispensing record", "orange"]
    assert steps[5]["top_warnings"] == ["Possible double pack – Metoprolol succinate",
                                        "Split instruction not possible – new product must not be split"]
    assert steps[6]["key_has_new_box"] is True
    assert steps[7]["minutes_saved"] == 187


BANNED = ("100%", "guaranteed", "proves")


def test_no_overclaiming_words_anywhere(client):
    texts = {}
    for folder, patterns in (("app/l8_ui/templates", ["*.html"]), ("app/l8_ui/static", ["app.js", "styles.css"]),
                             ("docs", ["*.md"]), (".", ["README.md"]), ("app", ["**/*.py"])):
        for pattern in patterns:
            for path in (ROOT / folder).glob(pattern):
                texts[str(path)] = path.read_text(encoding="utf-8")
    for url in ("/consult", "/explorer", "/simulator", "/impact"):
        texts[url] = client.get(url, headers=HTML).text
    for url in ("/patients/1/key.txt", "/patients/1/key.txt?lang=en", "/patients/1/key.html"):
        texts[url] = client.get(url).text
    for url in ("/patients/1/medications", "/patients/1/recommendations", "/prescriptions/1/trail", "/impact"):
        texts[url] = client.get(url, headers=JSON).text
    assert len(texts) > 40
    for name, text in texts.items():
        lowered = text.lower()
        for word in BANNED:
            if word == "100%" and name.endswith((".css", ".js")):
                continue                      # CSS lengths such as a full-width bar are layout, not claims
            lowered_check = lowered
            assert word not in lowered_check, f"“{word}” found in {name}"
