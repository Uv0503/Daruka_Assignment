"""Build the offline index from reviewed, source-extracted child chunks.

Raw-source acquisition is deliberately separate from chat. Source parents are
split with the pinned encoder tokenizer and never silently truncated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


S8_PARSER_VERSION: Final = "s8_dom_literal_v1"
S8_REQUIRED_TITLES: Final = (
    "Water Budgeting and Climate-Resilient Cropping Systems",
    "Farmer Managed Natural Regeneration",
    "Crop Diversification and Intensification",
)
S8_PLACEHOLDER_MARKERS: Final = ("perspiciatis",)


def _normalise_s8_text(value: str) -> str:
    return " ".join(value.split())


def _s8_is_peer_title(node) -> bool:
    """Return true for a heading or for S8's standalone bold paragraph labels."""
    text = _normalise_s8_text(node.get_text(" ", strip=True))
    if not text:
        return False
    if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return True
    bold = node.find(["b", "strong"])
    return bold is not None and _normalise_s8_text(bold.get_text(" ", strip=True)) == text


def parse_s8_dom_literal_v1(html: str) -> dict[str, str]:
    """Extract S8's literal panels, retaining only text before the next peer title.

    S8 uses bold ``p`` elements as section labels.  Limiting the stream to
    paragraph/heading-level nodes prevents nested ``b`` tags from being treated
    as duplicate titles, while the peer-title boundary prevents adjacent,
    unrequested panels from being merged into a selected evidence passage.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "nav", "footer"]):
        node.decompose()

    content_tags = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
    title_nodes: dict[str, object] = {}
    for title in S8_REQUIRED_TITLES:
        matches = [
            node
            for node in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
            if _normalise_s8_text(node.get_text(" ", strip=True)) == title
        ]
        if not matches:
            raise ValueError(f"S8 required literal title missing: {title}")
        if len(matches) != 1:
            raise ValueError(f"S8 required literal title is ambiguous: {title} ({len(matches)} matches)")
        if not _s8_is_peer_title(matches[0]):
            raise ValueError(f"S8 required literal title is not a standalone peer title: {title}")
        title_nodes[title] = matches[0]

    # Choose the nearest common content block for all required literal titles.
    # A title-only match in a menu or a disconnected page region therefore
    # cannot satisfy this extraction contract.
    first_title = next(iter(title_nodes.values()))
    content_block = None
    for ancestor in [first_title, *first_title.parents]:
        if all(node is not ancestor and node in ancestor.descendants for node in title_nodes.values()):
            content_block = ancestor
            break
    if content_block is None:
        raise ValueError("S8 required literal titles do not share one content block")

    stream = []
    for node in content_block.find_all(list(content_tags)):
        # Keep an outer paragraph/list/heading only.  This avoids duplicate
        # text for, for example, a paragraph nested inside a list item.
        if any(parent is not content_block and parent.name in content_tags for parent in node.parents):
            continue
        if node.get_text(" ", strip=True):
            stream.append(node)

    positions = {title: stream.index(node) for title, node in title_nodes.items() if node in stream}
    if len(positions) != len(S8_REQUIRED_TITLES):
        raise ValueError("S8 required literal title is outside the selected content block stream")

    output: dict[str, str] = {}
    for title in S8_REQUIRED_TITLES:
        start = positions[title]
        body: list[str] = []
        for node in stream[start + 1:]:
            if _s8_is_peer_title(node):
                break
            candidate = _normalise_s8_text(node.get_text(" ", strip=True))
            if not any(marker in candidate.lower() for marker in S8_PLACEHOLDER_MARKERS):
                body.append(candidate)
        joined = " ".join(body).strip()
        if len(joined) < 40:
            raise ValueError(f"S8 required title has no substantive body: {title}")
        output[title] = joined
    if "sahel" not in output["Farmer Managed Natural Regeneration"].lower():
        raise ValueError("S8 FMNR body lost its Sahel qualifier")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="app/knowledge/sources.yaml")
    parser.add_argument("--fetch-s8", action="store_true", help="Fetch and validate current S8 HTML; fails if its required literal sections changed.")
    parser.add_argument("--download-model", action="store_true", help="Allow the pinned embedding model to be downloaded on a first install.")
    args = parser.parse_args()
    import chromadb
    import yaml
    from sentence_transformers import SentenceTransformer

    from app.config import get_settings
    from app.storage.db import Database

    settings = get_settings()
    root = Path(__file__).resolve().parents[1]
    source_data = yaml.safe_load(Path(args.manifest).read_text())["sources"]
    cards = [json.loads(line) for line in (root / "app" / "knowledge" / "cards.jsonl").read_text().splitlines() if line.strip()]
    reviewed = [card for card in cards if card["review_status"] == "reviewed"]
    passages_path = settings.data_dir / "processed" / "passages.jsonl"
    if not passages_path.exists(): raise SystemExit("missing extracted passages; run scripts/extract_passages.py after acquisition")
    passages = {item["chunk_id"]: item for line in passages_path.read_text().splitlines() if line.strip() for item in [json.loads(line)]}
    unresolved = [card["evidence_id"] for card in reviewed if any(chunk_id not in passages or passages[chunk_id].get("source_id") != card["source_id"] for chunk_id in card["chunk_ids"])]
    if unresolved: raise SystemExit("reviewed cards without source-linked extracted passages: " + ", ".join(unresolved))
    source_by_id = {source["source_id"]: source for source in source_data}
    provenance_errors = []
    active_parent_ids = {
        passages[chunk_id]["parent_id"]
        for card in reviewed
        for chunk_id in card["chunk_ids"]
    }
    active_chunk_ids = [
        chunk_id
        for chunk_id, passage in passages.items()
        if passage["parent_id"] in active_parent_ids
    ]
    for card in reviewed:
        card_passages = [passages[chunk_id] for chunk_id in card["chunk_ids"]]
        source = source_by_id[card["source_id"]]
        for passage in card_passages:
            raw_path = root / passage["raw_path"]
            if source.get("access_status") != "verified" or source.get("content_sha256") != passage.get("raw_sha256"):
                provenance_errors.append(card["evidence_id"])
                break
            if not raw_path.is_file() or sha(raw_path.read_bytes()) != passage.get("raw_sha256") or sha(passage["text"]) != passage.get("text_sha256"):
                provenance_errors.append(card["evidence_id"])
                break
    if provenance_errors: raise SystemExit("reviewed passages have invalid raw-source provenance: " + ", ".join(provenance_errors))
    if len({card["source_id"] for card in reviewed}) < 6: raise SystemExit("reviewed cards do not cover six source works")
    if args.fetch_s8:
        import httpx
        s8 = next(source for source in source_data if source["source_id"] == "S8")
        response = httpx.get(s8["url"], timeout=15, follow_redirects=True)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            raise SystemExit(f"S8 expected HTML but received content type: {content_type or 'missing'}")
        if len(response.content) > 10_000_000:
            raise SystemExit("S8 response exceeds the 10 MB ingestion limit")
        raw = response.text
        sections = parse_s8_dom_literal_v1(raw)
        (settings.data_dir / "raw").mkdir(parents=True, exist_ok=True)
        path = settings.data_dir / "raw" / "S8.html"
        path.write_text(raw)
        provenance = {
            "source_id": "S8",
            "source_url": str(response.url),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "content_sha256": sha(raw),
            "parser_version": S8_PARSER_VERSION,
            "sections": [
                {
                    "title": title,
                    "paragraph_index": 1,
                    "passage_sha256": sha(body),
                }
                for title, body in sections.items()
            ],
        }
        (settings.data_dir / "raw" / "S8.s8_dom_literal_v1.json").write_text(json.dumps(provenance, indent=2))
    # Ingestion must be reproducible from the pinned local model cache rather
    # than silently downloading a changed encoder at build time.
    model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device, local_files_only=not args.download_model)
    texts = [passages[chunk_id]["text"] for chunk_id in active_chunk_ids]
    token_counts = [len(model.tokenizer.encode(text, add_special_tokens=True)) for text in texts]
    if max(token_counts) > 256: raise SystemExit("embedding input would be silently truncated")
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()
    chroma_path = settings.data_dir / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_path))
    try: client.delete_collection("biodiversity_chunks")
    except Exception:  # noqa: BLE001 - collection is absent on first build
        print("No existing Chroma collection to replace.")
    collection = client.create_collection("biodiversity_chunks", metadata={"embedding_model": settings.embedding_model, "dimension": len(embeddings[0])})
    evidence_by_chunk = {chunk_id: [card["evidence_id"] for card in reviewed if chunk_id in card["chunk_ids"]] for chunk_id in active_chunk_ids}
    card_by_id = {card["evidence_id"]: card for card in reviewed}
    collection.add(ids=active_chunk_ids, documents=texts, embeddings=embeddings, metadatas=[{"source_id": passages[chunk_id]["source_id"], "evidence_ids": ",".join(evidence_by_chunk[chunk_id]), "review_status": "reviewed_source_context", "raw_sha256": passages[chunk_id]["raw_sha256"], "text_sha256": passages[chunk_id]["text_sha256"], "locator": passages[chunk_id]["locator"], "ecosystems": ",".join(sorted({ecosystem for evidence_id in evidence_by_chunk[chunk_id] for ecosystem in card_by_id[evidence_id]["ecosystems"]}))} for chunk_id in active_chunk_ids])
    active_passages = {chunk_id: passages[chunk_id] for chunk_id in active_chunk_ids}
    db = Database(settings.data_dir); db.initialize(); db.seed_knowledge(source_data, reviewed, active_passages)
    processed = settings.data_dir / "processed"; processed.mkdir(parents=True, exist_ok=True)
    parent_path = settings.data_dir / "processed" / "parent_passages.jsonl"
    manifest = {"kb_version": settings.active_kb_version, "sources": [{"source_id": s["source_id"], "url": s["url"], "content_sha256": s.get("content_sha256"), "local_path": s.get("local_path"), "retrieved_at": s.get("retrieved_at"), "manifest_sha256": sha(json.dumps(s, sort_keys=True))} for s in source_data], "cards": len(reviewed), "chunks": len(active_chunk_ids), "parents": sum(1 for line in parent_path.read_text().splitlines() if line.strip()), "cards_sha256": sha((root / "app" / "knowledge" / "cards.jsonl").read_bytes()), "passages_sha256": sha(passages_path.read_bytes()), "parents_sha256": sha(parent_path.read_bytes()), "embedding_model": settings.embedding_model, "embedding_dimension": len(embeddings[0]), "preprocessing_version": "minilm_wordpiece_175_overlap_25_v1", "collection_name": "biodiversity_chunks", "created_at": datetime.now(UTC).isoformat()}
    (processed / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"status": "built", "cards": len(reviewed), "chunks": len(texts), "dimension": len(embeddings[0])}))
    return 0

if __name__ == "__main__": raise SystemExit(main())
