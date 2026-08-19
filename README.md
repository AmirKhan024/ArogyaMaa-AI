<div align="center">

# ArogyaMaa AI — आरोग्य माँ

### *Voice-First AI for Maternal Healthcare in Rural India*

**Because no mother should die from a complication that was predictable.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-uvicorn-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-parallel_multi--agent-1C3C3C?style=flat)](https://github.com/langchain-ai/langgraph)
[![Groq](https://img.shields.io/badge/Groq-LLM_+_Whisper-F55036?style=flat)](https://groq.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-FF6B6B?style=flat)](https://www.trychroma.com/)
[![PWA](https://img.shields.io/badge/PWA-offline--first-5A0FC8?style=flat)](https://web.dev/progressive-web-apps/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot_API-26A5E4?style=flat&logo=telegram&logoColor=white)](https://core.telegram.org/bots)

<sub>**100% free-tier stack** — the only external services are Supabase (free Postgres) and Groq (free LLM + Whisper). No OpenAI, no paid HuggingFace keys.</sub>

</div>

---

## 🩸 The Silent Crisis

> **In India, a mother dies from a pregnancy-related cause roughly every 22 minutes.**
> That's over **23,000 deaths a year** — and nearly all of them are preventable.

India carries about **one in every four** maternal deaths on Earth. Despite an 86% drop in maternal mortality over the last three decades — the steepest decline of any major country — India still loses mothers to complications that medicine has known how to prevent for fifty years: hemorrhage (47% of deaths), sepsis (12%), and hypertensive disorders like preeclampsia (7%).

The deaths are not random. They cluster in three failures:

| # | Failure | Why it kills |
|---|---------|--------------|
| 1️⃣ | **The silence gap** | ASHA workers record vitals on paper. Nobody reads the trend. A BP creeping from 118 → 128 → 138 is three separate notes — not a warning. |
| 2️⃣ | **The language wall** | 40% of rural Indian women cannot read or type. Every text-based health app excludes them by default. |
| 3️⃣ | **The escalation void** | Doctors learn about complications when the patient arrives in crisis, not 4 weeks earlier when the trajectory first bent wrong. |

**ArogyaMaa AI closes all three gaps — with voice, with parallel multi-agent AI, and with a zero-gap escalation protocol.**

---

## ✨ What We Built

**ArogyaMaa AI** is a multi-agent AI platform that connects pregnant mothers in rural India to ASHA workers and doctors through a single Telegram bot and three role-specific web dashboards. It listens to mothers in their own voice, reasons about their health using a graph of specialized AI agents grounded in WHO clinical guidelines, and routes every alert to the right person.

**In one sentence:** A mother speaks into Telegram in Hindi → a graph of AI agents analyzes her vitals and symptoms concurrently → an ASHA worker gets a prioritized to-do list → a doctor sees a risk-scored dashboard with AI-drafted case notes → nobody falls through the cracks.

### What makes it different

- 🎙️ **Voice-first** — Mothers speak; they don't type. Speech-to-text via Groq Whisper + text-to-speech via Edge-TTS in natural Hindi.
- 🧠 **A graph of AI agents, not one LLM call** — Orchestrator → {Risk Stratification ∥ Symptom Reasoning ∥ Trend Analysis ∥ Document Analysis} → {Nutrition ∥ Communication} → Finalize, coordinated by LangGraph. **Independent agents run in parallel**, cutting the AI critical path from 5 sequential LLM calls to 2.
- ⚡ **Async-capable web core** — FastAPI + uvicorn serve all dashboards and APIs with true request concurrency (measured: 2× throughput at 10 simultaneous requests with flat p95), built for a future IVR/call channel.
- 📚 **Clinically grounded, not black-box** — Risk scoring uses explicit WHO ANC thresholds (e.g., BP ≥160/110 = +30 points). Every AI decision is auditable and returned with reasoning.
- 🛡️ **Safety-bounded by design** — RAG chatbot has query/response safety filters. Doctor AI is non-diagnostic by explicit system prompt. Rule-based fallback scoring at three layers ensures the system never fails silently — even with no LLM key at all.
- 📴 **Offline-first field capture** — the ASHA dashboard is a PWA: assessments taken in no-signal villages are saved on-device (IndexedDB) and sync automatically when connectivity returns, deduplicated server-side (`client_uuid` idempotency) so a replay never double-counts.
- 🔗 **Four stakeholders, one story** — Mother, ASHA, doctor, and admin each see the same pregnancy from the angle they need.

---

## 🔄 How It Works — End-to-End Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│   👩 MOTHER                                                           │
│   Sends voice note on Telegram:                                      │
│   "Mere sar mein bahut dard hai aur aankhon ke samne dhundhla        │
│    dikh raha hai" (severe headache + blurred vision)                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│   🎙️  VOICE LAYER                                                     │
│   Groq Whisper transcribes → LLM extracts symptoms → structured data │
└───────────────────────────────┬──────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│   🧠 LANGGRAPH AGENT WORKFLOW (parallel phases)                       │
│                                                                      │
│              ┌── Risk Stratification ──┐                             │
│  Orchestra── ┼── Symptom Reasoning ────┼──┬── Nutrition ────┬─ Final │
│      tor     ├── Trend Analysis ───────┤  └── Communication ┘  ize   │
│              └── Document Analysis ────┘                             │
│              (phase A: all in parallel)   (phase B: in parallel)     │
│                                                                      │
│   Output: Risk Score 78/100 (HIGH)  •  Flag: Preeclampsia triad      │
│           Tailored messages for mother / ASHA / doctor               │
└───────────────────────────────┬──────────────────────────────────────┘
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
    👩 MOTHER              👩‍⚕️ ASHA                   👨‍⚕️ DOCTOR
    Voice reply in        Dashboard alert:          Dashboard alert:
    simple Hindi:         "Visit Priya within       "HIGH RISK — review
    "Please visit the     4 hours. Check BP,        case. Preeclampsia
    health centre         protein in urine,         suspicion. Consider
    today."               reflexes."                aspirin + referral."

          ASHA visits  →  vitals confirm  →  doctor teleconsults  →
                  mother referred  →  safe delivery
```

### Step-by-step, in plain English

**Step 1 — Mother registers** (once, via Telegram)
She opens the bot, taps `/start`, and answers a short set of fixed, bilingual questions. She can **speak her answers** — the AI does extraction only (the question wording is deterministic, never LLM-generated), handles typos, and confirms before saving. No reading. No typing. No new app to download.

**Step 2 — Mother sends a health update**
She speaks into Telegram at any time: a symptom, a question, "what should I eat today?" — or she uploads a photo of her lab report. The bot understands voice, text, and images.

**Step 3 — AI evaluates**
A LangGraph workflow fans out the independent agents concurrently. The **Risk Stratification Agent** applies WHO-aligned clinical scoring to produce a transparent 0–100 score. The **Symptom Reasoning Agent** looks for clinical clusters (e.g., headache + vision changes + high BP = preeclampsia warning). The **Trend Analysis Agent** examines longitudinal history. Then **Nutrition** and **Communication** (which depend only on the risk result) run as a second parallel phase. The whole graph runs under a hard 120-second budget; on timeout or any failure, a deterministic rule-based scorer takes over so no assessment ever fails silently.

**Step 4 — Alerts route by risk level**

| Risk | Who gets notified | Action |
|------|------------------|--------|
| LOW | Mother only (reassurance + nutrition tip) | — |
| MODERATE | Mother + ASHA | ASHA follow-up visit |
| HIGH | Mother + ASHA + doctor | Doctor review flagged |
| CRITICAL | All three simultaneously | Immediate escalation |

**Step 5 — ASHA worker responds**
She opens her dashboard, sees a color-coded list of assigned mothers sorted by urgency. For each, she can record vitals (BP, Hb, weight, pulse, temperature, glucose), tick through symptoms, upload photos of lab reports, and — when she's unsure — ask the **RAG chatbot** questions in plain English. The chatbot answers from an embedded knowledge base (ASHA Module 6, WHO guidelines, skilled birth attendance protocols) with source citations and a confidence score. **All of this works offline** — captures queue on-device and sync when signal returns.

**Step 6 — Doctor reviews**
The doctor's portal shows a triage list: HIGH-risk cases at the top, with AI-drafted case summaries highlighting abnormal findings, trend observations, and suggested urgency. The **Doctor AI Assistant** — explicitly non-diagnostic — helps the doctor think: "BP is up 18 points since last visit. Consider preeclampsia screening." The doctor then creates a consultation (diagnosis, treatment plan, follow-up), confirms/reschedules appointment requests, and messages the mother via Telegram — all delivered instantly to her phone.

**Step 7 — Admin oversees the system**
Hospital or PHC admins see analytics across every mother, every ASHA, every doctor — assignment load, risk distribution, 7-day risk trends — and can rebalance workloads and onboard new workers.

---

## 👥 What Each User Can Do

### 👩 Mother — via Telegram (voice or text)
- Self-register in her own language using voice
- View health summary with latest vitals and risk level
- Upload lab reports, ultrasound scans, prescriptions (photos/PDFs)
- Receive personalized nutrition advice (time-aware: breakfast/lunch/dinner)
- Book appointments by voice (guided FSM flow with TTS voice prompts)
- Get alerts in simple, non-medical language
- Message her doctor and ASHA worker directly
- Commands: `/start`, `/status`, `/help`, `/profile`, `/cancel`

### 👩‍⚕️ ASHA Worker — Web Dashboard (installable PWA)
- View assigned mothers with color-coded risk indicators
- Digital assessment form (vitals + symptom checklist + notes + photos) with physiological sanity checks (an impossible BP like 87/98 is rejected before it can corrupt a risk score)
- Real-time AI risk scoring the moment the form is submitted
- RAG-powered medical chatbot with source citations, confidence scores, and persistent chat threads
- Notifications inbox: doctor reviews, AI risk alerts, direct messages from mothers
- **Works offline** — install the dashboard as an app; capture assessments with no signal and they sync automatically and idempotently on reconnect

### 👨‍⚕️ Doctor — Web Dashboard
- Triage list sorted by AI-determined urgency
- Full assessment timeline per mother with vitals, symptoms, and AI evaluations
- Document viewer with AI-extracted summaries; can override AI analysis with corrected findings and notify ASHA/mother
- **Doctor AI Assistant**: case analysis, abnormal-findings highlighting, urgency estimation, and free-form chat about a specific patient's history — strictly non-diagnostic
- Consultation form (diagnosis, treatment, follow-up) with automatic Telegram notification to the mother
- Appointment management (confirm / reschedule / cancel, with instant Telegram notification in the mother's language)
- Direct messaging to mothers

### 🛡️ Admin — Web Dashboard
- Manage mothers, ASHA workers, and doctors (registration with bcrypt-hashed credentials)
- Assign workers to mothers (with automatic re-routing of the mother's earlier messages to the new care team)
- System-wide analytics: risk distribution, 8-day risk trend chart, worker performance badges

---

## 🧠 Under the Hood — AI Architecture

### The parallel agent graph

Only one true data dependency exists between agents — nutrition and communication need the risk result. Everything else is independent, so the graph exploits it:

```
                    ┌──────────────────┐
                    │   Orchestrator   │   (deterministic: decides agent list)
                    └────────┬─────────┘
        ┌────────────┬───────┴───────┬──────────────┐
        ▼            ▼               ▼              ▼
┌──────────────┐ ┌───────────┐ ┌───────────┐ ┌────────────┐
│    Risk      │ │  Symptom  │ │   Trend   │ │  Document  │   PHASE A
│Stratification│ │ Reasoning │ │ Analysis  │ │  Analysis  │   (parallel)
│ (WHO rules)  │ │(clusters) │ │(history)  │ │ (uploads)  │
└──────┬───────┘ └─────┬─────┘ └─────┬─────┘ └─────┬──────┘
       └───────────────┴──────┬──────┴──────────────┘
                 ┌────────────┴────────────┐
                 ▼                         ▼
       ┌──────────────────┐     ┌──────────────────┐
       │    Nutrition &   │     │  Communication   │              PHASE B
       │    Lifestyle     │     │ (3 audiences: mo-│              (parallel)
       │                  │     │ ther/ASHA/doctor)│
       └────────┬─────────┘     └────────┬─────────┘
                └───────────┬────────────┘
                            ▼
                    ┌──────────────┐
                    │   Finalize   │   (deterministic aggregation)
                    └──────────────┘
```

**Measured impact** (real requests, per-stage server instrumentation): the sequential graph's time was the *sum* of its LLM calls; the parallel graph's is the *max of each phase*. In one representative run the graph went from summing 26.8s of calls to finishing in 23.0s (= 17.1s phase A max + 5.9s phase B max); in another, two rate-limit-delayed 35s and 67s calls overlapped, saving ~37 seconds of wall time. Full before/after tables live in [`MIGRATION_NOTES.md`](MIGRATION_NOTES.md), raw data in [`baselines/`](baselines/).

Every LLM agent's output is validated against a **Pydantic schema** (risk scores bounded 0–100, confidences 0–1, reasoning with minimum length); a malformed LLM response triggers that agent's deterministic fallback rather than corrupting the pipeline.

### Three layers of safety

**1. Clinical grounding, not vibes.** Risk scoring uses explicit WHO-aligned thresholds:
- DANGER SYMPTOMS (+40 each): bleeding, decreased fetal movement, severe headache, vision changes, convulsions
- SEVERE VITALS (+30 each): BP ≥160/110, Hb <7 g/dL, temp >102°F, glucose >200
- MODERATE (+20 each): BP 140-160/90-110, Hb 7-10 g/dL
- Missing optional vitals are presented to the AI as "Not measured" — never zero, so an absent hemoglobin reading can't masquerade as fatal anemia.

**2. Fallbacks at three depths.** Per-agent try/except fallbacks → a hybrid rescue (if only the risk agent fails, a rule-based scorer fills in just the score) → a full rule-based evaluation (if the whole graph fails or exceeds its 120s budget). Kill the `GROQ_API_KEY` entirely and assessments still return a real, vitals-driven risk score.

**3. RAG with safety filters.** Every ASHA chatbot query passes through:
- Query safety check (blocks dangerous "how do I self-treat" questions)
- Retrieval from ChromaDB (embedded ASHA Module 6, WHO guidelines, SBA protocols — all local, no API)
- Response validation (rejects non-medical or unsafe content)
- Confidence scoring based on retrieval quality and term coverage
- Source citation (every answer links back to its source document)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Web framework** | **FastAPI + uvicorn** (Python 3.11+) — plain `def` endpoints run in FastAPI's threadpool for true request concurrency over the sync data layer |
| **Database** | Supabase **Postgres** via SQLAlchemy Core + psycopg3 (UUID PKs, JSONB for nested/AI blobs, transaction-pooler-safe config) |
| **LLM** | Groq API — model from `LLM_MODEL` env (default `openai/gpt-oss-120b`, an **open-weights model served by Groq** — no OpenAI account) + `llama-3.1-8b-instant` for fast paths |
| **Agent orchestration** | LangGraph (parallel fan-out super-steps) + LangChain |
| **Structured AI output** | Pydantic v2 models validate every agent response |
| **Observability** | LangSmith (optional, free tier) + built-in per-stage latency instrumentation (`PERF_DEBUG=true`) |
| **RAG** | ChromaDB + **local** sentence-transformers embeddings (`all-MiniLM-L6-v2`) — runs on-device, no API key |
| **Voice input (STT)** | Groq Whisper Large V3 (free) |
| **Voice output (TTS)** | Edge-TTS (free, no key) — neural Hindi voices |
| **Messaging** | Telegram Bot API (python-telegram-bot v22, async polling) |
| **Email** | Brevo SMTP (free tier) for doctor appointment emails |
| **Offline field capture** | PWA + service worker + IndexedDB sync queue (ASHA dashboard) |
| **Frontend** | Jinja2 + Vanilla JS + token-based CSS design system (no SPA bloat) |
| **Testing** | pytest (51 tests: risk scoring, auth, bot handlers, repository round-trips, offline-replay idempotency, parallel-graph behavior) + Playwright browser E2E |

> **Security:** passwords are bcrypt-hashed; `SECRET_KEY` is required (the app fails fast without it); all `/admin /asha /doctor /api /ai` data routes are guarded by central middleware (session cookie OR an `X-Internal-Token` for server-to-server calls); `/health` endpoints stay public; uploaded-file serving is path-traversal-guarded.

### Performance (measured, not estimated)

| Metric | Before | After |
|--------|-------:|------:|
| AI graph critical path | 5 sequential LLM calls | **2 parallel phases** |
| Representative assessment request | 102.4s | **30.6s** |
| Throughput at 10 concurrent requests | — (dev server) | **1.71 req/s, p95 flat vs 5 concurrent, 0 errors** |

*(LLM latency varies with Groq free-tier rate limits; the structural win — max-per-phase instead of sum-of-calls — holds on every run. Methodology and honest caveats in [`MIGRATION_NOTES.md`](MIGRATION_NOTES.md).)*

---

## 📁 Repository Map

```
ArogyaMaa-AI/
├── run_fastapi.py             # ▶ START HERE: web app entry (uvicorn, port 8000)
├── run_telegram_bot.py        # ▶ bot entry (polling; also hosts appointment webhook :5050)
├── run.py                     # legacy Flask entry (identical routes; rollback path)
├── app/
│   ├── fastapi_app.py         # FastAPI factory: middleware, sessions, auth guard, errors
│   ├── routers/               # all web routes (one module per domain)
│   │   ├── auth.py            #   login/logout (bcrypt, session cookie)
│   │   ├── asha.py            #   assessments (offline-sync target), stats, uploads, notifications
│   │   ├── doctor.py          #   triage, consultations, appointments, messaging, doc review
│   │   ├── admin.py           #   analytics, user management, assignment
│   │   ├── rag.py             #   ASHA chatbot API (query, threads, safety)
│   │   ├── doctor_ai.py       #   doctor case-analysis assistant API
│   │   └── *_dashboard.py     #   HTML dashboard pages per role
│   ├── ai/
│   │   ├── graph.py           # LangGraph topology (parallel fan-out) + node wrapper
│   │   ├── agents.py          # the 8 agent nodes + Pydantic output schemas
│   │   ├── helpers.py         # state prep + evaluation builder (with hybrid rescue)
│   │   ├── fallback.py        # deterministic rule-based scorer (no-LLM path)
│   │   ├── alerts.py          # risk-routed Telegram alerts (mother/ASHA/doctor)
│   │   ├── registration/      # bot registration engine (deterministic FSM + LLM extraction)
│   │   ├── document_analyzer.py  # lab-report analysis: PDF text → OCR → vision LLM
│   │   └── nutrition_advisor.py  # time-aware nutrition tips
│   ├── rag/                   # ChromaDB retrieval, safety filters, knowledge ingestion
│   ├── repositories/          # ALL database access (SQLAlchemy Core; the only SQL layer)
│   ├── services/              # telegram sender, Brevo email (framework-free)
│   ├── db.py                  # engine, pooling, row mapping (UUID→str, JSONB flattening)
│   ├── instrumentation.py     # per-stage latency timing
│   ├── static/js/             # sw.js (service worker) + offline-queue.js (IndexedDB sync)
│   └── templates/             # Jinja2 pages for all dashboards
├── appointment/               # voice appointment booking: FSM, STT, TTS, email, webhook
├── db/                        # schema.sql + seed.py (demo data)
├── tests/                     # 51 unit/integration tests
├── e2e/                       # Playwright browser tests (offline PWA flow, screenshots)
├── scripts/                   # latency measurement, concurrency probe, parity diff harness
├── baselines/                 # measured before/after performance data (JSON)
└── MIGRATION_NOTES.md         # the full performance story + architecture trade-offs
```

### Environment variables (`.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `SECRET_KEY` | ✅ | Session signing (app refuses to boot without it) |
| `DATABASE_URL` | ✅ | Supabase transaction-pooler URI (`postgresql+psycopg://...:6543/postgres`) or any Postgres |
| `GROQ_API_KEY` | ✅ for AI | The only AI key; without it, rule-based fallbacks take over |
| `TELEGRAM_BOT_TOKEN` | ✅ for bot | From @BotFather |
| `INTERNAL_API_TOKEN` | ✅ | Server-to-server auth header for guarded APIs |
| `LLM_MODEL` / `LLM_MODEL_FAST` / `WHISPER_MODEL` | optional | Model id overrides (swap in one line if Groq rotates a model) |
| `BREVO_SMTP_LOGIN` / `BREVO_SMTP_KEY` / `EMAIL_FROM` / `DOCTOR_EMAIL` | optional | Appointment emails (everything else works without email) |
| `ADMIN_PASSWORD` | optional | Dev-only static admin login (`APP_ENV=development` only) |
| `FASTAPI_PORT` / `WEB_CONCURRENCY` / `PERF_DEBUG` | optional | Port override / uvicorn workers / latency breakdown in responses |

---

## ✅ What's Working — Honest Scope

Every feature listed above is implemented and runs on a **100% free-tier stack** (Supabase + Groq only). The project started as a hackathon build and has been hardened iteratively: the store moved from MongoDB to Supabase Postgres, all voice moved to free Groq Whisper + Edge-TTS, passwords are bcrypt-hashed behind auth-guarded APIs, the ASHA dashboard became an offline-first PWA, and the web core was migrated from Flask to FastAPI with the agent graph parallelized — with byte-level response parity between old and new verified across every endpoint.

### Fully working
- Parallel LangGraph multi-agent workflow (orchestrator + specialist agents, 2-phase critical path)
- 0–100 risk scoring with WHO-aligned thresholds + three-layer rule-based fallback (degrades gracefully even with no LLM key)
- Telegram bot (voice registration, health updates, documents, alerts, messaging, voice appointment booking)
- ASHA dashboard + RAG medical chatbot with safety filters and persistent threads
- **Offline-first ASHA capture** — PWA + IndexedDB queue + idempotent server sync (replay-safe)
- Doctor dashboard + AI case assistant (non-diagnostic) + appointment management
- Admin dashboard + analytics
- Time-aware nutrition advisor
- Document upload + AI analysis pipeline (PDF text → OCR → vision LLM; never invents findings)
- Supabase Postgres persistence, bcrypt auth, centrally-guarded data APIs
- Built-in latency instrumentation + measurement scripts + response-parity harness
- 51-test pytest suite + Playwright browser E2E (offline flow, all-pages screenshot sweep)

---

## 🧭 Known Limitations & Roadmap

An honest defect log — because a healthcare tool earns trust by naming its edges, not hiding them.

### Known limitations (today)
- **Offline scope is the ASHA web dashboard only.** The mother-facing Telegram flow needs internet on the mother's phone. AI risk analysis for an offline-captured assessment runs **server-side on sync** — the risk score appears only after the item syncs.
- **PWA offline shell caches on first online load.** A page must be opened online once before it is available offline.
- **Supabase free tier auto-pauses** after ~7 days idle — open the dashboard once before a demo to wake it.
- **Groq free tier is rate-limited** and rotates models. Model ids are env vars (one-line swap); the rule-based fallback keeps the app working if the LLM is unavailable, and the whole graph runs under a hard 120s budget so a rate-limit storm can never hang a request.
- **Hindi only** — voice works for Hindi; other languages are templated but not active.
- **Document vision** — OCR + LLM text analysis works; deeper multimodal image understanding (ultrasounds, edema photos) is future work.
- **Static dev-admin login** — the admin login is a dev convenience gated behind `APP_ENV=development` + `ADMIN_PASSWORD`; there is no admin user table yet.

### Roadmap — the real vision

**Phase 2 — Reach**
- 📱 **WhatsApp Business API** — WhatsApp is where 500M Indians already are.
- 📞 **SMS + IVR fallback** — for mothers without smartphones; the FastAPI core was chosen specifically so a concurrent call channel can be added. Fallback chain: Telegram → WhatsApp → SMS → automated voice call.
- 🗣️ **Bhashini multilingual** — India's government ASR/TTS platform for 22 Indian languages.

**Phase 3 — Intelligence**
- 📈 **Trajectory prediction** — model BP, Hb, weight over the 40-week curve; flag a preeclampsia-bound BP trajectory at week 24, not week 32.
- 👁️ **Vision-based screening** — multimodal analysis of ultrasound thumbnails, edema photos.
- 💊 **Prescription + referral automation** — integrated with India's ABDM / Ayushman Bharat stack.

**Phase 4 — Scale**
- 🏥 **FHIR / HL7 compliance** for hospital integration
- 📊 **Population-level dashboards** for district health officers
- 🔁 **Zero-gap escalation protocol** — SLA-tracked alert chain (ASHA → doctor → backup doctor → district officer) with automatic tripwire if any link doesn't respond.

---

## 💡 The Impact We're Aiming At

| Metric | Today (India rural) | ArogyaMaa vision |
|--------|---------------------|------------------|
| Early detection of high-risk pregnancies | ~30% | >85% |
| Avg time from danger sign → doctor intervention | 4–12 hours | Under 30 minutes |
| Women excluded by literacy barriers | ~40% | 0% (voice-first) |
| Alert accountability | None | SLA-tracked, auto-escalated |

> **If ArogyaMaa can prevent even 10% of the 23,000 annual maternal deaths in India, that's 2,300 mothers alive at the end of the year.**

---

## 🚀 Running Locally

### Prerequisites
- Python 3.11+
- **ffmpeg** on PATH (voice-note conversion for TTS replies)
- A **Supabase** project (free) — or any Postgres — for `DATABASE_URL`
- Groq API key ([free at groq.com](https://groq.com)) — the only AI key needed
- Telegram Bot token ([via @BotFather](https://t.me/BotFather))
- Brevo SMTP credentials (free at [brevo.com](https://www.brevo.com)) — optional, for appointment emails

### Setup
```bash
git clone https://github.com/AmirKhan024/ArogyaMaa-AI.git
cd ArogyaMaa-AI
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in: SECRET_KEY, DATABASE_URL, GROQ_API_KEY, TELEGRAM_BOT_TOKEN, INTERNAL_API_TOKEN
#          + BREVO_SMTP_LOGIN / BREVO_SMTP_KEY / EMAIL_FROM / DOCTOR_EMAIL for email
#   SECRET_KEY:         python -c "import secrets;print(secrets.token_hex(32))"
#   DATABASE_URL:       postgresql+psycopg://...pooler.supabase.com:6543/postgres  (transaction pooler)
#   INTERNAL_API_TOKEN: any random hex (used for server-to-server API calls)

psql "$DATABASE_URL" -f db/schema.sql     # or paste db/schema.sql into the Supabase SQL editor
python db/seed.py                         # seeds demo doctor/asha/mothers; prints credentials
python -m app.rag.knowledge_ingestion     # build the local RAG vector DB (first run only, ~2 min)

python run_fastapi.py                     # web server (uvicorn) → http://localhost:8000
python run_telegram_bot.py                # Telegram bot (separate terminal)
```

Demo credentials after seeding: `doctor / doctor123`, `asha / asha123` (admin via `ADMIN_PASSWORD` in dev). Dashboards open at `http://localhost:8000`.

**Verify everything:**
```bash
python -m pytest tests/ -q          # 51 tests: units + DB round-trips + parallel-graph suite
python -m pytest e2e/ -q            # browser offline-PWA flow (server must be running)
python e2e/screenshot_pages.py      # renders every dashboard page per role, reports console errors
python scripts/measure_latency.py --port 8000 --label mine   # per-stage AI latency breakdown
python scripts/concurrency_test.py --n 10                    # throughput / p95 probe
```
A guided demo script lives in [`DEMO_CHECKLIST.md`](DEMO_CHECKLIST.md).

### Try the offline ASHA capture
1. Log in as the seeded ASHA (`asha / asha123`) and open **New Assessment**; the header shows an **Online** pill.
2. Open DevTools → **Network → Offline**. The pill flips to **Offline**.
3. Submit an assessment → it is saved on-device and a **"pending sync"** chip appears in the header.
4. Turn the network back **Online** → the queue flushes automatically, the chip clears, and the row appears in Supabase. Submitting the same capture twice still results in exactly **one** row (idempotent on `client_uuid`).
5. The dashboard shell also loads while offline once it has been opened online at least once (service-worker cache).

---

## 📜 Clinical Data Sources

- WHO Antenatal Care Recommendations (2016)
- ICMR National Guidelines for Maternal Health
- NICE Guideline CG107 (Hypertension in Pregnancy)
- ASPRE Trial — Rolnik et al., NEJM 2017 (aspirin for preeclampsia prevention)
- ASHA Module 6 (Government of India)
- Sample Registration System (SRS) Maternal Mortality Bulletin

---

## 🙏 Acknowledgments

Built on the shoulders of the one-million-strong ASHA workforce — the largest community health worker program on Earth — and the open-source AI ecosystem that makes ideas like this possible in a weekend.

---

<div align="center">

### *ArogyaMaa AI — because no mother should die from a complication that was predictable.*

</div>
