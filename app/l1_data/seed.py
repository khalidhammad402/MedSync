"""Seed a believable, internally consistent mock world.

All insurers, manufacturers, brand names and PZNs are fictional.
Dates are relative to "today" so the demo looks the same on any day.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app import config, db
from app.l1_data.models import (Contract, ContractProduct, DispensingEvent, Insurer, KeyIssue,
                                Patient, Prescription, Product, Shortage, Substance)
from app.l1_data.pills import pill_svg

INSURERS = [("Kasse Nord", "Kasse Nord – Demo-Krankenkasse"), ("Kasse Süd", "Kasse Süd – Demo-Krankenkasse"),
            ("Kasse West", "Kasse West – Demo-Krankenkasse"), ("Kasse Ost", "Kasse Ost – Demo-Krankenkasse"),
            ("Kasse Mitte", "Kasse Mitte – Demo-Krankenkasse"), ("Kasse Küste", "Kasse Küste – Demo-Krankenkasse")]

# key: (inn, inn_de, atc, class, purpose_key, purpose_en, purpose_de, risk, nti, otc, aliases, strength)
SUBSTANCES = {
    "meto": ("Metoprolol succinate", "Metoprololsuccinat", "C07AB02", "Beta blocker", "heart", "for your heart", "für das Herz", "red", False, False, "Cardimet,Metozor", "47.5 mg"),
    "biso": ("Bisoprolol", "Bisoprolol", "C07AB07", "Beta blocker", "heart", "for your heart", "für das Herz", "red", False, False, "Bisocard", "5 mg"),
    "rami": ("Ramipril", "Ramipril", "C09AA05", "ACE inhibitor", "blood_pressure", "for your blood pressure", "für den Blutdruck", "amber", False, False, "Ramicor", "5 mg"),
    "sv": ("Sacubitril/valsartan", "Sacubitril/Valsartan", "C09DX04", "ARNI", "heart", "for your heart", "für das Herz", "amber", False, False, "Sacuval", "49/51 mg"),
    "spiro": ("Spironolactone", "Spironolacton", "C03DA01", "Aldosterone antagonist", "water", "water tablet", "Wassertablette", "amber", False, False, "Spirolan", "25 mg"),
    "dapa": ("Dapagliflozin", "Dapagliflozin", "A10BK01", "SGLT2 inhibitor", "heart", "for your heart", "für das Herz", "green", False, False, "Dapaglin", "10 mg"),
    "tora": ("Torasemide", "Torasemid", "C03CA04", "Loop diuretic", "water", "water tablet", "Wassertablette", "amber", False, False, "Torasan", "10 mg"),
    "apix": ("Apixaban", "Apixaban", "B01AF02", "Anticoagulant", "blood_thinner", "blood thinner", "Blutverdünner", "red", False, False, "Apixor", "5 mg"),
    "ator": ("Atorvastatin", "Atorvastatin", "C10AA05", "Statin", "cholesterol", "for your cholesterol", "für das Cholesterin", "green", False, False, "Atorlip", "20 mg"),
    "levo": ("Levothyroxine", "Levothyroxin", "H03AA01", "Thyroid hormone", "thyroid", "for your thyroid", "für die Schilddrüse", "red", True, False, "Thyrolev", "75 µg"),
    "panto": ("Pantoprazole", "Pantoprazol", "A02BC02", "Proton pump inhibitor", "stomach", "for your stomach", "für den Magen", "green", False, False, "Pantogast", "40 mg"),
    "ibu": ("Ibuprofen", "Ibuprofen", "M01AE01", "OTC painkiller (NSAID)", "pain", "for pain", "gegen Schmerzen", "amber", False, True, "Ibudolor", "400 mg"),
}

M_NORD, M_RHEIN, M_ISAR, M_FRANK, M_ALP = ("Nordlicht Generika", "Rheingold Demo-Pharma", "Isartal Pharma",
                                           "Franken Generika", "Alpina Demo-Pharma")
# key: (substance, manufacturer, color, shape, size_mm, score_line, divisible_parts, coating, imprint)
PRODUCTS = {
    "MA": ("meto", M_NORD, "white", "round", 6, "functional", 2, "prolonged-release", "M47"),
    "MB": ("meto", M_RHEIN, "orange", "oval", 9, "decorative", 1, "prolonged-release", "RG"),
    "MC": ("meto", M_ISAR, "yellow", "oblong", 11, "functional", 2, "prolonged-release", "47"),
    "BA": ("biso", M_NORD, "yellow", "round", 7, "functional", 2, "film-coated", "B5"),
    "BB": ("biso", M_FRANK, "white", "shield", 7, "functional", 2, "film-coated", "5"),
    "BC": ("biso", M_ALP, "pink", "round", 6, "none", 1, "film-coated", ""),
    "RA": ("rami", M_NORD, "white", "round", 6.5, "none", 1, "uncoated", ""),
    "RB": ("rami", M_ALP, "pink", "oblong", 9, "functional", 2, "uncoated", "R5"),
    "RC": ("rami", M_ISAR, "red", "capsule", 14, "none", 1, "capsule", ""),
    "SVA": ("sv", M_RHEIN, "yellow", "oval", 13, "none", 1, "film-coated", "SV"),
    "SVB": ("sv", M_FRANK, "purple", "oval", 13, "none", 1, "film-coated", "49"),
    "SA": ("spiro", M_NORD, "yellow", "round", 8, "functional", 2, "film-coated", "S25"),
    "SB": ("spiro", M_ISAR, "white", "round", 8, "functional", 2, "film-coated", "SP"),
    "SC": ("spiro", M_ALP, "brown", "round", 9, "none", 1, "film-coated", ""),
    "DA": ("dapa", M_FRANK, "white", "round", 6, "none", 1, "film-coated", ""),
    "DB": ("dapa", M_RHEIN, "yellow", "shield", 9, "none", 1, "film-coated", "10"),
    "TA": ("tora", M_ALP, "white", "oblong", 10, "functional", 2, "uncoated", "TO"),
    "TB": ("tora", M_NORD, "white", "round", 6, "functional", 2, "uncoated", "T10"),
    "TC": ("tora", M_ISAR, "white", "round", 9, "functional", 4, "uncoated", "T"),
    "AA": ("apix", M_RHEIN, "blue", "oval", 9, "none", 1, "film-coated", "A5"),
    "AB": ("apix", M_ALP, "pink", "oval", 10, "none", 1, "film-coated", "5"),
    "AC": ("apix", M_FRANK, "white", "round", 7, "none", 1, "film-coated", "AP"),
    "ATA": ("ator", M_NORD, "white", "oval", 10, "none", 1, "film-coated", "A20"),
    "ATB": ("ator", M_ISAR, "white", "round", 8, "decorative", 1, "film-coated", "20"),
    "ATC": ("ator", M_RHEIN, "yellow", "oblong", 12, "functional", 2, "film-coated", ""),
    "LA": ("levo", M_FRANK, "pink", "round", 6.5, "functional", 2, "uncoated", "75"),
    "LB": ("levo", M_ALP, "white", "round", 6.5, "functional", 2, "uncoated", "L75"),
    "LC": ("levo", M_ISAR, "blue", "round", 7, "functional", 2, "uncoated", "75"),
    "PA": ("panto", M_NORD, "yellow", "oval", 10, "none", 1, "gastro-resistant", "P40"),
    "PB": ("panto", M_FRANK, "brown", "oval", 11, "none", 1, "gastro-resistant", ""),
    "PC": ("panto", M_RHEIN, "white", "oval", 10, "none", 1, "gastro-resistant", ""),
    "IA": ("ibu", M_ALP, "white", "oblong", 14, "functional", 2, "film-coated", "IBU"),
    "IB": ("ibu", M_ISAR, "pink", "oval", 13, "none", 1, "film-coated", ""),
}


def _std(current: list[str], previous: str, shift: int):
    """A previous contract and the current one, staggered so rotation dates differ."""
    return [(-565 - shift, -201 - shift, [previous]), (-200 - shift, 165 - shift, current)]


def _contract_plan() -> dict[str, dict[str, list]]:
    """insurer -> substance -> list of (valid_from offset, valid_to offset, product keys)."""
    order = ["meto", "biso", "rami", "sv", "spiro", "dapa", "tora", "apix", "ator", "levo", "panto"]
    sh = {k: (i * 23) % 120 for i, k in enumerate(order)}
    nord = {
        "meto": _std(["MA"], "MC", sh["meto"]), "biso": _std(["BC"], "BA", sh["biso"]),
        # expires within 25 days, successor looks different (drives R1)
        "rami": [(-710, -346, ["RC"]), (-345, 20, ["RA"]), (21, 386, ["RB"])],
        "sv": _std(["SVA"], "SVB", sh["sv"]), "spiro": _std(["SA"], "SB", sh["spiro"]),
        "dapa": _std(["DA"], "DB", sh["dapa"]),
        # rotated 30 days ago (drives the recorded contract switch)
        "tora": [(-400, -31, ["TA"]), (-30, 335, ["TB"])],
        "apix": _std(["AA"], "AB", sh["apix"]), "ator": _std(["ATA"], "ATC", sh["ator"]),
        "levo": _std(["LB"], "LC", sh["levo"]), "panto": _std(["PA"], "PB", sh["panto"]),
    }
    sued = {
        "meto": _std(["MC"], "MA", sh["meto"]), "biso": _std(["BB"], "BC", sh["biso"]),
        "rami": _std(["RB"], "RA", sh["rami"]), "sv": _std(["SVB"], "SVA", sh["sv"]),
        "spiro": _std(["SB", "SC"], "SA", sh["spiro"]),  # two contract partners
        "dapa": _std(["DB"], "DA", sh["dapa"]), "tora": _std(["TC"], "TA", sh["tora"]),
        "apix": _std(["AB"], "AC", sh["apix"]), "ator": _std(["ATB"], "ATA", sh["ator"]),
        "levo": _std(["LC"], "LA", sh["levo"]), "panto": _std(["PB"], "PC", sh["panto"]),
    }
    west = {
        "meto": _std(["MB"], "MA", sh["meto"]), "biso": _std(["BA"], "BB", sh["biso"]),
        "rami": _std(["RC"], "RB", sh["rami"]), "sv": _std(["SVA"], "SVB", sh["sv"]),
        "spiro": _std(["SC"], "SA", sh["spiro"]), "dapa": _std(["DA"], "DB", sh["dapa"]),
        "tora": _std(["TA"], "TC", sh["tora"]), "apix": _std(["AC"], "AA", sh["apix"]),
        "ator": [(-375, -10, ["ATC"])],                  # expired, no successor
        "levo": _std(["LA"], "LB", sh["levo"]),
        "panto": _std(["PB", "PC"], "PA", sh["panto"]),  # two contract partners
    }
    ost = {
        "meto": _std(["MA"], "MB", sh["meto"]), "biso": _std(["BA"], "BC", sh["biso"]),
        "rami": _std(["RA"], "RC", sh["rami"]), "sv": _std(["SVB"], "SVA", sh["sv"]),
        "spiro": _std(["SA"], "SC", sh["spiro"]), "dapa": _std(["DB"], "DA", sh["dapa"]),
        "tora": _std(["TB"], "TC", sh["tora"]), "apix": _std(["AA"], "AC", sh["apix"]),
        "ator": _std(["ATC"], "ATB", sh["ator"]), "levo": _std(["LA"], "LC", sh["levo"]),
        "panto": _std(["PC"], "PA", sh["panto"]),
    }
    mitte = {**sued, "meto": _std(["MB"], "MC", sh["meto"]), "tora": _std(["TA"], "TB", sh["tora"])}
    kueste = {**ost, "meto": _std(["MC"], "MB", sh["meto"]), "rami": _std(["RB"], "RC", sh["rami"])}
    return {"Kasse Nord": nord, "Kasse Süd": sued, "Kasse West": west, "Kasse Ost": ost,
            "Kasse Mitte": mitte, "Kasse Küste": kueste}


# rx: (substance, instruction, times, with_meal, aut-idem product key, dispensings [(offset, product, reason)])
PATIENTS = [
    dict(salutation="Herr", first="Karl", last="Müller", age=82, insurer="Kasse Nord",
         address="Musterweg 12, 91052 Erlangen", phone="09131 5550101", key_issued=-60, rx=[
             ("meto", "1-0-½", "morning,evening", False, None, [(-130, "MA", "normal")]),
             ("dapa", "1-0-0", "morning", False, None, [(-20, "DA", "normal")]),
             ("tora", "1-0-0", "morning", False, None, [(-100, "TA", "normal"), (-30, "TB", "contract_switch")]),
             ("rami", "1-0-1", "morning,evening", False, None, []),
             ("apix", "1-0-1", "morning,evening", False, None, [(-45, "AA", "normal")]),
             ("spiro", "0-1-0", "noon", True, None, [(-60, "SA", "normal")]),
             ("panto", "1-0-0", "morning", False, None, []),
             ("levo", "1-0-0", "morning", False, "LA", []),
         ]),
    dict(salutation="Frau", first="Helga", last="Schneider", age=76, insurer="Kasse Süd",
         address="Beispielallee 4, 90402 Nürnberg", phone="0911 5550102", key_issued=None, rx=[
             ("meto", "1-0-1", "morning,evening", False, None, [(-40, "MC", "normal")]),
             ("rami", "1-0-0", "morning", False, None, []),
             ("tora", "1-0-0", "morning", False, None, [(-25, "TC", "normal")]),
             ("apix", "1-0-1", "morning,evening", False, None, [(-50, "AB", "normal")]),
             ("ator", "0-0-1", "evening", False, None, []),
             ("spiro", "1-0-0", "morning", True, None, []),
         ]),
    dict(salutation="Herr", first="Mehmet", last="Yilmaz", age=79, insurer="Kasse West",
         address="Demostraße 7, 90762 Fürth", phone="0911 5550103", key_issued=None, rx=[
             ("biso", "1-0-0", "morning", False, None, [(-35, "BA", "normal")]),
             ("sv", "1-0-1", "morning,evening", False, None, [(-15, "SVA", "normal")]),
             ("ator", "0-0-1", "evening", False, None, [(-50, "ATC", "normal")]),
             ("panto", "1-0-0", "morning", False, None, []),
             ("ibu", "1 tablet when needed", "", True, None, []),
         ]),
    dict(salutation="Frau", first="Sabine", last="Weber", age=62, insurer="Kasse Ost",
         address="Probeweg 21, 96047 Bamberg", phone="0951 5550104", key_issued=None, rx=[
             ("biso", "1-0-0", "morning", False, None, [(-30, "BA", "normal")]),
             ("sv", "1-0-1", "morning,evening", False, None, [(-20, "SVB", "normal")]),
             ("dapa", "1-0-0", "morning", False, None, []),
             ("ator", "0-0-1", "evening", False, None, [(-40, "ATC", "normal")]),
         ]),
    dict(salutation="Herr", first="Jonas", last="Hoffmann", age=54, insurer="Kasse Mitte",
         address="Testgasse 3, 91301 Forchheim", phone="09191 5550105", key_issued=None, rx=[
             ("meto", "1-0-0", "morning", False, None, [(-25, "MB", "normal")]),
             ("rami", "1-0-0", "morning", False, None, []),
             ("spiro", "1-0-0", "morning", True, None, []),
             ("panto", "1-0-0", "morning", False, None, [(-15, "PB", "normal")]),
         ]),
]


def seed(session: Session, today: date | None = None) -> bool:
    """Load the mock world. Idempotent: does nothing if data is already there."""
    if session.exec(select(Insurer)).first():
        return False
    today = today or config.today()

    def d(offset: int) -> date:
        return today + timedelta(days=offset)

    insurers = {}
    for short, full in INSURERS:
        row = Insurer(short_name=short, full_name=full)
        session.add(row)
        insurers[short] = row
    subs = {}
    for key, (inn, inn_de, atc, cls, pk, pen, pde, risk, nti, otc, aliases, _strength) in SUBSTANCES.items():
        row = Substance(inn_name=inn, inn_name_de=inn_de, atc_code=atc, class_label=cls, purpose_key=pk,
                        plain_purpose_en=pen, plain_purpose_de=pde, risk_tier=risk,
                        narrow_therapeutic_index=nti, otc_caution=otc, aliases=aliases)
        session.add(row)
        subs[key] = row
    session.flush()

    prods = {}
    for n, (key, (sk, manu, color, shape, size, score, parts, coating, imprint)) in enumerate(PRODUCTS.items(), start=1):
        strength = SUBSTANCES[sk][11]
        row = Product(pzn=str(99900000 + n * 37), substance_id=subs[sk].id,
                      name=f"{SUBSTANCES[sk][0].split(' ')[0]} {manu.split(' ')[0]} {strength}",
                      strength=strength, form="capsule" if shape == "capsule" else "tablet", manufacturer=manu,
                      color=color, shape=shape, size_mm=size, score_line=score, divisible_parts=parts,
                      coating=coating, imprint=imprint,
                      image_svg=pill_svg(color, shape, size, score, imprint, parts))
        session.add(row)
        prods[key] = row
    session.flush()

    for ins_name, plan in _contract_plan().items():
        for sk, windows in plan.items():
            for start, end, keys in windows:
                c = Contract(insurer_id=insurers[ins_name].id, substance_id=subs[sk].id,
                             strength=SUBSTANCES[sk][11], valid_from=d(start), valid_to=d(end))
                session.add(c)
                session.flush()
                for k in keys:
                    session.add(ContractProduct(contract_id=c.id, product_id=prods[k].id))

    for p in PATIENTS:
        birth = date(today.year - p["age"], today.month, min(today.day, 28)) - timedelta(days=100)
        pat = Patient(name=f'{p["salutation"]} {p["last"]}', first_name=p["first"], last_name=p["last"],
                      salutation=p["salutation"], birth_date=birth, insurer_id=insurers[p["insurer"]].id,
                      address=p["address"], phone=p["phone"])
        session.add(pat)
        session.flush()
        for n_rx, (sk, instr, times, meal, aut, disp) in enumerate(p["rx"]):
            rx = Prescription(prescribed_on=d(-210 - n_rx * 17), patient_id=pat.id, substance_id=subs[sk].id, strength=SUBSTANCES[sk][11],
                              instruction_text=instr, times_of_day=times, with_meal=meal,
                              aut_idem_excluded=aut is not None,
                              prescribed_product_id=prods[aut].id if aut else None)
            session.add(rx)
            session.flush()
            for off, pk, reason in disp:
                session.add(DispensingEvent(patient_id=pat.id, prescription_id=rx.id, product_id=prods[pk].id,
                                            dispensed_at=d(off), reason=reason))
        if p["key_issued"] is not None:
            session.add(KeyIssue(patient_id=pat.id, issued_at=d(p["key_issued"]), lang="de"))

    session.add(Shortage(substance_id=subs["ator"].id, strength="20 mg", active_from=d(-5), active_to=d(30)))
    session.commit()
    return True


def reset() -> None:
    """Drop everything and load the seed again."""
    db.drop_tables()
    db.create_tables()
    with Session(db.get_engine()) as session:
        seed(session)


if __name__ == "__main__":
    reset()
    print("MedSync demo data restored.")
