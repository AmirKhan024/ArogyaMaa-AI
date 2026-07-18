# CLAUDE.md — ArogyaMaa-AI

Guidance for Claude Code working in this repo. Read this before making changes.

## What this is

Flask + Telegram maternal-health app: a LangGraph multi-agent AI risk pipeline, a RAG
chatbot (ChromaDB, local), three role dashboards (ASHA / doctor / admin), and a
voice-first Telegram bot for mothers. Being transformed to run **100% free-tier**:
**Supabase Postgres + Groq only** (no OpenAI, no HuggingFace paid keys).

## Architecture (current state)

- **Database:** Supabase/Postgres via **SQLAlchemy Core + psycopg** (`app/db.py`). There is
  NO MongoDB anymore. `DATABASE_URL` drives it (works with Supabase pooler URI *or* a local
  Postgres — the SQL is portable). The engine sets `connect_args={"prepare_threshold": None}` —
  REQUIRED with the Supabase transaction pooler (:6543) or prepared statements collide
  ("DuplicatePreparedStatement"). Do not remove it.
- **There is ONE Telegram bot: the polling bot** (`run_telegram_bot.py`). The legacy Flask
  webhook bot (`app/blueprints/telegram/`, `app/services/telegram_handlers.py`) was DELETED —
  do not resurrect it. `app/services/telegram_service.py` (raw HTTP sender) stays: it is used
  by `app/ai/alerts.py` and doctor routes to push messages to mothers.
- **Email:** Brevo SMTP via `app/services/email_service.py` (Flask-free; used by web AND bot
  processes). Appointment doctor emails go through `appointment/email_sender.py` → Brevo.
  Env: `BREVO_SMTP_LOGIN/KEY`, `EMAIL_FROM`, `EMAIL_FROM_NAME`, `DOCTOR_EMAIL`. Failures are
  non-fatal by design.
- **Data access seam = `app/repositories/*.py`.** Blueprints/services/bot must go through
  repositories, never raw SQL. Shared query/insert/update helpers live in
  `app/repositories/_sql.py`.
- **AI:** Groq only (`GROQ_API_KEY`). Model ids come from env: `LLM_MODEL`
  (default `openai/gpt-oss-120b`, an open-weights model *served by Groq* — no OpenAI account),
  `LLM_MODEL_FAST` (default `llama-3.1-8b-instant`), `WHISPER_MODEL` (`whisper-large-v3`).
  Rule-based fallback scorer in `app/ai/fallback.py` must stay wired (graceful degradation).
- **Voice:** STT = Groq Whisper, TTS = Edge-TTS (free, no key). Registration voice:
  `app/ai/registration/voice_processor.py`. Appointment voice: `appointment/transcriber.py`
  (STT) + `appointment/tts_sender.py` (TTS).
- **RAG:** ChromaDB + local sentence-transformers embeddings (`app/rag/`). Local & free — do
  not migrate to Supabase.
- **Two processes:** `run.py` (Flask web, port 8000) and `run_telegram_bot.py` (bot, polling;
  also starts the appointment webhook on port 5050). Both call `app.db.init_db()`.

## Repository conventions (IMPORTANT — preserve these)

- Reads return plain dicts with a **string `_id`** aliased from the Postgres `id` UUID
  (downstream code does `str(doc['_id'])` and stores ids in the Flask session). All UUID
  values are stringified by `rows_to_dicts`.
- `create()` returns the new id as a **str**. `list_*` → `list[dict]`; `get_*`/`find_*` →
  `dict | None`; `update*`/`add*`/`mark*` → `bool`.
- Nested/rich fields are **JSONB columns** (`vitals`, `ai_evaluation`, `performance_stats`,
  `medical_history`, `current_pregnancy`, `assigned_mothers[]`, message arrays, etc.). When
  writing JSONB, use `to_jsonb(...)` + a `cast(:x as jsonb)` (the `_sql` helpers do this).
- Mongo fields without a dedicated column fold into an **`extra` JSONB** column (mothers).
  `asha_workers`/`doctors` have no `extra` — unknown keys are dropped there.
- The old `messages` collection is split into **`message_threads`** (per-mother chat) and
  **`notifications`** (standalone alerts). `rag_chat_threads` and `registration_sessions` are
  their own tables/repos.
- IDs are UUID strings now — **never wrap ids in `ObjectId(...)`** and compare ids as strings.

## Security

- Passwords are **bcrypt** hashes (`app/security.py`); login verifies via
  `verify_password`. Never store/query plaintext.
- `SECRET_KEY` is **required** — the app factory fails fast if unset.
- JSON API routes under `/admin /asha /doctor /api /ai` are guarded centrally in
  `app/__init__.py::register_route_protection` (session OR `X-Internal-Token ==
  INTERNAL_API_TOKEN`); `/health` endpoints stay public. Bot→API server-to-server calls use
  the internal token. There's an `api_login_required` decorator in the auth blueprint too.
- Dev-only static admin login (there is no admins table): set `ADMIN_PASSWORD` in `.env`
  with `APP_ENV=development`.

## Setup & run

```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill SECRET_KEY, DATABASE_URL, GROQ_API_KEY, TELEGRAM_BOT_TOKEN, INTERNAL_API_TOKEN
psql "$DATABASE_URL" -f db/schema.sql   # or run db/schema.sql in the Supabase SQL editor
python db/seed.py             # seeds demo doctor/asha/mothers, prints credentials
python run.py                 # Flask web (port 8000)
python run_telegram_bot.py    # Telegram bot (separate terminal)
```

Demo creds after seeding: `doctor/doctor123`, `asha/asha123`, admin via `ADMIN_PASSWORD`.

One-time for the RAG chatbot: `python -m app.rag.knowledge_ingestion` (builds the local
ChromaDB from `rag_pdf_source/` PDFs; ~2 min).

## Verify

- `python -m pytest tests/ -q` — risk scoring, auth, bot handlers (no DB) plus repo
  round-trips and offline-replay idempotency (need `DATABASE_URL` + schema; skipped otherwise).
- Browser E2E (server running on :8000 + seeded): `python -m pytest e2e/ -q` (offline PWA
  flow) and `python e2e/screenshot_pages.py` (screenshots every dashboard page + console
  errors per role).
- Email smoke: `python scripts/send_test_email.py` (real Brevo send to DOCTOR_EMAIL).
- Quick DB-agnostic check: point `DATABASE_URL` at a throwaway local Postgres, apply
  `db/schema.sql`, run `db/seed.py`, then `python run.py`.
- Env-only smoke: booting the app requires `SECRET_KEY` + `DATABASE_URL`; AI/voice need
  `GROQ_API_KEY`; killing `GROQ_API_KEY` must fall back to the rule-based scorer, not crash.

## Free-tier gotchas

- Supabase free projects auto-pause after ~7 days idle — open the dashboard once before a demo.
- Groq is rate-limited and rotates models — swap `LLM_MODEL` (one env change) if an id is
  retired; verify current ids at console.groq.com/docs/models.

## Gotchas specific to this codebase

- JSONB cannot hold Python `datetime` — the repo layer serializes datetimes to ISO strings
  inside JSONB (`to_jsonb`). When reading a timestamp out of a JSONB blob it may be a **string**,
  not a datetime — guard with something like `api/routes.py::_iso`.
- `run_telegram_bot.py` runs as a separate process and calls `init_db()` itself; it uses
  repositories, not raw SQL.
- Windows console is cp1252 — avoid non-ASCII glyphs (→, ✓) in `print()` in CLI scripts.
- **UI:** all dashboards share `app/static/css/admin.css`, a token-based design system. The
  class names AND CSS variable names (including legacy `--sakura-*`/`--fuji-*` aliases) are a
  stable API referenced by template inline styles — restyle by changing values, never rename.
  Chart.js uses the `--viz-*` status colors for risk and `--chart-1..8` for series.
- Missing optional vitals must be presented to the AI as "Not measured", never 0
  (`app/ai/agents.py::_measured`) — "Hemoglobin: 0" reads as fatal anemia and corrupts scores.
- `assessments_repo.find_id_by_client_uuid` is checked in `submit_assessment` BEFORE create so
  offline replays skip AI + alert side effects. Keep both layers of idempotency.
- Document analysis (`app/ai/document_analyzer.py`): PDF text layer → OCR → Groq vision
  (`GROQ_VISION_MODEL`, default llama-4-scout). If nothing is readable it returns
  `success: False` — it must NEVER invent findings. Transient 429/5xx → error "AI_BUSY".
- `app/db.py::_map_row` FLATTENS the mothers `extra` JSONB to top level on read (real
  columns win when non-null). Registration fields like location/edd/danger_signs/
  substance_usage/preferred_language are read at the ROOT of the dict — keep it that way.
- **Registration** (`app/ai/registration/`): question text is FIXED bilingual copy in
  `questions.py` (REGISTRATION_STEPS, grouped steps); the LLM does extraction ONLY
  (FAST model, temp 0, escalates to LLM_MODEL when empty). The engine is deterministic/
  idempotent; the bot serializes per-chat input with `_reg_locks`. Never reintroduce
  LLM-generated question wording.
- Every Supabase pooler round-trip costs ~0.5s — NEVER loop per-row repo lookups in a
  request (N+1). Bulk-fetch once or memoize per-request (see doctor/routes.py,
  admin/routes.py get_mothers).
- `graph.invoke` in submit_assessment runs under a 120s hard budget (Groq 429 backoffs
  can spiral to an hour); on timeout the rule-based fallback scores. Keep the budget.
- Appointments: table + `appointments_repo` (list/act); `appointment/excel_manager.py` is
  a legacy-named shim used by the bot flow. Doctor dashboard page + bot "My appointments"
  submenu both act via `appointments_repo.update_status` and notify via telegram_service.
