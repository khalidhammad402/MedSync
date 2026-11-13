"""Clinical evidence shown on the Impact tab. The wording is pinned by a test: do not strengthen it."""
from __future__ import annotations

TITLE = "Clinical Evidence"

REFERENCES = [
    {
        "authors": "Kesselheim AS, Bykov K, Avorn J, Tong A, Doherty M, Choudhry NK.",
        "title": ("Burden of changes in pill appearance for patients receiving generic cardiovascular medications "
                  "after myocardial infarction: cohort and nested case-control studies."),
        "journal": "Annals of Internal Medicine. 2014;161(2):96-103.",
        "doi": "10.7326/M13-2381",
        "found": ("In 11,513 US patients who started a generic beta-blocker, ACE inhibitor, angiotensin receptor "
                  "blocker or statin after a heart attack, 29 percent had a change in pill color or shape during the "
                  "following year. Changes in appearance were associated with higher odds of stopping the "
                  "medication: a color change with an adjusted odds ratio of 1.34 and a shape change with 1.66."),
        "not_shown": ("It is an observational study using insurance claims. It shows an association with "
                      "nonpersistence, not a proven cause, and the authors note that clinical outcomes were not "
                      "addressed."),
        "matters": ("Generic switching changes how a patient's pills look. MedSync makes those changes visible to "
                    "the clinic and to the patient before they cause confusion."),
        "checked": False,
    },
    {
        "authors": "Hauber B, Hand MV, Hancock BC, Zarrella J, Harding L, Ogden-Barker M, Antipas AS, Watt SJ.",
        "title": ("Patient acceptability and preferences for solid oral dosage form drug product attributes: "
                  "a scoping review."),
        "journal": "Patient Preference and Adherence. 2024;18:1281-1297.",
        "doi": "10.2147/PPA.S443213",
        "found": ("The review summarises 19 studies from 2013 to 2023 and describes physical attributes such as "
                  "color, shape and size as notable determinants of acceptance, noting that they can help patients "
                  "tell products apart, which matters for people prescribed several products. It also found that few "
                  "studies examined the effect of these attributes on behaviors and outcomes."),
        "not_shown": ("It is not specific to heart failure or to Germany, and it addresses design of medicines more "
                      "than communication with clinicians. The authors include employees of a pharmaceutical "
                      "company."),
        "matters": ("It supports the idea that appearance is how patients tell their medicines apart, and it "
                    "identifies a research gap that a pilot could help fill."),
        "checked": True,
    },
]

RELATED = {
    "label": "Related note, different setting",
    "authors": "Ryan AN, Robertson KL, Glass BD.",
    "title": ("Look-alike medications in the perioperative setting: scoping review of medication incidents and risk "
              "reduction interventions."),
    "journal": "International Journal of Clinical Pharmacy. 2024;46(1):26-39.",
    "doi": "10.1007/s11096-023-01629-2",
    "line": ("Shows that look-alike confusion is a recognised medication-safety issue in another setting "
             "(intravenous drugs in operating theatres); not evidence about oral medicines at home."),
}

FOOTER = ("The second reference was checked against the publisher's page. The first reference and the related note "
          "are quoted as supplied by the team and should be checked against the publisher abstracts before they are "
          "cited. Pilot data would replace the modelled numbers above.")
