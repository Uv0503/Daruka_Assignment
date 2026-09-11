"""Extract complete source parents and MiniLM-tokenizer-aware child chunks."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evidence_display import ANCHORS

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TARGET_WORD_PIECES = 175
OVERLAP_WORD_PIECES = 25

def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def normalise(value: str) -> str:
    return " ".join(value.split())


def source_path(root: Path, source_id: str) -> Path | None:
    return next((path for suffix in (".html", ".pdf") if (path := root / "data" / "raw" / f"{source_id}{suffix}").exists()), None)


def html_parent(path: Path, anchor: str) -> tuple[str, str, str | None, int | None] | None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(errors="replace"), "html.parser")
    for node in soup(["script", "style", "nav", "footer"]):
        node.decompose()
    for index, node in enumerate(soup.find_all(["p", "li", "figcaption"]), 1):
        text = normalise(node.get_text(" ", strip=True))
        if anchor.casefold() in text.casefold():
            heading = node.find_previous(["h1", "h2", "h3", "h4"])
            section = normalise(heading.get_text(" ", strip=True)) if heading else "unheaded HTML passage"
            candidates = [node, *node.find_all_previous("p")]
            for candidate in candidates:
                strong = candidate.find(["strong", "b"])
                if not strong:
                    continue
                label = normalise(strong.get_text(" ", strip=True)).rstrip(".")
                full = normalise(candidate.get_text(" ", strip=True)).rstrip(".")
                # Some publisher pages encode a section label as the bold
                # opening sentence of its first paragraph (S5), while others
                # use a standalone bold paragraph (S8). Long descriptive
                # labels are retained as the source-relative section; short
                # inline emphasis such as a process name is not promoted.
                if label == full or (full.startswith(label + ".") and len(label.split()) >= 4):
                    section = label
                    break
            return text, f"{section}, paragraph {index}", section, index
    abstract = soup.find("meta", attrs={"name": "citation_abstract"})
    if abstract and abstract.get("content"):
        text = normalise(str(abstract["content"]))
        if anchor.casefold() in text.casefold():
            return text, "citation_abstract metadata", "Abstract", None
    return None


def pdf_parent(path: Path, anchor: str) -> tuple[str, str, str | None, int | None] | None:
    from pypdf import PdfReader

    for page_index, page in enumerate(PdfReader(str(path)).pages):
        text = normalise(page.extract_text() or "")
        if anchor.casefold() in text.casefold():
            return text, f"PDF page index {page_index}", None, page_index
    return None


def split_parent(parent: dict, tokenizer, card: dict, anchor: str) -> list[dict]:
    encoded = tokenizer(parent["text"], add_special_tokens=False, return_offsets_mapping=True, verbose=False)
    offsets = encoded["offset_mapping"]
    total = len(offsets)
    windows: list[tuple[int, int]] = []
    if total <= 190:
        windows.append((0, total))
    else:
        start = 0
        while start < total:
            end = min(total, start + TARGET_WORD_PIECES)
            if 0 < total - end < 150:
                start, end = max(0, total - TARGET_WORD_PIECES), total
            if not windows or windows[-1] != (start, end):
                windows.append((start, end))
            if end == total:
                break
            start = end - OVERLAP_WORD_PIECES
        # Add one normal-sized anchor-centred window when a literal phrase
        # would otherwise straddle a child boundary. The regular windows still
        # cover the complete parent; this window makes the reviewed claim link
        # explicit without dropping surrounding source context.
        anchor_char = parent["text"].casefold().find(anchor.casefold())
        if anchor_char >= 0:
            anchor_token = next((i for i, (_, stop) in enumerate(offsets) if stop > anchor_char), 0)
            start = max(0, anchor_token - 50)
            end = min(total, start + TARGET_WORD_PIECES)
            start = max(0, end - TARGET_WORD_PIECES)
            if (start, end) not in windows:
                windows.append((start, end))
    children = []
    for start, end in windows:
        text = parent["text"][offsets[start][0]:offsets[end - 1][1]].strip()
        text_hash = sha(text)
        identity = f"{parent['raw_sha256']}|{parent['locator']}|{text_hash}"
        children.append({
            "chunk_id": f"chunk_{sha(identity)[:20]}", "source_id": parent["source_id"],
            "parent_id": parent["parent_id"], "text": text, "text_sha256": text_hash,
            "section": parent["section"], "paragraph_index": parent["paragraph_index"],
            "pdf_page_index": parent["pdf_page_index"], "printed_page_label": None,
            "embedding_token_count": len(tokenizer.encode(text, add_special_tokens=True)),
            "domain_tags": [card["metric"], card["intervention"]], "ecosystem_tags": card["ecosystems"],
            "geography_tags": [card["geography"]], "review_status": "reviewed", "kb_version": "v1",
            "raw_path": parent["raw_path"], "raw_sha256": parent["raw_sha256"], "locator": parent["locator"],
        })
    return children


def extract(root: Path) -> tuple[list[dict], list[dict], dict[str, list[str]], list[str]]:
    from transformers import AutoTokenizer

    cards = [json.loads(line) for line in (root / "app" / "knowledge" / "cards.jsonl").read_text().splitlines() if line.strip()]
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    parents_by_key: dict[tuple[str, str, str], dict] = {}
    chunks_by_id: dict[str, dict] = {}
    card_map: dict[str, list[str]] = {}
    failures: list[str] = []
    for card in cards:
        if card["review_status"] != "reviewed":
            continue
        evidence_id, source_id = card["evidence_id"], card["source_id"]
        anchor, path = ANCHORS.get(evidence_id), source_path(root, source_id)
        if not anchor or path is None:
            failures.append(f"{evidence_id}: missing literal anchor or raw source")
            continue
        if source_id == "S8" and evidence_id == "ev_dryland_water_budget":
            from scripts.ingest import parse_s8_dom_literal_v1
            title = "Water Budgeting and Climate-Resilient Cropping Systems"
            text = parse_s8_dom_literal_v1(path.read_text(errors="replace"))[title]
            found = (text, f"{title}, extracted body", title, None)
        else:
            found = html_parent(path, anchor) if path.suffix == ".html" else pdf_parent(path, anchor)
        if found is None:
            failures.append(f"{evidence_id}: literal anchor not found in {path.name}")
            continue
        text, locator, section, position = found
        raw_hash, text_hash = sha(path.read_bytes()), sha(text)
        key = (source_id, locator, text_hash)
        parent = parents_by_key.get(key)
        if parent is None:
            identity = f"{raw_hash}|{locator}|{text_hash}"
            parent = {
                "parent_id": f"parent_{sha(identity)[:20]}", "source_id": source_id, "text": text,
                "text_sha256": text_hash, "raw_path": str(path.relative_to(root)), "raw_sha256": raw_hash,
                "locator": locator, "section": section, "paragraph_index": position if path.suffix == ".html" else None,
                "pdf_page_index": position if path.suffix == ".pdf" else None, "kb_version": "v1",
            }
            parents_by_key[key] = parent
        children = split_parent(parent, tokenizer, card, anchor)
        for child in children:
            chunks_by_id.setdefault(child["chunk_id"], child)
        anchored = [child["chunk_id"] for child in children if anchor.casefold() in child["text"].casefold()]
        if source_id == "S8" and evidence_id == "ev_dryland_water_budget":
            anchored = [child["chunk_id"] for child in children]
        if not anchored:
            failures.append(f"{evidence_id}: no child chunk retains the literal anchor")
            continue
        # A card points only to the child that contains its reviewed literal
        # anchor. Sibling children remain indexed as source context through
        # the shared parent, but cannot by themselves activate this card.
        card_map[evidence_id] = anchored
    return list(parents_by_key.values()), list(chunks_by_id.values()), card_map, failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parents, chunks, card_map, failures = extract(root)
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    parent_path, chunk_path, map_path = processed / "parent_passages.jsonl", processed / "passages.jsonl", processed / "card_chunk_map.json"
    parent_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in parents))
    chunk_path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in chunks))
    map_path.write_text(json.dumps(card_map, indent=2) + "\n")
    report = {"parents": len(parents), "chunks": len(chunks), "mapped_cards": len(card_map), "failures": failures, "chunking": {"tokenizer": MODEL, "target_word_pieces": TARGET_WORD_PIECES, "overlap_word_pieces": OVERLAP_WORD_PIECES, "max_model_tokens": 256}}
    (processed / "passage_extraction_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
