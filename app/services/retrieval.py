from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

SYNONYMS = {"soc": "soil organic carbon", "water shortage": "moisture limitation", "habitat strip": "field margin native perennial strip"}


def tokens(text: str) -> list[str]:
    normalized = text.lower()
    for old, new in SYNONYMS.items():
        normalized = normalized.replace(old, new)
    return re.findall(r"[a-z0-9]+", normalized)


class Retriever:
    def __init__(self, knowledge_dir: Path, *, use_dense: bool = True):
        import yaml
        from rank_bm25 import BM25Okapi

        self.knowledge_dir, self.use_dense = knowledge_dir, use_dense
        self.sources = yaml.safe_load((knowledge_dir / "sources.yaml").read_text())["sources"]
        self.actions = {
            action["action_id"]: action
            for action in yaml.safe_load((knowledge_dir / "actions.yaml").read_text())["actions"]
        }
        self.all_cards = [json.loads(line) for line in (knowledge_dir / "cards.jsonl").read_text().splitlines() if line.strip()]
        self.cards = [card for card in self.all_cards if card["review_status"] == "reviewed"]
        self.cards_by_id = {card["evidence_id"]: card for card in self.cards}
        self.sources_by_id = {source["source_id"]: source for source in self.sources}
        passages_path = knowledge_dir.parents[1] / "data" / "processed" / "passages.jsonl"
        self.passages_by_id = {
            passage["chunk_id"]: passage
            for line in passages_path.read_text().splitlines()
            if line.strip()
            for passage in [json.loads(line)]
        } if passages_path.exists() else {}
        parents_path = knowledge_dir.parents[1] / "data" / "processed" / "parent_passages.jsonl"
        self.parents_by_id = {
            parent["parent_id"]: parent
            for line in parents_path.read_text().splitlines()
            if line.strip()
            for parent in [json.loads(line)]
        } if parents_path.exists() else {}
        active_parent_ids = {
            self.passages_by_id[chunk_id]["parent_id"]
            for card in self.cards
            for chunk_id in card["chunk_ids"]
            if chunk_id in self.passages_by_id
        }
        active_chunk_ids = [
            chunk_id
            for chunk_id, passage in self.passages_by_id.items()
            if passage["parent_id"] in active_parent_ids
        ]
        self.chunks = [self.passages_by_id[chunk_id] for chunk_id in active_chunk_ids]
        self.chunk_to_card_ids = {chunk_id: [card["evidence_id"] for card in self.cards if chunk_id in card["chunk_ids"]] for chunk_id in active_chunk_ids}
        if self.chunks:
            self.bm25 = BM25Okapi([tokens(chunk["text"]) for chunk in self.chunks])
        else:
            self.bm25 = None
        self._encoder = None
        self._embeddings = None
        self._chroma = None
        self._chroma_by_chunk = {chunk["chunk_id"]: index for index, chunk in enumerate(self.chunks)}
        self.integrity_errors = self._integrity_errors()

    def _integrity_errors(self) -> list[str]:
        """Cheap startup checks; retrieval does not silently claim a ready corpus."""
        errors: list[str] = []
        if len(self.cards_by_id) != len(self.cards) or len(self.cards_by_id) != len(set(self.cards_by_id)):
            errors.append("corpus has duplicate reviewed evidence IDs")
        for card in self.cards:
            card_passages = [self.passages_by_id.get(chunk_id) for chunk_id in card["chunk_ids"]]
            if not card_passages or any(passage is None for passage in card_passages):
                errors.append(f"reviewed card lacks extracted passage: {card['evidence_id']}")
                continue
            for passage in card_passages:
                if passage.get("source_id") != card["source_id"]:
                    errors.append(f"passage/card source link mismatch: {card['evidence_id']}")
                if not passage.get("raw_sha256") or not passage.get("text_sha256") or not passage.get("locator"):
                    errors.append(f"passage provenance incomplete: {card['evidence_id']}")
                    continue
                if hashlib.sha256(passage["text"].encode()).hexdigest() != passage["text_sha256"]:
                    errors.append(f"passage text hash mismatch: {card['evidence_id']}")
                if passage.get("embedding_token_count", 257) > 256:
                    errors.append(f"passage exceeds encoder token limit: {card['evidence_id']}")
                source = self.sources_by_id.get(card["source_id"], {})
                raw_path = self.knowledge_dir.parents[1] / str(passage.get("raw_path", ""))
                if source.get("access_status") != "verified" or source.get("content_sha256") != passage["raw_sha256"]:
                    errors.append(f"source registry provenance mismatch: {card['evidence_id']}")
                elif not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest() != passage["raw_sha256"]:
                    errors.append(f"stored raw source hash mismatch: {card['evidence_id']}")
        manifest_path = self.knowledge_dir.parents[1] / "data" / "processed" / "manifest.json"
        if not manifest_path.exists():
            return ["processed corpus manifest is missing"]
        try:
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("cards") != len(self.cards):
                errors.append("manifest card count does not match reviewed cards")
            raw_cards = (self.knowledge_dir / "cards.jsonl").read_bytes()
            expected = manifest.get("cards_sha256")
            if expected and expected != hashlib.sha256(raw_cards).hexdigest():
                errors.append("manifest card hash does not match reviewed cards")
            passages_path = self.knowledge_dir.parents[1] / "data" / "processed" / "passages.jsonl"
            expected_passages = manifest.get("passages_sha256")
            if not expected_passages or not passages_path.exists() or expected_passages != hashlib.sha256(passages_path.read_bytes()).hexdigest():
                errors.append("manifest passage hash does not match extracted passages")
            parents_path = self.knowledge_dir.parents[1] / "data" / "processed" / "parent_passages.jsonl"
            expected_parents = manifest.get("parents_sha256")
            if not expected_parents or not parents_path.exists() or expected_parents != hashlib.sha256(parents_path.read_bytes()).hexdigest():
                errors.append("manifest parent-passage hash does not match extracted parents")
            if manifest.get("embedding_model") != "sentence-transformers/all-MiniLM-L6-v2":
                errors.append("manifest embedding model is not all-MiniLM-L6-v2")
            if manifest.get("embedding_dimension") != 384:
                errors.append("manifest embedding dimension is not 384")
            chroma_path = self.knowledge_dir.parents[1] / "data" / "chroma"
            try:
                import chromadb

                collection = chromadb.PersistentClient(path=str(chroma_path)).get_collection(manifest.get("collection_name", "biodiversity_chunks"))
                if collection.count() != len(self.chunks) or manifest.get("chunks") != len(self.chunks):
                    errors.append("Chroma chunk count does not match active chunks")
                metadata = collection.metadata or {}
                if metadata.get("embedding_model") != manifest.get("embedding_model") or metadata.get("dimension") != manifest.get("embedding_dimension"):
                    errors.append("Chroma metadata does not match manifest")
                stored = collection.get(include=["documents", "metadatas"])
                expected_chunks = {chunk["chunk_id"]: chunk for chunk in self.chunks}
                if set(stored["ids"]) != set(expected_chunks):
                    errors.append("Chroma chunk IDs do not match active passages")
                else:
                    for chunk_id, document, record in zip(stored["ids"], stored["documents"], stored["metadatas"]):
                        passage = expected_chunks[chunk_id]
                        if document != passage["text"] or record.get("text_sha256") != passage["text_sha256"] or record.get("raw_sha256") != passage["raw_sha256"]:
                            errors.append(f"Chroma document provenance mismatch: {chunk_id}")
            except Exception:  # noqa: BLE001 - third-party persistent-store boundary
                errors.append("Chroma collection is missing or unreadable")
        except (OSError, ValueError, TypeError):
            errors.append("processed corpus manifest is unreadable")
        return errors

    @property
    def corpus_ready(self) -> bool:
        return not self.integrity_errors

    def _dense_scores(self, query: str) -> list[float] | None:
        if not self.use_dense:
            return None
        try:
            if self._encoder is None:
                from sentence_transformers import SentenceTransformer
                self._encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu", local_files_only=True)
                chroma_dir = self.knowledge_dir.parents[1] / "data" / "chroma"
                if chroma_dir.exists():
                    import chromadb
                    self._chroma = chromadb.PersistentClient(path=str(chroma_dir)).get_collection("biodiversity_chunks")
                else:
                    self._embeddings = self._encoder.encode([chunk["text"] for chunk in self.chunks], normalize_embeddings=True)
            vector = self._encoder.encode([query], normalize_embeddings=True)[0]
            if self._chroma is not None:
                result = self._chroma.query(query_embeddings=[vector.tolist()], n_results=min(12, len(self.chunks)), include=["distances"])
                scores = [-999.0] * len(self.chunks)
                for chunk_id, distance in zip(result["ids"][0], result["distances"][0]): scores[self._chroma_by_chunk[chunk_id]] = -float(distance)
                return scores
            return (self._embeddings @ vector).tolist()
        except Exception:  # noqa: BLE001 - dense retrieval is an optional channel; lexical trace remains available
            return None

    def queries(self, state: dict, goal: str) -> list[str]:
        current = {field: event["value"] for field, event in state["current"].items() if event}
        land = current.get("land.use_type", "unknown land system")
        crop = current.get("land.crop_system", "")
        rainfall = current.get("climate.rainfall_pattern", current.get("climate.annual_rainfall_mm", "unknown rainfall"))
        queries = [f"{land} {crop} soil biodiversity {rainfall} {goal}".strip()]
        if current.get("pressures.pesticide_use"):
            queries.append("pesticide soil invertebrate exposure assessment evidence")
        if land == "crop":
            queries.append(f"crop diversification biodiversity evidence {crop} {rainfall}")
            queries.append(f"cover crop water use rainfall termination risk {rainfall}")
        elif land in {"forest", "grassland", "wetland", "pasture"}:
            queries.append(f"native habitat land conversion protection {land} {goal}")
            queries.append(f"habitat restoration reconnection biodiversity {land}")
        else:
            queries.append(f"{goal} evidence conditions limitations")
            queries.append(f"{goal} risks trade-offs context dependence")
        # Bound multi-query retrieval to three explicit, traceable queries.
        return queries[:3]

    def retrieve(self, state: dict, goal: str, candidate_action_ids: list[str]) -> dict:
        if not self.corpus_ready:
            raise RuntimeError("corpus integrity check failed: " + "; ".join(self.integrity_errors))
        started = time.perf_counter()
        all_scores: dict[int, dict[str, int | float]] = {}
        query_list = self.queries(state, goal)
        query_details: list[dict] = [
            {"query": query, "purpose": "site_context"} for query in query_list
        ]

        def score_query(query: str, purpose: str) -> list[int]:
            """Rank one query and add its channels to the shared RRF trace."""
            query_index = len(query_details)
            if query_index >= 12:
                return []
            query_list.append(query)
            query_details.append({"query": query, "purpose": purpose})
            lexical = self.bm25.get_scores(tokens(query))
            lexical_order = sorted(range(len(self.chunks)), key=lambda i: (-lexical[i], self.chunks[i]["chunk_id"]))[:12]
            dense = self._dense_scores(query)
            dense_order = sorted(range(len(self.chunks)), key=lambda i: (-(dense[i] if dense else -999), self.chunks[i]["chunk_id"]))[:12] if dense else []
            for rank, idx in enumerate(lexical_order, 1):
                item = all_scores.setdefault(idx, {"rrf": 0.0})
                item["rrf"] += 1 / (60 + rank)
                item[f"lexical_rank_q{query_index + 1}"] = rank
            for rank, idx in enumerate(dense_order, 1):
                item = all_scores.setdefault(idx, {"rrf": 0.0})
                item["rrf"] += 1 / (60 + rank)
                item[f"dense_rank_q{query_index + 1}"] = rank
            return list(dict.fromkeys([*lexical_order, *dense_order]))

        # Score the site queries first. query_details is pre-populated, so run
        # these without appending a duplicate description.
        initial_queries = list(query_list)
        query_list.clear()
        query_details.clear()
        for query in initial_queries:
            score_query(query, "site_context")

        # A single generic top-k became brittle as the corpus grew. Each
        # applicable candidate now receives an explicit, bounded action query.
        # A card is eligible only when one of its reviewed anchor chunks ranks
        # in the top 12 for that query (or a bounded evidence-coverage query).
        # This is retrieval, not an action/evidence allowlist bypass, and every
        # added chunk retains its query ranks in the public trace.
        coverage_by_action: dict[str, dict[str, int]] = {}
        for action_id in candidate_action_ids:
            action = self.actions.get(action_id)
            if not action or not action.get("enabled"):
                continue
            required = [eid for eid in action.get("activation_evidence_ids", action["evidence_ids"]) if eid in self.cards_by_id]
            claim_text = " ".join(self.cards_by_id[eid]["claim_summary"] for eid in required)
            ranked_indices = score_query(f"{action['title']} {claim_text}", f"candidate_action:{action_id}")
            found: dict[str, int] = {}
            for idx in ranked_indices:
                for evidence_id in self.chunk_to_card_ids[self.chunks[idx]["chunk_id"]]:
                    if evidence_id in required and evidence_id not in found:
                        found[evidence_id] = idx
            # Only missing coverage gets a focused query, and the total query
            # ceiling above prevents unbounded per-card corpus expansion.
            for evidence_id in required:
                if evidence_id in found:
                    continue
                card = self.cards_by_id[evidence_id]
                focused = score_query(
                    f"{action['title']} {card['claim_summary']} {' '.join(card['applicability_conditions'])}",
                    f"evidence_coverage:{action_id}:{evidence_id}",
                )
                anchor = next(
                    (
                        idx for idx in focused
                        if evidence_id in self.chunk_to_card_ids[self.chunks[idx]["chunk_id"]]
                    ),
                    None,
                )
                if anchor is not None:
                    found[evidence_id] = anchor
            coverage_by_action[action_id] = found

        ranked_all = sorted(all_scores, key=lambda i: (-float(all_scores[i]["rrf"]), self.chunks[i]["chunk_id"]))
        selected_indices: list[int] = []
        selected_card_ids: list[str] = []

        def add_index(idx: int) -> None:
            if idx not in selected_indices and len(selected_indices) < 18:
                selected_indices.append(idx)
            for evidence_id in self.chunk_to_card_ids[self.chunks[idx]["chunk_id"]]:
                if evidence_id not in selected_card_ids and len(selected_card_ids) < 12:
                    selected_card_ids.append(evidence_id)

        # Preserve general relevance, then guarantee only complete action
        # coverage sets that fit the bounded 12-card packet.
        for idx in ranked_all:
            if self.chunk_to_card_ids[self.chunks[idx]["chunk_id"]]:
                add_index(idx)
            if len(selected_card_ids) >= 4:
                break
        for action_id in candidate_action_ids:
            action = self.actions.get(action_id)
            found = coverage_by_action.get(action_id, {})
            if not action:
                continue
            required = list(action.get("activation_evidence_ids", action["evidence_ids"]))
            if not set(required) <= set(found):
                continue
            new_cards = set(required) - set(selected_card_ids)
            if len(selected_card_ids) + len(new_cards) > 12:
                continue
            for evidence_id in required:
                add_index(found[evidence_id])

        # Fill remaining space with ranked reviewed anchors without evicting a
        # complete action evidence set.
        for idx in ranked_all:
            card_ids = self.chunk_to_card_ids[self.chunks[idx]["chunk_id"]]
            if card_ids and len(set(selected_card_ids) | set(card_ids)) <= 12:
                add_index(idx)
            if len(selected_indices) >= 18 or len(selected_card_ids) >= 12:
                break
        selected = [self.cards_by_id[evidence_id] for evidence_id in selected_card_ids]
        trace_excerpts = []
        for i in selected_indices:
            chunk = self.chunks[i]
            for evidence_id in self.chunk_to_card_ids[chunk["chunk_id"]]:
                card = self.cards_by_id[evidence_id]
                trace_excerpts.append({"chunk_id": chunk["chunk_id"], "evidence_id": evidence_id, "source_id": chunk["source_id"], "locator": chunk["locator"], "excerpt": chunk["text"], "relevance": all_scores[i].get("rrf", 0), "ranks": {key: value for key, value in all_scores[i].items() if key != "rrf"}, "evidence_quality": card["relation_type"]})
        return {"queries": query_details, "cards": selected, "card_ids": {card["evidence_id"] for card in selected}, "trace_excerpts": trace_excerpts, "coverage_by_action": {action_id: sorted(found) for action_id, found in coverage_by_action.items()}, "timings": {"retrieval_seconds": round(time.perf_counter() - started, 4)}, "dense_available": self._encoder is not None}
