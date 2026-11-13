# Assumptions and choices

Where the specification was silent, the simplest option that keeps the live demo reliable was chosen.

## Tooling

- `make` is not installed on the build machine, so `run.py` provides `setup`, `run`, `test`, `demo` and
  `reset` instead of a Makefile.
- `htmx.min.js` (version 1.9.12) is stored in `app/l8_ui/static/`. Nothing is loaded from a CDN at runtime.
- `boto3` is not in `requirements.txt`. It is only needed when the AI extractor is switched on.

## Data

- Dates in the seed are relative to "today", so the demo looks the same whichever day it runs. Set
  `MEDSYNC_TODAY=YYYY-MM-DD` to freeze the date for a rehearsal.
- Every start of the app restores the demo data. A prototype that always starts clean is safer on stage
  than one that remembers yesterday's rehearsal.
- All names are invented: insurers ("Kasse Nord" …), manufacturers ("Nordlicht Generika" …) and brand
  aliases ("Cardimet" …). Any resemblance to a real product is unintended. PZNs lie in 99900000–99999999.
- Each substance has one strength. Two extra fields were added to the tables: `substance.aliases` and
  `substance.purpose_key`, plus `prescription.override_product_id` for the manual selection.
- Herr Müller's eight medicines: four small white round tablets (metoprolol, dapagliflozin, torasemide,
  ramipril), one blue (apixaban), two yellow (spironolactone, pantoprazole), and pink levothyroxine with the
  aut-idem exclusion. His metoprolol record is older than 120 days, so it starts as a prediction and becomes
  "Confirmed by dispensing record" when the simulator substitutes it.
- Dapagliflozin is labelled "for your heart", because that is how it is explained to a heart-failure patient.
- The OTC painkiller (ibuprofen) has no rebate contract, so it shows as "Unresolved" with a neutral
  "OTC · confirm with patient" badge. MedSync gives no clinical judgement about it.

## Resolution (Layer 3)

- A manual selection by the clinician wins over everything else and gets its own label, "Selected manually
  by clinician". This is a sixth label next to the five in the specification.
- A "switch" is a dispensing record whose product differs from the previous dispensing record.
- The manual selector is unlocked when the result is unresolved, has several candidates, or a shortage is active.

## Warnings (Layer 4)

- R2 (recent switch) is shown as "info" because R3 (possible double pack) already covers the first 90 days.
- R4 (shortage) stops once a pack has been dispensed after the shortage began: the substitution has happened.
- Look-alike groups only include medicines whose product is known. Score lines count as "has a line" whether
  functional or decorative, because a patient cannot see the difference.
- The minimal separating set prefers attributes that are easy to say on the phone: time of day, score line,
  size, purpose, imprint.
- The "What is new" box on the patient key lists switches from the last 90 days.

## Conversation (Layer 5)

- Anchors of the same kind are alternatives ("white or blue or yellow"); different kinds must all hold
  ("heart" and one of those colours). Box anchors override everything else.
- On the demo patient the narrowing runs 8 → 7 → 2 → 1 rather than the 8 → 4 → 1 of the specification's
  example. The numbers are what the seeded data honestly gives.
- "Prefer asking for the box" is implemented two ways: a tick box "Patient has the boxes at hand" makes the
  box question the first choice, and the box question is also used whenever no visual attribute separates the
  remaining medicines. Without either, the most even visual split is asked first. Demo step 3 needs this,
  because it expects the score-line question.
- When the patient gives a count ("three white") and the list has a different number, MedSync says so.
- Cards glow once three or fewer medicines remain; before that, non-matching cards dim.
- De-identification also hides long digit runs, so a PZN is never sent to the model. The rule-based parser
  reads PZNs locally.

## Outputs, API and UI

- The key preview in the app is an HTML rendering of the same data as the PDF. It is more reliable on a
  projector than an embedded PDF viewer. "Open PDF" produces the real one-page A4 file and records the issue.
- On the PDF, text that does not fit is shortened with an ellipsis rather than shrunk below 18 pt. The night
  column is only printed when a medicine uses it.
- Routes return JSON to API clients and HTML to browsers and HTMX. Extra routes beyond the minimum list:
  `/prescriptions/{id}/trail`, `/prescriptions/{id}/instruction-form`, `/recommendations/{id}/respond`,
  `/sessions/{id}/box`, `/patients/{id}/key.html`, `/explorer/search`, `/ui/poll`, `/ui/sim-preview`,
  `/demo/scenario`.
- Live updates use a change counter in memory. Open pages ask once a second and receive nothing unless
  something changed. This suits one process on one laptop.
- The risk badge is hidden for the green tier to keep cards calm.
- The Simulator tab has a live view of the demo patient, so the picture change is visible next to the button.

## Demo

- The seven steps are stored as eight entries, because step 5 spans two screens (Simulator, then Consult).
- Step 5 returns to a fresh Consult view: after the substitution the tablet no longer matches what the
  patient described earlier, and an all-dimmed screen would distract from the two warnings.
- Step 3 adds the patient's answer ("Ja, mit einer Kerbe in der Mitte.") so that one card is left glowing.
- The impact model assumes 46 working weeks a year.

## Refinement round

- Scope was trimmed on purpose: no German translation of the UI, no new web font, no browser-automation test.
  The patient key stays bilingual.
- The practice-software mock is a separate page (`/host`) with a launch button, instead of a sliding panel
  around Consult. The scripted demo and its screen layout are untouched; Consult opened with `?launched=1`
  shows a slim launch strip.
- There are now five tabs. The original "at most four" rule was relaxed for the "How We Work" story page.
- "Selected manually by clinician" was renamed to "Confirmed with patient". It covers both the new one-click
  confirmation and picking a product by hand after the patient reads the box.
- A substitution recorded by the simulator clears an earlier confirmation, because a newer pack supersedes it.
- The green tier is now shown on cards as "Lower attention". Warning severity (Important, Attention, Info)
  keeps its own colours and is a separate concept from the attention tier of a medicine.
- "Verordnet am" on the host table comes from a new seeded field, `prescription.prescribed_on`.
- The How We Work page shows "Kasse Nord" and "Kasse Süd", not a real insurer, and says the medication plan
  and Telematikinfrastruktur data "would provide" the inputs, because nothing is connected.
- The evidence-order strip shows the engine's real order: confirmed with patient, dispensing record, aut-idem,
  contract.
- The evidence footer does not say "verified" for all references: only the second could be checked online.
- Demo steps 6 and 7 were shortened by 1 and 3 seconds to leave a margin under 2 min 15 s.
- Two agent skills were installed into `.claude/skills/` at the owner's request (frontend-design,
  web-design-guidelines). They are development aids and are not part of the app.

## Redesign round

- The look changed to flat cards with fine borders on a light canvas. The font stack asks for Inter or Geist
  first and falls back to the system font, because no font file is bundled and the app must run offline.
- The Impact tab, its route and the Clinical Evidence section were removed. The calculation module
  (`app/l6_outputs/impact.py`) and the reference list (`evidence.py`) remain in the code but are not shown.
- "Change instruction" was removed from the cards together with its window. The API route that records an
  instruction still exists; the split check after a substitution does not depend on the window.
- The demo now has six steps (seven entries) and ends on the patient key.
- The Explorer lists six real insurer names as examples (TK, BARMER, DAK-Gesundheit, Debeka, DKV, Allianz),
  at the owner's request. They are display names for the Explorer only; a note on the screen says the
  contracts are invented. Two fictional insurers ("Kasse Mitte", "Kasse Küste") were added to the seed to
  back the last two. Consult, How We Work and the simulator keep the fictional names.
- How We Work was cut to three short sections. The loop diagram, the evidence-order strip and the
  side-by-side contrast were removed.
- Consult shows three cards per row at 1440 px wide.
