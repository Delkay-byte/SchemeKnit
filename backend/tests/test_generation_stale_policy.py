"""Operational policy for generation stale detection and heartbeats.

The duration is configurable, but invalid or unsafe combinations must fail at
startup rather than silently reclaiming live work or leaving crashed jobs
unrecoverable forever.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_stale_duration_and_heartbeat_defaults_are_documented():
    settings = Settings()
    assert settings.GENERATION_STALE_MINUTES == 60
    assert settings.GENERATION_HEARTBEAT_SECONDS == 30
    # The heartbeat must beat more than once inside the stale window.
    assert (
        settings.GENERATION_HEARTBEAT_SECONDS
        < settings.GENERATION_STALE_MINUTES * 60
    )


@pytest.mark.parametrize("minutes", [0, -1, 1_441, 10_000])
def test_stale_duration_rejects_invalid_values(minutes):
    with pytest.raises(ValidationError):
        Settings(GENERATION_STALE_MINUTES=minutes)


@pytest.mark.parametrize("seconds", [0, -5, 3_601, 100_000])
def test_heartbeat_interval_rejects_invalid_values(seconds):
    with pytest.raises(ValidationError):
        Settings(GENERATION_HEARTBEAT_SECONDS=seconds)


def test_heartbeat_must_fit_inside_the_stale_window():
    with pytest.raises(ValidationError):
        Settings(
            GENERATION_STALE_MINUTES=1,
            GENERATION_HEARTBEAT_SECONDS=60,
        )


def test_valid_non_default_configuration_is_accepted():
    settings = Settings(
        GENERATION_STALE_MINUTES=15,
        GENERATION_HEARTBEAT_SECONDS=10,
    )
    assert settings.GENERATION_STALE_MINUTES == 15
    assert settings.GENERATION_HEARTBEAT_SECONDS == 10
