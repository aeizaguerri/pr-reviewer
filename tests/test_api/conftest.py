"""Local conftest for test_api — no neo4j imports needed here."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def no_configure_logging():
    """Prevent configure_logging() from applying dictConfig during API tests.

    TestClient triggers the FastAPI lifespan, which calls configure_logging().
    dictConfig sets propagate=False on the 'src' logger, breaking caplog in
    observability tests that run later in the same session.
    """
    with patch("backend.main.configure_logging"):
        yield
