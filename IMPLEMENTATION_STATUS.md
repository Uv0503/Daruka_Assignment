# Implementation Status

## Demo stabilization and independent validation — 2026-09-11 (in progress)

- Assignments: GPT-6 Astra (medium) owns minimal code/logic fixes in app/UI;
  GPT-5.6 Terra (high) owns independent tests and neutral-prompt results and
  reports failures directly to Astra. Lead owns integration, documentation
  consistency and the isolated Chrome UI check.
- Read the supplied stabilization instructions and repository Markdown files.
- `.venv/bin/python scripts/validate_kb.py` reports 8 sources, 20 reviewed
  cards, 19 parent passages, 54 children, 18 risk/prerequisite cards and no
  failures. All registry IDs have acquired sources; S5 is no longer blocked.
- Manual inspection of public passages found 19 readable candidates and the
  existing excluded chart-only species-richness card. Some shortened spans
  omit antecedents or adjacent supporting context; sent findings to Astra.
- The composition input omitted original source passages; general evidence
  questions incorrectly entered site-action clarification. Astra is repairing
  these shared paths, without per-test canned answers or weakened gates.
- Live Groq neutral-prompt validation was rejected twice by automatic approval
  review as requiring explicit consent for the prompt/passage payload. A
  specific approval question is pending; local/injected checks continue.
- Browser skill control tools are unavailable. Added an opt-in isolated local
  Chrome check (`scripts/browser_demo_check.py`), using installed Chrome and
  websocket-client. Syntax and Ruff checks passed; execution is pending.

## Final small UI reliability fixes — 2026-09-11

- Changed `ui/app.py` to retry session initialization on a rerun after an
  unavailable backend recovers. Failed New conversation requests now preserve
  the current session and show a readable error instead of a traceback.
- Reject non-object structured JSON before submission. Render API failures
  without raw response bodies. Allow up to 90 seconds for a chat response,
  with a 10-second connection timeout, and never automatically retry chat POSTs.
- Removed an extra import-block blank line in `ui/components.py`.
- `.venv/bin/python -m py_compile ui/app.py ui/components.py` succeeded.
- `.venv/bin/ruff check ui/app.py ui/components.py` initially found one import
  formatting issue; after the blank-line fix it returned All checks passed.
- A focused Streamlit AppTest with mocked HTTP verified offline startup,
  recovery on rerun, and preservation of the session on failed New conversation.
  All three assertions completed successfully; this was not a live-provider test.
- `API_BASE_URL=http://127.0.0.1:8010 .venv/bin/python scripts/ui_smoke.py`
  returned passed with two recommendation cards through the running backend.
- Full-suite and scientific acceptance verification remain deferred. These
  changes do not change evidence records, provenance gates or action eligibility.

This log records observed implementation work and results. It is intentionally
updated only with commands that were actually run and outcomes that were
actually observed.

## Phase 0 — Preflight and contracts

**Status:** Complete

### Completed tasks

- Read `BIODIVERSITY_CHATBOT_BUILD_SPEC (4).md` completely (1,309 lines).
- Inspected the initially supplied workspace.
- Confirmed a `.env` file exists while listing configuration *names only*; no
  secret values were read or logged.
- Created the project dependency declaration, CPU-only Torch source selection,
  `uv.lock`, `.env.example`, secret/data `.gitignore`, minimal FastAPI health
  application, strict canonical contracts, and the single Groq Chat
  Completions adapter.
- Ran a real authenticated Groq strict JSON-schema smoke request using
  `openai/gpt-oss-120b` at `https://api.groq.com/openai/v1`.
- Re-ran the provider preflight after the configured key was updated; it passed
  the strict JSON-schema and local semantic validation.

### Files created or changed

- Created `IMPLEMENTATION_STATUS.md`, `pyproject.toml`, `uv.lock`,
  `.env.example`, `.gitignore`, `README.md`, `app/config.py`,
  `app/schemas.py`, `app/main.py`, `app/services/llm_client.py`, and
  `scripts/preflight.py`.

### Commands executed

- `pwd && rg --files -g '!*__pycache__*' -g '!*.pyc' | sed -n '1,240p'`
- `wc -l ...` and segmented `sed` reads of the full build specification.
- `git status --short` (repository metadata is not present in this workspace).
- `find . -maxdepth 2 -type f -printf '%p\\n' | sort`
- `python --version` and `uv --version` (both commands were not available on
  the current PATH at this point).
- Created a local tooling virtual environment and installed `uv 0.12.13` into
  it; ran `.tooling/bin/uv lock` successfully.
- Installed the Phase 0 FastAPI/OpenAI/Pydantic runtime dependencies into
  `.venv` and ran `.venv/bin/python scripts/preflight.py`.

### Actual results

- The initial workspace has the build specification, assignment PDF, and
  `.env`; it has no application source tree or Git repository metadata.
- `.env` contains the required `GROQ_API_KEY` setting name and the expected
  LLM/configuration variable names.
- Python 3.12.3 is available (the project supports Python 3.11 through 3.12).
- `uv.lock` resolved 125 packages after switching Torch to the CPU wheel index.
- The live request used the configured provider/model/base URL and reached
  Groq. The initial request received HTTP 401 `invalid_api_key`; after the key
  update, the repeat request passed with `result="ok"` and `value=7`.
  This confirms Groq Chat Completions strict JSON-schema behavior for the
  configured `openai/gpt-oss-120b` model and project schema method.

### Failures or limitations

- The full local embedding/UI dependency environment is still installing; the
  focused Phase 0 runtime dependencies are installed.

### Next phase

Phase 0.5: run the narrow BM25 walking skeleton with reviewed S4/S5 evidence,
then extend it through corpus ingestion and hybrid retrieval.

## Phase 0.5 — Walking skeleton

**Status:** Complete

### Completed tasks

- Added reviewed S4/S5 evidence cards, an allowlisted source registry, a
  deterministic BM25 retrieval slice, citation resolution, and a terminal
  answer that includes the required water-related condition.
- Added early integrity validation for reviewed-card count, source IDs,
  locators, and risk/prerequisite coverage.

### Files created or changed

- `app/knowledge/sources.yaml`, `app/knowledge/cards.jsonl`,
  `app/services/retrieval.py`, `scripts/walking_skeleton.py`, and
  `scripts/validate_kb.py`.

### Commands executed and actual results

- `.venv/bin/python scripts/validate_kb.py` → valid: 7 source records, 20
  reviewed cards, 16 cards with explicit risk/prerequisite limitations.
- `.venv/bin/python scripts/walking_skeleton.py` → printed a conditional
  diversification assessment with S4 and S5 canonical citations and the
  water-use condition.
- `.venv/bin/python -c "from app.main import app; ..."` → initialized the
  FastAPI application and seeded SQLite with 7 sources, 20 chunks, and 20
  cards.

### Failures or limitations

- This deliberately narrow early slice uses BM25/reviewed excerpts only. Dense
  embeddings, persistent Chroma, state, API/UI and full validation are added
  in later phases.

### Next phase

Phase 1: build and validate the persistent scientific corpus, coverage matrix,
and source-specific S8 parser checks.

## Phase 1 — Curated coverage and corpus build

**Status:** Implemented with an evidence-provenance acceptance blocker.

### Completed tasks

- Built SQLite/Chroma from 20 reviewed cards across seven allowlisted source
  records and generated a manifest with encoder dimensions and card hash.
- Implemented the literal S8 parser, fixture tests, raw-content hash and
  provenance record. Independent implementation review fetched the live S8
  page successfully (HTTP 200, 111,362 bytes) and found all required panels,
  Sahel qualifier, and no placeholder marker.
- Added startup manifest/card/model/dimension integrity checks. A failed check
  now prevents retrieval and returns a degraded response rather than silently
  using a stale corpus.

### Files created or changed

- `scripts/ingest.py`, `tests/fixtures/s8_dom_literal_v1.html`,
  `tests/unit/test_s8_ingest.py`, `app/services/retrieval.py`,
  `app/main.py`, `app/api/routes.py`.

### Commands executed and actual results

- `.venv/bin/python scripts/ingest.py --manifest app/knowledge/sources.yaml`
  → `{"status":"built","cards":20,"chunks":20,"dimension":384}`.
- `.venv/bin/python -m pytest tests/unit/test_s8_ingest.py -q` → `2 passed`.
- Independent live S8 check reported HTTP 200, `text/html`, unchanged URL and
  parsed body lengths 427/699/274 characters for the three required panels.

### Failures or limitations

- Only S8 has an acquired raw source body/provenance record. The other cards
  remain reviewed excerpts/paraphrases rather than a complete acquired-source
  → passage → card chain. This fails the full evidence-provenance gate.
- The S4 numeric result/Figure 2A passage is not stored, so the mandatory
  numerical illustration is disabled rather than rendered from unsupported
  values.

### Next phase

Phase 2 retrieval and evidence-packet safeguards.

## Phase 2 — Hybrid retrieval

**Status:** Implemented and measured; corpus limitation above remains.

### Completed tasks

- Added local MiniLM dense retrieval, BM25 over the same reviewed excerpts,
  RRF fusion, explicit three-query trace, and a 12-card packet cap.
- Added saved relevance labels, a four-scenario measured hybrid-vs-BM25
  retrieval-policy ablation, and an ID/provenance support diagnostic.

### Files created or changed

- `app/services/retrieval.py`, `scripts/evaluate.py`,
  `artifacts/evaluation.json`.

### Commands executed and actual results

- `.venv/bin/python scripts/evaluate.py` → dense macro Recall@8
  `0.7777777777777778`; hybrid macro Recall@8
  `0.9166666666666666` (0.917 rounded) over six saved labeled card queries.

### Failures or limitations

- This is a six-query development retrieval measurement, not a benchmark or
  semantic entailment evaluation. The dryland water-budget query has hybrid
  Recall@8 of 0.5.

### Next phase

Phase 3 state/input and memory safeguards.

## Phase 3 — State, text/JSON input, and memory

**Status:** Implemented and tested.

### Completed tasks

- Added finite-number rejection, generic text bounds, explicit `null` clearing,
  omitted-field preservation, negative irrigation/pesticide handling,
  annual-vs-monthly rainfall separation, correction handling, conflict hold,
  session locks, and isolated hypothetical state.
- Separated UI structured-profile submission from text chat; the example is now
  displayed but never silently submitted.

### Files created or changed

- `app/schemas.py`, `app/services/state.py`, `app/services/orchestrator.py`,
  `ui/app.py`, `tests/integration/test_api.py`, `tests/unit/test_safeguards.py`.

### Commands executed and actual results

- `.venv/bin/python -m pytest -q --disable-warnings --maxfail=1` → `12 passed`
  after all listed state safeguards were added.

### Failures or limitations

- Text extraction is deterministic and intentionally narrow, not a general
  natural-language extraction model; ambiguous units remain unaccepted rather
  than inferred.

### Next phase

Phase 4 rules, paths, and validation.

## Phase 4 — Reasoning and deterministic validation

**Status:** Implemented and tested.

### Completed tasks

- Added activation-evidence gates, land/prerequisite checks, rainfall gate for
  cover crops, non-empty observation-linked reviewed interaction paths, and a
  three-environmental-concept check that excludes location.
- Expanded the response validator to reject unknown/disabled actions, draft or
  out-of-packet evidence, unreviewed edges, foreign observations, local model
  predictions, free numerical prose, and inadequate concept coverage.
- Provider composition exceptions now return `degraded` while retaining only
  server-rendered reviewed-evidence templates.

### Files created or changed

- `app/knowledge/actions.yaml`, `app/services/reasoning.py`,
  `app/services/verification.py`, `app/services/orchestrator.py`,
  `tests/unit/test_safeguards.py`, `tests/integration/test_api.py`.

### Commands executed and actual results

- The test suite includes injected fabricated action/edge/local-prediction and
  provider-failure cases; its final observed result is `12 passed`.

### Failures or limitations

- The deterministic validator checks contract/provenance references, not full
  semantic entailment of every English sentence.

### Next phase

Phase 5 evidence console.

## Phase 5 — Evidence console and API/UI integration

**Status:** Implemented and smoke-tested.

### Completed tasks

- Added evidence endpoint, source/locator/excerpt citations, trace inspection,
  interaction paths, condition/metric display, and turn-keyed downloads.
- Started both Uvicorn and Streamlit locally; verified Streamlit HTTP 200 and
  its headless UI-to-backend chat workflow with Streamlit AppTest.

### Files created or changed

- `ui/components.py`, `ui/app.py`, `scripts/ui_smoke.py`, `scripts/smoke_api.py`.

### Commands executed and actual results

- Temporary local API + Streamlit run: Streamlit HTTP returned 200; AppTest
  returned `{"status":"passed","title":"Biodiversity Intelligence",
  "recommendation_cards":2,"api_base_url":"http://127.0.0.1:8765"}`.
- Live HTTP smoke returned health 200/healthy, text and JSON `recommend`,
  equivalent normalized profiles, omitted-preserves-SOC true,
  explicit-null-clears-SOC true, and session-isolated true.

### Failures or limitations

- This environment has no interactive browser automation available; the UI
  interaction check is Streamlit's headless test API plus a real local backend.

### Next phase

Phase 6 focused evaluation.

## Phase 6 — Golden scenarios and evaluation

**Status:** Implemented and measured.

### Completed tasks

- Replaced ten prompt stubs with executable scenario data and runner covering
  incomplete opening, text/JSON profile, corrections, hypotheticals, invalid
  value, pesticide pressure, natural habitat, empty corpus, invented-number
  validator injection, and session isolation.
- Produced golden, retrieval, ablation and support-diagnostic artifacts.

### Files created or changed

- `tests/golden/cases.jsonl`, `scripts/run_golden.py`,
  `scripts/evaluate.py`, `artifacts/golden_results.json`,
  `artifacts/evaluation.json`.

### Commands executed and actual results

- `.venv/bin/python scripts/run_golden.py` → `{"passed":10,"total":10}`.
- `.venv/bin/python scripts/evaluate.py` → metrics recorded above.

### Failures or limitations

- Golden runs are deterministic server-template API tests with hybrid retrieval
  enabled and Groq composition disabled. They are correctly not reported as a
  live generation benchmark. Support diagnostic is ID/provenance-only.

### Next phase

Phase 7 documentation and handover.

## Phase 7 — Handover and rehearsal

**Status:** Documentation complete; final acceptance remains blocked by source
provenance and the disabled mandatory numeric demonstration.

### Completed tasks

- Wrote setup, first-install corpus build, exact two-terminal run commands,
  architecture, safeguards, evidence boundaries, actual metrics, transcript,
  `.env.example`, and this phase log.
- Refreshed `uv.lock` and executed `UV_CACHE_DIR=/tmp/daruka-uv-cache
  .tooling/bin/uv sync --frozen` successfully in the project environment.
- Re-ran live structured Groq preflight using the real `CompositionChoice`
  schema: passed for `openai/gpt-oss-120b` at the configured Groq base URL.
- Ran `.venv/bin/ruff check app scripts ui tests` → `All checks passed!`, then
  reran the final pytest and golden commands (`12 passed`; `10/10`).

### Files created or changed

- `README.md`, `artifacts/demo_transcript.md`, `.env.example`, `pyproject.toml`,
  `uv.lock`, `.gitignore`, and `IMPLEMENTATION_STATUS.md`.

### Historical acceptance table (superseded by the 2026-09-11 provenance remediation below)

| Gate | Result | Evidence |
|---|---|---|
| Provider strict structured output | Pass | `scripts/preflight.py` live run |
| Backend health and live text/JSON HTTP | Pass | `scripts/smoke_api.py` local run |
| UI-to-backend workflow | Pass (headless) | `scripts/ui_smoke.py` local run |
| Tests | Pass | `12 passed` |
| Ten golden scenarios | Pass, deterministic | `artifacts/golden_results.json` |
| Hybrid Recall@8 | Pass for saved dev labels | 0.9166666666666666 |
| Complete source→passage→card provenance | Superseded | see current 16-card/S5-blocked status below |
| Mandatory S4 numeric literature illustration | Superseded | see current acquired S4 Results passage status below |
| Fresh setup from an empty machine/cache | Not fully verified | lock sync succeeded; first model download command documented |

### Next phase

No optional deployment work was started. To close the remaining core gates,
acquire and hash the allowlisted source bodies, link reviewed passages to every
active card, and add the verified S4 Results/Figure 2A passage before restoring
the server-calculated numerical illustration.

## Knowledge-base provenance remediation — 2026-09-11

**Status:** Core source-to-index wiring repaired for 16 active cards; release
coverage remains blocked by S5. Per the current request, no test suite, golden
scenario, retrieval evaluation, UI test, live API test, or clean-install check
was run after these changes.

### Completed tasks

- Completed a focused GPT-5.6 Sol read-only review against the full 1,309-line
  build specification. Its concrete findings were integrated rather than
  treating the old reviewed flags as evidence provenance.
- Refreshed allowlisted acquisition metadata for S2, S3, and S4, preserving
  existing metadata on partial refreshes. S6, S8, and S9 retain their prior
  successful source records. Raw files, final URLs, acquisition times, local
  paths, and SHA-256 values now align in `sources.yaml` and acquisition
  metadata for those six sources.
- Added source-extracted, hash-linked passages for every active card. Each
  passage records source/evidence IDs, raw path/hash, passage hash, literal
  anchor and source-relative locator. Passages are bounded conservatively so
  MiniLM does not silently truncate them.
- Corrected source anchors and claims for S6 scope/risk, S8 climate context,
  S9 reconnection/natural-habitat scope, S3 moisture context, and S2 biology
  context. The S4 Results passage now supports the reviewed lnRR 0.34, 95% CI
  [0.15, 0.53] literature card; the server calculation remains bounded to the
  specified pooled-literature illustration.
- Marked all four unverified S5 cover-crop cards as `draft`; disabled the
  dependent cover-crop action and its three interaction edges. This applies to
  all runtime paths, including degraded responses.
- Tightened active action eligibility so every configured evidence card for an
  action must be present in the retrieval packet before the action can render.
  In particular, crop diversification now requires the S8 dryland water-budget
  card as well as the S4 synthesis/context cards.
- Rebuilt BM25/Chroma/SQLite from the 16 active passages. Ingestion now embeds
  extracted source text, not card prose, and writes passage/raw hashes and
  locators into Chroma metadata and the corpus manifest.
- Added fail-closed provenance validation code and runtime integrity checks for
  registry/acquisition/raw/passage/manifest/Chroma ID/document/hash links.
  Citations now emit one extracted passage per evidence card rather than
  attaching several evidence IDs to the first same-source excerpt. SQLite
  knowledge seeding deletes stale chunks/cards before inserting the active set.
- Replaced `artifacts/coverage_matrix.json` with source-passage links for each
  active domain, action, and reviewed edge. It names blocked S5 water-risk
  coverage and the unproven soil-health-to-biodiversity interaction instead of
  presenting them as supported.

### Files created or changed

- `scripts/acquire_sources.py`, `scripts/extract_passages.py`,
  `scripts/ingest.py`, `scripts/validate_kb.py`
- `app/knowledge/sources.yaml`, `app/knowledge/cards.jsonl`,
  `app/knowledge/actions.yaml`, `app/knowledge/interactions.yaml`
- `app/schemas.py`, `app/services/retrieval.py`,
  `app/services/orchestrator.py`, `app/storage/db.py`, `app/api/routes.py`
- `data/raw/S2.html`, `data/raw/S3.pdf`, `data/raw/S4.html`,
  `data/processed/acquisition_metadata.json`,
  `data/processed/passages.jsonl`, `data/processed/passage_extraction_report.json`,
  `data/processed/manifest.json`, `data/chroma/`, `data/app.sqlite3`
- `README.md`, `IMPLEMENTATION_STATUS.md`
- `artifacts/coverage_matrix.json`

### Commands executed and actual results

- `.venv/bin/python scripts/acquire_sources.py --source S2 --source S3 --source S4 --source S5`
  initially encountered sandbox DNS failures. The approved allowlisted retry
  acquired S2/S3/S4 and recorded their provenance; S5 ended with
  `ConnectTimeout` and remains blocked.
- `.venv/bin/python scripts/extract_passages.py` →
  `{"passages": 16, "failures": []}` after source-specific anchor repairs.
- `.venv/bin/python scripts/ingest.py --manifest app/knowledge/sources.yaml`
  first rejected an overlong source passage rather than silently truncating it.
  After conservative source-passage bounding, the rebuild reported
  `{"status":"built","cards":16,"chunks":16,"dimension":384}`.
- Re-ran that corpus build after tightening habitat-edge and full-evidence
  action prerequisites; it
  again reported `{"status":"built","cards":16,"chunks":16,"dimension":384}`.

### Failures or limitations

- S5 cannot be acquired from its allowlisted URL in this environment. Its four
  cards cannot count toward the mandatory 20 reviewed cards, so the coverage
  gate is intentionally failing at 16/20. Its required dryland water-risk
  evidence is therefore unavailable for a cover-crop recommendation.
- The required release validation, golden scenarios, retrieval evaluation,
  live Groq/API checks, UI browser check, and clean-environment setup check
  are explicitly deferred by the current request. Earlier artifacts predate
  this corpus and are not evidence for the repaired pipeline.
- The current source passages are bounded at up to 120 words to respect the
  encoder’s hard 256-token limit. This avoids silent truncation but must be
  revisited if the specification’s 150–190-word child-chunk policy is a strict
  acceptance requirement for all sources.

### Next phase

Restore an acquired, hash-verified S5 source or retain its action/cards as
disabled; then run the deferred validation and acceptance workflow against the
rebuilt corpus without weakening its coverage or provenance gates.

## Knowledge-base connection and conversation remediation — 2026-09-11

**Status:** Implementation and file-level inspection complete. This section
supersedes the 16/20 S5 blocker above. Tests and evaluations remain deferred by
request.

### Completed tasks

- Fixed the repeated clarification loop. Standalone rainfall answers such as
  `erratic` are now interpreted against the active cropland context. Explicit
  unknown answers are stored against the next unanswered prerequisite so the
  same question is not asked indefinitely. Question selection distinguishes an
  omitted field from an explicitly answered unknown. The Streamlit question
  component now renders a real paragraph break instead of the literal
  `\\n+Why it matters` text.
- Audited S1 explicitly. The canonical FAO page was acquired into
  `data/raw/S1.html`; registry and acquisition metadata record its exact final
  URL, retrieval time and SHA-256. Its reviewed soil-biology card is linked to
  the source paragraph describing nutrient cycling, soil organic matter,
  physical structure and water regimes.
- Retried the exact allowlisted S5 SARE chapter with two bounded transport
  retries, a 45-second timeout and a transparent browser-compatible user-agent.
  The canonical chapter returned HTTP 200 and was stored as `data/raw/S5.html`
  with exact acquisition metadata and SHA-256. No substitute source was used.
- Reviewed S5's literal passages for growing-cover-crop water use and possible
  cash-crop effects, the possible post-termination infiltration/evaporation
  benefit, rainfall/termination timing, and the dryland moisture limitation.
  Restored its four cards, conditional action and three interaction edges. All
  four cards—including adverse dryland evidence—are mandatory activation
  evidence.
- Replaced the old 120-word bounding with complete parent passages plus child
  chunks made by the pinned `all-MiniLM-L6-v2` tokenizer. Long parents use a
  175-word-piece target and 25-word-piece overlap under the 256-token encoder
  ceiling. Naturally shorter source paragraphs remain intact; they are not
  padded with unrelated text. No parent source text is silently truncated.
- Narrowed card activation links to anchor-containing child chunks. Sibling
  chunks remain indexed as source context through their shared parent but
  cannot independently activate an evidence card. Stable chunk IDs derive
  from the raw hash, locator and text hash.
- Synchronized card and extracted-passage locators, including S5's publisher
  section labels and the S3 PDF index. Confirmed the acquired S4 Results
  paragraph states lnRR 0.34 and 95% CI [0.15, 0.53] with Figure 2A. The server
  retains `100 * expm1(value)` and labels the output only as a pooled literature
  illustration, not a local prediction.
- Rebuilt SQLite and Chroma. SQLite seeding now removes stale sources as well
  as stale chunks/cards. The coverage matrix contains a per-source chain for
  every registry ID. A read-only post-build consistency inspection found all
  eight source IDs connected to reviewed cards: S1=1, S2=1, S3=1, S4=3,
  S5=4, S6=3, S8=3 and S9=4.

### Files created or changed

- `app/services/state.py`, `app/services/orchestrator.py`,
  `app/services/retrieval.py`, `app/services/verification.py`,
  `app/storage/db.py`, `ui/components.py`
- `scripts/acquire_sources.py`, `scripts/extract_passages.py`,
  `scripts/ingest.py`, `scripts/validate_kb.py`
- `app/knowledge/sources.yaml`, `app/knowledge/cards.jsonl`,
  `app/knowledge/actions.yaml`, `app/knowledge/interactions.yaml`
- `data/raw/S1.html`, `data/raw/S5.html`,
  `data/processed/acquisition_metadata.json`,
  `data/processed/parent_passages.jsonl`,
  `data/processed/passages.jsonl`, `data/processed/card_chunk_map.json`,
  `data/processed/passage_extraction_report.json`,
  `data/processed/manifest.json`, `data/chroma/`, `data/app.sqlite3`
- `artifacts/coverage_matrix.json`, `README.md`,
  `IMPLEMENTATION_STATUS.md`

### Commands executed and actual results

- The initial exact S5 requests with a generic client user-agent returned HTTP
  403. The bounded retry with the acquisition profile returned HTTP 200 from
  the same configured SARE URL.
- `.venv/bin/python scripts/acquire_sources.py --source S1 --source S5` →
  `{"acquired":8,"failed":0,"metadata":"data/processed/acquisition_metadata.json"}`.
  The counts cover the merged eight-source acquisition registry.
- `.venv/bin/python scripts/extract_passages.py` → 19 complete parents, 54
  child chunks, 20 mapped reviewed cards and zero extraction failures; target
  175 word pieces, overlap 25, maximum model input 256.
- A mechanical card-manifest replacement produced an invalid patch after the
  deletion half. The 20 unchanged card records were recovered from the current
  SQLite corpus through `apply_patch`, then remapped to the newly extracted
  stable chunk IDs. No card or provenance record was lost.
- `.venv/bin/python scripts/ingest.py --manifest app/knowledge/sources.yaml`
  was run after the final metadata/card changes →
  `{"status":"built","cards":20,"chunks":54,"dimension":384}`.
- A read-only cross-store inspection compared registry/acquisition URLs and
  hashes, raw files, parents, card chunks, Chroma documents/metadata, SQLite
  counts and manifest hashes. Observed: 8 sources, 20 cards, 19 parents, 54
  Chroma/SQLite chunks, and no connection/hash mismatches.

### Failures or limitations

- No test suite, golden scenario, retrieval evaluation, UI test, live API/Groq
  request or clean-install verification was run in this task. Historical
  artifacts predate this 20-card/54-chunk corpus and cannot validate it.
- Short source paragraphs below the approximate 150-word-piece target remain
  short by design; padding them would mix unrelated scientific context. This
  is a documented boundary case, not silent truncation.
- The running backend/UI processes, if any, must be restarted before they can
  load this rebuilt corpus and conversation fix.

### Next phase

Run the separately requested validation and evaluation workflow against this
exact rebuilt corpus, including the repeated-question regression, retrieval
coverage, golden cases, UI/API checks and live provider behavior. Do not use
the older result artifacts as current acceptance evidence.

## 2026-09-11 — Retrieval/evidence rendering implementation review

### Implemented

- Clarification turns remain retrieval-free and now render an explicit
  “retrieval has not run” explanation instead of empty Evidence and `[]`
  panels. Generic clarification still receives no scientific citation.
- Retrieval-run `insufficient_evidence` responses retain readable retrieved
  context and citations while explicitly stating that those citations do not
  support an action that failed the observation/applicability/evidence gates.
- Replaced the brittle corpus-wide top-12 cutoff with bounded candidate-action
  and missing-coverage queries. A card is admitted only when one of its
  reviewed anchor chunks ranks through lexical/semantic retrieval. The packet
  remains capped at 12 cards, 18 selected chunks and 12 queries; action gates
  still require the complete configured activation evidence set.
- Normalized event-backed active state before interpreting short follow-up
  answers. Explicit unknown/declined answers advance to the next prerequisite
  without pretending that a cleared value is known. Canonical deterministic
  extraction now wins over equivalent provider spellings such as `semi-arid`.
- Annual rainfall plus explicit concentration/seasonality is treated as known
  water context. The next clarification asks only whether irrigation is
  available and explains its crop-diversification/water-budget relevance.
- Dryland crop diversification retains mandatory S8 water-budget evidence,
  names water budgeting and local adaptation as prerequisites/trade-offs, and
  remains conditionally applicable until local design (and, where relevant,
  irrigation availability) is resolved. The qualified S4 lnRR conversion to
  the 40.5% pooled illustration is preserved.
- Public chat traces and the evidence endpoint no longer expose raw chunk IDs,
  hashes, rank maps or evidence-quality internals. Evidence is rendered as a
  readable chain: reviewed claim → source → exact locator → complete extracted
  parent passage → source URL. The UI no longer dumps raw JSON for interaction
  paths or retrieval traces and converts metric/monitoring identifiers to
  readable labels.
- Made Streamlit imports package-safe through `ui/__init__.py` and an absolute
  `ui.components` import. Removed the unused `re` import from passage
  extraction. Reworked evaluation ranking to rank 54 chunks first and only
  then map/deduplicate reviewed card IDs, avoiding card/chunk index mismatch.

### Verification status

- Per the latest scope instruction, no acceptance test, golden, evaluation,
  live provider, HTTP or UI pass is claimed for this implementation state.
  Restart the API/UI before the separately authorized verification phase so
  both processes load these changes.

## 2026-09-11 — Response construction and readable evidence review

**Status:** Implementation review complete; verification deliberately deferred.

### Findings and fixes

- Confirmed that an annual rainfall observation plus explicit four-month
  concentration is already sufficient water-seasonality context. The next
  question asks only whether irrigation is available and describes its
  relevance to a dryland crop-diversification pilot, not a cover-crop action.
- Retained the explicit unknown/declined state marker so a user who cannot
  answer the irrigation question advances instead of receiving it repeatedly.
- Added deterministic public-passage selection. Each visible citation now
  resolves reviewed evidence claim → source title/publisher → exact locator →
  exact, semantically complete source sentence/paragraph/bullet → source URL.
  Long PDF pages are no longer rendered wholesale. Citation validation checks
  the selected public passage against the stored parent source passage.
- The IPBES species-richness card currently resolves only to a Figure SPM.8
  chart-axis extraction. It is excluded from public evidence and marked as an
  offline-provenance-only gap in the coverage matrix. The habitat-strip action
  now requires the reviewed IPBES locally tailored design/scope card instead;
  it does not weaken its complete-evidence activation gate.
- Removed user-visible raw retrieval objects and internal identifiers. The UI
  renders readable claims, sources, locators and links; interaction paths and
  metric names are converted from internal dotted/underscore labels.
- Expanded deterministic monitoring text for each configured monitoring item:
  what to observe, how to keep the method comparable, the pre-action baseline,
  and when to repeat under comparable seasonal or management conditions. No
  numerical target or guaranteed timeframe was added.
- Crop diversification remains conditionally applicable. The dryland wording
  explicitly requires the S8 water-budget evidence and local crop/water design.
  The S4 `100 * expm1` result remains identified as a pooled literature
  illustration and never as a local forecast.
- S5 is not currently blocked: its exact configured SARE page, raw bytes,
  final URL, acquisition time and SHA-256 remain stored and linked. Its
  limitations are transferability (United States guidance), local water-budget
  uncertainty and termination timing. S5 cards can appear only when retrieved
  for the distinct cover-crop action; they are not used as substitutes for S8
  dryland crop-diversification evidence.

### Files changed

- `app/services/evidence_display.py`, `app/services/orchestrator.py`,
  `app/services/state.py`, `app/services/reasoning.py`,
  `app/services/retrieval.py`, `app/services/verification.py`
- `app/api/routes.py`, `app/schemas.py`, `ui/app.py`, `ui/components.py`,
  `ui/__init__.py`
- `app/knowledge/actions.yaml`, `artifacts/coverage_matrix.json`
- `scripts/evaluate.py`, `scripts/extract_passages.py`
- Focused assertions were edited for the later verification task, but were not
  executed under this request.

### Commands and observed inspection results

- Read the response-construction, retrieval, validation, API route and
  Streamlit rendering paths against the specification.
- Inspected candidate public excerpts for all 20 cards from the stored parent
  passages. Nineteen resolve to complete source prose/bullets; the Figure
  SPM.8 species-richness item is intentionally excluded as described above.
- Searched current processed passages and UI code for `[svg]` markers and
  direct `chunk_id`/`evidence_quality` rendering; no such public renderer
  remains.

### Deferred verification and limitations

- Per request, the full test suite, golden scenarios, retrieval evaluation,
  HTTP/live-provider tests and Streamlit tests were not run after these final
  edits. No pass claim is made.
- The API and Streamlit processes must be restarted to load this response/UI
  implementation before the separate testing task.

## 2026-09-11 — Generalized action-aware clarification

**Status:** Implemented and inspected; full tests remain deferred.

### Completed tasks

- Added a dedicated clarification service that reads normalized current
  observations, explicit clears/declines, unresolved conflicts and the last
  persisted question field before asking anything. Zero remains a known
  numeric value; `null` and an explicit unknown remain answered-but-unknown and
  are not silently converted to zero or repeatedly requested.
- Replaced the fixed global field order with release-action-specific question
  policies. Prospective action selection uses normalized land type, disclosed
  pesticide pressure and explicit user intent. Cropland defaults to the
  crop-diversification assessment unless the user explicitly requests cover
  crops or habitat connectivity; natural forest/grassland/wetland uses habitat
  protection, never agricultural defaults.
- Questions attached to recommendation responses are recomputed after
  retrieval and action selection. Their `why_it_matters` text names the
  selected action and relevant retrieved evidence boundary (S8 water budget,
  S4 diversification comparison, S5 cover-crop water balance, S6 pesticide
  exposure or S9 local habitat scope) rather than a generic cover-crop phrase.
- Retrieval now occurs before non-blocking, action-specific clarification when
  land type is known. An incomplete land-use or conflict question remains a
  blocking pre-retrieval clarification. Evidence shown with an incomplete
  response is labeled prospective context, not recommendation support.
- Added normalized equivalence for a rainfall total explicitly described as
  concentrated in a stated number of months. `350 mm concentrated in four
  months` records the annual total and seasonal concentration. An unqualified
  `350 mm`, or a value explicitly described as monthly, remains ambiguous and
  requests the reporting period instead of being annualized.
- Added normalized qualitative observations for low soil moisture, a
  single-crop statement such as `grow only wheat`, reported fewer
  insects/birds/pollinators/species, and explicitly unknown soil measurements.
  The semi-arid location label no longer independently manufactures a rainfall
  observation.
- Replaced root-name concept counting with distinct decision concepts: land
  system, cropping pattern, water/climate, soil carbon, other soil condition,
  habitat, biodiversity condition and pressure. The deterministic response
  validator uses the same mapping.
- Persisted `last_question_fields` in session state. A short `I don't know`
  answer is therefore applied to the field actually asked on the previous
  turn, including land and habitat questions, and corrections later remove the
  decline marker. Hypothetical questions and answers operate on the cloned
  state and do not modify actual observations.
- Added bounded contextual answer parsing for the previously asked field:
  yes/no irrigation, canonical land choices, annual rainfall with explicit
  period, zero-valued percentages/pH, crop-system vocabulary, habitat
  descriptions and reported biodiversity changes. Unrelated disclosures are
  not forced into the prior field; for example, pesticide disclosure while a
  habitat question is pending changes the prospective action instead.
- Made conditionality action-specific: diversification retains its local
  crop/water design condition; cover crops retain water/termination checks;
  habitat strips retain local habitat/design checks; natural-habitat protection
  remains conditional while habitat type is undocumented.

### Scenarios considered

- Incomplete biodiversity complaint → asks land type first.
- Semi-arid, low-SOC, single-crop profile with rainfall concentrated in four
  months → does not repeat rainfall; asks supplemental irrigation only where
  the selected crop action uses water feasibility.
- Rainfall correction → latest explicit annual value and seasonality replace
  the current event without clearing crop/SOC observations.
- Irrigation hypothetical → uses cloned state; actual irrigation remains
  unchanged.
- Newly disclosed pesticide pressure → prospective action changes to the S6
  exposure/IPM assessment rather than repeating soil questions.
- Natural-grassland tree request → selects habitat protection context and asks
  for existing habitat/vegetation condition; no crop action is considered.
- Missing habitat information → asked only for habitat-sensitive actions.
- Unknown soil measurements → stored as explicit clears and not repeatedly
  requested; no numeric soil value is invented.
- Invalid or ambiguous units → existing schema bounds still reject invalid
  values; rainfall without a usable period receives a unit-period question.
- Conflicting observations → held outside accepted state until the conflict is
  explicitly resolved.

### Files changed

- Added `app/services/clarification.py`.
- Updated `app/services/state.py`, `app/services/orchestrator.py`,
  `app/services/reasoning.py`, `app/services/verification.py`,
  `app/services/evidence_display.py`, `app/schemas.py`, `app/storage/db.py`,
  and `IMPLEMENTATION_STATUS.md`.

### Commands and observed results

- A focused read-only normalization/clarification inspection of the supplied
  dryland message produced annual rainfall `350.0`, four-month seasonality,
  `monoculture wheat`, crop land use, low qualitative soil moisture, reported
  organism decline, SOC `0.3`, and semi-arid region. The prospective action was
  crop diversification; the only question returned was supplemental
  irrigation, with an S8 water-budget reason. Five distinct environmental
  concepts were recognized.
- Two attempted combined scenario-inspection shell one-liners and one local
  orchestration attempt did not execute due to quoting/tool-runtime errors and
  changed no files or state.
- A subsequent read-only focused scenario matrix completed. It selected land
  type for the incomplete complaint, preserved the 900 mm rainfall correction,
  isolated the irrigation hypothetical, selected pesticide reassessment after
  disclosure, selected habitat information for natural grassland, retained
  explicit-null soil measurements, requested the period for ambiguous rainfall,
  prioritized the conflicting field, and mapped a short unknown reply to the
  previously asked irrigation field. This was a focused logic inspection, not
  the full test suite or an acceptance result.
- A final AST syntax inspection parsed all nine modified Python modules
  successfully. This is a syntax check, not an acceptance test.

### Remaining limitations and next phase

- No full pytest, golden, retrieval evaluation, backend/UI, live-provider or
  fresh-install run was performed after these changes; no pass claim is made.
- The action-aware question policy is intentionally bounded to the five active
  release action classes and canonical profile fields. New action classes must
  add their own prerequisite/reason mapping rather than falling back to an
  unrelated question.
- Existing sessions created before this change gain persisted question history
  after their next response; normalized current observations and explicit-null
  keys remain backward compatible immediately.
- Restart the API and Streamlit processes before the separately requested test
  phase.

## Streamlit legacy-response compatibility hotfix — 2026-09-11

**Status:** Fixed and verified with focused runtime checks; the full test suite
was not run.

### Finding and fix

- Streamlit session state could retain citation dictionaries created before
  `evidence_claim` and the public retrieval-trace shape were added. The UI
  accessed `citation["evidence_claim"]` and trace display fields directly, so
  replaying one of those saved turns raised `KeyError` and stopped the app.
- Updated the response renderer and Markdown exporter to tolerate legacy saved
  citation fields, use explicit readable fallbacks, and invite the user to
  resubmit the message for refreshed evidence. Legacy raw trace records are
  hidden instead of rendering internal IDs or serialization fields.
- Current responses still render the complete reviewed evidence chain. No
  citation validation, retrieval, provenance or action gates were changed.

### Files changed

- `ui/components.py`
- `IMPLEMENTATION_STATUS.md`

### Commands and actual results

- `.venv/bin/python -m py_compile ui/components.py ui/app.py` and a focused
  import check completed successfully.
- A focused render invocation using a citation without `evidence_claim` and a
  legacy internal trace completed with `legacy response rendered without
  KeyError`.
- Fresh instances were started on backend port 8010 and UI port 8510 because
  ports 8000, 8501 and 8502 were already occupied by stale/external processes.
- `GET http://127.0.0.1:8010/health` returned HTTP 200 with `status=healthy`,
  `corpus_ready=true`, and no corpus integrity errors. `GET
  http://127.0.0.1:8510` returned HTTP 200.
- `API_BASE_URL=http://127.0.0.1:8010 .venv/bin/python scripts/ui_smoke.py`
  returned `status=passed`, title `Biodiversity Intelligence`, and two rendered
  recommendation cards. This was a targeted UI-to-backend smoke check, not the
  full suite or release acceptance run.
- Independent Terra testing rendered both current and legacy citation shapes
  without exceptions and confirmed HTTP 200 from ports 8010 and 8510.
  Independent Sol review found no remaining direct-key access in the citation
  path and confirmed that legacy internal trace fields remain hidden. Neither
  agent edited files or ran the full test suite.

### Remaining limitations

- Correction to the original hotfix note: S5 was already acquired and restored
  by the connection remediation above. Its four linked cards and conditional
  action are available subject to retrieval and water/prerequisite gates.
- Old turns without the newly added evidence claim cannot reconstruct that
  field safely. They render the available source, locator, passage and URL and
  ask the user to resubmit for the complete current response.
