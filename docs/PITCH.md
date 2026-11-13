# Pitch script (3 minutes)

Roles for up to four people. With fewer, merge B into A and D into C.

- **A – Storyteller:** opening and close
- **B – Driver:** at the laptop; presses Run demo and Next
- **C – Narrator:** speaks over the demo
- **D – Closer:** outcome and next step; takes questions on feasibility

Before you start: run `python run.py demo` once, press Pause on step 1, and leave the browser in full screen
(F11) at normal zoom (Ctrl+0). The narrator bar shows each step; B presses **Next** if C is ahead of the timer.

## 0:00 – 0:30 · The problem (A)

On screen while A speaks: the mock practice software at `http://localhost:8000/host`. It shows only a text
table. When A finishes, B clicks **Launch MedSync VisualID**, then **Run demo**.

> "I take three white tablets, one blue and two yellow ones."
>
> That is Herr Müller. He is 82, his heart is weak, and he is on the phone with his heart-failure nurse.
> She wants to change one tablet. She knows it by its ingredient. He knows it by its colour.
>
> Prescribed by name. Dispensed by contract. Described by color.
> That is the blind spot: the practice sees a text table, the patient sees a tablet.
>
> And the colour keeps changing. When his insurer changes supplier, or the pharmacy runs out, the same
> medicine comes in a new shape. Nobody on that call knows what is in his hand.
> So calls run long, people call back, and sometimes the wrong tablet gets changed.

## 0:30 – 2:15 · Live demo (B drives, C speaks)

| Time | Step | C says |
|---|---|---|
| 0:30 | 1 · Consult | "This is MedSync. The nurse sees what Herr Müller sees: eight medicines as pictures. Four are small white tablets. MedSync has outlined them: look-alikes." |
| 0:40 | 2 · Patient talks | "She types what he says. In German. MedSync picks out colours and counts, and notices he mentions three white tablets where the list has four." |
| 1:00 | 3 · Heart or yellow? | "He asks: the one for the heart? Two tablets are left, both white. MedSync suggests the one question that separates them: does it have a line across the middle? He says yes. One tablet left, and the nurse records it with one click: confirmed with patient. She decides, not the software." |
| 1:20 | 4 · How do we know? | "And it never asks for blind trust. One click shows the trail: his insurer, the drug, the contract, the product, the appearance. In plain words." |
| 1:35 | 5 · Simulator | "Now real life. The pharmacy is out of stock and substitutes. Watch the picture. … Back on the call screen: confirmed by the dispensing record, and two warnings. He may have old and new packs at home. And his instruction says half a tablet, but the new tablet must not be split." |
| 2:00 | 6 · Patient key | "Herr Müller installs nothing. He gets one page in large print: same medicine, new look, do not take both." |

## 2:15 – 3:00 · Outcome and next step (D)

> The challenge asks for fewer healthcare contacts. We have not measured that yet, and we will not pretend
> we have. So our next step is a four-week pilot in one heart-failure clinic, measuring call duration,
> callback rate, refill loops, patient confidence and reported mix-ups.
>
> Everything you saw runs on mock data, offline, on this laptop. The four data sources are behind clean
> interfaces, ready for the ePA medication list and a licensed appearance database.
>
> And it does not replace anything: it is designed to open from inside the practice software a clinic
> already uses.
>
> MedSync does not decide anything. It makes sure that when the nurse says "the heart tablet", Herr Müller
> picks up the right one. Thank you.

## If the demo fails: 30-second fallback (A, with a screenshot)

Open `docs/screens/consult-after-substitution.png` (keep it open in a second window before you start).

> "Let me show you one screen instead. This is Herr Müller's medicine list as pictures. His pharmacy has
> just substituted his heart tablet: it is now orange instead of white. MedSync knows this from the
> dispensing record, and it raises two warnings on its own: he may have both packs at home, and his
> instruction needs half a tablet, but this one must not be split. The nurse sees that before she says a
> word. Then he gets a one-page picture key by post. That is the whole idea: both sides of the phone call
> looking at the same tablet."

## Stage checklist

- Laptop on power, notifications off, Wi-Fi off (it runs offline; this shows it).
- App started with `python run.py run`, browser on `http://localhost:8000/host` for the opening.
- Browser zoom at normal (Ctrl+0), full screen. Check the back row can read the card titles.
- Fallback screenshot open in a second window.
- If something looks wrong mid-demo: Simulator tab → **Reset demo**, then **Run demo**.
