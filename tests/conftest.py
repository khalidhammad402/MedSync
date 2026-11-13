import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="medsync_test_")
os.environ["MEDSYNC_DB"] = os.path.join(_tmp, "test.db")
os.environ["USE_LLM_EXTRACTOR"] = "false"
os.environ["MEDSYNC_TODAY"] = ""

import pytest  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app import config, db  # noqa: E402
from app.l1_data import seed as seed_mod  # noqa: E402


@pytest.fixture()
def session():
    seed_mod.reset()
    with Session(db.get_engine()) as s:
        yield s


@pytest.fixture()
def today():
    return config.today()
