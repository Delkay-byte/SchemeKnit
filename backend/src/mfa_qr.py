"""Local QR rendering for TOTP provisioning URIs.

The provisioning URI contains the pending TOTP secret, so it must never be
sent to an external QR service. ``segno`` is a pure-Python encoder and stays
inside the backend process. The helper returns a data URI so the frontend can
render it with a plain ``<img>`` and no HTML injection.
"""

from __future__ import annotations

import base64
import io

import segno


def provisioning_qr_data_uri(otpauth_uri: str) -> str:
    """Return an inline SVG QR code as a ``data:`` URI.

    Error correction level M tolerates a partially obscured scan without
    inflating the symbol beyond what a setup screen needs.
    """
    qr = segno.make(otpauth_uri, error="m")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=4, border=2, xmldecl=False)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
