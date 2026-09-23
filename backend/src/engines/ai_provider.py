"""
SchemeKnit AI Provider Abstraction — Generation V2/V3

Optional AI enrichment layer using indicator-grounded, subject-aware prompts.
AI must NEVER be required for core pipeline functionality.

All providers return the SAME canonical structured lesson schema. Provider
choice never changes curriculum authority, quota enforcement, the quality
gate, lesson structure, or allocation rules.

Secrets come ONLY from environment variables (GEMINI_API_KEY, GROQ_API_KEY,
…). Keys are never logged, never sent to the browser, never hard-coded.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import json
import os
import re

#: Named provider keys accepted by ``get_provider`` (lowercase).
NAMED_PROVIDERS = frozenset({
    "gemini", "groq", "openai", "minimax", "ollama", "opencode-zen",
})

#: Auto-selection order when AI is on but no named provider is pinned.
#: Key-only providers first (no network probe); local Ollama last.
_AUTO_PROVIDER_ORDER = ("gemini", "groq", "openai", "opencode-zen", "ollama")

#: Default model IDs — overridable via environment (never assume obsolete IDs).
#: Google's new authorization-key prefix is rejected by :generateContent
#: (ACCESS_TOKEN_TYPE_UNSUPPORTED); gemini-3.x-flash is the current documented
#: stable family. Groq retired llama-3.3-70b-versatile (2026-08-16);
#: openai/gpt-oss-20b is its current replacement.
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

#: Hard timeout for provider HTTP calls (seconds).
PROVIDER_TIMEOUT_SECONDS = 90


def _env(name: str, default: str = "") -> str:
    """Read a configuration value from the process environment.

    Falls back to pydantic Settings when the key is not exported to
    ``os.environ`` (pydantic loads ``.env`` into Settings only).
    """
    val = os.environ.get(name)
    if val is not None and val != "":
        return val
    try:
        from ..config import get_settings
        settings = get_settings()
        return str(getattr(settings, name, default) or default)
    except Exception:
        return default


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers models often add around JSON payloads,
    including unclosed fences from truncated generations."""
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```(?:json)?\s*(.*)$", text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return text


class AIResponseParseError(RuntimeError):
    """The AI response could not be parsed into a valid dict.

    Raised by ``_parse_json_response`` so callers can record a structured,
    secret-free diagnostic (malformed_json / schema_invalid / empty_response)
    instead of conflating "valid empty object" with "failed to parse".
    """


def _parse_json_response(text: str) -> dict:
    """Parse JSON from model output, handling markdown fences.

    Raises ``AIResponseParseError`` on empty, malformed, or non-object JSON so
    callers can distinguish "empty output" from "valid empty object" and never
    report a false success. Use ``_parse_or_diagnose`` in providers.
    """
    if not text:
        raise AIResponseParseError("empty_response")
    cleaned = _strip_fences(text)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                raise AIResponseParseError("malformed_json")
        else:
            raise AIResponseParseError("malformed_json")
    if not isinstance(parsed, dict):
        raise AIResponseParseError("schema_invalid")
    return parsed


def _validate_v2_content(content: Any) -> bool:
    """True if the parsed payload carries the canonical V2 lesson shape."""
    if not isinstance(content, dict):
        return False
    return any(key in content for key in (
        "learning_objectives", "starter", "main_learning", "assessment", "plenary",
    ))


def _parse_or_diagnose(
    provider: "AIProvider",
    text: str,
    *,
    require_lesson_schema: bool = False,
) -> dict:
    """Parse a provider response into a dict, recording a structured diagnostic.

    Never raises and never reports a false success:
      * empty text        → {} (transport/availability error already recorded)
      * malformed JSON    → {} with provider.last_error = "malformed_json"
      * non-object JSON   → {} with provider.last_error = "schema_invalid"
      * V2 schema missing → {} with provider.last_error = "schema_invalid"
    """
    if not text:
        return {}
    try:
        parsed = _parse_json_response(text)
    except AIResponseParseError:
        provider.last_error = "malformed_json"
        return {}
    if require_lesson_schema and not _validate_v2_content(parsed):
        provider.last_error = "schema_invalid"
        return {}
    return parsed


def provider_status(provider: "AIProvider") -> str:
    """Classify a provider's state (Phase 16I/16C).

    Config availability never implies live success: "CONFIGURED" only means a
    key is present (or Ollama is reachable). Live calls then resolve to a
    success/failure state recorded in ``last_error``.
    """
    if provider is None:
        return "NOT_CONFIGURED"
    if not provider.is_available():
        return "MISSING_KEY"
    error = getattr(provider, "last_error", None)
    if error in ("auth_failed", "auth_key_rejected", "invalid_api_key"):
        return "LIVE_AUTH_FAILURE"
    if error in ("model_not_found", "http_404"):
        return "MODEL_UNAVAILABLE"
    if error == "rate_limit":
        return "LIVE_RATE_LIMITED"
    if error is None:
        return "CONFIGURED"
    if error in ("content_refusal", "empty_output"):
        return "LIVE_EMPTY_OUTPUT"
    return "LIVE_ERROR"


def _record_error(provider: "AIProvider", exc: Exception) -> None:
    """Store a secret-free diagnostic on the provider instance.

    Exception text from HTTP libraries can embed request URLs; Gemini auth
    uses a header (never a query param) and Groq/OpenAI use Authorization
    headers, so keys do not appear in these messages. We still truncate hard.
    """
    provider.last_error = f"{type(exc).__name__}: {exc}"[:300]


def _build_v2_prompt_from_context(
    *,
    subject: str,
    class_level: str,
    strand: str,
    sub_strand: str,
    content_standard: str,
    indicator_code: str,
    indicator_text: str,
    class_size: int = 35,
    duration_minutes: int = 60,
    source_resources: Optional[list] = None,
    previous_lesson_context: Optional[str] = None,
    next_lesson_context: Optional[str] = None,
    teaching_day: Optional[str] = None,
    week_number: Optional[int] = None,
    source_week_ending: Optional[str] = None,
    term: Optional[str] = None,
    teaching_week: Optional[int] = None,
    period: Optional[str] = None,
    teacher_keywords: Optional[list] = None,
    other_tlrs: Optional[list] = None,
    core_competencies: Optional[list] = None,
    references: Optional[list] = None,
) -> str:
    """Build a V2 prompt directly from context (no indicator interpretation needed)."""
    from ..curriculum.indicator_interpreter import interpret_indicator, Indicator
    from ..curriculum.generation_prompt import build_generation_prompt

    ind = Indicator(
        code=indicator_code,
        exact_text=f"{indicator_code} {indicator_text}",
        description=indicator_text,
        source_week=week_number or 0,
        source_subject=subject,
    )
    interp = interpret_indicator(ind, subject)

    return build_generation_prompt(
        subject=subject,
        class_level=class_level,
        strand=strand,
        sub_strand=sub_strand,
        content_standard=content_standard,
        indicator_code=indicator_code,
        indicator_text=indicator_text,
        interpretation=interp,
        class_size=class_size,
        duration_minutes=duration_minutes,
        source_resources=source_resources,
        previous_lesson_context=previous_lesson_context,
        next_lesson_context=next_lesson_context,
        teaching_day=teaching_day,
        week_number=week_number,
        source_week_ending=source_week_ending,
        term=term,
        teaching_week=teaching_week,
        period=period,
        teacher_keywords=teacher_keywords,
        other_tlrs=other_tlrs,
        core_competencies=core_competencies,
        references=references,
    )


class AIProvider(ABC):
    """Base AI provider interface."""

    #: Secret-free diagnostic from the most recent failure (None when healthy).
    last_error: Optional[str] = None

    def generate_lesson_content(
        self,
        indicator: str,
        strand: str,
        sub_strand: str,
        content_standard: str,
        lesson_type: str = "instruction",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Legacy V1 generation — flat string output. Kept for backward compat."""
        return {}

    def generate_lesson_v2(
        self,
        *,
        subject: str,
        class_level: str,
        strand: str,
        sub_strand: str,
        content_standard: str,
        indicator_code: str,
        indicator_text: str,
        class_size: int = 35,
        duration_minutes: int = 60,
        source_resources: Optional[list] = None,
        previous_lesson_context: Optional[str] = None,
        next_lesson_context: Optional[str] = None,
        teaching_day: Optional[str] = None,
        week_number: Optional[int] = None,
        source_week_ending: Optional[str] = None,
        term: Optional[str] = None,
        teaching_week: Optional[int] = None,
        period: Optional[str] = None,
        teacher_keywords: Optional[list] = None,
        other_tlrs: Optional[list] = None,
        core_competencies: Optional[list] = None,
        references: Optional[list] = None,
    ) -> Dict[str, Any]:
        """V2 structured lesson generation.

        Returns a dict matching the Generation V2 output schema, or {} on failure.
        The caller applies the quality gate before marking the lesson ready.
        """
        return {}

    def generate_structured(self, prompt: str) -> dict:
        """Raw prompt in, parsed JSON dict out ({} on any failure).

        Used by section regeneration and lesson enrichment. Providers that
        support structured output override this with schema-enforced calls.
        """
        return {}

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is configured and available."""
        pass

    def get_name(self) -> str:
        return "base"


class MockProvider(AIProvider):
    """Mock provider for testing and OFF mode."""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        return {}

    def is_available(self) -> bool:
        return True

    def get_name(self) -> str:
        return "mock"


class GeminiProvider(AIProvider):
    """Google Gemini API provider (REST — no SDK dependency).

    Model is configurable via GEMINI_MODEL (default: current stable Flash).
    Auth uses the ``x-goog-api-key`` header so the key never appears in URLs
    or logs. Structured output uses ``responseMimeType: application/json``.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or _env("GEMINI_API_KEY")
        self.model = (model or _env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL).strip()

    def _generate_text(self, prompt: str, *, json_mode: bool = False,
                       system: Optional[str] = None) -> str:
        import requests

        self.last_error = None
        if not self.is_available():
            self.last_error = "missing_api_key"
            return ""
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        body: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        try:
            resp = requests.post(
                url,
                json=body,
                headers={"x-goog-api-key": self.api_key},
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            if resp.status_code == 429:
                self.last_error = "rate_limit"
                return ""
            if resp.status_code in (401, 403):
                # Google's current auth model: AI Studio issues authorization
                # keys, which ARE the supported credential format on the native
                # REST surface via x-goog-api-key (Bearer is only for
                # /v1beta/openai). A 401 ACCESS_TOKEN_TYPE_UNSUPPORTED
                # therefore means the specific key string was rejected — invalid,
                # truncated, expired, or constrained to another Google service —
                # NOT that the key format is unsupported. The owner must verify
                # or regenerate the key in AI Studio (restricted to Gemini API),
                # not downgrade to the legacy standard-key format.
                body = resp.text or ""
                if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in body:
                    self.last_error = "auth_key_rejected"
                else:
                    self.last_error = "auth_failed"
                return ""
            if resp.status_code == 400 and "API key not valid" in resp.text:
                self.last_error = "invalid_api_key"
                return ""
            if resp.status_code == 404:
                self.last_error = "model_not_found"
                return ""
            if resp.status_code >= 500:
                self.last_error = f"http_{resp.status_code}"
                return ""
            if resp.status_code != 200:
                self.last_error = f"http_{resp.status_code}"
                return ""
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                # Content refusal / safety block / empty output
                feedback = data.get("promptFeedback") or {}
                block = feedback.get("blockReason") or data.get("promptFeedback", {}).get("blockReason")
                self.last_error = f"empty_or_refused:{block}" if block else "empty_output"
                return ""
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
            if not text.strip():
                self.last_error = "empty_output"
                return ""
            return text
        except Exception as exc:
            _record_error(self, exc)
            return ""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        prompt = _build_v2_prompt_from_context(
            subject=context.get("subject", strand) if context else strand,
            class_level=context.get("class_level", "") if context else "",
            strand=strand, sub_strand=sub_strand,
            content_standard=content_standard,
            indicator_code=context.get("indicator_code", "") if context else "",
            indicator_text=indicator,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._generate_text(prompt, json_mode=True, system=SYSTEM_PROMPT),
        )

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           source_week_ending=None,
                           term=None, teaching_week=None, period=None,
                           teacher_keywords=None, other_tlrs=None,
                           core_competencies=None, references=None):
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
            previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
            term=term, teaching_week=teaching_week, period=period,
            teacher_keywords=teacher_keywords,
                            source_week_ending=source_week_ending,
                            other_tlrs=other_tlrs,
                            core_competencies=core_competencies,
                            references=references,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._generate_text(prompt, json_mode=True, system=SYSTEM_PROMPT),
            require_lesson_schema=True,
        )

    def generate_structured(self, prompt: str) -> dict:
        return _parse_or_diagnose(self, self._generate_text(prompt, json_mode=True))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "gemini"


class GroqProvider(AIProvider):
    """Groq API provider (OpenAI-compatible chat completions).

    Model is configurable via GROQ_MODEL. Auth is a Bearer header — the key
    is never placed in URLs, logs, or frontend code.
    """

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or _env("GROQ_API_KEY")
        self.model = (model or _env("GROQ_MODEL", DEFAULT_GROQ_MODEL) or DEFAULT_GROQ_MODEL).strip()
        self.base_url = _env("GROQ_BASE_URL", self.BASE_URL) or self.BASE_URL

    def _chat(self, prompt: str, *, json_mode: bool = False,
              system: Optional[str] = None) -> str:
        import requests

        self.last_error = None
        if not self.is_available():
            self.last_error = "missing_api_key"
            return ""
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
            if resp.status_code == 429:
                self.last_error = "rate_limit"
                return ""
            if resp.status_code in (401, 403):
                self.last_error = "auth_failed"
                return ""
            if resp.status_code == 404:
                self.last_error = "model_not_found"
                return ""
            if resp.status_code >= 500:
                self.last_error = f"http_{resp.status_code}"
                return ""
            if resp.status_code != 200:
                # Some models reject response_format — retry once without it.
                if json_mode and resp.status_code == 400:
                    body.pop("response_format", None)
                    resp = requests.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        json=body,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        timeout=PROVIDER_TIMEOUT_SECONDS,
                    )
                if resp.status_code != 200:
                    self.last_error = f"http_{resp.status_code}"
                    return ""
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                self.last_error = "empty_output"
                return ""
            message = choices[0].get("message") or {}
            # Groq may signal refusal in message.refusal
            if message.get("refusal"):
                self.last_error = "content_refusal"
                return ""
            content = message.get("content") or ""
            if not str(content).strip():
                self.last_error = "empty_output"
                return ""
            return str(content)
        except Exception as exc:
            _record_error(self, exc)
            return ""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        prompt = _build_v2_prompt_from_context(
            subject=context.get("subject", strand) if context else strand,
            class_level=context.get("class_level", "") if context else "",
            strand=strand, sub_strand=sub_strand,
            content_standard=content_standard,
            indicator_code=context.get("indicator_code", "") if context else "",
            indicator_text=indicator,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._chat(prompt, json_mode=True, system=SYSTEM_PROMPT),
        )

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           source_week_ending=None,
                           term=None, teaching_week=None, period=None,
                           teacher_keywords=None, other_tlrs=None,
                           core_competencies=None, references=None):
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
            previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
            term=term, teaching_week=teaching_week, period=period,
            teacher_keywords=teacher_keywords,
                            source_week_ending=source_week_ending,
                            other_tlrs=other_tlrs,
                            core_competencies=core_competencies,
                            references=references,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._chat(prompt, json_mode=True, system=SYSTEM_PROMPT),
            require_lesson_schema=True,
        )

    def generate_structured(self, prompt: str) -> dict:
        return _parse_or_diagnose(self, self._chat(prompt, json_mode=True))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "groq"


class OpenAIProvider(AIProvider):
    """OpenAI API provider. Model configurable via OPENAI_MODEL."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or _env("OPENAI_API_KEY")
        self.model = (model or _env("OPENAI_MODEL", DEFAULT_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL).strip()

    def _chat(self, prompt: str, *, json_mode: bool = False,
              system: Optional[str] = None) -> str:
        self.last_error = None
        if not self.is_available():
            self.last_error = "missing_api_key"
            return ""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, timeout=PROVIDER_TIMEOUT_SECONDS)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            else:
                messages.append({
                    "role": "system",
                    "content": "You are an expert Ghanaian educator. Output valid JSON only.",
                })
            messages.append({"role": "user", "content": prompt})
            kwargs: Dict[str, Any] = dict(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception:
                # Older models reject response_format — retry once without it.
                kwargs.pop("response_format", None)
                response = client.chat.completions.create(**kwargs)
            choices = response.choices or []
            if not choices:
                self.last_error = "empty_output"
                return ""
            content = choices[0].message.content or ""
            if not content.strip():
                self.last_error = "empty_output"
                return ""
            return content
        except Exception as exc:
            _record_error(self, exc)
            return ""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        prompt = _build_v2_prompt_from_context(
            subject=context.get("subject", strand) if context else strand,
            class_level=context.get("class_level", "") if context else "",
            strand=strand, sub_strand=sub_strand,
            content_standard=content_standard,
            indicator_code=context.get("indicator_code", "") if context else "",
            indicator_text=indicator,
        )
        return _parse_or_diagnose(self, self._chat(prompt, json_mode=True))

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           source_week_ending=None,
                           term=None, teaching_week=None, period=None,
                           teacher_keywords=None, other_tlrs=None,
                           core_competencies=None, references=None):
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
            previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
            term=term, teaching_week=teaching_week, period=period,
            teacher_keywords=teacher_keywords,
                            source_week_ending=source_week_ending,
                            other_tlrs=other_tlrs,
                            core_competencies=core_competencies,
                            references=references,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._chat(prompt, json_mode=True, system=SYSTEM_PROMPT),
            require_lesson_schema=True,
        )

    def generate_structured(self, prompt: str) -> dict:
        return _parse_or_diagnose(self, self._chat(prompt, json_mode=True))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "openai"


class MiniMaxProvider(AIProvider):
    """MiniMax API provider (stub — configured key only, no generation)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _env("MINIMAX_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "minimax"


class OpenCodeZenProvider(AIProvider):
    """OpenCode Zen provider — OpenAI-compatible gateway with free models."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or _env("OPENCODE_ZEN_API_KEY")
        self.model = model or _env("OPENCODE_ZEN_MODEL", "nemotron-3-ultra-free")
        self.base_url = _env("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1")

    def _chat(self, prompt: str, *, json_mode: bool = False,
              system: Optional[str] = None) -> str:
        self.last_error = None
        if not self.is_available():
            self.last_error = "missing_api_key"
            return ""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                            timeout=PROVIDER_TIMEOUT_SECONDS)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            else:
                messages.append({
                    "role": "system",
                    "content": "You are an expert Ghanaian educator. Output valid JSON only. No markdown fences.",
                })
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
            )
            choices = response.choices or []
            if not choices:
                self.last_error = "empty_output"
                return ""
            content = choices[0].message.content or ""
            if not content.strip():
                self.last_error = "empty_output"
                return ""
            return content
        except Exception as exc:
            _record_error(self, exc)
            return ""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        prompt = _build_v2_prompt_from_context(
            subject=context.get("subject", strand) if context else strand,
            class_level=context.get("class_level", "") if context else "",
            strand=strand, sub_strand=sub_strand,
            content_standard=content_standard,
            indicator_code=context.get("indicator_code", "") if context else "",
            indicator_text=indicator,
        )
        return _parse_or_diagnose(self, self._chat(prompt, json_mode=True))

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           source_week_ending=None,
                           term=None, teaching_week=None, period=None,
                           teacher_keywords=None, other_tlrs=None,
                           core_competencies=None, references=None):
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
            previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
            term=term, teaching_week=teaching_week, period=period,
            teacher_keywords=teacher_keywords,
                            source_week_ending=source_week_ending,
                            other_tlrs=other_tlrs,
                            core_competencies=core_competencies,
                            references=references,
        )
        from ..curriculum.generation_prompt import SYSTEM_PROMPT
        return _parse_or_diagnose(
            self,
            self._chat(prompt, json_mode=True, system=SYSTEM_PROMPT),
            require_lesson_schema=True,
        )

    def generate_structured(self, prompt: str) -> dict:
        return _parse_or_diagnose(self, self._chat(prompt, json_mode=True))

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "opencode-zen"


class OllamaProvider(AIProvider):
    """Ollama local provider. Model via OLLAMA_MODEL env (default llama3).

    Local Ollama NEVER bypasses commercial quota or entitlement checks —
    those are enforced by callers before any provider is constructed.
    """

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or _env("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or _env("OLLAMA_MODEL", "llama3")

    def _generate(self, prompt: str) -> str:
        import requests

        self.last_error = None
        try:
            # Full V2 lesson JSON regularly exceeds 800 tokens and was
            # truncated mid-object on real-doc runs (unparseable → empty).
            # 2048 covers the schema with headroom for differentiation/notes.
            timeout = _env("OLLAMA_TIMEOUT_SECONDS", "180")
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": 2048}},
                timeout=int(timeout) if str(timeout).isdigit() else 180,
            )
            if resp.status_code != 200:
                self.last_error = f"http_{resp.status_code}"
                return ""
            data = resp.json()
            text = data.get("response", "")
            if not str(text).strip():
                self.last_error = "empty_output"
                return ""
            return str(text)
        except Exception as exc:
            _record_error(self, exc)
            return ""

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None, section=None):
        if not self.is_available():
            self.last_error = "unavailable"
            return {}
        if section:
            prompt = (
                f"Write the '{section}' section for a lesson on: {strand} - {sub_strand}\n"
                f"Indicator: {indicator}\n"
                f"Return ONLY a JSON object with a single string key '{section}'. "
                f"No markdown fences. Keep it under 120 words."
            )
        else:
            prompt = _build_v2_prompt_from_context(
                subject=context.get("subject", strand) if context else strand,
                class_level=context.get("class_level", "") if context else "",
                strand=strand, sub_strand=sub_strand,
                content_standard=content_standard,
                indicator_code=context.get("indicator_code", "") if context else "",
                indicator_text=indicator,
            )
        return _parse_or_diagnose(self, self._generate(prompt))

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None,
                           source_week_ending=None,
                           term=None, teaching_week=None, period=None,
                           teacher_keywords=None, other_tlrs=None,
                           core_competencies=None, references=None):
        if not self.is_available():
            self.last_error = "unavailable"
            return {}
        prompt = _build_v2_prompt_from_context(
            subject=subject, class_level=class_level, strand=strand,
            sub_strand=sub_strand, content_standard=content_standard,
            indicator_code=indicator_code, indicator_text=indicator_text,
            class_size=class_size, duration_minutes=duration_minutes,
            source_resources=source_resources,
previous_lesson_context=previous_lesson_context,
            next_lesson_context=next_lesson_context,
            teaching_day=teaching_day, week_number=week_number,
            term=term, teaching_week=teaching_week, period=period,
            teacher_keywords=teacher_keywords,
                            source_week_ending=source_week_ending,
                            other_tlrs=other_tlrs,
                            core_competencies=core_competencies,
                            references=references,
        )
        return _parse_or_diagnose(self, self._generate(prompt), require_lesson_schema=True)

    def generate_structured(self, prompt: str) -> dict:
        if not self.is_available():
            self.last_error = "unavailable"
            return {}
        return _parse_or_diagnose(self, self._generate(prompt))

    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def get_name(self) -> str:
        return "ollama"


def get_provider(mode: str = "OFF", **kwargs) -> AIProvider:
    """Factory function to get the appropriate AI provider.

    ``OFF`` / ``BASIC`` / ``ENHANCED`` map to MockProvider (deterministic
    engine) — use ``resolve_provider_mode`` first when AI should reach a
    real provider. Unknown keys also fall back to Mock.
    """
    key = (mode or "OFF").strip()
    providers = {
        "OFF": MockProvider,
        "BASIC": MockProvider,
        "ENHANCED": MockProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "openai": OpenAIProvider,
        "minimax": MiniMaxProvider,
        "ollama": OllamaProvider,
        "opencode-zen": OpenCodeZenProvider,
    }
    provider_class = providers.get(key, MockProvider)
    try:
        return provider_class(**kwargs)
    except TypeError:
        return provider_class()


def resolve_provider_mode(ai_mode: Any) -> str:
    """Map a generation config's ``ai_mode`` onto a ``get_provider`` key.

    * ``OFF`` → ``"OFF"`` (never reaches a provider).
    * A named provider pinned in the ``AI_MODE`` environment setting
      (``gemini``, ``groq``, …) wins when AI is on.
    * Otherwise auto-select the first available real provider
      (key present, or local Ollama reachable).
    * If none is available, return the original ``BASIC``/``ENHANCED``
      token so the pipeline falls back to Mock/deterministic content.

    Provider choice never changes curriculum authority, quota, quality gate,
    lesson structure, or allocation — only the content source.
    """
    value = ai_mode.value if hasattr(ai_mode, "value") else str(ai_mode or "OFF")
    value = value.strip()
    if value.upper() == "OFF":
        return "OFF"
    if value.lower() in NAMED_PROVIDERS:
        return value.lower()

    pinned = (_env("AI_MODE", "") or "").strip().lower()
    if pinned in NAMED_PROVIDERS:
        return pinned

    # Auto-select: key-only providers first (no network), Ollama last.
    for candidate in _AUTO_PROVIDER_ORDER:
        if candidate == "ollama":
            # Only probe the network when nothing else is configured.
            provider = get_provider(candidate)
            try:
                if provider.is_available():
                    return candidate
            except Exception:
                continue
            continue
        provider = get_provider(candidate)
        if provider.is_available():
            return candidate

    # No real provider configured → deterministic Mock path.
    return value if value.upper() in ("BASIC", "ENHANCED") else "BASIC"
