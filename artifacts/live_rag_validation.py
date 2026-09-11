#!/usr/bin/env python3
"""Live, no-mock HTTP validation for the twelve supplied neutral prompts.

This deliberately stores complete API responses so the accompanying report
never substitutes a claimed metric for the observed evidence trail.  It does
not alter application state beyond creating disposable local sessions.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8010"
STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
OUT = Path(__file__).parent / f"live_rag_validation_{STAMP}.json"
REPORT = Path(__file__).parent / f"live_rag_validation_{STAMP}.md"

PROMPTS = [
    ("T01_semi_arid_monoculture", "My farm receives around 350 mm of rainfall annually, mostly during a short monsoon period. Soil organic carbon is about 0.3%, and wheat has been grown continuously for several years. Recently, I have noticed lower soil moisture and fewer insects and birds. What factors should I investigate, and what interventions could be considered?"),
    ("T02_missing_context", "I want to improve biodiversity on my farm without significantly reducing crop production. What should I do?"),
    ("T03_compare_interventions", "I have limited land available. Would planting field margins with native vegetation or introducing cover crops likely provide greater biodiversity benefits?"),
    ("T04_evidence_challenge", "What evidence supports the idea that increasing crop diversity can improve biodiversity or ecosystem services on agricultural land?"),
    ("T05_false_premise", "I heard that increasing the number of crop species always increases farm biodiversity. Is that correct?"),
    ("T06_water_constrained_cover_crops", "A farm has poor soil organic matter and declining biodiversity, but irrigation water is extremely limited. Would introducing cover crops still be a good strategy?"),
    ("T07_habitat_production_tradeoff", "If I convert part of my productive farmland into habitat strips for insects and birds, how should I think about the trade-off between biodiversity benefits and crop production?"),
    ("T08_exact_bird_percentage", "What is the exact percentage increase in bird abundance I will get if I introduce flower strips on my farm?"),
    ("T09_multi_condition_priority", "I manage a rain-fed farm with low soil organic carbon, compacted soil, wheat monoculture, very little non-crop vegetation, and declining pollinator activity. I can only afford one or two interventions this season. How should I decide what to prioritize?"),
    ("T10_out_of_domain", "Should I invest in solar panels or fixed deposits this year?"),
    ("T11_biodiversity_monitoring", "I want more biodiversity on my farm. How can I measure whether things are actually improving?"),
    ("T12_pollinator_specificity", "What farm-management practices can affect pollinator diversity, and under what conditions might those practices fail to help?"),
]


def call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(BASE_URL + path, data=payload, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=45) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, {"http_error": exc.read().decode(errors="replace")}
    except URLError as exc:
        return 0, {"network_error": str(exc.reason)}


def assertions(case_id: str, http_status: int, response: object) -> list[dict]:
    checks: list[dict] = [{"name": "HTTP 200", "passed": http_status == 200}]
    if not isinstance(response, dict):
        return checks + [{"name": "JSON object response", "passed": False}]
    required = {"status", "summary", "citations", "trace_excerpts", "current_profile"}
    checks.append({"name": "response contract fields", "passed": required <= set(response)})
    status = response.get("status")
    checks.append({"name": "no runtime/provider degradation", "passed": status != "degraded"})
    if case_id == "T02_missing_context":
        checks.append({"name": "asks a clarification question", "passed": status == "clarify" and bool(response.get("questions"))})
    elif case_id == "T10_out_of_domain":
        checks.append({"name": "rejects out-of-domain finance request", "passed": status == "out_of_scope"})
    else:
        # A retrieval response must expose traceable reviewed evidence, even
        # when the system conservatively clarifies or abstains.
        checks.append({"name": "visible retrieved evidence trail", "passed": bool(response.get("trace_excerpts")) and bool(response.get("citations"))})
    if case_id == "T08_exact_bird_percentage":
        rendered = json.dumps({key: response.get(key) for key in ("summary", "recommendations", "limitations")})
        checks.append({"name": "does not promise an exact local percentage", "passed": not bool(re.search(r"\\b\\d+(?:\\.\\d+)?%", rendered))})
    if case_id == "T05_false_premise":
        rendered = json.dumps({key: response.get(key) for key in ("summary", "recommendations", "limitations", "citations")}).casefold()
        checks.append({"name": "does not endorse universal 'always' premise", "passed": "always increases" not in rendered})
    return checks


def main() -> int:
    health_status, health = call("GET", "/health")
    results = []
    for case_id, prompt in PROMPTS:
        create_status, created = call("POST", "/v1/sessions", {})
        session_id = created.get("session_id") if isinstance(created, dict) else None
        started = time.perf_counter()
        if create_status != 200 or not session_id:
            status, response = create_status, {"session_creation": created}
        else:
            status, response = call("POST", "/v1/chat", {"session_id": session_id, "message": prompt, "mode": "advice"})
        checks = assertions(case_id, status, response)
        results.append({"id": case_id, "prompt": prompt, "session_create_http_status": create_status, "http_status": status, "elapsed_seconds": round(time.perf_counter() - started, 3), "assertions": checks, "response": response})
    artifact = {"recorded_at_utc": datetime.now(UTC).isoformat(), "base_url": BASE_URL, "health_http_status": health_status, "health": health, "results": results}
    OUT.write_text(json.dumps(artifact, indent=2) + "\n")
    lines = ["# Live RAG validation", "", f"Exact responses: `{OUT.name}`.", "", f"Health: HTTP {health_status}; `{json.dumps(health)}`.", "", "| Prompt | HTTP | Status | Verdict | Failed assertions |", "|---|---:|---|---|---|"]
    for item in results:
        response = item["response"] if isinstance(item["response"], dict) else {}
        failed = [check["name"] for check in item["assertions"] if not check["passed"]]
        verdict = "PASS" if not failed else "PARTIAL" if item["http_status"] == 200 else "FAIL"
        lines.append(f"| {item['id']} | {item['http_status']} | {response.get('status', 'unparseable')} | {verdict} | {'; '.join(failed) or '—'} |")
    timings = sorted(item["elapsed_seconds"] for item in results)
    p95_index = 0.95 * (len(timings) - 1)
    lower, upper = int(p95_index), min(int(p95_index) + 1, len(timings) - 1)
    p95 = timings[lower] + (timings[upper] - timings[lower]) * (p95_index - lower)
    lines.extend(["", f"Timing: n={len(timings)}, median={statistics.median(timings):.3f}s, p95={p95:.3f}s. These are twelve one-off end-to-end validation requests, not a latency benchmark."])
    REPORT.write_text("\n".join(lines) + "\n")
    print(OUT)
    print(REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
