import json

import pytest
import structlog

from sqa.core.logging import REDACTED, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _json_logging() -> None:
    structlog.reset_defaults()
    configure_logging("INFO", json=True)


def test_unknown_keys_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    get_logger("t").info(
        "search", org_id="o1", query="do you encrypt data at rest", filename="soc2.pdf"
    )
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["org_id"] == "o1"
    assert line["query"] == REDACTED
    assert line["filename"] == REDACTED


def test_exception_message_is_not_logged(capsys: pytest.CaptureFixture[str]) -> None:
    try:
        raise ValueError("customer secret: ACME uses AES-256")
    except ValueError as exc:
        get_logger("t").error("failed", exc_info=exc)
    out = capsys.readouterr().out
    assert "ACME" not in out
    line = json.loads(out.strip().splitlines()[-1])
    assert line["error_type"] == "ValueError"
    assert line["stack"]
