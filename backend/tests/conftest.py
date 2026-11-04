import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="tollgate-test-")
os.environ["TOLLGATE_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TOLLGATE_LOCAL_STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["TOLLGATE_INFERENCE_API_KEY"] = ""
os.environ["TOLLGATE_MAIL_ENABLED"] = "false"
os.environ["TOLLGATE_GMAIL_ADDRESS"] = ""

import pytest  # noqa: E402

from tollgate.db import Base, engine, init_db, session_scope  # noqa: E402


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    init_db()
    from tollgate.seed import reset_and_seed

    with session_scope() as s:
        reset_and_seed(s)
    yield
