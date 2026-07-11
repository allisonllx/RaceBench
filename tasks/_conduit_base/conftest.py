import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest
from fastapi.testclient import TestClient

from conduit.api.deps import reset_schema_flag
from conduit.main import create_app


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "test.db")
    reset_schema_flag()
    app = create_app(db_path=db)
    with TestClient(app) as c:
        yield c
