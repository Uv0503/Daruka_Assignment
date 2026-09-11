"""Phase 0.5 terminal slice: JSON-like observations → BM25 → cited conditional answer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.retrieval import Retriever


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    retriever = Retriever(root / "app" / "knowledge", use_dense=False)
    state = {"current": {"land.use_type": {"value": "crop"}, "land.crop_system": {"value": "monoculture wheat"}, "soil.organic_carbon_pct": {"value": 0.3}, "climate.rainfall_pattern": {"value": "low"}}}
    packet = retriever.retrieve(state, "improve biodiversity", ["crop_diversification", "conditional_cover_cropping"])
    needed = {"ev_diversification_biodiversity", "ev_cover_water_risk"}
    if not needed <= packet["card_ids"]: raise SystemExit("required benefit/risk cards missing from BM25 slice")
    s4, s5 = retriever.sources_by_id["S4"], retriever.sources_by_id["S5"]
    print("Conditional diversification assessment: the reviewed agricultural synthesis supports considering diversification, but it is not a farm forecast. Because rainfall is reported low, first assess water availability and timing before any cover-crop component; growing cover crops can use soil water while active.")
    print(f"S4: {s4['title']} — {s4['url']}")
    print(f"S5: {s5['title']} — {s5['url']}")
    print("Skeleton limitation: BM25 and reviewed excerpts only; no state, Chroma, UI, or live LLM composition in this early slice.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
