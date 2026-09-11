# Biodiversity Intelligence

🚀 **Live Deployment:** [Daruka Assignment on Streamlit](https://darukaassignment-xogej2zbsrk9stxh45ubrw.streamlit.app/)
Local, single-user biodiversity decision support built with FastAPI, Streamlit,
SQLite, Chroma, BM25, and `all-MiniLM-L6-v2`. Groq Chat Completions is used only
for strict-schema action selection; the server renders scientific wording,
citations, and numerical fields deterministically.

## Requirement-to-evidence map

| Requirement | Evidence in this repository | Observed status |
|---|---|---|
| FastAPI, Streamlit, SQLite, Chroma | `app/main.py`, `ui/app.py`, `app/storage/db.py`, `scripts/ingest.py` | Healthy backend and focused UI smoke verified on current corpus |
| Groq strict structured output | `app/services/llm_client.py`, `scripts/preflight.py` | Prior live preflight passed; not rerun in this task |
| BM25 + dense hybrid retrieval | `app/services/retrieval.py`, `artifacts/evaluation.json` | Implemented; the recorded 0.9167 result predates this corpus |
| Reviewed evidence cards and citations | `app/knowledge/cards.jsonl`, `data/processed/passages.jsonl`, `/v1/evidence/{id}` | File validation passes: 20 hash-linked cards across eight sources; 19 publicly readable cards |
| State, corrections, null/omitted, hypotheticals | `app/services/state.py`, `tests/integration/test_api.py` | Repetition fix implemented; verification deferred |
| Ten golden cases, ablation, support diagnostic | `scripts/run_golden.py`, `artifacts/golden_results.json`, `artifacts/evaluation.json` | Historical artifacts; rerun required |
| S8 source parser | `scripts/ingest.py`, `tests/unit/test_s8_ingest.py` | Acquired page/parser retained; tests not rerun |
| Flagship S4 numeric illustration | `app/services/verification.py`, `data/processed/passages.jsonl` | Implemented from the acquired S4 Results passage; acceptance scenario has not been rerun |

## Setup

Prerequisites: Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Set GROQ_API_KEY in .env. Do not commit this file.
uv sync --frozen
uv run python scripts/preflight.py
# Acquire only allowlisted sources; this preserves raw bytes and acquisition
# metadata. A blocked source remains blocked rather than becoming reviewed.
uv run python scripts/acquire_sources.py
uv run python scripts/extract_passages.py
# First installation only: permits the pinned encoder download.
uv run python scripts/ingest.py --download-model --manifest app/knowledge/sources.yaml
```

Subsequent local corpus builds are offline with the cached encoder:

```bash
uv run python scripts/extract_passages.py
uv run python scripts/ingest.py --manifest app/knowledge/sources.yaml
# Check source hashes, passage links, card coverage and action evidence gates.
uv run python scripts/validate_kb.py
```

## Run in two terminals

Terminal 1:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Terminal 2:

```bash
API_BASE_URL=http://127.0.0.1:8000 uv run streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Open the local URL printed by Streamlit. If ports 8000/8501 are occupied, use
8010/8510 respectively and set `API_BASE_URL=http://127.0.0.1:8010` in the UI
terminal. The currently checked demo uses `http://127.0.0.1:8501`.
The UI sends only HTTP requests to the
API; it never opens SQLite or Chroma directly. Do not use more than one API
worker for this local SQLite demonstration.

## Verification commands

```bash
uv run pytest -q
uv run python scripts/run_golden.py
uv run python scripts/evaluate.py
```

Historical evaluation artifacts predate the source-passage corpus and must not
be treated as validation of the current build. The current file-level validator
reports 8 acquired sources, 20 reviewed cards, 19 parent passages and 54 indexed
children with no failures. The approximate 100–300 chunk figure in the build
specification is a capacity estimate, not a minimum: unrelated or duplicated
passages should not be added merely to increase this count.

For a temporary local HTTP smoke while the API is running on port 8765:

```bash
uv run python scripts/smoke_api.py
```

It uses fresh sessions and checks text/JSON equivalence, null versus omitted,
and session isolation. Provider-failure behavior is deterministically injected
in `tests/integration/test_api.py`; it is not falsely described as a live
Groq outage check.

## Architecture and safeguards

1. FastAPI validates strict `ChatRequest` input (including finite numeric
   values) and serializes each session with an `asyncio.Lock`.
2. SQLite stores accepted observation events, profiles, turns, and traces.
   Text and JSON use shared normalized dotted-field updates; `null` clears and
   omitted fields preserve state. Hypotheticals use an isolated copy.
3. The retriever runs BM25 and local MiniLM dense retrieval over the same
   extracted, hash-linked source passages, fuses top results with RRF, and caps
   the packet at 12 cards. Raw-source, passage, manifest, model, Chroma-ID,
   document, and hash checks make corpus failure explicit.
4. Rules activate only enabled action classes with retrieved activation cards,
   compatible land use, and required observations. Water-sensitive cover crops
   require rainfall context. Interaction paths point to reviewed edges and
   accepted observation IDs.
5. The deterministic validator rejects unreviewed evidence, unknown/disabled
   actions, out-of-packet citations, unreviewed edges, local predictions, free
   numerical prose, and insufficient environmental-concept coverage. A Groq
   failure returns `degraded` with reviewed server templates.

## Evidence and known limitations

Each active card now resolves through an allowlisted source registry entry,
acquisition metadata, stored raw bytes and SHA-256, a complete extracted
parent passage, one or more tokenizer-aware child chunks, a chunk hash and an
exact locator. All registered IDs—S1, S2, S3, S4, S5, S6, S8 and S9—have at
least one reviewed card and complete that file-level chain. The acquired S5
chapter supplies both adverse growing-season/dryland water evidence and the
possible post-termination water benefit; all four cards must be retrieved
before its conditional action can activate. The S4 Results paragraph supports lnRR 0.34 with 95% CI
[0.15, 0.53]; the server can only render the derived 40.5% [16.2%, 69.9%]
figure as a pooled literature illustration, never as a local forecast, SOC
effect, or guaranteed outcome.

Long source passages are split with the pinned MiniLM tokenizer into about
175 word-piece children with 25-word-piece overlap. Short, indivisible source
paragraphs remain intact instead of being padded with unrelated prose; no
source passage is silently truncated. Only an anchor-containing child is
allowed to activate its reviewed evidence card, while sibling chunks remain
indexed as source context through the same parent.

Nineteen cards have readable public evidence passages. The remaining IPBES
species-richness card currently resolves to a chart-axis extraction and is
excluded from public responses; the file-level count alone does not close this
semantic coverage gap. Fresh-install, full evaluation and scientific support
acceptance must be distinguished from the focused demo checks recorded in
`IMPLEMENTATION_STATUS.md`.

The support diagnostic validates card IDs and activation coverage; it cannot
prove semantic entailment of prose. No weather enrichment, reranker, Docker,
hosting, authentication, or public multi-user security is included.

See `artifacts/demo_transcript.md` and `IMPLEMENTATION_STATUS.md` for actual
commands, results, and remaining acceptance blockers.
