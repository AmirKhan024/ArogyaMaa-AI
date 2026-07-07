# ArogyaMaa-AI Transformation — Handoff

State as of this session. Full plan: `ArogyaMaa_Transformation_Spec.md`. Repo conventions:
`CLAUDE.md`.

## Done this session (verified end-to-end)

**Phase 1 — MongoDB → Supabase Postgres (complete)**
- `requirements.txt`: removed `pymongo`, `openpyxl`, `openai`, `huggingface_hub`; added
  `SQLAlchemy`, `psycopg[binary]`, `bcrypt`, `pytest`.
- `db/schema.sql` — full Postgres schema (UUID PKs, JSONB, `client_uuid` unique for offline
  idempotency). `message_threads` + `notifications` (split from Mongo `messages`),
  `registration_sessions`, `rag_chat_threads`, `appointments`.
- `app/db.py` — SQLAlchemy engine + `rows_to_dicts` (`_id` alias, UUID→str), `to_jsonb`.
- `app/repositories/_sql.py` — shared insert/update/query helpers (param-bound, JSONB, `extra`).
- All 8 repos rewritten + new `rag_threads_repo.py`; `get_by_username` added to asha/doctors.
- Route sweep: removed all `ObjectId`/`get_collection` from `admin`, `asha`, `doctor`,
  `doctor/ai_api`, `rag/api`, `api`, `shared_logic`, `services/telegram_handlers`.
- External Mongo paths migrated: `run_telegram_bot.py` (own client → `init_db()` + repos),
  `appointment/handler.py` (per-call client → `mothers_repo`).
- `appointment/excel_manager.py` — Excel → Postgres `appointments` table (same signatures).
- `db/seed.py` — bcrypt-hashed demo doctor/asha + mothers; prints creds.

**Phase 2 — free AI/voice (complete)**
- Model ids via env in `agents.py`, `nutrition_advisor.py`, `document_analyzer.py`,
  `registration/assistant.py`, `rag/retriever.py`, `doctor/ai_assistant.py`, bot nutrition.
- `appointment/transcriber.py` → Groq Whisper. `appointment/tts_sender.py` → Edge-TTS.
  No live OpenAI/HF/Voxtral references remain (grep-clean).

**Phase 3 — security (complete)**
- `app/security.py` (bcrypt). `auth/__init__.py` rewritten (no plaintext `MOCK_USERS`;
  bcrypt verify; dev-only env admin). `SECRET_KEY` fail-fast in `app/__init__.py`.
- Central API auth guard (session OR `X-Internal-Token`) over `/admin /asha /doctor /api /ai`,
  `/health` public. Admin create-user routes hash passwords.

**Phase 5 (partial) — tests**
- `tests/test_risk_scoring.py`, `tests/test_auth.py`, `tests/test_repositories.py`
  (DB-guarded). All green (`9 passed`).

**Verification performed:** byte-compiled all changed files; imported repos/app/appointment
(no circular imports); applied `db/schema.sql` to a throwaway local Postgres; ran `db/seed.py`;
full repo round-trip (JSONB read/write, `_id` alias, `client_uuid` idempotency,
`assessment_number`, nested JSONB increment, notifications, threads, registration merge,
bcrypt login); booted the Flask app (`✓ Postgres connected`); confirmed `/admin/health`=200,
`/admin/mothers` no-auth=401, with internal token=200, `/asha/mothers` no-auth=401; `pytest`=9
passed. The throwaway DB was dropped afterward.

## NOT done yet (next session)

**Phase 4 — offline-first PWA for ASHA** (`ArogyaMaa_Transformation_Spec.md` §6). Greenfield;
the schema already has `assessments.client_uuid` unique and `assessments_repo.create` is
idempotent on it. Remaining: `manifest.webmanifest`, service worker (`app/static/js/sw.js`),
IndexedDB queue (`app/static/js/offline-queue.js`) intercepting the existing
`fetch('/asha/assessment', …)` in `app/templates/asha/new_assessment.html`, connectivity/pending
UI in `app/templates/asha/base.html`, and a root-scope route to serve `sw.js` with
`Service-Worker-Allowed: /`. Note: the `/asha/assessment` POST now requires auth — offline
replays run in the browser session, so they're covered; if any bot path posts assessments it
must send `X-Internal-Token`.

**Phase 5 (rest)** — pin every `requirements.txt` line (`pip freeze` in a clean venv);
replace remaining `print(`/`datetime.utcnow()` (many in `app/ai/`, `services/telegram_handlers.py`,
`shared_logic.py`, bot) with `logging`/`datetime.now(timezone.utc)`; add `Dockerfile` +
`docker-compose.yml` (web + bot, shared `.env`); rewrite `README.md` (Supabase+Groq setup,
"Known limitations & roadmap", drop MongoDB/OpenAI/telephony claims + badges).

## Known caveats to check

- `asha_workers`/`doctors` have no `extra` column, so repo `create/update` silently drop
  unknown keys there. Fine currently, but keep in mind if new fields are added.
- Some `messages_repo.create` call sites (doctor consultation/message/review logging) map into
  the limited `notifications` columns; a few old free-form fields are not persisted (non-critical
  delivery-log metadata). Revisit if that log matters.
- The user targets **Supabase**; full end-to-end there still needs the user's pooler
  `DATABASE_URL` + running `db/schema.sql` in Supabase. Local Postgres verified the code.

## Next-session prompt (paste this)

> Continue the ArogyaMaa-AI transformation. Phases 1–3 (Postgres migration, free Groq/Edge-TTS
> voice, security hardening) and the initial test suite are DONE and verified — see `HANDOFF.md`
> and `CLAUDE.md`. Do Phase 4 (offline-first PWA for the ASHA dashboard) and the rest of Phase 5
> (pin requirements, logging + `datetime.now(timezone.utc)` sweep, Dockerfile + docker-compose,
> README rewrite) per `ArogyaMaa_Transformation_Spec.md` §6–7. Verify each phase (a local
> throwaway Postgres works: apply `db/schema.sql`, run `db/seed.py`, `python run.py`, `pytest`).
> Preserve the repository seam conventions in `CLAUDE.md` (string `_id`, JSONB, no `ObjectId`).
