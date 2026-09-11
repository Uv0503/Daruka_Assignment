"""Minimal API application; routes are added after Phase 0 preflight."""

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.services.orchestrator import Orchestrator
from app.storage.db import Database


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Biodiversity Intelligence", version="0.1.0")
    db = Database(settings.data_dir)
    db.initialize()
    app.state.settings = settings
    app.state.db = db
    app.state.orchestrator = Orchestrator(db, __import__("pathlib").Path(__file__).parent / "knowledge", settings.active_kb_version, settings)

    @app.get("/health")
    async def health() -> dict[str, object]:
        corpus_ready = app.state.orchestrator.retriever.corpus_ready
        return {
            "status": "healthy" if corpus_ready and app.state.db.knowledge_counts()["evidence_cards"] >= 20 else "unhealthy",
            "provider_configured": settings.provider_configured,
            "model": settings.llm_model,
            "corpus_ready": corpus_ready,
            "corpus_errors": app.state.orchestrator.retriever.integrity_errors,
        }

    app.include_router(router)
    return app


app = create_app()
