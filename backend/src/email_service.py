"""
SchemeKnit Email Service
========================

Provider-agnostic transactional email for production lifecycle features:

  * password reset / account recovery
  * school activation / invitations
  * subscription notifications
  * license notifications
  * security notifications

Provider: Resend (https://resend.com) — a modern transactional email API.

Configuration (server-side environment variables ONLY)
------------------------------------------------------
    RESEND_API_KEY=re_xxxxx           # NEVER expose to browser code.
                                     # NEVER use NEXT_PUBLIC_RESEND_API_KEY.
    EMAIL_FROM=notify@schemeknit.com  # verified sending domain
    EMAIL_REPLY_TO=support@schemeknit.com

Failure behaviour
-----------------
If email sending fails the caller receives a controlled ``EmailResult``
with ``success=False`` and a safe, generic error message.  Provider
secrets and raw API errors are NEVER surfaced to the end user; they are
logged server-side at ``error`` level with the key redacted.

Do not tell a user: "Resend API error: ..."
Do tell a user:  "Unable to send email at this time. Please try again later."
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .logging_config import get_logger

logger = get_logger()

RESEND_API_URL = "https://api.resend.com/emails"


@dataclass
class EmailResult:
    """Outcome of an email send attempt."""
    success: bool
    message: str = ""
    provider_id: str = ""
    # Internal detail — never serialized to client responses
    _internal_error: str = field(default="", repr=False)


class EmailService:
    """Resend-backed transactional email.

    All methods return ``EmailResult`` — they never raise, so callers can
    degrade gracefully (e.g. fall back to displaying a reset token in the
    admin UI when email delivery is unavailable).
    """

    def __init__(
        self,
        api_key: str = "",
        from_email: str = "",
        reply_to: str = "",
    ):
        self.api_key = api_key
        self.from_email = from_email
        self.reply_to = reply_to or from_email
        self._enabled = bool(api_key and from_email)

    # ── Low-level send ────────────────────────────────────────────────

    def _send(self, to: str, subject: str, html: str,
              text: str = "") -> EmailResult:
        if not self._enabled:
            logger.warning("email_not_configured", to=to, subject=subject)
            return EmailResult(
                success=False,
                message="Email delivery is not configured on this server.",
            )

        try:
            with httpx.Client(timeout=30.0) as client:
                payload = {
                    "from": self.from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
                if text:
                    payload["text"] = text
                if self.reply_to and self.reply_to != self.from_email:
                    payload["reply_to"] = self.reply_to

                resp = client.post(
                    RESEND_API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if resp.status_code in (200, 201):
                data = resp.json()
                pid = data.get("id", "")
                logger.info("email_sent", to=to, subject=subject, provider_id=pid)
                return EmailResult(success=True, provider_id=pid)

            # Provider rejected — log full detail server-side, give the
            # user only a safe generic message.
            body = resp.text[:500]
            logger.error(
                "email_provider_error",
                to=to, subject=subject,
                status_code=resp.status_code,
                provider_response=body,
                api_key=_redact(self.api_key),
            )
            return EmailResult(
                success=False,
                message="Unable to send email at this time. Please try again later.",
                _internal_error=f"provider returned {resp.status_code}: {body}",
            )

        except Exception as exc:
            logger.error(
                "email_send_failed",
                to=to, subject=subject,
                error=str(exc),
                api_key=_redact(self.api_key),
            )
            return EmailResult(
                success=False,
                message="Unable to send email at this time. Please try again later.",
                _internal_error=str(exc),
            )

    # ── Lifecycle emails ──────────────────────────────────────────────

    def send_password_reset(
        self, to: str, reset_url: str, expiry_hours: float = 0.5,
    ) -> EmailResult:
        """Password-reset link (or embedded token) to a user."""
        hours_str = f"{expiry_hours:.0f} minutes" if expiry_hours < 1 else f"{expiry_hours:.0f} hours"
        return self._send(
            to=to,
            subject="Reset your SchemeKnit password",
            html=(
                f"<div style='font-family:sans-serif;max-width:480px;margin:auto'>"
                f"<h2 style='color:#102A43'>Reset your SchemeKnit password</h2>"
                f"<p>We received a request to reset the password on your "
                f"SchemeKnit account.</p>"
                f"<p><a href='{reset_url}' style='background:#04A9CE;color:#fff;"
                f"padding:10px 20px;border-radius:6px;text-decoration:none'>"
                f"Reset password</a></p>"
                f"<p style='color:#666'>This link expires in {hours_str}.</p>"
                f"<p style='color:#666'>If you did not request this, you can "
                f"safely ignore this email.</p>"
                f"</div>"
            ),
            text=f"Reset your SchemeKnit password: {reset_url}\n"
                 f"This link expires in {hours_str}.",
        )

    def send_welcome(self, to: str, name: str = "") -> EmailResult:
        """Welcome a newly created account."""
        greeting = f"Welcome, {name}!" if name else "Welcome!"
        return self._send(
            to=to,
            subject="Welcome to SchemeKnit",
            html=(
                f"<div style='font-family:sans-serif;max-width:480px;margin:auto'>"
                f"<h2 style='color:#102A43'>{greeting}</h2>"
                f"<p>Your SchemeKnit account has been created. You can now "
                f"sign in and start creating professional lesson plans.</p>"
                f"</div>"
            ),
            text=f"{greeting} Your SchemeKnit account has been created.",
        )

    def send_school_activation(
        self, to: str, school_name: str, activation_url: str = "",
    ) -> EmailResult:
        """Notify a school that their SchemeKnit license is active."""
        link_html = ""
        if activation_url:
            link_html = (
                f"<p><a href='{activation_url}' style='background:#04A9CE;"
                f"color:#fff;padding:10px 20px;border-radius:6px;"
                f"text-decoration:none'>Get started</a></p>"
            )
        return self._send(
            to=to,
            subject=f"SchemeKnit is active for {school_name}",
            html=(
                f"<div style='font-family:sans-serif;max-width:480px;margin:auto'>"
                f"<h2 style='color:#102A43'>Your school is ready</h2>"
                f"<p>SchemeKnit has been activated for <strong>{school_name}</strong>. "
                f"Teachers can now be added and lesson plans generated.</p>"
                f"{link_html}"
                f"</div>"
            ),
            text=f"SchemeKnit is active for {school_name}.",
        )

    def send_subscription_notification(
        self, to: str, plan_name: str, amount: str = "",
        expiry: str = "",
    ) -> EmailResult:
        """Subscription receipt / renewal notice."""
        detail = f" ({amount})" if amount else ""
        exp = f" Valid until {expiry}." if expiry else ""
        return self._send(
            to=to,
            subject=f"SchemeKnit {plan_name} subscription{detail}",
            html=(
                f"<div style='font-family:sans-serif;max-width:480px;margin:auto'>"
                f"<h2 style='color:#102A43'>Subscription confirmation</h2>"
                f"<p>Your <strong>{plan_name}</strong> subscription is active.{exp}</p>"
                f"</div>"
            ),
            text=f"Your {plan_name} subscription is active.{exp}",
        )


def _redact(secret: str) -> str:
    """Redact a secret for safe logging: show only first 6 + last 4 chars."""
    if not secret or len(secret) < 12:
        return "[REDACTED]"
    return f"{secret[:6]}...{secret[-4:]}"


# ── Factory ─────────────────────────────────────────────────────────────

_email: Optional[EmailService] = None


def get_email() -> EmailService:
    """Return the process-wide email service (lazy singleton).

    Reads environment at first call, so monkeypatched env vars work in tests.
    """
    global _email
    if _email is None:
        _email = EmailService(
            api_key=os.environ.get("RESEND_API_KEY", ""),
            from_email=os.environ.get("EMAIL_FROM", ""),
            reply_to=os.environ.get("EMAIL_REPLY_TO", ""),
        )
    return _email
