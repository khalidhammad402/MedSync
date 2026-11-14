"""Tests for the refinement round: demo contract, risk badge, nurse confirmation, host page, story, evidence."""
import json
import re
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient  # noqa: E402

from app.l7_api.common import templates  # noqa: E402
from app.main import app  # noqa: E402

JSON = {"accept": "application/json"}
HTML = {"accept": "text/html"}
HX = {"hx-request": "true"}
SELECTORS = json.loads((Path(__file__).parent / "fixtures" / "demo_selectors.json").read_text(encoding="utf-8"))
SAY = ["I take three white tablets, one blue and two yellow ones.", "Is that the one for the heart or the yellow one?",
       "Yes, with a line across the middle."]


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _assert_present(html, spec, where):
    for element_id in spec["ids"]:
        assert f'id="{element_id}"' in html, f"#{element_id} is missing on {where}"
    for cls in spec["classes"]:
        assert re.search(rf'class="[^"]*\b{re.escape(cls)}\b', html), f".{cls} is missing on {where}"


def test_demo_selectors_are_still_present(client):
    _assert_present(client.get("/consult?patient_id=1", headers=HTML).text, SELECTORS["consult"], "Consult")
    call = client.post("/sessions", data={"patient_id": 1}, headers=HX)
    _assert_present(call.text, {"ids": ["utterance-input"], "classes": ["copilot"]}, "copilot after Start call")
    call_id = int(call.headers["hx-replace-url"].split("session_id=")[1])
    html = ""
    for sentence in SAY[:2]:
        html = client.post(f"/sessions/{call_id}/utterance", data={"text": sentence}, headers=HX).text
    _assert_present(html, SELECTORS["consult_in_call"], "copilot during a call")
    html = client.post(f"/sessions/{call_id}/utterance", data={"text": SAY[2]}, headers=HX).text
    _assert_present(html, SELECTORS["consult_one_left"], "copilot with one medicine left")
    client.post("/simulator/shortage_substitution", headers=JSON)
    _assert_present(client.get("/simulator", headers=HTML).text, SELECTORS["simulator"], "Simulator")
    _assert_present(client.get("/patients/1/key.html", headers=HX).text, SELECTORS["key_preview"], "key preview")


def test_nurse_confirmation_flips_predicted_to_confirmed(client):
    call_id = client.post("/sessions", data={"patient_id": 1}, headers=JSON).json()["id"]
    for sentence in SAY:
        client.post(f"/sessions/{call_id}/utterance", data={"text": sentence}, headers=JSON)
    before = client.get("/patients/1/medications", headers=JSON).json()[0]["resolution"]
    assert before["confidence"] == "Predicted from insurer contract"
    page = client.get(f"/consult?patient_id=1&session_id={call_id}", headers=HTML).text
    assert 'id="confirm-identity"' in page and "You decide." in page

    after_click = client.post(f"/prescriptions/1/confirm?session_id={call_id}", headers=HX).text
    assert 'id="identity-confirmed"' in after_click and 'id="confirm-identity"' not in after_click
    assert "badge conf manual" in after_click                      # the card is re-sent with the green label
    after = client.get("/patients/1/medications", headers=JSON).json()[0]["resolution"]
    assert after["confidence"] == "Confirmed with patient" and after["product"]["pzn"] == before["product"]["pzn"]

    # a newer pack from the pharmacy supersedes the earlier confirmation
    client.post("/simulator/shortage_substitution", headers=JSON)
    newer = client.get("/patients/1/medications", headers=JSON).json()[0]["resolution"]
    assert newer["confidence"] == "Confirmed by dispensing record" and newer["product"]["color"] == "orange"
    # nothing to confirm when the product is not known
    assert client.post("/prescriptions/19/confirm", headers=JSON).status_code == 422


def test_one_risk_badge_for_all_three_tiers():
    macro = templates.env.get_template("_macros.html").module
    expected = {"red": ("High attention", "rb-mark"), "amber": ("Medium attention", "rb-mark"),
                "green": ("Lower attention", "rb-check")}
    icons = set()
    for tier, (label, mark) in expected.items():
        html = str(macro.risk_badge(tier))
        assert f"risk-badge risk-{tier}" in html and label in html and mark in html
        assert 'aria-hidden="true"' in html and "not a clinical safety rating" in html
        icons.add(re.search(r'<path d="([^"]+)"|<circle', html).group(0))
    assert len(icons) == 3                                         # three different shapes, not colour alone
    assert "Safe" not in str(macro.risk_badge("green"))
    legend = str(macro.risk_legend())
    assert legend.count("risk-badge") == 3


def test_old_risk_markup_is_gone_and_badge_is_used(client):
    ui = Path(__file__).resolve().parent.parent / "app" / "l8_ui"
    for path in list((ui / "templates").glob("*.html")) + [ui / "static" / "styles.css"]:
        assert 'class="badge risk' not in path.read_text(encoding="utf-8"), path.name
        assert ".badge.risk" not in path.read_text(encoding="utf-8"), path.name
    consult = client.get("/consult?patient_id=1", headers=HTML).text
    assert consult.count("risk-badge risk-") == 8 + 3              # one per card plus the legend
    panel = client.get("/prescriptions/1/trail", headers=HX).text
    assert "risk-badge risk-" in panel and "How do we know?" not in panel
    assert "risk-badge risk-" in client.get("/explorer", headers=HTML).text


def test_navigation_order_on_every_page(client):
    for url in ("/consult", "/explorer", "/simulator", "/how-we-work"):
        page = client.get(url, headers=HTML).text
        labels = re.findall(r'<a class="tab [^>]*>([^<]+)</a>', page)
        assert labels == ["Consult", "Explorer", "How We Work", "Simulator"], url
        assert page.count('aria-current="page"') == 1, url
        assert "SYNTHETIC DEMO DATA – NOT FOR CLINICAL USE" in page


def test_mock_host_table_matches_the_prescriptions(client):
    host = client.get("/host?patient_id=1", headers=HTML).text
    meds = client.get("/patients/1/medications", headers=JSON).json()
    assert host.count("<tr><td>") == len(meds) == 8
    for med in meds:
        assert med["substance_name"] in host and med["instruction_text"] in host
    for text in ("Practice Software (Demo)", "Launch MedSync VisualID", 'id="launch-medsync"',
                 "Static text view: shows what was prescribed, not what the patient holds.",
                 "Mock host for demonstration. Not a real practice-software product.",
                 "SYNTHETIC DEMO DATA – NOT FOR CLINICAL USE"):
        assert text in host
    assert "<svg" not in host                                      # text only, no pictures
    assert 'href="/consult?patient_id=1&launched=1"' in host

    launched = client.get("/consult?patient_id=1&launched=1", headers=HTML).text
    assert 'id="launch-strip"' in launched and "Show launch context" in launched
    assert 'id="launch-strip"' not in client.get("/consult?patient_id=1", headers=HTML).text
    drawer = client.get("/ui/launch-context?patient_id=1", headers=HX).text
    assert "MedicationStatement" in drawer and "Illustrative only" in drawer


def test_how_we_work_is_short_and_uses_real_seed_values(client):
    page = client.get("/how-we-work", headers=HTML).text
    for text in ("Prescribed by name. Dispensed by contract. Described by color.", "Metoprolol succinate", "TK",
                 "BARMER", "The GP prescribes", "The pharmacy dispenses", "The patient describes",
                 "What is simulated here", "no integration exists", "Extract", "Transform", "Load",
                 "Zero friction communication.", "Contract data source: simulated in this prototype"):
        assert text in page, text
    pzns = re.findall(r"PZN (\d{8})", page)
    assert len(set(pzns)) >= 2 and all(99900000 <= int(p) <= 99999999 for p in pzns)
    assert page.count("<section") == 4 and page.count('class="loop-node') == 3   # short page plus the cycle diagram
    for href in ('href="/host?patient_id=1"', 'href="/explorer?insurer_id=1&substance_id=1"', 'href="/consult?patient_id=1&open=key"'):
        assert href in page
    assert "Kasse" not in page and "Rabattvertrag" not in page       # English only, listed insurers only


def test_explorer_lists_the_six_example_insurers(client):
    page = client.get("/explorer", headers=HTML).text
    for name in ("Techniker Krankenkasse (TK)", "BARMER", "DAK-Gesundheit", "Debeka", "DKV", "Allianz"):
        assert f">{name}</a>" in page, name
    assert "Kasse" not in page and "invented demo data" in page
    consult = client.get("/consult?patient_id=1", headers=HTML).text
    assert "Herr Karl Müller" in consult and "TK" in consult and "Kasse" not in consult
    assert "lang=de" not in consult                                 # the app opens the patient key in English
    for insurer_id in range(1, 7):
        assert client.get(f"/explorer?insurer_id={insurer_id}", headers=JSON).json()["periods"]


def test_pages_load_nothing_from_other_hosts(client):
    allowed = ("https://doi.org/",)                                # reference links: optional, only work online
    for url in ("/consult", "/explorer", "/simulator", "/how-we-work", "/host"):
        page = client.get(url, headers=HTML).text
        for found in re.findall(r'(?:src|href)="(https?://[^"]+)"', page):
            assert found.startswith(allowed), f"{url} points to {found}"
        assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)="https?://', page), url
