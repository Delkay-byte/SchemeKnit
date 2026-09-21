"""
SchemeKnit AI Provider Abstraction — Generation V2

Optional AI enrichment layer using indicator-grounded, subject-aware prompts.
AI must NEVER be required for core pipeline functionality.

V2 providers return structured lesson objects matching the Generation V2 schema.
The quality gate runs AFTER provider output and BEFORE marking a lesson ready.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import json
import os
import re


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


def _parse_json_response(text: str) -> dict:
    """Safely parse JSON from model output, handling markdown fences."""
    if not text:
        return {}
    cleaned = _strip_fences(text)
    try:
        return json.loads(cleaned)
    except Exception:
        # Try to extract JSON object from surrounding text
        m = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {}


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
) -> str:
    """Build a V2 prompt directly from context (no indicator interpretation needed).

    This is the lightweight path for providers that don't need the full
    CurriculumDocument IR — they just need the prompt built from context.
    """
    from ..curriculum.indicator_interpreter import interpret_indicator, Indicator
    from ..curriculum.generation_prompt import build_generation_prompt

    # Create a temporary indicator for interpretation
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
    )


class AIProvider(ABC):
    """Base AI provider interface."""

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
    ) -> Dict[str, Any]:
        """V2 structured lesson generation.

        Returns a dict matching the Generation V2 output schema, or {} on failure.
        The caller applies the quality gate before marking the lesson ready.
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
    """Google Gemini API provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        if not self.is_available():
            return {}
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-pro')
            prompt = _build_v2_prompt_from_context(
                subject=context.get("subject", strand) if context else strand,
                class_level=context.get("class_level", "") if context else "",
                strand=strand, sub_strand=sub_strand,
                content_standard=content_standard,
                indicator_code=context.get("indicator_code", "") if context else "",
                indicator_text=indicator,
            )
            response = model.generate_content(prompt)
            return _parse_json_response(response.text)
        except Exception:
            return {}

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None):
        if not self.is_available():
            return {}
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-pro')
            prompt = _build_v2_prompt_from_context(
                subject=subject, class_level=class_level, strand=strand,
                sub_strand=sub_strand, content_standard=content_standard,
                indicator_code=indicator_code, indicator_text=indicator_text,
                class_size=class_size, duration_minutes=duration_minutes,
                source_resources=source_resources,
                previous_lesson_context=previous_lesson_context,
                next_lesson_context=next_lesson_context,
                teaching_day=teaching_day, week_number=week_number,
            )
            response = model.generate_content(prompt)
            return _parse_json_response(response.text)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "gemini"


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        if not self.is_available():
            return {}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            prompt = _build_v2_prompt_from_context(
                subject=context.get("subject", strand) if context else strand,
                class_level=context.get("class_level", "") if context else "",
                strand=strand, sub_strand=sub_strand,
                content_standard=content_standard,
                indicator_code=context.get("indicator_code", "") if context else "",
                indicator_text=indicator,
            )
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return _parse_json_response(response.choices[0].message.content)
        except Exception:
            return {}

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None):
        if not self.is_available():
            return {}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            prompt = _build_v2_prompt_from_context(
                subject=subject, class_level=class_level, strand=strand,
                sub_strand=sub_strand, content_standard=content_standard,
                indicator_code=indicator_code, indicator_text=indicator_text,
                class_size=class_size, duration_minutes=duration_minutes,
                source_resources=source_resources,
                previous_lesson_context=previous_lesson_context,
                next_lesson_context=next_lesson_context,
                teaching_day=teaching_day, week_number=week_number,
            )
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert Ghanaian educator. Output valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            return _parse_json_response(response.choices[0].message.content)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "openai"


class MiniMaxProvider(AIProvider):
    """MiniMax API provider (stub)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "minimax"


class OpenCodeZenProvider(AIProvider):
    """OpenCode Zen provider — OpenAI-compatible gateway with free models."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENCODE_ZEN_API_KEY", "")
        self.model = model or os.environ.get("OPENCODE_ZEN_MODEL", "nemotron-3-ultra-free")
        self.base_url = os.environ.get("OPENCODE_ZEN_BASE_URL", "https://opencode.ai/zen/v1")

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        if not self.is_available():
            return {}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            prompt = _build_v2_prompt_from_context(
                subject=context.get("subject", strand) if context else strand,
                class_level=context.get("class_level", "") if context else "",
                strand=strand, sub_strand=sub_strand,
                content_standard=content_standard,
                indicator_code=context.get("indicator_code", "") if context else "",
                indicator_text=indicator,
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1500,
            )
            return _parse_json_response(response.choices[0].message.content)
        except Exception:
            return {}

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None):
        if not self.is_available():
            return {}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            prompt = _build_v2_prompt_from_context(
                subject=subject, class_level=class_level, strand=strand,
                sub_strand=sub_strand, content_standard=content_standard,
                indicator_code=indicator_code, indicator_text=indicator_text,
                class_size=class_size, duration_minutes=duration_minutes,
                source_resources=source_resources,
                previous_lesson_context=previous_lesson_context,
                next_lesson_context=next_lesson_context,
                teaching_day=teaching_day, week_number=week_number,
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert Ghanaian educator. Output valid JSON only. No markdown fences."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )
            return _parse_json_response(response.choices[0].message.content)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "opencode-zen"


class OllamaProvider(AIProvider):
    """Ollama local provider. Model via OLLAMA_MODEL env (default llama3)."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3")

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None, section=None):
        if not self.is_available():
            return {}
        try:
            import requests
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
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": 800}},
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                return _parse_json_response(data.get("response", ""))
            return {}
        except Exception:
            return {}

    def generate_lesson_v2(self, *, subject, class_level, strand, sub_strand,
                           content_standard, indicator_code, indicator_text,
                           class_size=35, duration_minutes=60, source_resources=None,
                           previous_lesson_context=None, next_lesson_context=None,
                           teaching_day=None, week_number=None):
        if not self.is_available():
            return {}
        try:
            import requests
            prompt = _build_v2_prompt_from_context(
                subject=subject, class_level=class_level, strand=strand,
                sub_strand=sub_strand, content_standard=content_standard,
                indicator_code=indicator_code, indicator_text=indicator_text,
                class_size=class_size, duration_minutes=duration_minutes,
                source_resources=source_resources,
                previous_lesson_context=previous_lesson_context,
                next_lesson_context=next_lesson_context,
                teaching_day=teaching_day, week_number=week_number,
            )
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": 800}},
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                return _parse_json_response(data.get("response", ""))
            return {}
        except Exception:
            return {}

    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def generate_structured(self, prompt: str) -> dict:
        """Raw prompt in, parsed JSON dict out ({} on any failure)."""
        if not self.is_available():
            return {}
        try:
            import requests
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": 800}},
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                return _parse_json_response(data.get("response", ""))
            return {}
        except Exception:
            return {}

    def get_name(self) -> str:
        return "ollama"


def get_provider(mode: str = "OFF", **kwargs) -> AIProvider:
    """Factory function to get the appropriate AI provider."""
    providers = {
        "OFF": MockProvider,
        "BASIC": MockProvider,
        "ENHANCED": MockProvider,
        "gemini": GeminiProvider,
        "openai": OpenAIProvider,
        "minimax": MiniMaxProvider,
        "ollama": OllamaProvider,
        "opencode-zen": OpenCodeZenProvider,
    }
    provider_class = providers.get(mode, MockProvider)
    return provider_class(**kwargs)
