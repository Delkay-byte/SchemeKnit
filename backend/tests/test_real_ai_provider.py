"""
Real AI Provider Test — OpenRouter + Nemotron 3 Ultra (free)

Tests real V2 generation with actual Ghanaian curriculum PDFs.
"""
import sys; sys.path.insert(0, '.')
import asyncio
import json
import os
import httpx
from pathlib import Path
from datetime import date

from src.parsers.pdf_parser import PDFParser
from src.models import TermConfig, AIMode, Holiday, Week
from src.engines.ai_provider import _build_v2_prompt_from_context, _parse_json_response
from src.curriculum import Indicator
from src.curriculum.quality_gate import validate_lesson_quality

REAL_DOCS = Path("real_documents")
BASIC7_PDF = REAL_DOCS / "BASIC 7 TERM 1.pdf"

OPENROUTER_KEY = os.environ.get("OPENCODE_ZEN_API_KEY", "")
OPENROUTER_BASE = os.environ.get("OPENCODE_ZEN_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENCODE_ZEN_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

SYSTEM_PROMPT = "You are an expert Ghanaian educator. Output valid JSON only. No markdown fences."


def call_openrouter(system_msg: str, user_msg: str, max_tokens: int = 2000) -> dict:
    """Call OpenRouter API directly with httpx."""
    resp = httpx.post(
        f"{OPENROUTER_BASE}/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
        },
        timeout=120.0,
    )
    if resp.status_code != 200:
        print(f"  API ERROR: {resp.status_code} - {resp.text[:300]}")
        return {}
    data = resp.json()
    if "choices" not in data:
        print(f"  API ERROR: no choices")
        return {}
    content = data["choices"][0]["message"]["content"]
    print(f"  Raw response length: {len(content)} chars")
    result = _parse_json_response(content)
    if not result:
        print(f"  PARSE FAILED. Raw content (first 500):\n{content[:500]}")
    return result


def _make_term_config(scheme_id="real-ai-test"):
    return TermConfig(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7),
        term_end_date=date(2026, 12, 18),
        semester=1,
        lessons_per_week=3,
        lesson_duration_minutes=45,
        teaching_days=[0, 1, 2, 3, 4],
        holidays=[Holiday(name="Founder's Day", date=date(2026, 11, 20))],
        ai_mode=AIMode.BASIC,
    )


def build_simple_prompt(week: Week, indicator_str: str, subject: str, class_level: str) -> str:
    """Build a prompt from Week model data (SchemeOfWork, not CurriculumDocument)."""
    # Extract indicator code and text
    from src.curriculum import split_indicator_text
    code, text = split_indicator_text(indicator_str)

    parts = [
        f"CURRICULUM CONTEXT",
        f"Subject: {subject}",
        f"Class Level: {class_level}",
        f"Strand: {week.strand or 'N/A'}",
        f"Sub-Strand: {week.sub_strand or 'N/A'}",
        f"Indicator Code: {code}",
        f"Indicator: {text}",
        f"Week: {week.week_number}",
        f"",
        f"CLASS CONTEXT",
        f"Class Size: 35 learners",
        f"Duration: 45 minutes",
        f"",
        f"OUTPUT REQUIREMENTS",
        f"Return a JSON object with these keys:",
        f"- learning_objectives: array of strings starting with 'Learners can'",
        f"- starter: object with activity, duration_minutes, teacher_action, learner_action",
        f"- main_learning: object with phase1/phase2, each having name, activity, duration_minutes, teacher_action, learner_action",
        f"- assessment: object with method, activity, success_criteria, duration_minutes",
        f"- plenary: object with activity, duration_minutes, teacher_action, learner_action",
        f"- differentiation: object with support, core, extension",
        f"- homework_or_extension: string",
        f"",
        f"RULES:",
        f"1. Learning objectives MUST start with 'Learners can' followed by a measurable verb.",
        f"2. Assessment MUST directly check the indicator.",
        f"3. Resources MUST be realistic for Ghanaian classrooms.",
        f"4. NO invented textbook references or page numbers.",
        f"5. Output MUST be valid JSON only, no markdown fences.",
    ]
    return "\n".join(parts)


def test_single_indicator():
    """Test a single indicator through the real AI provider."""
    print("=" * 80)
    print("REAL AI PROVIDER TEST - Single Indicator")
    print(f"Provider: OpenRouter | Model: {OPENROUTER_MODEL}")
    print("=" * 80)

    prompt = build_simple_prompt(
        week=Week(
            week_number=1, start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            strand="Diversity of Matter", sub_strand="Materials",
            content_standards=["B7.1.1.1 Recognise materials as important resources"],
            indicators=["B7.1.1.1.1 Classify materials into liquids, solids and gases"],
            resources=["chart", "real objects"], scheme_of_work_id="test",
        ),
        indicator_str="B7.1.1.1.1 Classify materials into liquids, solids and gases",
        subject="Science",
        class_level="Basic 7",
    )

    print(f"\nPrompt length: {len(prompt)} chars")
    result = call_openrouter(SYSTEM_PROMPT, prompt)
    print(f"\nResponse received: {bool(result)}")
    if result:
        print(f"Keys: {list(result.keys())}")
        print(f"\nFull response:\n{json.dumps(result, indent=2, default=str)[:2000]}")

        has_objectives = bool(result.get("learning_objectives"))
        has_starter = bool(result.get("starter"))
        has_main = bool(result.get("main_learning"))
        has_assessment = bool(result.get("assessment"))

        print(f"\nField checks:")
        print(f"  learning_objectives: {'OK' if has_objectives else 'MISSING'}")
        print(f"  starter: {'OK' if has_starter else 'MISSING'}")
        print(f"  main_learning: {'OK' if has_main else 'MISSING'}")
        print(f"  assessment: {'OK' if has_assessment else 'MISSING'}")
    else:
        print("ERROR: Empty response from provider")

    return result


def test_basic7_science_batch():
    """Test with real Basic 7 Science curriculum, 3 indicators."""
    print("\n" + "=" * 80)
    print("REAL AI PROVIDER TEST - Basic 7 Science (3 indicators)")
    print("=" * 80)

    parser = PDFParser()
    scheme = asyncio.run(
        parser.parse(BASIC7_PDF, original_filename="BASIC 7 TERM 1.pdf", target_subject="Science")
    )
    print(f"\nParsed scheme: {scheme.subject} | Weeks: {len(scheme.weeks)}")

    # Collect first 3 indicators from the scheme
    indicators = []
    for week in scheme.weeks[:3]:
        for ind_str in week.indicators:
            indicators.append({
                "week": week,
                "indicator_str": ind_str,
            })
            if len(indicators) >= 3:
                break
        if len(indicators) >= 3:
            break

    print(f"\nTesting {len(indicators)} indicators:")
    for ind in indicators:
        print(f"  Wk{ind['week'].week_number}: {ind['indicator_str'][:70]}...")

    results = []
    for i, ind in enumerate(indicators):
        week = ind["week"]
        ind_str = ind["indicator_str"]
        code, text = split_indicator_text(ind_str)

        print(f"\n{'='*60}")
        print(f"INDICATOR {i+1}: {code}")
        print(f"  Text: {text[:80]}")
        print(f"  Strand: {(week.strand or 'N/A')[:60]}")

        prompt = build_simple_prompt(week, ind_str, "Science", "Basic 7")
        result = call_openrouter(SYSTEM_PROMPT, prompt)

        if result:
            print(f"  OK: {len(result)} keys")
            for key in ["learning_objectives", "starter", "main_learning", "assessment"]:
                has = bool(result.get(key))
                print(f"    {key}: {'OK' if has else 'MISSING'}")

            # Quality gate
            indicator_obj = Indicator(
                code=code,
                exact_text=ind_str,
                description=text,
                source_week=week.week_number,
                source_subject="Science",
            )
            lesson_dict = {
                "indicator_codes": [code],
                "learning_objectives": [{"text": o, "indicator_code": code}
                                        for o in (result.get("learning_objectives") or [])],
                "main_activities": [{"phase": p.get("name", ""), "description": p.get("activity", ""),
                                    "duration_minutes": p.get("duration_minutes", 15)}
                                   for p in (result.get("main_learning") or {}).values()
                                   if isinstance(p, dict)],
                "learner_activities": [],
                "assessment": result.get("assessment", {}).get("activity", "") if isinstance(result.get("assessment"), dict) else str(result.get("assessment", "")),
                "introduction": result.get("starter", {}).get("activity", "") if isinstance(result.get("starter"), dict) else "",
                "conclusion": result.get("plenary", {}).get("activity", "") if isinstance(result.get("plenary"), dict) else "",
                "subject": "Science",
                "strand": week.strand or "",
                "duration_minutes": 45,
                "resources": [],
            }
            report = validate_lesson_quality(lesson_dict, indicator_obj)
            status = "PASS" if report.overall_status in ("pass", "warn") else "FAIL"
            print(f"  Quality Gate: {status} (score={report.score}, status={report.overall_status})")
            for issue in report.issues:
                if issue.status in ("fail", "warn"):
                    print(f"    [{issue.status.upper()}] {issue.message}")
            results.append({"indicator": code, "result": result, "quality": report.overall_status})
        else:
            print(f"  FAILED: Empty response")
            results.append({"indicator": code, "result": None, "quality": "error"})

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    passed = sum(1 for r in results if r["quality"] in ("pass", "warn"))
    print(f"Indicators tested: {len(results)}")
    print(f"Quality gate passed: {passed}/{len(results)}")
    for r in results:
        print(f"  {r['indicator']}: {r['quality']}")

    return results


def split_indicator_text(text: str):
    """Split indicator text into (code, description)."""
    from src.curriculum import INDICATOR_CODE_RE
    m = INDICATOR_CODE_RE.search(text)
    if m:
        code = m.group(0)
        desc = text[m.end():].strip()
        import re
        desc = re.sub(r'^[:.\s]+', '', desc)
        return code, desc
    return "", text.strip()


if __name__ == "__main__":
    # Test 1: Single indicator
    single = test_single_indicator()

    # Test 2: Batch with real PDF
    batch = test_basic7_science_batch()

    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print(f"Single indicator: {'PASS' if single else 'FAIL'}")
    passed = sum(1 for r in batch if r["quality"] in ("pass", "warn"))
    print(f"Batch ({len(batch)} indicators): {passed} passed quality gate")
