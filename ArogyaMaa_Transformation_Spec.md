# ArogyaMaa-AI — Transformation Spec (for Claude Code)

> **Read this whole file before making any change.** Execute in the exact phase order
> below. Run and verify after **each** phase. Do not start a phase until the previous
> phase's acceptance criteria pass. Commit at the end of every phase.

---

## 0. Context & goals

ArogyaMaa-AI is a Flask + Telegram maternal-health app with a LangGraph multi-agent
AI pipeline and a RAG chatbot. This transformation must achieve four outcomes:

1. **Replace local MongoDB with Supabase (Postgres).** No local database.
2. **Be 100% free-tier and require NO OpenAI or HuggingFace paid keys.** The only
   external services are Supabase (free) and Groq (free). All voice (STT + TTS) must
   run on free services.
3. **Add an offline-first capability for rural ASHA field workers** so assessments can
   be captured without internet and synced later.
4. **Fix the pre-existing security / robustness issues** listed in Phase 3 & 5 so an
   interviewer or hackathon judge finds no negligent defects.

### Guardrails (apply to every phase)

- **Preserve public interfaces to minimize blast radius.** The repository layer
  (`app/repositories/*.py`) is the seam. Rewrite repository *internals* but keep every
  function's **name, signature, and return shape** identical (functions that returned a
  `dict` must still return a `dict`; lists of dicts stay lists of dicts). Downstream
  blueprints must not need changes beyond mechanical ones.
- Repository return dicts must keep an **`_id`** key (a `str`) even though Postgres uses
  UUIDs, so existing code like `str(doc['_id'])` and `session['doctor_id']` keeps working.
- **Do not break the Telegram bot.** `run_telegram_bot.py` and its handlers must keep
  functioning after the DB swap.
- Keep the **RAG stack (ChromaDB + sentence-transformers) unchanged** — it is local and
  free and already works. Do NOT migrate vectors to Supabase in this pass.
- After each phase: `pip install -r requirements.txt`, start the app (`python run.py`),
  and confirm it boots with no import/connection errors before proceeding.
- Never commit real secrets. `.env` stays gitignored; only `.env.example` is committed.

---

## 1. Target architecture (before → after)

| Concern            | Before                                   | After                                             |
|--------------------|------------------------------------------|---------------------------------------------------|
| Operational DB     | Local MongoDB (pymongo)                  | Supabase Postgres via SQLAlchemy Core + psycopg3  |
| Appointments store | Excel files (openpyxl)                   | Supabase `appointments` table                     |
| LLM                | Groq `llama-3.3-70b-versatile` (hardcoded, deprecating) | Groq, model from `LLM_MODEL` env       |
| STT (appointment)  | OpenAI Whisper `whisper-1` (**paid**)    | Groq Whisper `whisper-large-v3` (**free**)        |
| TTS (appointment)  | HF Voxtral (broken/paid)                 | Edge-TTS (**free**, no key)                       |
| STT/TTS (registration) | Groq Whisper + Edge-TTS (already free) | Unchanged                                       |
| Passwords          | Plaintext in DB / hardcoded              | bcrypt hashes                                      |
| API auth           | Data routes open to the internet         | Auth guard on all data routes                     |
| RAG                | ChromaDB + sentence-transformers (local) | Unchanged                                          |
| Field data capture | Online only                              | Offline-first PWA + sync queue for ASHA           |

External services after transformation: **Supabase (free) + Groq (free) only.**

---

## 2. Final environment variables

Rewrite `.env.example` to exactly this (no OpenAI, no HuggingFace token). Update
`app/config.py` to read these. Remove all `MONGODB_*`, `OPENAI_*`, `HF_*`, `WHISPER_*`
(OpenAI), and `VOXTRAL`/`HF_TTS_MODEL` variables.

```dotenv
# ── Flask ──────────────────────────────────────────────
SECRET_KEY=            # REQUIRED. Generate: python -c "import secrets;print(secrets.token_hex(32))"
APP_ENV=development
DEBUG=True
HOST=0.0.0.0
PORT=8000

# ── Supabase (Postgres) ───────────────────────────────
# Supabase Dashboard → Project Settings → Database → Connection string → "URI"
# Use the connection POOLER URI (port 6543) for app runtime.
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<host>:6543/postgres

# ── Groq (LLM + Whisper STT) — FREE tier, the ONLY AI key you need ──
GROQ_API_KEY=
# NOTE: gpt-oss models are OPEN-WEIGHTS models HOSTED BY GROQ. Using them needs only
# GROQ_API_KEY — NOT an OpenAI account. Verify a current id at console.groq.com/docs/models
LLM_MODEL=openai/gpt-oss-120b
WHISPER_MODEL=whisper-large-v3

# ── Telegram ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
APPOINTMENT_WEBHOOK_PORT=5050

# ── Internal service auth (bot → API) ─────────────────
INTERNAL_API_TOKEN=    # Generate a random hex; used for server-to-server calls

# ── Optional: LangSmith tracing (free tier) ───────────
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ArogyaMaa
LANGCHAIN_TRACING_V2=false

# ── Feature flags ─────────────────────────────────────
ENABLE_AI_ADVISORY=True
```

---

## 3. PHASE 1 — Migrate MongoDB → Supabase (Postgres)

**Objective:** all operational data moves to Supabase Postgres; repository interfaces stay identical.

### 3.1 Dependencies
In `requirements.txt`, remove `pymongo`. Add (pinned versions — see Phase 5):
`sqlalchemy`, `psycopg[binary]`, `python-dotenv`, `bcrypt`.

### 3.2 Create the schema
Create `db/schema.sql` and run it once in the Supabase SQL editor. Use UUID PKs and
JSONB for nested/AI blobs. Minimum tables (derive exact columns from the current
repositories — grep each `app/repositories/*.py` for the fields it reads/writes):

```sql
create extension if not exists "pgcrypto";

create table asha_workers (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  password_hash text not null,
  name text,
  phone text,
  active boolean default true,
  created_at timestamptz default now()
);

create table doctors (
  id uuid primary key default gen_random_uuid(),
  username text unique not null,
  password_hash text not null,
  name text,
  specialty text,
  active boolean default true,
  created_at timestamptz default now()
);

create table mothers (
  id uuid primary key default gen_random_uuid(),
  telegram_chat_id text unique,
  name text,
  age int,
  phone text,
  gestational_week int,
  assigned_asha_id uuid references asha_workers(id),
  assigned_doctor_id uuid references doctors(id),
  extra jsonb default '{}'::jsonb,      -- any Mongo fields without a dedicated column
  created_at timestamptz default now()
);

create table assessments (
  id uuid primary key default gen_random_uuid(),
  mother_id uuid references mothers(id),
  asha_id uuid references asha_workers(id),
  vitals jsonb default '{}'::jsonb,
  symptoms jsonb default '[]'::jsonb,
  ai_analysis jsonb default '{}'::jsonb,
  risk_level text,
  client_uuid text unique,              -- for offline idempotency (Phase 4)
  created_at timestamptz default now()
);

create table consultations (
  id uuid primary key default gen_random_uuid(),
  mother_id uuid references mothers(id),
  doctor_id uuid references doctors(id),
  notes jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create table messages (
  id uuid primary key default gen_random_uuid(),
  mother_id uuid references mothers(id),
  sender_role text,
  body text,
  created_at timestamptz default now()
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  mother_id uuid references mothers(id),
  filename text,
  storage_path text,
  analysis jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create table registrations (
  id uuid primary key default gen_random_uuid(),
  telegram_chat_id text,
  state jsonb default '{}'::jsonb,
  completed boolean default false,
  created_at timestamptz default now()
);

create table appointments (
  id uuid primary key default gen_random_uuid(),
  telegram_chat_id text,
  patient_name text,
  patient_age text,
  patient_phone text,
  requested_date text,
  requested_time text,
  status text default 'Pending',
  confirmed_date text,
  confirmed_time text,
  doctor_notes text,
  security_token text,
  created_at timestamptz default now()
);
```

> When migrating each repository, if it reads a field not in the schema above, add a
> column for it (if it's queried/filtered) or fold it into the `extra`/relevant `jsonb`
> column (if it's just stored/returned). Do not silently drop fields.

### 3.3 Rewrite `app/db.py`
Replace the pymongo singleton with a SQLAlchemy engine + a helper for dict rows:

```python
"""Postgres (Supabase) connection layer — SQLAlchemy Core."""
import os
from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import Engine

_engine: Engine | None = None
metadata = MetaData()

def init_db(app):
    global _engine
    if _engine is None:
        url = app.config["DATABASE_URL"]
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        with _engine.connect() as conn:
            conn.exec_driver_sql("select 1")
        app.logger.info("✓ Supabase Postgres connected")

def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("DB not initialised; call init_db() first.")
    return _engine

def rows_to_dicts(result):
    """Map rows to dicts and expose the PK as string '_id' for back-compat."""
    out = []
    for row in result.mappings():
        d = dict(row)
        if "id" in d and "_id" not in d:
            d["_id"] = str(d["id"])
        out.append(d)
    return out
```

Remove `get_db()` / `get_collection()` OR keep thin stubs only if something still imports
them — but the goal is to route everything through repositories.

### 3.4 Rewrite repositories (the important part)
For **each** file in `app/repositories/`, reimplement its functions with SQLAlchemy Core
`text()` queries against the new tables, **keeping signatures and return shapes identical**.
Pattern:

```python
from sqlalchemy import text
from app.db import get_engine, rows_to_dicts

def list_all() -> list[dict]:
    with get_engine().begin() as conn:
        res = conn.execute(text("select * from doctors where active = true order by created_at"))
        return rows_to_dicts(res)

def find_by_id(doctor_id: str) -> dict | None:
    with get_engine().begin() as conn:
        res = conn.execute(text("select * from doctors where id = :id"), {"id": doctor_id})
        rows = rows_to_dicts(res)
        return rows[0] if rows else None
```

- Convert Mongo operators to SQL: `find_one({k: v})` → `WHERE k = :v`; `insert_one` →
  `INSERT ... RETURNING id`; `update_one({$set})` → `UPDATE ... SET`.
- Use **parameter binding everywhere** (`:name`) — never f-string interpolation into SQL.
- For JSONB columns, pass Python dicts with `json.dumps` or SQLAlchemy JSON handling.

### 3.5 Audit direct DB access outside repositories
Grep and fix every direct call:
```
grep -rn "get_collection\|get_db\|find_one\|insert_one\|update_one\|MongoClient\|pymongo" app/ appointment/ run_telegram_bot.py
```
Route each through the appropriate repository function. **Special case:**
`appointment/handler.py` creates its own `MongoClient` per call — replace with the
`mothers_repo.find_by_telegram_chat_id(...)` repository call.

### 3.6 Move appointment storage off Excel
Rewrite `appointment/excel_manager.py` so `create_appointment`, `get_appointment_by_id`,
and `update_appointment_status` read/write the Supabase `appointments` table (keep the same
function names + signatures). Remove `openpyxl` from requirements. Delete Excel file paths
from `.gitignore` cleanup notes if no longer used.

### 3.7 Seed script
Create `db/seed.py` that inserts one admin, one doctor, one ASHA, and 1–2 demo mothers with
**bcrypt-hashed** passwords (coordinate with Phase 3). Print the demo credentials to stdout.

### Phase 1 acceptance criteria
- App boots and logs "Supabase Postgres connected".
- Login works against seeded DB users.
- ASHA dashboard lists mothers; submitting an assessment writes a row to `assessments`.
- Telegram registration writes to `mothers`/`registrations`.
- `grep` for `pymongo`/`MongoClient` returns nothing in app code.

---

## 4. PHASE 2 — Remove OpenAI/HF; all-free voice + fix LLM model

**Objective:** zero paid AI dependencies; one consistent free voice stack; configurable model.

### 4.1 LLM model
- In `app/ai/agents.py` replace the hardcoded `DEFAULT_MODEL = "llama-3.3-70b-versatile"`
  with `DEFAULT_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")`.
- Grep for any other hardcoded model id and route them through the same env var:
  `grep -rn "llama-3\|versatile\|gpt-oss\|model=" app/`.
- Confirm `app/ai/fallback.py` (rule-based) still triggers on LLM error — keep it.

### 4.2 Appointment STT → Groq Whisper (free)
Rewrite `appointment/transcriber.py` to use the Groq client instead of OpenAI. Mirror the
approach already used in `app/ai/registration/voice_processor.py`:
```python
from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
with open(oga_path, "rb") as f:
    tr = client.audio.transcriptions.create(
        model=os.getenv("WHISPER_MODEL", "whisper-large-v3"),
        file=f, language="hi", response_format="text")
```
Delete all `OPENAI_API_KEY` / `OpenAI` references.

### 4.3 Appointment TTS → Edge-TTS (free)
Rewrite `appointment/tts_sender.py` to use `edge-tts` (already a dependency) exactly like
the registration voice path, producing an OGG/OPUS Telegram voice note. Delete all
`HF_API_TOKEN` / `Voxtral` / `InferenceClient` references. If a shared TTS helper exists in
the registration module, reuse it instead of duplicating.

### 4.4 Requirements cleanup
Remove `openai`, `huggingface_hub` (unless `sentence-transformers` needs it transitively —
keep only if an import breaks). Remove `openpyxl` (done in 3.6). Keep `edge-tts`, `pydub`,
`groq`, `chromadb`, `sentence-transformers`.

### 4.5 Config cleanup
Delete every OpenAI/HF/Voxtral/Whisper-1 variable from `app/config.py` and `.env.example`.

### Phase 2 acceptance criteria
- `grep -rni "openai\|voxtral\|huggingface" app/ appointment/` shows only the harmless
  `openai/gpt-oss` model id and no key usage.
- An appointment voice interaction transcribes (Groq) and replies with voice (Edge-TTS).
- App runs with only `GROQ_API_KEY` + `DATABASE_URL` + `TELEGRAM_BOT_TOKEN` set.

---

## 5. PHASE 3 — Security hardening

**Objective:** remove the disqualifying defects for a healthcare app.

### 5.1 Password hashing (bcrypt)
- Add `app/security.py` with `hash_password(pw)` and `verify_password(pw, hash)` using `bcrypt`.
- Rewrite `app/blueprints/auth/__init__.py`:
  - Remove the plaintext `MOCK_USERS` dict from source. Seed a demo admin in the DB via
    `db/seed.py` instead, with a hashed password. If a static evaluator login is still
    desired, gate it behind `APP_ENV == "development"` and read the password from env, never
    hardcoded.
  - Replace `find_one({'password': password})` DB lookups with: fetch by username, then
    `verify_password(...)`. Never send the password to the DB query.
- The seed script must store `password_hash`, not `password`.

### 5.2 Secret key
In `app/__init__.py` remove the hardcoded `SECRET_KEY` fallback. If `SECRET_KEY` is missing,
**fail fast** with a clear error (do not silently invent one).

### 5.3 Auth guard on API routes
Add a decorator `@api_login_required` (session-based) in `app/blueprints/auth/__init__.py`
and apply it to every route that returns or mutates patient data across `/asha`, `/doctor`,
`/admin`, `/api`. For endpoints the **Telegram bot** must call server-to-server, accept an
`X-Internal-Token` header equal to `INTERNAL_API_TOKEN` as an alternative to a session:
```python
def api_login_required(f):
    @wraps(f)
    def w(*a, **k):
        if session.get("logged_in"):
            return f(*a, **k)
        if request.headers.get("X-Internal-Token") == current_app.config["INTERNAL_API_TOKEN"]:
            return f(*a, **k)
        return {"error": "unauthorized"}, 401
    return w
```
Audit `app/__init__.py::register_route_protection` — the comment that leaves API routes open
must be removed and the routes actually protected.

### 5.4 Input validation
For POST endpoints that accept assessment/consultation data, validate the request body with
a Pydantic model (Pydantic is already a dependency) and return 400 on failure.

### Phase 3 acceptance criteria
- No plaintext password anywhere (`grep -rn "'password'" app/` shows only `password_hash`).
- Hitting `/asha/mothers` (or any data route) without a session returns 401.
- Bot-invoked endpoints work with the `X-Internal-Token` header.
- App refuses to start without `SECRET_KEY`.

---

## 6. PHASE 4 — Offline-first PWA for rural ASHA workers

**Objective:** ASHA field workers in low/no-connectivity villages can capture assessments
offline; data syncs automatically when connectivity returns.

> Scope note: the *mother-facing* Telegram flow requires internet on the mother's phone, so
> offline support targets the **ASHA worker web dashboard**, which is where field capture
> happens. State this clearly in the README.

### 6.1 Make the ASHA dashboard a PWA
- Add `app/static/manifest.webmanifest` (name, short_name, icons, `display: standalone`,
  theme color) and link it from `app/templates/asha/base.html`.
- Add `app/static/js/sw.js` (service worker) that pre-caches the app shell (HTML/CSS/JS of
  the ASHA dashboard) with a cache-first strategy for static assets and network-first for
  API GETs. Register it from the ASHA base template:
  ```html
  <script>if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/js/sw.js');</script>
  ```
- Serve `sw.js` from the app root scope if needed (add a small route returning the file with
  `Service-Worker-Allowed: /`).

### 6.2 Offline assessment queue (IndexedDB)
- Add `app/static/js/offline-queue.js`:
  - On assessment submit, generate a **`client_uuid`** (crypto.randomUUID()).
  - If `navigator.onLine` is false OR the POST fails, store the payload in IndexedDB
    (object store `pending_assessments`) and show a "Saved offline — will sync" badge with a
    pending counter.
  - Expose `flushQueue()` that POSTs each pending item to `/asha/assessment` and deletes it
    from IndexedDB on success.
- Trigger `flushQueue()` on `window 'online'` event, on page load, and (optionally) via the
  Background Sync API (`registration.sync.register('sync-assessments')`) with the
  online-event listener as the reliable fallback.

### 6.3 Idempotent server ingest
- The `/asha/assessment` endpoint must accept `client_uuid`, and `assessments_repo.create()`
  must **upsert on `client_uuid`** (the unique column added in the schema) so replays after
  flaky connectivity never create duplicates:
  `INSERT ... ON CONFLICT (client_uuid) DO NOTHING RETURNING id`.
- Note: the AI risk analysis for offline-captured assessments runs **server-side on sync**
  (not on the offline device), so no AI keys are needed offline.

### 6.4 UX
- A persistent connectivity indicator (online/offline) in the ASHA dashboard header.
- A "Pending sync: N" chip that decrements as the queue flushes.

### Phase 4 acceptance criteria
- Load the ASHA dashboard, go offline (DevTools → Network → Offline), submit an assessment →
  it is saved locally and the pending counter shows 1.
- Go back online → the assessment auto-syncs, appears in Supabase `assessments`, counter → 0.
- Submitting the same offline item twice results in exactly one DB row (idempotency).
- The dashboard shell loads while offline (service worker cache).

---

## 7. PHASE 5 — Robustness, reproducibility, tests

**Objective:** clean, reproducible, testable — the polish that removes "can I even run this?"

### 7.1 Pin dependencies
Pin **every** line in `requirements.txt` to a specific working version (run `pip freeze` in a
clean venv after everything imports, and copy exact versions). Unpinned LangChain/LangGraph
is a known breakage risk.

### 7.2 Logging
Replace `print(...)` with the `logging` module across `app/ai/`, `run.py`,
`run_telegram_bot.py`, and blueprints. Configure a root logger in `app/__init__.py`.

### 7.3 Deprecations & leaks
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` everywhere.
- Replace bare `except Exception: pass` in `auth/__init__.py` with logged handling.

### 7.4 Docker
Add a `Dockerfile` (python:3.11-slim, install requirements, run `run.py`) and a
`docker-compose.yml` with two services — `web` (Flask) and `bot` (`run_telegram_bot.py`) —
both reading the same `.env`. The DB is Supabase (cloud), so no DB container is needed;
optionally include a commented local-postgres service for offline dev.

### 7.5 Tests
Add `pytest` and a `tests/` folder. At minimum:
- `test_risk_scoring.py` — deterministic tests for the rule-based scorer in
  `app/ai/fallback.py` / risk logic (danger symptom → CRITICAL, normal vitals → LOW, etc.).
- `test_repositories.py` — smoke tests against a test schema (or mocked engine) verifying
  insert/find round-trips and the `_id` aliasing.
- `test_auth.py` — hash/verify round-trip and that a wrong password fails.

### 7.6 README
Add a **"Known limitations & roadmap"** section (honest defect log turns weaknesses into
credibility) and update setup instructions for Supabase + Groq only. Remove any claim about
OpenAI Realtime / telephony; describe the actual Telegram-voice + offline-ASHA design.

### Phase 5 acceptance criteria
- Fresh `python -m venv` + `pip install -r requirements.txt` installs cleanly and the app boots.
- `pytest` passes.
- `docker compose up` starts web + bot.
- No `print(` remains in `app/ai/` or entry scripts.

---

## 8. PHASE 6 — Final verification checklist

Run all of these and confirm green:

- [ ] App boots with ONLY these env vars set: `SECRET_KEY`, `DATABASE_URL`, `GROQ_API_KEY`,
      `TELEGRAM_BOT_TOKEN`, `INTERNAL_API_TOKEN`. No OpenAI/HF keys anywhere.
- [ ] Login (seeded, hashed) works for admin, doctor, ASHA.
- [ ] Data API route without auth → 401; with session or `X-Internal-Token` → 200.
- [ ] Telegram: registration → mother row; appointment → voice STT (Groq) + voice TTS
      (Edge-TTS) + `appointments` row.
- [ ] AI pipeline runs on `LLM_MODEL`; killing the key falls back to the rule-based path
      without crashing.
- [ ] Offline ASHA capture → local queue → auto-sync → single Supabase row (idempotent).
- [ ] `grep -rni "pymongo\|MongoClient\|openai_api_key\|voxtral\|hf_api_token"` → no live usage.
- [ ] `pytest` green; `docker compose up` green.

---

## 9. Free-tier gotchas (tell the user, so a demo never looks "broken")

- **Supabase free tier may auto-pause a project after ~7 days of inactivity.** Before a demo
  or interview, open the Supabase dashboard once to wake it. Verify current behavior in the
  Supabase docs.
- **Groq free tier is rate-limited.** Under rapid testing you may hit limits; the rule-based
  fallback in `app/ai/fallback.py` must stay wired so the app degrades gracefully instead of
  erroring.
- **Groq deprecates models periodically.** Because the model is now an env var, swapping is a
  one-line change. Verify a current free model id at `console.groq.com/docs/models` before a
  demo. `openai/gpt-oss-120b` is an open-weights model **served by Groq** — it does NOT
  require an OpenAI account.
- **`whisper-large-v3` on Groq is free** and replaces the paid OpenAI Whisper.

---

## 10. Suggested commit sequence

1. `chore: pin deps, add supabase/sqlalchemy, remove pymongo/openai/hf`
2. `feat(db): migrate operational data + repositories to Supabase Postgres`
3. `feat(appointments): store appointments in Supabase instead of Excel`
4. `feat(voice): move appointment STT/TTS to free Groq Whisper + Edge-TTS`
5. `refactor(ai): model id from LLM_MODEL env`
6. `feat(security): bcrypt passwords, required SECRET_KEY, auth on API routes`
7. `feat(offline): PWA + IndexedDB queue + idempotent sync for ASHA field capture`
8. `chore(robustness): logging, datetime fix, Docker, tests, README`

Execute phase-by-phase, verify, then commit. Do not batch phases together.
