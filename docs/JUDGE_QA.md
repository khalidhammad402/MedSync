# Likely jury questions

Short, honest answers. Where the answer is "we have not built that", say so.

**What if the pharmacy substituted a product?**
That is the case MedSync is built around. A dispensing record always overrides the contract prediction. The
card switches to "Confirmed by dispensing record", shows the old picture next to the new one, and raises two
checks: possible double pack at home, and whether the instruction can still be carried out (for example
half a tablet). If the dispensing record has not arrived yet, the prediction can be wrong; the label says
"Predicted", and the patient reading the box settles it.

**What if the pills are in a weekly dispenser?**
Then the box and its name are gone and only appearance is left. MedSync still helps with pictures, the
look-alike hints and the time of day, but this is its weakest case and we say so. The picture key is
designed to be kept next to the dispenser.

**What if two pills look identical?**
MedSync does not guess. It groups look-alikes, finds the smallest set of attributes that separates them
(time of day, score line, size, imprint), and if nothing separates two tablets it says: "These two cannot
be told apart by appearance – ask the patient to read the box or blister."

**How reliable is the conversation parsing, and what happens when it is wrong?**
The default parser is rule-based: a fixed German and English vocabulary, tested on the organizers' example
sentences. The demo is shown in English. It will miss dialect and unusual wording. That is why nothing is applied silently. Every anchor
appears as a chip, shows its source, and can be removed with one click. The parser filters and ranks; the
clinician decides. We have not measured accuracy on real calls; a pilot would.

**Why not a camera app?**
Our patient is over 80, on a landline, often with poor eyesight. A camera app needs a smartphone, an
install, good light and a steady hand, and a small white round tablet is still a small white round tablet
on a photo. We put the tool where the skill is: with the clinician. The patient installs nothing and gets
paper.

**How is data protected, including the Bedrock option?**
The prototype uses only synthetic data and runs offline on one laptop. The AI extractor is off by default.
If switched on, the transcript sentence is de-identified first (names, dates of birth, addresses, phone
numbers) and sent to Claude on Amazon Bedrock in an EU region; no patient record is sent. De-identifying
free text is not perfect, so real use would need a data protection impact assessment, a processing
agreement and a decision on whether the AI option is worth it at all. The product works without it.

**Is this a medical device?**
We do not know yet, and we will not claim either way. MedSync does not suggest doses or therapy; it supports
identification and communication. Whether that falls under the medical device rules needs a formal
regulatory assessment before any clinical use. It is on our list in `LIMITATIONS.md`.

**Where does real appearance data come from, and who pays?**
From a licensed drug appearance database; several commercial ones exist in Germany. We have integrated none
and all pictures here are drawn in code. A licence would be paid by whoever operates MedSync, most plausibly
as part of practice or clinic software where such data is often already licensed. Checking the cost and
coverage is a first task for a pilot.

**How do you show fewer healthcare contacts?**
Today we cannot, and the app shows no impact numbers. A pilot would measure call duration, callback rate, refill-request loops, patient-reported
confidence and reported mix-ups, before and after, in one clinic.

**Why would clinics adopt it?**
It sits inside a call they already make, needs nothing from the patient, and saves time on the part of the
call nobody enjoys. It shows its reasoning, so staff can check it. And it produces something tangible for
the patient. The risk is integration effort, which is why the data sources are behind four small adapters.

**What happens when contracts change?**
MedSync knows the validity window of each contract. Thirty days before a rotation it warns "appearance
change ahead" and shows the next tablet, so the clinic can send an updated key before the new pack arrives.
After the rotation, the prediction changes; once dispensed, the record confirms it.

**How does this work in Denmark as well as Germany?**
The problem is the same wherever generic substitution exists: same ingredient, different-looking tablet.
The chain is built in levels, and only the middle of it is German. In Germany the product follows from
insurer rebate contracts. In Denmark, substitution is driven by the pharmacy offering the cheapest
equivalent product in regularly updated price periods, and there is a national shared medication record. So
the "contract" stage would be replaced by a price-period source and the "insurer" stage would matter less;
dispensing records, appearance, warnings, the copilot and the patient key stay the same. We have not built
or verified a Danish adapter; details would need checking with Danish partners.

**What is really working today, and what is mock?**
Working: the resolution logic, the warning rules, the parser, the narrowing, the PDF key, the UI, 94 tests.
Mock: every data source. See `LIMITATIONS.md`.

**Does this really plug into practice software today?**
No. It is a concept shown with a mock host screen and FHIR-shaped data. The "launch context" drawer shows what
a host would hand over, in the style of a SMART on FHIR launch, but nothing is connected. Real integration would
run through each vendor's partner programme and the applicable gematik specifications. The mock host is generic
and is labelled as a mock on screen.

**Where does the Rabattvertrag mapping come from?**
It is simulated here. In production it needs a contract-marker data source from pharmacy-side or clearing-house
providers. Licensing and availability would have to be confirmed: the prices in these contracts are
confidential, even though which product is the contract product is visible to pharmacies. We have not verified
any source.

**Is the evidence about heart failure?**
Not directly. The strongest study we cite is in patients after a heart attack in the US, and it is an
association study from insurance claims: appearance changes went along with more people stopping their
medicine. It does not show cause, and it did not look at clinical outcomes. The app itself no longer shows these studies.
One of our three references was checked against the publisher's page; the other two should be checked before
they are cited elsewhere.

**Why does the app show real insurer names?**
As examples only, so the screens look familiar. The contracts, products and dates shown for them are invented,
and the screen says so. Three of the six (Debeka, DKV, Allianz) are private insurers, where rebate contracts
do not steer the pharmacy in the same way; in a real product they would need their own logic.

**Why is the green tier called "lower attention" and not "safe"?**
Because the tiers describe how prominent a warning should be in the clinic workflow, not how safe a medicine
is. No medicine is "safe" to mix up. The three badges also differ in shape, so they work without colour.

**Who confirms that the tablet is the right one?**
The clinician, with one click on their own screen ("Confirmed with patient"), after asking the patient. The
label then changes from "Predicted" to "Confirmed with patient" and the click is written to the audit trail.
A newer dispensing record from the pharmacy supersedes an earlier confirmation.
