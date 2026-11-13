# Limitations

MedSync is a hackathon prototype. It shows that the idea works end to end on mock data. It is not ready
for patients.

## What is simulated

| Component | In the prototype | In reality |
|---|---|---|
| Appearance data | 33 invented products, pictures drawn in code | A licensed drug appearance database |
| Rebate contracts | Invented contracts for four invented insurers | Rebate flags in pharmacy article master data |
| Dispensing feed | Rows in a local table | Dispensing data in the electronic medication list (eML) of the ePA |
| Shortages | Rows in a local table, or a simulator button | Official and wholesaler shortage feeds |
| Conversation input | Typed or pasted text | The clinician typing during a call; no microphone |
| Patients | Three invented people | Real records, with consent and access control |
| Impact numbers | Not shown; nothing has been measured | Measured in a pilot |

## What production needs

- A licence for a drug appearance database, and a check of how complete and current it is.
- Access to the ePA through the Telematikinfrastruktur, with the required authorisation and certification.
- Interface details verified against the current gematik specifications. Nothing here was tested against them.
- A regulatory assessment of medical-device status before any clinical use.
- A data protection impact assessment, including the optional AI extractor.
- Clinical validation: does it shorten calls and reduce mix-ups without introducing new errors?
- Real authentication, roles and a tamper-evident audit trail. The prototype has none of these.

## Honest failure modes

- **Weekly dispensers.** Once tablets leave the box, the box name and PZN are gone. Only appearance is left,
  and that is the weakest anchor.
- **Blister repacking.** A pharmacy or care service that repacks tablets breaks the link between pack and tablet.
- **Old packs at home.** After a switch, the patient may hold two different-looking packs of the same
  medicine. MedSync warns about this but cannot see into the cupboard.
- **Look-alikes that cannot be separated.** Two small white round tablets without a marking look the same.
  MedSync says so and asks for the box instead of guessing.
- **Inconsistent colour descriptions.** One person's "yellow" is another's "beige". Lighting and eyesight matter.
  A wrong colour can filter out the right medicine; every anchor can be removed with one click.
- **Multi-partner contracts.** When a contract has several partners, the exact product is uncertain until a
  dispensing record or the box confirms it. MedSync shows "one of N possible".
- **Missing or late dispensing data.** A prediction from a contract can be wrong if the pharmacy substituted
  and the record has not arrived.
- **The parser.** The rule-based parser knows a fixed vocabulary. Dialect, unusual wording or typing errors
  can be missed. Nothing is applied silently: every anchor is shown and removable.
- **The AI option.** De-identification of free text is not perfect, and model replies can be wrong. Replies
  are restricted to the vocabulary, but a valid-looking wrong anchor is possible.

## Production integration path (a design direction, not built)

The four adapters in `app/l1_data/adapters.py` are the seams. In a real deployment each would read from a
separate system: eML dispensing data, pharmacy article master data with rebate flags, a licensed appearance
database, and shortage feeds. These systems have different owners and cannot simply be copied into one
database. A federated query layer, for example Exasol virtual schemas, could join them in place at query time
without copying patient data. This is a design direction only. None of it is built or tested here, and no
vendor is integrated.

## Scope limits by design

- MedSync never suggests a dose or a dose change. It records an instruction the clinician has already
  decided on and checks whether the tablet in hand can be split that way.
- Every result is a best estimate with a confidence label and a visible trail. The clinician confirms with
  the patient before acting.

## Added in the refinement round

- **The host shell is a mock.** `/host` imitates a generic, dated practice-software screen. It is not a real
  product, no vendor is involved, and nothing is integrated.
- **The launch context is illustrative.** The Patient, Encounter and Practitioner values and the FHIR-shaped
  data show what a host could hand over. No launch protocol is implemented or tested.
- **The evidence is associational and from the US.** The main study links appearance changes with people
  stopping their medicine after a heart attack; it does not show cause and is not about heart failure or
  Germany. Only one of the three references was checked against the publisher's page during the build.
- **The contract data source is unverified.** Where a production system would get rebate-contract markers,
  and under which licence, has not been confirmed.
- **"Confirmed with patient" records a click.** It documents what the clinician says they checked. It does not
  verify anything by itself.
