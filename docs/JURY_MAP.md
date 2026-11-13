# Jury criteria mapped to MedSync

| # | Criterion | Features | Demo moment | Evidence in the repo |
|---|---|---|---|---|
| 1 | **Challenge fit and impact** – solves a real problem, shows measurable value | Picture-based medicine list; narrowing from the patient's own words; warnings for switches, double packs and tablets that cannot be split; large-print patient key; impact model with pilot metrics | Step 2 (the organizers' sentence, typed in German), step 5 (substitution raises two warnings), step 7 (minutes saved, labelled as modelled) | `app/l5_conversation/`, `app/l4_insight/recommend.py`, `app/l6_outputs/impact.py`, `tests/test_l5_conversation.py` (organizer dialogues), `docs/screens/impact.png` |
| 2 | **Feasibility and integration** – realistic, compatible with real systems | Four adapters naming the real system categories (eML in the ePA, article master data with rebate flags, appearance database, shortage feeds); dispensing records override prediction; FHIR-shaped export with PZN; runs offline with one command | Step 4 (the trail shows each data source in order), step 5 (a dispensing record overrides the contract) | `app/l1_data/adapters.py`, `app/l3_resolve/pipeline.py`, `app/l6_outputs/fhir_export.py`, `GET /fhir/MedicationStatement`, `docs/LIMITATIONS.md` (integration path) |
| 3 | **Innovation and creativity** – original or technology-driven | The clinician-side copilot: best next question chosen by the most even split; look-alike groups with the smallest separating attribute set; split check re-run after every switch; optional Claude extractor with validation and silent fallback | Step 3 (next-question bubble: "Does the tablet have a line across the middle?"), step 5 ("new product must not be split") | `app/l5_conversation/narrowing.py`, `app/l4_insight/clusters.py`, `app/l5_conversation/llm_extractor.py`, `tests/test_l4_insight.py` |
| 4 | **User-centric design** – intuitive, safe, accepted | Patient installs nothing; four tabs; pill pictures as the hero; severity shown by colour, icon and text; every result has a confidence label and a "How do we know?" trail; anchors removable; "Records your decision. MedSync does not suggest doses."; audit trail; keyboard operable with visible focus | Step 1 (the screen is readable without explanation), step 4 (trail), step 6 (patient key with "Same medicine, new look – do not take both.") | `app/l8_ui/templates/`, `app/l8_ui/static/styles.css`, `app/l6_outputs/patient_key.py`, `docs/screens/consult.png`, `tests/test_l7_api.py` (footer and wording checks) |
| 5 | **Teamwork and presentation** – clear, confident, coordinated | Scripted two-minute demo with a narrator bar and Pause/Next/Back; speaker roles; 30-second fallback; honest Q&A sheet | The whole run: `python run.py demo` | `docs/PITCH.md`, `docs/JUDGE_QA.md`, `app/demo/scenario.py`, `tests/test_l7_api.py::test_demo_scenario_is_repeatable_and_short` |

## One sentence per criterion, for the closing slide

1. A nurse and an 82-year-old finally talk about the same tablet, and the clinic gets time back.
2. Four small adapters stand where the ePA medication list, contract data, an appearance database and
   shortage feeds would plug in.
3. The tool does not identify pills from photos; it tells the clinician which question to ask next.
4. Nothing for the patient to install, nothing the clinician has to take on trust.
5. A two-minute demo that runs the same way every time.

## Added in the refinement round

| # | Criterion | New feature | Where to see it |
|---|---|---|---|
| 1 | Challenge fit and impact | Clinical Evidence section with what each study found and what it does not show | Impact tab, below the modelled numbers; `app/l6_outputs/evidence.py` |
| 2 | Feasibility and integration | Mock practice-software screen with a launch button, launch-context drawer with FHIR-shaped data, and the "How We Work" tab | `/host`, `/consult?patient_id=1&launched=1`, `/how-we-work` |
| 3 | Innovation and creativity | The Extract, Transform, Load loop with real seed values, and "one prescription, two insurers, two tablets" | How We Work tab |
| 4 | User-centric design | One attention badge used everywhere (three shapes, not colour alone) with a legend; the nurse's "Confirmed with patient" click that flips the label | Consult tab; demo step 3 |
| 5 | Teamwork and presentation | The opening now starts on the text-only host screen; the tagline "Prescribed by name. Dispensed by contract. Described by color." | `docs/PITCH.md` |
