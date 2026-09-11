from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ChatRequest, ChatResponse
from app.services.evidence_display import complete_display_passage, display_claim

router = APIRouter()

@router.post("/v1/sessions")
async def create_session(request: Request) -> dict:
    return request.app.state.db.create_session()

@router.post("/v1/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> dict:
    try:
        return await request.app.state.orchestrator.chat(payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown session") from None

@router.get("/v1/knowledge/status")
async def knowledge_status(request: Request) -> dict:
    db = request.app.state.db
    counts = db.knowledge_counts()
    retriever = request.app.state.orchestrator.retriever
    return {"status": "ready" if retriever.corpus_ready and counts["evidence_cards"] >= 20 else "incomplete", "counts": counts, "kb_version": request.app.state.settings.active_kb_version, "integrity_errors": retriever.integrity_errors, "sources": [{"source_id": s["source_id"], "access_status": s["access_status"]} for s in retriever.sources]}

@router.get("/v1/evidence/{evidence_id}")
async def evidence(evidence_id: str, request: Request) -> dict:
    card = request.app.state.db.evidence(evidence_id)
    retriever = request.app.state.orchestrator.retriever
    if card is None or evidence_id not in retriever.cards_by_id or not retriever.corpus_ready: raise HTTPException(status_code=404, detail="Unknown active, provenance-verified evidence")
    source = retriever.sources_by_id[card["source_id"]]
    anchor = retriever.passages_by_id[card["chunk_ids"][0]]
    parent = retriever.parents_by_id[anchor["parent_id"]]
    display_passage = complete_display_passage(evidence_id, parent["text"])
    if display_passage is None:
        raise HTTPException(status_code=409, detail="Reviewed provenance exists, but no semantically complete public passage is available for this evidence card")
    return {
        "evidence": {
            "claim": display_claim(card),
            "applicability_conditions": card["applicability_conditions"],
            "limitations": card["limitations"],
        },
        "source": {
            "source_id": source["source_id"],
            "title": source["title"],
            "publisher": source["publisher"],
            "publication_year": source.get("publication_year"),
        },
        "exact_locator": parent["locator"],
        "complete_extracted_passage": display_passage,
        "url": source["url"],
    }
