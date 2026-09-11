"""Small, transparent development evaluation; not a scientific benchmark."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.reasoning import Reasoner
from app.services.retrieval import Retriever, tokens

LABELS = {
    "dryland cover crop water risk": {"ev_cover_water_risk", "ev_cover_dryland_limit", "ev_cover_termination"},
    "cover crop residue infiltration": {"ev_cover_residue_water", "ev_cover_water_risk"},
    "agricultural diversification biodiversity": {"ev_diversification_biodiversity", "ev_diversification_context"},
    "pesticide soil invertebrate adverse effects": {"ev_pesticide_soil_hazard", "ev_pesticide_scope"},
    "habitat restoration reconnection land conversion": {"ev_habitat_reconnection", "ev_land_change_driver"},
    "dryland water budgeting crop decisions": {"ev_dryland_water_budget", "ev_crop_climate_context"},
}


def rankings(retriever: Retriever, query: str) -> tuple[list[str], list[str], list[str]]:
    """Rank chunks, then honestly map and deduplicate their reviewed card IDs."""
    dense = retriever._dense_scores(query)
    lexical = retriever.bm25.get_scores(tokens(query)).tolist()
    dense_order = sorted(range(len(retriever.chunks)), key=lambda i: (-(dense[i] if dense else -999), retriever.chunks[i]["chunk_id"])) if dense else []
    lexical_order = sorted(range(len(retriever.chunks)), key=lambda i: (-lexical[i], retriever.chunks[i]["chunk_id"]))

    def card_ids(order: list[int], limit: int = 8) -> list[str]:
        mapped: list[str] = []
        for index in order:
            for evidence_id in retriever.chunk_to_card_ids[retriever.chunks[index]["chunk_id"]]:
                if evidence_id not in mapped:
                    mapped.append(evidence_id)
                    if len(mapped) == limit:
                        return mapped
        return mapped

    rrf: dict[int, float] = {}
    for order in (dense_order[:12], lexical_order[:12]):
        for rank, index in enumerate(order, 1):
            rrf[index] = rrf.get(index, 0) + 1 / (60 + rank)
    hybrid_order = sorted(rrf, key=lambda i: (-rrf[i], retriever.chunks[i]["chunk_id"]))
    return card_ids(dense_order), card_ids(lexical_order), card_ids(hybrid_order)


def state_for(values: dict[str, object]) -> dict:
    return {"current": {field: {"observation_id": f"obs_{index}", "value": value} for index, (field, value) in enumerate(values.items(), 1)}}


ABLATION_SCENARIOS = {
    "E02": state_for({"soil.organic_carbon_pct": 0.3, "climate.rainfall_pattern": "low", "land.use_type": "crop", "land.crop_system": "monoculture wheat"}),
    "E04": state_for({"soil.organic_carbon_pct": 0.3, "climate.annual_rainfall_mm": 900.0, "climate.rainfall_pattern": "low", "land.use_type": "crop", "land.crop_system": "monoculture wheat"}),
    "E12": state_for({"soil.organic_carbon_pct": 0.3, "climate.rainfall_pattern": "low", "land.use_type": "crop", "land.crop_system": "monoculture", "biodiversity.decline_reported": "reported decline", "pressures.pesticide_use": "reported use or concern"}),
    "E20": state_for({"land.use_type": "grassland", "biodiversity.habitat_types": ["user-reported habitat diversity"], "pressures.recent_land_clearing": True}),
}


def ablation(root: Path) -> dict:
    """Compare retrieval support only; templates make a generation ablation inapplicable."""
    reasoner = Reasoner(root / "app" / "knowledge")
    result: dict[str, list[dict]] = {"hybrid_rrf": [], "bm25_only": []}
    for arm, dense in (("hybrid_rrf", True), ("bm25_only", False)):
        retriever = Retriever(root / "app" / "knowledge", use_dense=dense)
        for scenario_id, state in ABLATION_SCENARIOS.items():
            packet = retriever.retrieve(deepcopy(state), scenario_id, [key for key, value in reasoner.actions.items() if value.get("enabled")])
            ranked, _ = reasoner.evaluate(state, packet["card_ids"])
            result[arm].append({"scenario_id": scenario_id, "retrieved_evidence_ids": sorted(packet["card_ids"]), "eligible_action_ids": [item["action"]["action_id"] for item in ranked], "retrieval_seconds": packet["timings"]["retrieval_seconds"]})
    return {"status": "measured retrieval-policy ablation", "arms": result, "scope": "No generation arm: public recommendation prose is deterministic server rendering from reviewed cards."}


def support_diagnostic(root: Path) -> dict:
    golden_path = root / "artifacts" / "golden_results.json"
    if not golden_path.exists():
        return {"status": "not_run", "reason": "run scripts/run_golden.py first"}
    golden = json.loads(golden_path.read_text())
    cards = {json.loads(line)["evidence_id"]: json.loads(line) for line in (root / "app" / "knowledge" / "cards.jsonl").read_text().splitlines() if line.strip()}
    rows = []
    for case in golden["cases"]:
        ids = case["cited_evidence_ids"]
        supported = all(eid in cards and cards[eid]["review_status"] == "reviewed" for eid in ids)
        rows.append({"case_id": case["id"], "cited_evidence_ids": ids, "reviewed_id_check": supported, "classification": "supported_by_id_contract" if supported else "unsupported"})
    return {"status": "completed deterministic ID/provenance diagnostic", "semantic_review": "not performed; this diagnostic verifies reviewed-card IDs and activation coverage, not scientific entailment.", "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--suite", default="tests/golden/cases.jsonl"); args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    retriever = Retriever(root / "app" / "knowledge", use_dense=True)
    query_results = []
    for query, expected in LABELS.items():
        dense_ids, lexical_ids, hybrid_ids = rankings(retriever, query)
        dense, hybrid = set(dense_ids), set(hybrid_ids)
        query_results.append({"query": query, "expected": sorted(expected), "dense_recall_at_8": len(expected & dense) / len(expected), "hybrid_recall_at_8": len(expected & hybrid) / len(expected), "dense_ids": dense_ids, "lexical_ids": lexical_ids, "hybrid_ids": hybrid_ids})
    cases = [json.loads(line) for line in Path(args.suite).read_text().splitlines() if line.strip()]
    report = {"retrieval": {"query_count": len(query_results), "dense_macro_recall_at_8": sum(q["dense_recall_at_8"] for q in query_results) / len(query_results), "hybrid_macro_recall_at_8": sum(q["hybrid_recall_at_8"] for q in query_results) / len(query_results), "labels": query_results, "note": "Small saved hand-labeled development set. Scores rank source chunks first, then map and deduplicate reviewed card anchors at eight; this is not a scientific benchmark or runtime answer evaluation."}, "golden_suite": {"case_ids": [case["id"] for case in cases], "artifact": "artifacts/golden_results.json", "mode": "deterministic API suite; see artifact for actual run status"}, "ablation": ablation(root), "support_diagnostic": support_diagnostic(root)}
    path = root / "artifacts" / "evaluation.json"; path.write_text(json.dumps(report, indent=2)); print(json.dumps(report["retrieval"], indent=2)); return 0

if __name__ == "__main__": raise SystemExit(main())
