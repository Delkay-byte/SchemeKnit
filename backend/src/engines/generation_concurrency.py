"""Bounded, provider-aware concurrency for lesson-unit generation.

The parent generation run owns one bounded worker pool. A worker never fans
out further: the pool size is the hard ceiling for this run, and the shared
AI spend ledger (``AI_MAX_CONCURRENT_PER_TEACHER`` / ``AI_GLOBAL_MAX_CONCURRENT``)
remains the cross-run authority.

Provider limits are deliberately conservative. They can be overridden for a
measured deployment with ``GENERATION_PROVIDER_CONCURRENCY``, either JSON
(``{"groq": 4}``) or ``groq=4,gemini=1``.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

#: Per-provider simultaneous request ceilings used when nothing overrides them.
#: Values reflect each integration's documented/observed tolerance and the
#: retry behaviour in ``ai_provider``; they are not a promise of free capacity.
PROVIDER_CONCURRENCY_LIMITS: Dict[str, int] = {
    "groq": 3,
    "deepseek": 3,
    "gemini": 1,       # free/authorization-key quotas are the tightest
    "openai": 4,
    "minimax": 2,
    "opencode-zen": 2,
    "ollama": 1,       # local CPU/GPU: parallel calls make each one slower
    "mock": 8,
}

#: Default when a provider has no explicit entry.
DEFAULT_PROVIDER_LIMIT = 2


def _provider_overrides() -> Dict[str, int]:
    raw = (os.environ.get("GENERATION_PROVIDER_CONCURRENCY") or "").strip()
    if not raw:
        return {}
    parsed: Dict[str, int] = {}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if isinstance(data, dict):
            for key, value in data.items():
                try:
                    parsed[str(key).strip().lower()] = max(1, int(value))
                except (TypeError, ValueError):
                    continue
        return parsed
    for part in raw.split(","):
        name, _, value = part.partition("=")
        try:
            parsed[name.strip().lower()] = max(1, int(value))
        except (TypeError, ValueError):
            continue
    return parsed


def provider_concurrency_limit(provider_name: Optional[str]) -> int:
    """Return the simultaneous-request ceiling for one provider."""
    name = str(provider_name or "").strip().lower()
    overrides = _provider_overrides()
    if name in overrides:
        return overrides[name]
    return PROVIDER_CONCURRENCY_LIMITS.get(name, DEFAULT_PROVIDER_LIMIT)


def teacher_ai_concurrency_limit() -> Optional[int]:
    """The existing per-teacher AI cap, or ``None`` when spend control is off."""
    try:
        from .. import ai_spend

        cfg = ai_spend.budget_config()
        if not cfg.get("enabled"):
            return None
        return max(1, int(cfg.get("max_concurrent_per_teacher") or 1))
    except Exception:
        return None


def effective_worker_count(
    requested: Optional[int],
    provider_name: Optional[str],
    *,
    ai_limit: Optional[int] = None,
) -> int:
    """Resolve the safe pool size for one run.

    ``requested`` is ``GENERATION_MAX_CONCURRENCY``. The result is never above
    the provider ceiling or the shared per-teacher AI cap, so a larger
    configured pool cannot cause the spend ledger to reject in-flight lessons.
    """
    try:
        wanted = int(requested or 1)
    except (TypeError, ValueError):
        wanted = 1
    wanted = max(1, wanted)
    provider = provider_concurrency_limit(provider_name)
    hard_ai = teacher_ai_concurrency_limit() if ai_limit is None else ai_limit
    limits = [wanted, provider]
    if hard_ai is not None:
        limits.append(max(1, int(hard_ai)))
    return max(1, min(limits))


def configured_max_concurrency() -> int:
    """Read ``GENERATION_MAX_CONCURRENCY`` from settings (default 1 on error)."""
    try:
        from ..config import get_settings

        return max(1, int(getattr(
            get_settings(), "GENERATION_MAX_CONCURRENCY", 3) or 3))
    except Exception:
        return 3
