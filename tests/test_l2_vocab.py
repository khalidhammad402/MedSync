import pytest
from sqlmodel import select

from app.l1_data.models import Product, Substance
from app.l2_classify import taxonomy as tx
from app.l2_classify import vocab


@pytest.mark.parametrize("word,expected", [
    ("hellgelb", "yellow"), ("gelblich", "yellow"), ("yellowish", "yellow"), ("gelbe", "yellow"),
    ("weiß", "white"), ("weiße", "white"), ("cremefarben", "white"), ("White", "white"),
    ("blaue", "blue"), ("rosa", "pink"), ("grey", "grey"), ("gray", "grey"), ("lila", "purple"),
])
def test_colour_synonyms_both_languages(word, expected):
    assert vocab.normalise_color(word) == expected


def test_other_facets_normalise():
    assert vocab.normalise_shape("runde") == "round"
    assert vocab.normalise_shape("länglich") == "oblong"
    assert vocab.normalise_size("kleine") == "small"
    assert vocab.normalise_schedule("abends") == "evening"
    assert vocab.normalise_schedule("in the morning") == "morning"
    assert vocab.normalise_purpose("Herz") == "heart"
    assert vocab.normalise_purpose("Wassertablette") == "water"
    assert vocab.normalise_purpose("blood thinner") == "blood_thinner"
    assert vocab.normalise_number("drei") == 3 and vocab.normalise_number("two") == 2
    assert vocab.normalise_color("tablet") is None
    assert vocab.normalise("color", "turquoise-ish") is None


def test_size_bands_and_chain_order():
    assert [tx.size_band(x) for x in (6, 6.9, 7, 11, 11.5)] == ["small", "small", "medium", "medium", "large"]
    assert tx.CHAIN_NAMES == ["insurer", "drug", "contract", "product", "appearance"]
    assert [n for n, _, _ in tx.CHAIN_LEVELS] == [1, 2, 3, 4, 5]


def test_every_substance_has_purpose_and_risk(session):
    for s in session.exec(select(Substance)).all():
        assert s.purpose_key in tx.PURPOSES
        assert s.risk_tier in tx.RISK_TIERS
        assert s.plain_purpose_en and s.plain_purpose_de


def test_every_product_has_complete_visual_description(session):
    for p in session.exec(select(Product)).all():
        assert p.color in tx.COLORS and p.shape in tx.SHAPES
        assert tx.size_band(p.size_mm) in tx.SIZE_BANDS
        assert p.score_line in tx.SCORE_LINES
        assert p.divisible_parts in tx.DIVISIBLE_PARTS
        assert p.imprint is not None
