"""Structured logging that cannot leak customer data.

Log events pass through an allowlist: only known-safe keys (ids, counts,
durations, status codes) are emitted. Anything else, such as document text,
questions, file names or emails, is replaced with "[redacted]". This is safer
than a denylist because new fields are redacted by default.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

SAFE_KEYS: frozenset[str] = frozenset(
    {
        # structlog internals
        "event",
        "level",
        "timestamp",
        "logger",
        "stack",
        # request metadata
        "request_id",
        "method",
        "route",
        "status_code",
        "duration_ms",
        # identifiers (opaque, non-identifying)
        "org_id",
        "user_id",
        "document_id",
        "job_id",
        "membership_id",
        # metrics
        "count",
        "attempt",
        "retry_after",
        "error_type",
        "webhook_type",
        "role",
        # ingestion
        "kind",
        "status",
        "error_code",
        "parser",
        "page_count",
        "chunk_count",
    }
)

REDACTED = "[redacted]"


def redact_unsafe_keys(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        if key not in SAFE_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def summarize_exception(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Replace exc_info with the exception type and stack frames.

    Exception messages can embed customer values (SQL parameters, parsed
    text), so the message itself is never logged.
    """
    exc_info = event_dict.pop("exc_info", None)
    if not exc_info:
        return event_dict
    if exc_info is True:
        exc_info = sys.exc_info()
    if isinstance(exc_info, BaseException):
        exc_info = (type(exc_info), exc_info, exc_info.__traceback__)
    exc_type, _exc, tb = exc_info
    if exc_type is None:
        return event_dict
    event_dict["error_type"] = exc_type.__name__
    frames = []
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append(f"{code.co_filename}:{tb.tb_lineno}:{code.co_name}")
        tb = tb.tb_next
    event_dict["stack"] = frames[-15:]
    return event_dict


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    # Third-party loggers (uvicorn access logs) can include query strings; keep them quiet.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            summarize_exception,
            redact_unsafe_keys,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
