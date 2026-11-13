"""Layer 2: the one controlled vocabulary used by the UI, the parser and the warnings."""
from __future__ import annotations

# The resolution chain. The order matters and is shown in code, tests and UI.
CHAIN_LEVELS: list[tuple[int, str, str]] = [
    (1, "insurer", "Insurer – which contracts apply"),
    (2, "drug", "Drug – active ingredient and strength"),
    (3, "contract", "Contract – the valid rebate contract today"),
    (4, "product", "Product – the pack the pharmacy hands over"),
    (5, "appearance", "Appearance – what the tablet looks like"),
]
CHAIN_NAMES = [name for _, name, _ in CHAIN_LEVELS]

COLORS = ["white", "yellow", "orange", "pink", "red", "brown", "green", "blue", "purple", "grey"]
SHAPES = ["round", "oval", "oblong", "shield", "capsule"]
SIZE_BANDS = ["small", "medium", "large"]
SCORE_LINES = ["none", "functional", "decorative"]
DIVISIBLE_PARTS = [1, 2, 4]
SCHEDULE = ["morning", "noon", "evening", "night", "with_meal"]
TIMES_OF_DAY = ["morning", "noon", "evening", "night"]
PURPOSES = ["heart", "water", "blood_thinner", "thyroid", "stomach", "cholesterol", "blood_pressure", "pain", "sugar"]
RISK_TIERS = ["red", "amber", "green"]

RISK_LABELS = {
    "red": "High attention",       # anticoagulants, narrow therapeutic index, rhythm-critical
    "amber": "Medium attention",   # diuretics, renin-angiotensin drugs
    "green": "Standard",
}
PURPOSE_LABELS = {
    "heart": ("heart", "Herz"), "water": ("water tablet", "Wassertablette"),
    "blood_thinner": ("blood thinner", "Blutverdünner"), "thyroid": ("thyroid", "Schilddrüse"),
    "stomach": ("stomach", "Magen"), "cholesterol": ("cholesterol", "Cholesterin"),
    "blood_pressure": ("blood pressure", "Blutdruck"), "pain": ("pain", "Schmerzen"),
    "sugar": ("sugar", "Zucker"),
}
SCHEDULE_LABELS = {
    "morning": ("morning", "morgens"), "noon": ("noon", "mittags"), "evening": ("evening", "abends"),
    "night": ("night", "zur Nacht"), "with_meal": ("with a meal", "zum Essen"),
}
COLOR_LABELS_DE = {"white": "weiß", "yellow": "gelb", "orange": "orange", "pink": "rosa", "red": "rot",
                   "brown": "braun", "green": "grün", "blue": "blau", "purple": "lila", "grey": "grau"}
SHAPE_LABELS_DE = {"round": "rund", "oval": "oval", "oblong": "länglich", "shield": "schildförmig",
                   "capsule": "Kapsel"}


def size_band(size_mm: float) -> str:
    """small < 7 mm, medium 7–11 mm, large > 11 mm."""
    if size_mm < 7:
        return "small"
    if size_mm <= 11:
        return "medium"
    return "large"


def split_sentence(divisible_parts: int) -> str:
    return {4: "It can be split into quarters.", 2: "It can be split in half."}.get(divisible_parts, "It must not be split.")


def can_split(divisible_parts: int) -> bool:
    return divisible_parts in (2, 4)


def split_label(divisible_parts: int) -> str:
    if divisible_parts == 4:
        return "Can be split (quarters)"
    if divisible_parts == 2:
        return "Can be split"
    return "Do not split"
