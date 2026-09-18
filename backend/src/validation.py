"""
Shared identity validation: password policy and email format.

Both rules are enforced on the backend (the authoritative layer) and mirrored in
the frontend so users get immediate feedback. The backend never trusts the
client, and the client never re-implements a weaker rule.

Password policy
---------------
Minimum 8 characters, containing at least:
  * one letter
  * one digit
  * one symbol (any non-alphanumeric printable character)

Email
-----
A real, RFC-ish email address is the login identifier. It is normalized to
lowercase for storage and comparison (so ``Foo@Example.com`` and
``foo@example.com`` are one account) while display formatting is preserved by
the caller. Placeholders, bare usernames and internal display names are never
accepted as account identifiers.
"""

import re
from typing import Optional, Tuple

# ── Password policy ───────────────────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 8

# One letter, one digit, one symbol (non-alphanumeric). The symbol class is kept
# broad on purpose: any printable non-alphanumeric counts, so international
# punctuation is not excluded.
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")
_HAS_SYMBOL = re.compile(r"[^A-Za-z\d\s]")

PASSWORD_RULES_TEXT = (
    "At least 8 characters, including a letter, a number and a symbol."
)


def validate_password(password: Optional[str]) -> Tuple[bool, str]:
    """Validate a password against the production policy.

    Returns ``(ok, message)``. ``message`` is safe to show users: it states the
    policy, never the specific secret content of the attempt.
    """
    if not password or not isinstance(password, str):
        return False, "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, PASSWORD_RULES_TEXT
    if not _HAS_LETTER.search(password):
        return False, PASSWORD_RULES_TEXT
    if not _HAS_DIGIT.search(password):
        return False, PASSWORD_RULES_TEXT
    if not _HAS_SYMBOL.search(password):
        return False, PASSWORD_RULES_TEXT
    return True, ""


def password_policy_hint() -> str:
    """Human-facing summary of the rule, shown beside the field."""
    return PASSWORD_RULES_TEXT


# ── Email ─────────────────────────────────────────────────────────────────────

# Deliberately pragmatic: catches the malformed identifiers the milestone lists
# (bare usernames, ``teacher@``, ``teacher@school``, ``@school.com``) without
# pretending to be a full RFC 5322 validator. The database unique constraint is
# the second guard.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Normalize an email for storage/comparison: trimmed and lower-cased.

    Returns ``None`` when the value is empty. Callers that treat email as a
    required identifier should validate before storing.
    """
    if email is None:
        return None
    return email.strip().lower() or None


def validate_email(email: Optional[str]) -> Tuple[bool, str]:
    """Validate that ``email`` is a real email address, not a placeholder.

    Accepts ``teacher.name@school.edu.gh``; rejects ``headteacher``,
    ``teacher@``, ``teacher@school`` and ``@school.com``.
    """
    if not email or not isinstance(email, str):
        return False, "A valid email address is required."
    if not _EMAIL_RE.match(email.strip()):
        return False, "Enter a valid email address, e.g. name@school.edu.gh."
    return True, ""
