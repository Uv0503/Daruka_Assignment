from __future__ import annotations

import math
import re

from app.services.evidence_display import complete_display_passage
from app.services.state import concept_for_field


def literature_illustration(card: dict) -> dict:
    effect = card["effect"]
    if not effect or effect["measure"] != "ln_response_ratio":
        raise ValueError("only verified lnRR cards may be transformed")
    transform = lambda value: round(100 * math.expm1(value), 1)
    return {"evidence_id": card["evidence_id"], "formula_id": "lnrr_to_relative_percent", "source_inputs": {"lnRR": effect["estimate"], "ci_lower": effect["ci_lower"], "ci_upper": effect["ci_upper"]}, "output_relative_percent": transform(effect["estimate"]), "output_ci_percent": [transform(effect["ci_lower"]), transform(effect["ci_upper"])], "estimate_type": "calculated_illustration", "transferability_note": "Pooled literature result across analyzed biodiversity measures; its confidence interval is not a prediction interval for this site."}


def verify_response(
    response: dict,
    cards_by_id: dict,
    state: dict,
    *,
    actions: dict[str, dict] | None = None,
    edges: list[dict] | None = None,
    supplied_evidence_ids: set[str] | None = None,
    passages_by_id: dict[str, dict] | None = None,
    parents_by_id: dict[str, dict] | None = None,
) -> list[str]:
    """Reject, rather than repair, output outside the reviewed evidence contract."""
    errors: list[str] = []
    known_obs = {event["observation_id"] for event in state["current"].values() if event}
    allowed_edges = {edge["edge_id"]: edge for edge in edges or [] if edge.get("review_status") == "reviewed"}
    used_concepts: set[str] = set()
    numeric_pattern = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|mm|°?c|years?|months?)", re.IGNORECASE)
    public_text = [response.get("summary", "")]
    cited_evidence_ids: set[str] = set()
    for rec in response.get("recommendations", []):
        action_id = rec.get("action_id")
        if not actions or action_id not in actions or not actions[action_id].get("enabled"):
            errors.append("recommendation has an unknown or disabled action")
            continue
        evidence_ids = rec.get("evidence_ids", [])
        if not evidence_ids or any(eid not in cards_by_id or cards_by_id[eid].get("review_status") != "reviewed" for eid in evidence_ids):
            errors.append("unknown, draft, or missing evidence ID")
        if supplied_evidence_ids is not None and not set(evidence_ids) <= supplied_evidence_ids:
            errors.append("recommendation cites evidence outside the retrieval packet")
        required = set(actions[action_id].get("activation_evidence_ids", actions[action_id].get("evidence_ids", [])))
        if not required <= set(evidence_ids):
            errors.append("recommendation omits an action activation evidence card")
        observation_ids = rec.get("used_observation_ids", [])
        if not observation_ids or any(oid not in known_obs for oid in observation_ids):
            errors.append("recommendation references an observation outside current state")
        for field, event in state["current"].items():
            if event and event["observation_id"] in observation_ids:
                concept = concept_for_field(field)
                if concept:
                    used_concepts.add(concept)
        for path in rec.get("interaction_paths", []):
            path_edges = path.get("edge_ids", [])
            if not path_edges or any(edge_id not in allowed_edges for edge_id in path_edges):
                errors.append("interaction path contains an unknown or unreviewed edge")
            if not path.get("observation_ids") or any(oid not in known_obs for oid in path["observation_ids"]):
                errors.append("interaction path is not linked to accepted observations")
            if any(eid not in evidence_ids for eid in path.get("evidence_ids", [])):
                errors.append("interaction path cites evidence not attached to its recommendation")
        if not rec.get("interaction_paths"):
            errors.append("recommendation has no reviewed observation-linked interaction path")
        for metric in rec.get("impacted_metrics", []):
            estimate = metric.get("quantitative_estimate")
            if estimate is not None and metric.get("estimate_type") != "literature_result":
                errors.append("unsupported quantitative estimate type")
            if metric.get("estimate_type") == "local_model_prediction":
                errors.append("local model predictions are prohibited")
            if estimate is not None:
                if not isinstance(estimate, dict):
                    errors.append("quantitative estimate is not a structured evidence object")
                    continue
                evidence_id = estimate.get("evidence_id")
                card = cards_by_id.get(evidence_id)
                effect = card.get("effect") if card else None
                if not card or evidence_id not in evidence_ids or not effect:
                    errors.append("quantitative estimate has no reviewed effect card")
                    continue
                for key in ("measure", "value", "unit", "comparator", "population"):
                    expected = effect.get("estimate") if key == "value" else effect.get({"population": "target_population"}.get(key, key))
                    if estimate.get(key) != expected:
                        errors.append("quantitative estimate differs from its reviewed evidence card")
                        break
        public_text.extend(rec.get("action_steps", []))
        public_text.extend([rec.get("rationale", "")])
        public_text.extend(item.get("statement", "") for item in rec.get("tradeoffs", []))
    for citation in response.get("citations", []):
        ids = citation.get("supporting_evidence_ids", [])
        if len(ids) != 1:
            errors.append("citation must resolve exactly one evidence passage")
            continue
        evidence_id = ids[0]
        card = cards_by_id.get(evidence_id)
        if not card or citation.get("source_id") != card.get("source_id"):
            errors.append("citation source does not match its evidence card")
            continue
        if card.get("review_status") != "reviewed" or (supplied_evidence_ids is not None and evidence_id not in supplied_evidence_ids):
            errors.append("citation is unreviewed or outside the retrieval packet")
            continue
        if passages_by_id is None:
            errors.append("citation provenance was not supplied for validation")
            continue
        passage = passages_by_id.get(card["chunk_ids"][0])
        parent = parents_by_id.get(passage.get("parent_id")) if passage and parents_by_id is not None else None
        expected_excerpt = complete_display_passage(evidence_id, parent.get("text", "")) if parent else None
        if not expected_excerpt or citation.get("locator") != parent.get("locator") or citation.get("excerpt") != expected_excerpt:
            errors.append("citation does not match its extracted source passage")
            continue
        cited_evidence_ids.add(evidence_id)
    response_evidence_ids = {eid for rec in response.get("recommendations", []) for eid in rec.get("evidence_ids", [])}
    if response.get("recommendations") and response_evidence_ids != cited_evidence_ids:
        errors.append("response evidence and citations do not have a one-passage trace")
    if response.get("recommendations") and len(used_concepts) < 3:
        errors.append("recommendations do not use three distinct environmental concepts")
    if numeric_pattern.search(" ".join(public_text)):
        errors.append("free numerical claim in response prose")
    return errors
