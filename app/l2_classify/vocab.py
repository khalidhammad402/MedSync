"""German and English synonyms for every facet, and the functions that normalise them."""
from __future__ import annotations

import re
from typing import Optional

from app.l2_classify import taxonomy as tx

COLOR_SYNONYMS = {
    "white": ["white", "whitish", "off-white", "cream", "creamy", "weiß", "weiss", "weißlich", "weisslich",
              "cremefarben", "cremeweiß", "creme", "hell"],
    "yellow": ["yellow", "yellowish", "pale yellow", "gelb", "hellgelb", "gelblich", "blassgelb"],
    "orange": ["orange", "orangefarben", "apricot"],
    "pink": ["pink", "rose", "rosa", "rosafarben", "rosé", "hellrosa", "altrosa"],
    "red": ["red", "reddish", "rot", "rötlich", "dunkelrot", "hellrot"],
    "brown": ["brown", "brownish", "braun", "bräunlich", "beige", "ocker"],
    "green": ["green", "greenish", "grün", "grünlich", "hellgrün"],
    "blue": ["blue", "bluish", "light blue", "blau", "hellblau", "bläulich", "dunkelblau"],
    "purple": ["purple", "violet", "lilac", "lila", "violett", "purpur"],
    "grey": ["grey", "gray", "greyish", "grau", "gräulich", "hellgrau"],
}
SHAPE_SYNONYMS = {
    "round": ["round", "circular", "rund", "kreisrund", "kugelig"],
    "oval": ["oval", "egg-shaped", "eiförmig", "ovale"],
    "oblong": ["oblong", "long", "elongated", "länglich", "laenglich", "lang", "stäbchen", "stäbchenförmig"],
    "shield": ["shield", "shield-shaped", "schild", "schildförmig", "wappen", "wappenförmig"],
    "capsule": ["capsule", "kapsel", "kapseln", "capsules"],
}
SIZE_SYNONYMS = {
    "small": ["small", "tiny", "little", "klein", "winzig", "kleinere"],
    "medium": ["medium", "medium-sized", "mittel", "mittelgroß", "mittelgross", "mittlere"],
    "large": ["large", "big", "huge", "groß", "gross", "größere", "dick", "riesig"],
}
SCORE_WORDS = ["score line", "score", "break line", "line across", "line in the middle", "line down the middle",
               "notch", "groove", "line", "kerbe", "bruchkerbe", "bruchrille", "rille", "teilungskerbe", "strich",
               "linie", "einkerbung"]
SCHEDULE_SYNONYMS = {
    "morning": ["morning", "mornings", "in the morning", "breakfast", "morgens", "morgen", "früh", "frühs",
                "am morgen", "frühstück", "vormittags"],
    "noon": ["noon", "midday", "lunch", "lunchtime", "mittags", "mittag", "am mittag", "mittagessen"],
    "evening": ["evening", "evenings", "in the evening", "dinner", "supper", "abends", "abend", "am abend",
                "abendessen", "abendbrot"],
    "night": ["night", "at night", "bedtime", "before bed", "nachts", "nacht", "zur nacht", "vor dem schlafen",
              "schlafengehen"],
    "with_meal": ["with food", "with a meal", "with meals", "with my meal", "zum essen", "mit dem essen",
                  "zur mahlzeit", "beim essen"],
}
PURPOSE_SYNONYMS = {
    "heart": ["heart", "heart tablet", "heart pill", "herz", "herztablette", "herzmittel", "fürs herz"],
    "water": ["water tablet", "water pill", "water tablets", "water pills", "diuretic", "wassertablette",
              "wassertabletten", "entwässerung", "entwässerungstablette", "wasserpille"],
    "blood_thinner": ["blood thinner", "blood thinning", "thinner", "anticoagulant", "blutverdünner",
                      "blutverdünnung", "gerinnungshemmer"],
    "thyroid": ["thyroid", "schilddrüse", "schilddrüsentablette"],
    "stomach": ["stomach", "stomach protection", "magen", "magenschutz", "magentablette"],
    "cholesterol": ["cholesterol", "cholesterin", "fett", "blutfett", "blutfette"],
    "blood_pressure": ["blood pressure", "pressure", "blutdruck", "blutdrucktablette", "bluthochdruck"],
    "pain": ["pain", "painkiller", "pain killer", "schmerz", "schmerzen", "schmerztablette", "schmerzmittel"],
    "sugar": ["sugar", "diabetes", "zucker", "zuckertablette", "blutzucker"],
}
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "ein": 1, "eine": 1, "einen": 1, "einer": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
    "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10,
}
NEGATION_WORDS = ["not", "no", "isn't", "isnt", "never", "without", "nicht", "kein", "keine", "keinen", "ohne",
                  "nie"]
_GERMAN_ENDINGS = ("en", "er", "es", "em", "e", "n", "s")


def _lookup(word: str, table: dict[str, list[str]]) -> Optional[str]:
    w = word.strip().lower()
    if not w:
        return None
    for key, synonyms in table.items():
        if w == key or w in synonyms:
            return key
    for ending in _GERMAN_ENDINGS:  # "weiße", "gelben", "rundes" ...
        if w.endswith(ending) and len(w) - len(ending) >= 3:
            stem = w[: -len(ending)]
            for key, synonyms in table.items():
                if stem == key or stem in synonyms:
                    return key
    return None


def normalise_color(word: str) -> Optional[str]:
    return _lookup(word, COLOR_SYNONYMS)


def normalise_shape(word: str) -> Optional[str]:
    return _lookup(word, SHAPE_SYNONYMS)


def normalise_size(word: str) -> Optional[str]:
    return _lookup(word, SIZE_SYNONYMS)


def normalise_schedule(word: str) -> Optional[str]:
    return _lookup(word, SCHEDULE_SYNONYMS)


def normalise_purpose(word: str) -> Optional[str]:
    return _lookup(word, PURPOSE_SYNONYMS)


def normalise_score_line(word: str) -> Optional[str]:
    w = word.strip().lower()
    if w in tx.SCORE_LINES:
        return w
    if w in ("yes", "ja", "present", "line"):
        return "yes"
    if w in ("no", "nein", "none"):
        return "no"
    return None


def normalise_number(word: str) -> Optional[int]:
    w = word.strip().lower()
    if w.isdigit() and 0 < int(w) <= 20:
        return int(w)
    return NUMBER_WORDS.get(w)


def normalise_imprint(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


VALID_VALUES = {
    "color": tx.COLORS, "shape": tx.SHAPES, "size": tx.SIZE_BANDS, "score_line": ["yes", "no"],
    "schedule": tx.SCHEDULE, "purpose": tx.PURPOSES,
}
NORMALISERS = {
    "color": normalise_color, "shape": normalise_shape, "size": normalise_size,
    "score_line": normalise_score_line, "schedule": normalise_schedule, "purpose": normalise_purpose,
}


def normalise(facet: str, value: str) -> Optional[str]:
    """Return the vocabulary value for a facet, or None if the value is outside the vocabulary."""
    fn = NORMALISERS.get(facet)
    return fn(value) if fn else None
