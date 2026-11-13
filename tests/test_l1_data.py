from sqlmodel import select

from app.l1_data import adapters, seed as seed_mod
from app.l1_data.models import Contract, ContractProduct, Insurer, Patient, Prescription, Product, Substance


def test_seed_is_idempotent(session):
    before = len(session.exec(select(Product)).all())
    assert seed_mod.seed(session) is False
    assert len(session.exec(select(Product)).all()) == before
    assert len(session.exec(select(Insurer)).all()) == 6
    assert len(session.exec(select(Substance)).all()) == 12
    assert [len(adapters.prescriptions_for(session, p.id)) for p in adapters.list_patients(session)] == [8, 6, 5, 4, 4]


def test_reset_restores_seed(session):
    rx = session.exec(select(Prescription)).first()
    rx.instruction_text = "changed"
    session.add(rx)
    session.commit()
    session.close()
    seed_mod.reset()
    assert session.exec(select(Prescription)).first().instruction_text == "1-0-½"


def test_same_drug_differs_by_insurer(session, today):
    meto = session.exec(select(Substance).where(Substance.inn_name.startswith("Metoprolol"))).one()
    src = adapters.mock_sources(session)
    current = {}
    for ins in session.exec(select(Insurer)).all():
        for c in src.contracts.contracts_for(ins.id, meto.id, "47.5 mg"):
            if c.valid_from <= today <= c.valid_to:
                current[ins.short_name] = tuple(c.product_ids)
    assert len({current["Kasse Nord"], current["Kasse Süd"], current["Kasse West"]}) == 3


def test_two_product_contract_is_readable(session):
    counts = {}
    for cp in session.exec(select(ContractProduct)).all():
        counts[cp.contract_id] = counts.get(cp.contract_id, 0) + 1
    multi = [cid for cid, n in counts.items() if n == 2]
    assert len(multi) >= 2
    c = session.get(Contract, multi[0])
    rec = [r for r in adapters.mock_sources(session).contracts.contracts_for(c.insurer_id, c.substance_id, c.strength)
           if r.contract_id == c.id][0]
    assert len(rec.product_ids) == 2


def test_fictional_pzn_range_and_pictures(session):
    for p in session.exec(select(Product)).all():
        assert 99900000 <= int(p.pzn) <= 99999999 and len(p.pzn) == 8
        assert p.image_svg.startswith("<svg")
    assert session.exec(select(Product).where(Product.score_line == "decorative", Product.divisible_parts == 1)).first()
    assert session.exec(select(Product).where(Product.score_line == "functional", Product.divisible_parts == 2)).first()
    assert session.exec(select(Patient)).first().name == "Herr Müller"
