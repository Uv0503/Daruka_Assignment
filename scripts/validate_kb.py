"""Fail-closed structural and provenance validation for the knowledge base.

This checks files only. It does not fetch sources, build embeddings, or call
the provider, making it suitable before an explicit corpus rebuild.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    import yaml
    from pydantic import ValidationError

    from app.schemas import EvidenceCard, SourceParentPassage, SourcePassage, SourceRecord

    root = Path(__file__).resolve().parents[1]
    knowledge = root / "app" / "knowledge"
    sources = yaml.safe_load((knowledge / "sources.yaml").read_text())["sources"]
    actions = yaml.safe_load((knowledge / "actions.yaml").read_text())["actions"]
    edges = yaml.safe_load((knowledge / "interactions.yaml").read_text())["interactions"]
    cards = load_jsonl(knowledge / "cards.jsonl")
    passage_path = root / "data" / "processed" / "passages.jsonl"
    parent_path = root / "data" / "processed" / "parent_passages.jsonl"
    acquisition_path = root / "data" / "processed" / "acquisition_metadata.json"
    coverage_path = root / "artifacts" / "coverage_matrix.json"
    failures: list[str] = []

    source_by_id: dict[str, dict] = {}
    for source in sources:
        try:
            SourceRecord.model_validate(source)
        except ValidationError as exc:
            failures.append(f"invalid source schema {source.get('source_id', '?')}: {exc.errors()[0]['msg']}")
        source_id = source.get("source_id")
        if source_id in source_by_id:
            failures.append(f"duplicate source ID: {source_id}")
        source_by_id[source_id] = source
    acquisition = {item.get("source_id"): item for item in json.loads(acquisition_path.read_text())} if acquisition_path.exists() else {}
    for source_id, source in source_by_id.items():
        record = acquisition.get(source_id)
        if source["access_status"] == "verified":
            if not record or record.get("error") is not None:
                failures.append(f"verified source has no successful acquisition: {source_id}")
                continue
            if any(source.get(key) != record.get(key) for key in ("retrieved_at", "content_sha256", "local_path")):
                failures.append(f"source registry/acquisition metadata mismatch: {source_id}")
                continue
            raw_path = root / str(source["local_path"])
            if not raw_path.is_file() or sha_bytes(raw_path.read_bytes()) != source["content_sha256"]:
                failures.append(f"stored raw content hash mismatch: {source_id}")

    card_by_id: dict[str, dict] = {}
    for card in cards:
        try:
            EvidenceCard.model_validate(card)
        except ValidationError as exc:
            failures.append(f"invalid evidence schema {card.get('evidence_id', '?')}: {exc.errors()[0]['msg']}")
        evidence_id = card.get("evidence_id")
        if evidence_id in card_by_id:
            failures.append(f"duplicate card ID: {evidence_id}")
        card_by_id[evidence_id] = card
        if card.get("source_id") not in source_by_id or not card.get("chunk_ids") or not card.get("support_excerpt", "").strip():
            failures.append(f"broken card registry link: {evidence_id}")

    parents: dict[str, dict] = {}
    if not parent_path.exists():
        failures.append("complete parent-passage file is missing")
    else:
        for parent in load_jsonl(parent_path):
            try:
                SourceParentPassage.model_validate(parent)
            except ValidationError as exc:
                failures.append(f"invalid parent schema {parent.get('parent_id', '?')}: {exc.errors()[0]['msg']}")
            parents[parent["parent_id"]] = parent

    passages: dict[str, dict] = {}
    if not passage_path.exists():
        failures.append("extracted passage file is missing")
    else:
        for passage in load_jsonl(passage_path):
            try:
                SourcePassage.model_validate(passage)
            except ValidationError as exc:
                failures.append(f"invalid passage schema {passage.get('chunk_id', '?')}: {exc.errors()[0]['msg']}")
            passage_id = passage.get("chunk_id")
            if passage_id in passages:
                failures.append(f"duplicate chunk ID: {passage_id}")
            passages[passage_id] = passage
            raw_path = root / str(passage.get("raw_path", ""))
            if not raw_path.is_file() or sha_bytes(raw_path.read_bytes()) != passage.get("raw_sha256"):
                failures.append(f"passage raw hash mismatch: {passage_id}")
            if sha_bytes(str(passage.get("text", "")).encode()) != passage.get("text_sha256"):
                failures.append(f"passage text hash mismatch: {passage_id}")
            parent = parents.get(passage.get("parent_id"))
            if not parent or passage.get("text", "") not in parent.get("text", ""):
                failures.append(f"chunk is not an exact span of its parent: {passage_id}")
            if passage.get("embedding_token_count", 257) > 256:
                failures.append(f"chunk exceeds encoder token limit: {passage_id}")

    reviewed = [card for card in cards if card["review_status"] == "reviewed"]
    for card in reviewed:
        card_passages = [passages.get(chunk_id) for chunk_id in card["chunk_ids"]]
        source = source_by_id.get(card["source_id"], {})
        if not card_passages or any(passage is None for passage in card_passages):
            failures.append(f"reviewed card lacks extracted passage: {card['evidence_id']}")
        elif any(passage.get("source_id") != card["source_id"] or passage.get("raw_sha256") != source.get("content_sha256") for passage in card_passages):
            failures.append(f"reviewed card passage/source mismatch: {card['evidence_id']}")

    active_ids = {card["evidence_id"] for card in reviewed}
    for action in actions:
        configured = set(action.get("evidence_ids", []))
        activation = set(action.get("activation_evidence_ids", action.get("evidence_ids", [])))
        action_cards = configured | activation
        if action.get("enabled") and not action_cards <= active_ids:
            failures.append(f"enabled action has inactive evidence: {action['action_id']}")
        if action.get("enabled") and activation != configured:
            failures.append(f"enabled action activation set differs from configured evidence: {action['action_id']}")
    for edge in edges:
        if edge.get("review_status") == "reviewed" and not set(edge.get("evidence_ids", [])) <= active_ids:
            failures.append(f"reviewed interaction has inactive evidence: {edge['edge_id']}")

    if len(reviewed) != 20:
        failures.append(f"required reviewed-card coverage is incomplete: {len(reviewed)}/20")
    risk_cards = [card for card in reviewed if any(word in item.casefold() for item in card["limitations"] for word in ("risk", "limit", "context", "not "))]
    if len(risk_cards) < 4:
        failures.append("fewer than four active risk/prerequisite cards")

    if not coverage_path.exists():
        failures.append("coverage matrix is missing")
    else:
        coverage = json.loads(coverage_path.read_text())
        def inspect_links(node: object, label: str = "coverage") -> None:
            if isinstance(node, dict):
                if "card_id" in node or "chunk_id" in node:
                    card = card_by_id.get(node.get("card_id"))
                    if not card or node.get("chunk_id") not in card.get("chunk_ids", []):
                        failures.append(f"stale coverage link in {label}: {node}")
                for key, value in node.items():
                    inspect_links(value, f"{label}.{key}")
            elif isinstance(node, list):
                for value in node:
                    inspect_links(value, label)
        inspect_links(coverage)
        for action in actions:
            if action.get("enabled") and action["action_id"] not in coverage.get("actions", {}):
                failures.append(f"enabled action missing from coverage matrix: {action['action_id']}")
        for edge in edges:
            if edge.get("review_status") == "reviewed" and edge["edge_id"] not in coverage.get("interaction_edges", {}):
                failures.append(f"reviewed edge missing from coverage matrix: {edge['edge_id']}")

    print(json.dumps({"reviewed_cards": len(reviewed), "parents": len(parents), "chunks": len(passages), "sources": len(sources), "active_risk_or_prerequisite_cards": len(risk_cards), "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
