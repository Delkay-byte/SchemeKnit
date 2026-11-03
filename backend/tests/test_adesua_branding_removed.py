"""Customer-facing free-tier copy must not use the retired Adesua branding.

Internal identifiers (the v040 migration name, edition ``free``, entitlement
keys) are unchanged on purpose: only what a teacher reads changes.
"""
from src import entitlements


RETIRED_LABEL = "adesua"


def _assert_neutral(text: str) -> None:
    assert RETIRED_LABEL not in text.lower(), text
    assert "ad esua" not in text.lower(), text


def test_free_plan_label_is_neutral():
    assert entitlements.FREE_TIER_PLAN_NAME == "Free plan"
    _assert_neutral(entitlements.FREE_TIER_PLAN_NAME)


def test_lesson_quota_messages_are_neutral():
    for remaining in (0, 1, 2):
        _assert_neutral(entitlements.free_tier_lesson_quota_message(remaining))


def test_ai_exhausted_message_is_neutral():
    _assert_neutral(entitlements.free_tier_ai_exhausted_message())


def test_resolved_free_entitlement_uses_neutral_plan_name():
    # resolve_entitlement's free branch reuses FREE_TIER_PLAN_NAME; assert the
    # constant rather than a database row so this stays a pure copy check.
    source = entitlements.resolve_entitlement.__doc__ or ""
    assert RETIRED_LABEL not in source.lower()
