"""
SchemeKnit AI Provider Abstraction

Optional AI enrichment layer.
AI must NEVER be required for core pipeline functionality.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import os


class AIProvider(ABC):
    """Base AI provider interface."""

    @abstractmethod
    def generate_lesson_content(
        self,
        indicator: str,
        strand: str,
        sub_strand: str,
        content_standard: str,
        lesson_type: str = "instruction",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Generate lesson content enrichment."""
        pass

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

            prompt = self._build_prompt(indicator, strand, sub_strand, content_standard, lesson_type)
            response = model.generate_content(prompt)
            return self._parse_response(response.text)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "gemini"

    def _build_prompt(self, indicator, strand, sub_strand, content_standard, lesson_type):
        return (
            f"Generate a lesson plan section for a Ghanaian {strand} lesson.\n"
            f"Sub-strand: {sub_strand}\n"
            f"Content Standard: {content_standard}\n"
            f"Indicator: {indicator}\n"
            f"Return JSON with keys: introduction, main_activity, learner_activity, assessment, conclusion\n"
            f"Keep responses practical for a Ghanaian classroom with limited resources."
        )

    def _parse_response(self, text):
        import json
        try:
            return json.loads(text)
        except Exception:
            return {"introduction": text[:200]}


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
            prompt = self._build_prompt(indicator, strand, sub_strand, content_standard)
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            return self._parse_response(response.choices[0].message.content)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "openai"

    def _build_prompt(self, indicator, strand, sub_strand, content_standard):
        return (
            f"Generate lesson content for a Ghanaian classroom.\n"
            f"Strand: {strand}, Sub-strand: {sub_strand}\n"
            f"Standard: {content_standard}\n"
            f"Indicator: {indicator}\n"
            f"Return JSON with keys: introduction, main_activity, learner_activity, assessment, conclusion"
        )

    def _parse_response(self, text):
        import json
        try:
            return json.loads(text)
        except Exception:
            return {"introduction": text[:200]}


class MiniMaxProvider(AIProvider):
    """MiniMax API provider."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")

    def generate_lesson_content(self, indicator, strand, sub_strand, content_standard,
                                 lesson_type="instruction", context=None):
        return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "minimax"


class OpenCodeZenProvider(AIProvider):
    """OpenCode Zen provider — OpenAI-compatible gateway with free models.

    Uses https://opencode.ai/zen/v1 as the base URL.
    Free models: nemotron-3-ultra-free, mimo-v2.5-free, muse-spark-1.3, etc.
    """

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
            prompt = (
                f"Generate lesson content for a Ghanaian classroom.\n"
                f"Strand: {strand}, Sub-strand: {sub_strand}\n"
                f"Standard: {content_standard}\n"
                f"Indicator: {indicator}\n"
                f"Return ONLY a flat JSON object (no markdown fences) with ALL of these "
                f"string keys: introduction, main_activity, learner_activity, assessment, conclusion"
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
            )
            return self._parse_response(response.choices[0].message.content)
        except Exception:
            return {}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def get_name(self) -> str:
        return "opencode-zen"

    def _parse_response(self, text):
        import json
        try:
            return json.loads(_strip_fences(text))
        except Exception:
            return {"introduction": _strip_fences(text)[:500] if text else ""}


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers models often add around JSON payloads,
    including unclosed fences from truncated generations."""
    import re
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```(?:json)?\s*(.*)$", text, re.DOTALL)
    if m2:
        return m2.group(1).strip()
    return text


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
                prompt = (
                    f"Generate lesson content for: {strand} - {sub_strand}\n"
                    f"Indicator: {indicator}\n"
                    f"Return ONLY a flat JSON object (no markdown fences) with ALL of these "
                    f"string keys: introduction, main_activity, assessment, conclusion"
                )
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "options": {"num_predict": 300}},
                # Local inference can be slow on first tokens; 120s documented.
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_response(data.get("response", ""))
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
                      "options": {"num_predict": 600}},
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                import json
                try:
                    return json.loads(_strip_fences(data.get("response", "")))
                except Exception:
                    return {}
            return {}
        except Exception:
            return {}

    def get_name(self) -> str:
        return "ollama"

    def _parse_response(self, text):
        import json
        try:
            return json.loads(_strip_fences(text))
        except Exception:
            return {"introduction": _strip_fences(text)[:500] if text else ""}


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
