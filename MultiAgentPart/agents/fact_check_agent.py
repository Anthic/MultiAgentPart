"""
fact_check_agent.py
────────────────────────────────────────────────────────────
Verifies key claims in the generated report against the original
scraped sources. Flags hallucinations and returns a corrected report.

Why it matters
──────────────
LLMs sometimes "hallucinate" — stating plausible-sounding facts that
aren't in the source material. This agent cross-references every major
claim the writer produced, marks unsupported ones, and optionally
strips them from the final output.
"""

import logging
from typing import Dict

log = logging.getLogger(__name__)

_FACT_CHECK_PROMPT = """\
You are a rigorous fact-checking assistant.

Your job is to verify every factual claim in the REPORT against the \
SOURCE MATERIAL provided. Do NOT rely on your training data — only check \
against the sources given.

Instructions:
1. Extract up to 10 key factual claims from the report.
2. For each claim, search the source material for supporting evidence.
3. Mark each claim as:
   -  SUPPORTED  — evidence found in sources
   -  UNSUPPORTED — no evidence found; likely hallucination
   -  PARTIAL     — partially supported; needs qualification
4. Produce a corrected version of the report with UNSUPPORTED claims \
   either removed or clearly flagged as [UNVERIFIED].
5. At the end, output a JSON block:

```json
{{
  "supported": <int>,
  "unsupported": <int>,
  "partial": <int>,
  "confidence": <0-1 float>
}}
```

---
SOURCE MATERIAL:
{sources}

---
REPORT TO FACT-CHECK:
{report}
"""


def run_fact_check_node(state: Dict, llm) -> Dict:
    """
    LangGraph node: checks the writer's report against scraped + RAG sources.

    Adds to state:
        fact_check_result  — raw LLM output with claim verdicts
        report             — corrected report (hallucinations flagged)
        fact_check_score   — confidence float 0-1 from JSON block
    """
    report: str = state.get("report", "").strip()
    if not report:
        log.warning("FactCheck: no report to verify, skipping")
        return {**state, "fact_check_result": "", "fact_check_score": 1.0}

    # Build source corpus (scraped + RAG context)
    sources = "\n\n".join(
        filter(None, [
            state.get("scraped_content", "")[:3000],
            state.get("rag_context", "")[:1500],
            state.get("search_results", "")[:1000],
        ])
    )

    if not sources.strip():
        log.warning("FactCheck: no sources available, skipping")
        return {**state, "fact_check_result": "No sources to verify against.", "fact_check_score": 0.5}

    try:
        prompt = _FACT_CHECK_PROMPT.format(
            sources=sources,
            report=report[:4000],   # stay within token limits
        )
        result: str = llm.invoke(prompt).content
        log.info("FactCheck: result length=%d chars", len(result))

        # Parse the JSON confidence block if present
        score = _parse_confidence(result)

        # Extract only the corrected report section (before the JSON block)
        corrected = _extract_corrected_report(result, report)

        return {
            **state,
            "fact_check_result": result,
            "report": corrected,
            "fact_check_score": score,
        }

    except Exception as exc:
        log.exception("FactCheck LLM call failed")
        return {
            **state,
            "fact_check_result": f"FactCheck error: {exc}",
            "fact_check_score": 0.5,
        }


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_confidence(result: str) -> float:
    """Extract confidence float from the JSON block in the LLM output."""
    import re, json
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", result, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return float(data.get("confidence", 0.8))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return 0.8  # default — can't parse, assume decent quality


def _extract_corrected_report(result: str, original_report: str) -> str:
    """
    Try to extract the corrected report section from fact-check output.
    Falls back to the original report if parsing fails or output appears truncated.
    """
    import re
    
    # If the JSON block isn't present, the LLM probably truncated the output.
    # We should NOT use a truncated corrected report, fallback to original.
    if "```json" not in result.lower():
        return original_report

    # Look for a corrected report section after claim verdicts
    match = re.search(
        r"(?:corrected report|revised report)[:\s]*\n(.*?)```json",
        result, re.IGNORECASE | re.DOTALL
    )
    if match:
        corrected = match.group(1).strip()
        if len(corrected) > 200:  # sanity-check: must be substantial
            return corrected
    return original_report
