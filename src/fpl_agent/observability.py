"""Secret-safe logging and exception helpers."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(password|secret|token|api[_-]?key|authorization|cookie|session|private[_-]?state|b64)",
    re.IGNORECASE,
)


def redact_mapping(
    data: Mapping[str, Any],
    *,
    literal_secrets: Iterable[str] | None = None,
) -> dict[str, Any]:
    literals = [s for s in (literal_secrets or []) if s]
    out: dict[str, Any] = {}
    for key, value in data.items():
        if SECRET_KEY_PATTERN.search(str(key)):
            out[key] = "***REDACTED***"
            continue
        out[key] = redact_value(value, literal_secrets=literals)
    return out


def redact_value(value: Any, *, literal_secrets: Iterable[str] | None = None) -> Any:
    literals = [s for s in (literal_secrets or []) if s]
    if isinstance(value, Mapping):
        return redact_mapping(value, literal_secrets=literals)
    if isinstance(value, list):
        return [redact_value(v, literal_secrets=literals) for v in value]
    if isinstance(value, str):
        text = value
        for secret in literals:
            if secret and secret in text:
                text = text.replace(secret, "***REDACTED***")
        return text
    return value


def safe_exception_message(exc: BaseException, *, literal_secrets: Iterable[str] | None = None) -> str:
    return str(redact_value(str(exc), literal_secrets=literal_secrets))


class RedactingFilter(logging.Filter):
    def __init__(self, literal_secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self.literal_secrets = list(literal_secrets or [])

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_value(record.getMessage(), literal_secrets=self.literal_secrets)
        record.args = ()
        return True


def configure_logging(*, level: int = logging.INFO, literal_secrets: Iterable[str] | None = None) -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in root.handlers:
        handler.addFilter(RedactingFilter(literal_secrets))
