# Flask → FastAPI Migration + LangGraph Parallelization

Date: 2026-07-19. Branch: `fastapi-migration`.

## What changed

- **Web framework:** the main web app is now FastAPI + uvicorn (`app/fastapi_app.py`,
  `app/routers/*`, `run_fastapi.py`, port 8000). Every route, response body, template,
  session flow, and the offline-PWA contract were ported 1:1 from the Flask blueprints.
  The legacy Flask app (`run.py`, `app/blueprints/*`) still runs and serves the identical
  surface — it is the **rollback path** until post-phone-test cleanup.
- **Agent graph:** the LangGraph risk pipeline now runs independent agents concurrently
  (see below). Agent node functions in `app/ai/agents.py` are byte-identical — only the
  edge topology and a build-time node wrapper in `app/ai/graph.py` changed.
- **Instrumentation:** per-stage timing on `POST /asha/assessment` (DB stages, graph
  total, per-agent node time, alerts). `PERF_DEBUG=true` adds a `_timings` breakdown to
  the response. Tools: `scripts/measure_latency.py`, `scripts/concurrency_test.py`,
  parity harness `scripts/diff_responses.py`. Raw numbers in `baselines/*.json`.
- **NOT changed:** repositories/DB layer (sync SQLAlchemy Core + psycopg3, untouched —
  including `prepare_threshold=None` for the Supabase pooler), the Telegram bot, the
  port-5050 appointment webhook (stays Flask), the RAG engine, the registration engine,
  all AI prompts and models.

## Which agents were parallelized

Verified by each node's actual state reads: `risk_stratification`, `symptom_reasoning`,
`trend_analysis`, `document_analysis` read only request inputs (mutually independent);
`nutrition_lifestyle` and `communication` read only `risk_stratification_result`;
`finalize` aggregates.

```
before:  orchestrator -> risk -> symptom -> trend -> document -> nutrition -> communication -> finalize
after:   orchestrator -> {risk || symptom || trend || document}      (phase A, one super-step)
                      -> {nutrition || communication}                (phase B, barrier join)
                      -> finalize
```

Critical path: **2 LLM calls deep instead of 5**. Phase B waits for all of phase A (not
just risk) — accepted tradeoff: trend/document are deterministic in practice, so the loss
is ~0 and the barrier topology is the simple, well-defined LangGraph pattern.

Safety mechanics (the part that made naive fan-out crash): the legacy nodes mutate state
in place and return the FULL state, which under parallel super-steps raises
`InvalidUpdateError`. `_wrap_node` in `graph.py` gives each node a shallow copy and
publishes only its declared output keys; `perf_timings` is the one multi-writer channel
and has an `operator.add` reducer. The old conditional routers were removed: nodes
self-short-circuit deterministically on the identical conditions, and the wrapper gates
`document_analysis` on `has_uploaded_documents` (key stays ABSENT when skipped —
`build_ai_evaluation` keys off its presence). The 120s hard budget and every fallback
layer (per-node, hybrid risk rescue, full rule-based) are unchanged and covered by
`tests/test_graph_parallel.py` (no network/DB).

## Numbers

One representative authenticated `POST /asha/assessment` (real Groq + Supabase, same
machine/DB; server-side per-stage timings, ms):

| stage                  | before (Flask, sequential) | after (FastAPI, sequential) | after (FastAPI, parallel) run 2 |
|------------------------|---------------------------:|----------------------------:|--------------------------------:|
| db: 4 stages combined  |                      5,025 |                       4,694 |                           4,051 |
| node: risk             |                      2,049 |                       1,941 |                          17,052 |
| node: symptom          |                     14,890 |                      14,841 |                           1,833 |
| node: nutrition        |                     35,329 |                      10,037 |                           2,011 |
| node: communication    |                     35,224 |                       9,320 |                           5,901 |
| graph total            |                     87,510 |                      36,148 |                          22,971 |
| alerts                 |                        968 |                         729 |                           1,148 |
| **request total**      |                **102,379** |                  **44,341** |                      **30,579** |

**Read the graph rows structurally, not as absolute speed:** Groq latency variance
(429 backoffs) between runs is far larger than any framework effect — e.g. nutrition was
35s on the Flask run and 10s on the FastAPI-sequential run with identical code paths.
The reliable claims are:

- **Sequential runs: graph total = SUM of the LLM nodes** (87.5s = 2.0+14.9+35.3+35.2;
  36.1s = 1.9+14.8+10.0+9.3). The framework migration alone bought ~nothing on the AI
  path — as predicted, latency is LLM-bound.
- **Parallel runs: graph total = max(phase A) + max(phase B)** (23.0s = 17.1 + 5.9,
  where the same calls would have summed to 26.8s; a second run overlapped 35s and 67s
  calls, saving ~37s of wall time). The win scales with how imbalanced the calls are and
  is what removes the worst-case pileup when Groq backoffs hit multiple agents.
- Supabase pooler round-trips cost ~0.5–2.5s each; the 4 DB stages cost ~4–5s per
  assessment regardless of framework.

Concurrency (N simultaneous `GET /asha/stats`, real DB):

| metric        | Flask dev server, n=5 | FastAPI/uvicorn, n=5 | FastAPI/uvicorn, n=10 |
|---------------|----------------------:|---------------------:|----------------------:|
| wall time     |                 5.16s |                5.91s |                 5.85s |
| throughput    |             0.97 rps  |             0.85 rps |          **1.71 rps** |
| p95           |                 4.89s |                5.65s |                 5.56s |
| errors        |                     0 |                    0 |                     0 |

Doubling the load (n=5 → n=10) left wall time and p95 flat and doubled throughput —
requests genuinely run concurrently, and **no DB-pool queuing appeared at n=10**
(pool_size=5 + max_overflow=5 = 10 connections exactly covers 10 in-flight requests).
Per the measure-first decision: **pool settings were NOT changed.** If load beyond 10
concurrent DB-bound requests becomes real, do NOT just bump pool_size — the Supabase
free-tier connection cap is a hard external ceiling multiplied by uvicorn workers, plus
the bot process holds connections against the same database. Prefer capping the anyio
threadpool, or accept queuing, and only raise the pool after computing
(pool x workers x processes) against the Supabase cap.

## Architecture notes / honest trade-offs

- **Zero `async def` endpoints, deliberately.** All latency is sync work (psycopg, sync
  Groq SDK, Chroma); plain `def` + FastAPI's threadpool gives request-level concurrency
  with zero risk to the untouched repo layer, and LangGraph's own executor supplies
  intra-request LLM concurrency. edge-tts/Whisper are bot-process concerns and were
  already correctly async / `asyncio.to_thread`.
- **Nested thread executors:** FastAPI runs each `def` endpoint in a threadpool thread,
  and inside an assessment LangGraph fans out onto its own executor — thread usage
  multiplies under real concurrency (same root cause as the pool ceiling). Fine at demo
  load. What breaks at scale, and the answer: move the LLM hot path to true async
  (AsyncGroq + async nodes) so threadpools stop stacking. That is the trigger to revisit
  the zero-async decision.
- **The Pydantic model on `/asha/assessment` is documentation, not enforcement.**
  `AssessmentSubmission` is all-optional/`extra="allow"` and the endpoint keeps the
  original manual validation verbatim, because the offline queue
  (`app/static/js/offline-queue.js`) drops items on exactly HTTP 400 and retries forever
  on anything else — the manual 400 bodies are a client contract. A global
  `RequestValidationError -> 400` handler guarantees no framework 422 can ever jam the
  queue. The existing agent-output Pydantic models (`app/ai/agents.py`) remain the real
  enforced schemas.
- **Session cookies:** Starlette's signed-cookie format is not Flask-compatible; the
  cookie name is kept (`session`) so stale Flask cookies fail cleanly to the login page.
  Everyone re-logs-in once after cutover.
- **url_for/`request.endpoint`:** FastAPI routes are named with the original Flask
  endpoint names; a Jinja shim resolves identical URLs (including the
  `url_for(..., mother_id='')` JS-prefix pattern and kwargs-to-query-string). Zero
  template edits; parity proven by byte-diffing every rendered page.

## Found and deliberately NOT fixed (each would change AI behavior — decide separately)

1. **Trend analysis never sees history:** `prepare_assessment_for_ai` writes
   `historical_assessments` but `trend_analysis_node` reads `previous_assessments`
   (agents.py:428), so trend always takes its deterministic baseline in the web flow.
   One-line fix, but it would change AI output for every assessment.
2. **RAG retrieval runs twice per query** (`app/rag/api.py` confidence pass +
   `retriever.py` inside `engine.query`) — halving it is an easy perf win for the
   chatbot, deferred to keep this migration behavior-neutral.
3. **Risk node's internal fallback crashes when glucose or temperature is absent**
   (`agents.py`: `glucose > 200` / `temp > 102` on None). The exception escalates to the
   outer rule-based fallback, so scoring still happens — but via a different (coarser)
   path than intended. Pre-existing; unchanged.
4. **finalize's summary keys (`final_results`, `workflow_complete`, ...) are undeclared
   state channels** and are silently dropped by LangGraph — true before the migration
   too; nothing downstream reads them (`build_ai_evaluation` re-aggregates itself).

## Verification performed

- `scripts/diff_responses.py`: **40/40 endpoints byte-identical** between Flask (:8000)
  and FastAPI (:8001) on the same DB — status, content-type, JSON deep-equality, HTML
  bytes — across admin/asha/doctor sessions.
- `pytest tests/ -q`: **51 passed** (risk scoring, auth, bot handlers, registration,
  repo round-trips, offline-replay on BOTH the Flask and FastAPI apps, parallel-graph
  suite).
- Playwright E2E against FastAPI on 8000 (verified `server: uvicorn` header): offline
  PWA flow (queue -> sync -> idempotent replay) passed; `e2e/screenshot_pages.py`
  rendered all 16 dashboard pages for all three roles with **0 console errors**.
- Real assessment through the full stack (Groq + Supabase + alerts) returns 201 with
  identical response shape; replay returns `already_synced` 200.

## Running

```bash
python run_fastapi.py                 # FastAPI/uvicorn, port 8000 (FASTAPI_PORT overrides)
WEB_CONCURRENCY=2 python run_fastapi.py   # multiple workers (Windows spawn; pool x workers DB connections)
# Linux/Docker production:
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 app.fastapi_app:app
# Rollback at any moment:
python run.py                         # legacy Flask entry, identical routes
```

Follow-up cleanup (a separate commit AFTER phone re-testing): delete
`app/blueprints/*` JSON/dashboard blueprints, `app/__init__.py` factory wiring,
`tests/test_offline_replay.py` (Flask variant), and `run.py`; keep
`appointment/webhook_server.py` (permanently Flask) and `werkzeug` (secure_filename).
