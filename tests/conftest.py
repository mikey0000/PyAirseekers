"""Global safety nets only (docs/testing.md §2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from tests._helpers import leaked_secrets

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def no_secrets_in_logs(caplog: pytest.LogCaptureFixture) -> Iterator[None]:
    """Fail any test whose log output carries a fixture secret."""
    caplog.set_level(logging.DEBUG, logger="pyairseekers")
    yield
    leaks = leaked_secrets(caplog.text)
    assert not leaks, f"secrets leaked into logs: {leaks}"
