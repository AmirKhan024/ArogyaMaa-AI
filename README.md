<div align="center">

# ArogyaMaa AI — आरोग्य माँ

### *Voice-First AI for Maternal Healthcare in Rural India*

**Because no mother should die from a complication that was predictable.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=flat&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Supabase](https://img.shields.io/badge/Supabase-Postgres-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C?style=flat)](https://github.com/langchain-ai/langgraph)
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

**ArogyaMaa AI closes all three gaps — with voice, with multi-agent AI, and with a zero-gap escalation protocol.**

---

## ✨ What We Built

**ArogyaMaa AI** is a multi-agent AI platform that connects pregnant mothers in rural India to ASHA workers and doctors through a single Telegram bot and three role-specific dashboards. It listens to mothers in their own voice, reasons about their health using a graph of specialized AI agents grounded in WHO clinical guidelines, and routes every alert to the right person with a tracked response deadline.

**In one sentence:** A mother speaks into Telegram in Hindi → seven AI agents analyze her voice note and vitals in real-time → an ASHA worker gets a prioritized to-do list → a doctor sees a risk-scored dashboard with AI-drafted case notes → nobody falls through the cracks.

### What makes it different

- 🎙️ **Voice-first** — Mothers speak; they don't type. Speech-to-text via Groq Whisper + text-to-speech via Edge-TTS in natural Hindi.
- 🧠 **7 AI agents, not one LLM call** — Orchestrator → Risk Stratification → Symptom Reasoning → Trend Analysis → Nutrition/Lifestyle → Communication → Finalize, all coordinated by LangGraph.
- 📚 **Clinically grounded, not black-box** — Risk scoring uses explicit WHO ANC thresholds (e.g., BP ≥160/110 = +30 points). Every AI decision is auditable.
- 🛡️ **Safety-bounded by design** — RAG chatbot has query/response safety filters. Doctor AI is non-diagnostic by explicit system prompt. Fallback rule-based scoring ensures the system never fails silently.
- 📴 **Offline-first field capture** — the ASHA dashboard is a PWA: assessments taken in no-signal villages are saved on-device (IndexedDB) and sync automatically when connectivity returns, deduplicated server-side so a replay never double-counts.
- 🔗 **Four stakeholders, one story** — Mother, ASHA, doctor, and admin each see the same pregnancy from the angle they need.

---

## 🔄 How It Works — End-to-End Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   👩 MOTHER                                                           │
│   Sends voice note on Telegram:                                      │
│   "Mere sar mein bahut dard hai aur aankhon ke samne dhundhla        │
│    dikh raha hai" (severe headache + blurred vision)                 │
│                                                                      │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│   🎙️  VOICE LAYER                                                     │
│   Groq Whisper transcribes → LLM extracts symptoms → structured data │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│   🧠 LANGGRAPH AGENT WORKFLOW                                         │
│                                                                      │
│   Orchestrator → Risk Stratification → Symptom Reasoning             │
│                      ↓                        ↓                      │
│              Trend Analysis ← Nutrition ← Communication → Finalize   │
│                                                                      │
│   Output: Risk Score 78/100 (HIGH)  •  Flag: Preeclampsia triad      │
│           Tailored messages for mother / ASHA / doctor               │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
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
She opens `@ArogyaMaaBot`, taps `/start`, and answers 15 simple questions. She can **speak her answers** — the AI handles transcription, handles typos, and confirms her identity before saving. No reading. No typing. No downloading a new app.

**Step 2 — Mother sends a health update**
She speaks into Telegram at any time: a symptom, a question, "what should I eat today?" — or she uploads a photo of her lab report. The bot understands voice, text, and images.

**Step 3 — AI evaluates** (under 5 seconds)
A LangGraph workflow fires off up to 7 agents in sequence. The **Risk Stratification Agent** combines WHO-aligned clinical rules (60%), longitudinal trend analysis (30%), and visit compliance (10%) into a transparent 0–100 score. The **Symptom Reasoning Agent** looks for clinical clusters (e.g., headache + vision changes + high BP = preeclampsia warning).

**Step 4 — Alerts route by risk level**

| Risk | Who gets notified | Deadline |
|------|------------------|----------|
| LOW | Mother only (reassurance + nutrition tip) | — |
| MODERATE | Mother + ASHA | ASHA visits within 48 hours |
| HIGH | Mother + ASHA + doctor | Doctor reviews within 4 hours |
| CRITICAL | All three simultaneously | Immediate teleconsultation |

**Step 5 — ASHA worker responds**
She opens her dashboard, sees a color-coded list of assigned mothers sorted by urgency. For each, she can record vitals (BP, Hb, weight, pulse, temperature, glucose, fetal heart rate), tick through 40+ symptoms, upload photos of lab reports, and — when she's unsure — ask the **RAG chatbot** questions in plain English. The chatbot answers from an embedded knowledge base (ASHA Module 6, WHO guidelines, skilled birth attendance protocols) with source citations and a confidence score.

**Step 6 — Doctor reviews**
The doctor opens their portal and sees a triage list: HIGH-risk cases at the top, with AI-drafted case summaries highlighting abnormal findings, trend observations, and suggested urgency. The **Doctor AI Assistant** — explicitly non-diagnostic — helps the doctor think: "BP is up 18 points since last visit. Proteinuria first appeared at week 22. Consider preeclampsia screening." The doctor then creates a consultation (diagnosis, treatment plan, follow-up) and messages the mother via Telegram.

**Step 7 — Admin oversees the system**
Hospital or PHC admins see analytics across every mother, every ASHA, every doctor — assignment load, risk distribution, assessment frequency, and performance metrics. They can rebalance workloads and onboard new workers.

---

## 👥 What Each User Can Do

### 👩 Mother — via Telegram (voice or text)
- Self-register in her own language using voice
- View health summary with latest vitals and risk level
- Upload lab reports, ultrasound scans, prescriptions (photos/PDFs)
- Receive personalized nutrition advice (time-aware: breakfast/lunch/dinner)
- Get alerts in simple, non-medical language
- Message her doctor and ASHA worker directly
- Commands: `/start`, `/status`, `/help`, `/profile`, `/cancel`

### 👩‍⚕️ ASHA Worker — Web Dashboard
- View assigned mothers with color-coded risk indicators
- Digital assessment form (vitals + 40 symptoms + notes + photos)
- Real-time AI risk scoring the moment the form is submitted
- RAG-powered medical chatbot with source citations and confidence scores
- Receive prioritized task list for the day
- Chat history with auto-generated titles
- Message mothers and coordinate with doctors
- **Works offline** — install the dashboard as an app; capture assessments with no signal and they sync automatically on reconnect

### 👨‍⚕️ Doctor — Web Dashboard
- Triage list sorted by AI-determined urgency
- Full assessment timeline per mother with vital-sign graphs (BP, weight, Hb trends)
- Document viewer with AI-extracted summaries
- **Doctor AI Assistant**: case analysis, abnormal-findings highlighting, urgency estimation — strictly non-diagnostic, always labeled as AI-assisted screening
- Consultation form (diagnosis, treatment, referral, follow-up)
- Message mothers and ASHA workers

### 🛡️ Admin — Web Dashboard
- Manage mothers, ASHA workers, and doctors
- Assign (and bulk-assign) workers to mothers
- System-wide analytics: risk distribution, assessment trends, worker performance
- Onboard new users and rebalance workloads

---

## 🧠 Under the Hood — AI Architecture

```
                    ┌─────────────────────────┐
                    │   LangGraph Orchestrator│
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐     ┌──────────────────┐     ┌───────────────┐
│    Risk       │     │     Symptom      │     │    Trend      │
│ Stratification│     │    Reasoning     │     │   Analysis    │
│  (WHO rules)  │     │  (LLM clusters)  │     │ (longitudinal)│
└───────┬───────┘     └─────────┬────────┘     └───────┬───────┘
        └─────────────────┬─────┴──────────────────────┘
                          ▼
             ┌────────────────────────┐
             │ Nutrition & Lifestyle  │
             └────────────┬───────────┘
                          ▼
             ┌────────────────────────┐
             │      Communication     │
             │  (mother/ASHA/doctor)  │
             └────────────┬───────────┘
                          ▼
             ┌────────────────────────┐
             │       Finalize         │
             └────────────────────────┘
```

### Three layers of safety

**1. Clinical grounding, not vibes.** Risk scoring uses explicit WHO-aligned thresholds:
- DANGER SYMPTOMS (+40 each): bleeding, decreased fetal movement, severe headache, vision changes, convulsions
- SEVERE VITALS (+30 each): BP ≥160/110, Hb <7 g/dL, temp >102°F, glucose >200
- MODERATE (+20 each): BP 140-160/90-110, Hb 7-10 g/dL

**2. Rule-based fallback.** If Groq's LLM API fails, the system automatically switches to pure rule-based scoring so no assessment ever silently fails.

**3. RAG with safety filters.** Every ASHA chatbot query passes through:
- Query safety check (blocks dangerous "how do I self-treat" questions)
- Retrieval from ChromaDB (embedded ASHA Module 6, WHO guidelines, SBA protocols)
- Response validation (rejects non-medical or unsafe content)
- Confidence scoring (0-100% based on retrieval quality and term coverage)
- Source citation (every answer links back to its source document)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Flask 3.0 (Python 3.11+) |
| **Database** | Supabase **Postgres** via SQLAlchemy Core + psycopg3 (UUID PKs, JSONB for nested/AI blobs) |
| **LLM** | Groq API — model from `LLM_MODEL` env (default `openai/gpt-oss-120b`, an **open-weights model served by Groq** — no OpenAI account) + `llama-3.1-8b-instant` for fast paths |
| **Agent orchestration** | LangGraph + LangChain |
| **Observability** | LangSmith (optional, free tier) |
| **RAG** | ChromaDB + **local** sentence-transformers embeddings (`all-MiniLM-L6-v2`) — runs on-device, no API key |
| **Voice input (STT)** | Groq Whisper Large V3 (free) |
| **Voice output (TTS)** | Edge-TTS (free, no key) — neural Hindi voices |
| **Messaging** | Telegram Bot API (polling) |
| **Offline field capture** | PWA + service worker + IndexedDB sync queue (ASHA dashboard) |
| **Frontend** | Jinja2 + Vanilla JS + Modern CSS (no SPA bloat) |
| **Appointment booking (bonus module)** | Groq Whisper STT + Edge-TTS + FSM (all free) |

> **Security:** passwords are bcrypt-hashed; `SECRET_KEY` is required (the app fails fast without it); all `/admin /asha /doctor /api /ai` data routes are auth-guarded (session or an `X-Internal-Token` for bot→API calls); `/health` endpoints stay public.

---

## ✅ What's Working — Honest Scope

Every feature listed above is implemented and runs on a **100% free-tier stack** (Supabase + Groq only). The project started as a hackathon build and has since been hardened toward an end-to-end product: the operational store moved from local MongoDB to Supabase Postgres, all voice moved to free Groq Whisper + Edge-TTS, passwords are bcrypt-hashed with auth-guarded APIs, and the ASHA dashboard is now an offline-first PWA.

### Fully working
- LangGraph multi-agent workflow (orchestrator + specialist agents)
- 0–100 risk scoring with WHO-aligned thresholds + rule-based fallback (degrades gracefully if the LLM key is missing or rate-limited)
- Telegram bot (registration, voice, documents, alerts, messaging)
- ASHA dashboard + RAG medical chatbot with safety filters
- **Offline-first ASHA capture** — PWA + IndexedDB queue + idempotent server sync
- Doctor dashboard + AI case assistant (non-diagnostic)
- Admin dashboard + analytics
- Time-aware nutrition advisor
- Document upload + AI analysis pipeline
- Supabase Postgres persistence, bcrypt auth, auth-guarded data APIs
- `pytest` suite (risk scoring, auth, repository round-trips) + Docker/compose

See **[Known Limitations & Roadmap](#-known-limitations--roadmap)** for the honest defect log.

---

## 🧭 Known Limitations & Roadmap

An honest defect log — because a healthcare tool earns trust by naming its edges, not hiding them.

### Known limitations (today)
- **Offline scope is the ASHA web dashboard only.** The mother-facing Telegram flow needs internet on the mother's phone; offline-first targets field capture by ASHA workers, which is where no-signal villages bite. AI risk analysis for an offline-captured assessment runs **server-side on sync**, not on the device — so no AI keys are needed in the field, but the risk score appears only after the item syncs.
- **PWA offline shell caches on first online load.** A page must be opened online once (to be cached by the service worker) before it is available offline; CDN assets (fonts, icons) likewise need one online load.
- **Supabase free tier auto-pauses** after ~7 days idle — open the dashboard once before a demo to wake it.
- **Groq free tier is rate-limited** and rotates models. The model id is an env var (`LLM_MODEL`), so swapping a retired id is a one-line change; the rule-based fallback keeps the app working if the LLM is unavailable.
- **Hindi only** — voice works for Hindi; other languages are templated but not active.
- **Document vision** — OCR + LLM text analysis works; true multimodal image understanding is a stub.
- **Static dev-admin login** — the admin login is a dev convenience gated behind `APP_ENV=development` + `ADMIN_PASSWORD`; there is no admin user table yet.

### Roadmap — the real vision

The real system — the one that could run in every Primary Health Centre in India — looks like this:

### Phase 2 — Reach
- 📱 **WhatsApp Business API integration** — Telegram has growing but limited rural penetration; WhatsApp is where 500M Indians already are.
- 📞 **SMS + IVR fallback** — for mothers without smartphones at all. Twilio-backed fallback chain: Telegram → WhatsApp → SMS → automated voice call.
- 🗣️ **Bhashini multilingual** — India's government ASR/TTS platform for 22 Indian languages: Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, and more.

### Phase 3 — Intelligence
- 📈 **Trajectory prediction** — Model BP, Hb, and weight over the 40-week curve. If a BP trajectory is heading for preeclampsia range by week 32, flag it at week 24.
- 👁️ **Vision-based screening** — multimodal analysis of ultrasound thumbnails, edema photos, skin conditions.
- 💊 **Prescription + referral automation** — auto-generate referral letters and digital prescriptions (integrated with India's ABDM / Ayushman Bharat stack).

### Phase 4 — Scale
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
- Brevo SMTP credentials (free at [brevo.com](https://www.brevo.com)) — for the doctor
  appointment confirm/reschedule emails (optional; everything else works without email)

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
#   INTERNAL_API_TOKEN: any random hex (used for bot → API server-to-server calls)

psql "$DATABASE_URL" -f db/schema.sql     # or paste db/schema.sql into the Supabase SQL editor
python db/seed.py                         # seeds demo doctor/asha/mothers; prints credentials
python -m app.rag.knowledge_ingestion     # build the local RAG vector DB (first run only)

python run.py                           # Flask web server  → http://localhost:8000
python run_telegram_bot.py              # Telegram bot (separate terminal)
```

Demo credentials after seeding: `doctor / doctor123`, `asha / asha123` (admin via `ADMIN_PASSWORD` in dev). Dashboards open at `http://localhost:8000`.

**Verify everything:** `python -m pytest tests/ -q` (unit + DB), `python -m pytest e2e/ -q`
(browser offline-PWA flow, needs the server running), `python scripts/send_test_email.py`
(Brevo smoke). A guided demo script lives in [`DEMO_CHECKLIST.md`](DEMO_CHECKLIST.md).

### Run with Docker
```bash
cp .env.example .env    # fill the same values as above (DB is your Supabase URL)
docker compose up --build
```
This starts two services off one image — `web` (port 8000) and `bot` (appointment webhook on 5050) — both reading `.env`. The database is Supabase (cloud), so no DB container is needed; a commented local-Postgres service is included in `docker-compose.yml` for fully-offline dev.

### Try the offline ASHA capture
1. Log in as the seeded ASHA (`asha / asha123`) and open **New Assessment**; the header shows an **Online** pill.
2. Open DevTools → **Network → Offline** (or Application → Service Workers → check *Offline*). The pill flips to **Offline**.
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
