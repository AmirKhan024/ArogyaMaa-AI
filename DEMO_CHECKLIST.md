# ArogyaMaa — Demo Checklist

Everything below the "Telegram (needs your phone)" section has already been verified
automatically. The Telegram flows need one manual pass from your phone because a bot
cannot message itself.

## Before the demo (5 minutes)

1. **Wake Supabase** — free projects pause after ~7 days idle. Open
   https://supabase.com/dashboard, open the project, wait for "Active".
2. Start both processes (two terminals, from the repo root):
   ```powershell
   venv\Scripts\python.exe run.py                # web  -> http://localhost:8000
   venv\Scripts\python.exe run_telegram_bot.py   # bot  -> @arogyamaa_ai_bot + webhook :5050
   ```
3. Logins: `admin / admin123`, `doctor / doctor123`, `asha / asha123`.

## Telegram (needs your phone) — walk this once

Bot: **@arogyamaa_ai_bot**

- [ ] `/start` → welcome + 7-button menu appears
- [ ] **📝 Register** → answer the questions; try BOTH typing and voice notes
      (each question also arrives as a voice reply — that's Edge-TTS)
- [ ] Speak one answer in English — transcription should stay English (auto-detect)
- [ ] Finish registration → "Registration Complete" confirmation
- [ ] `/start` again → "Welcome back" (recognized as registered)
- [ ] `/status` → profile summary
- [ ] **🩺 Health Summary** → shows latest assessment (submit one from the ASHA
      dashboard first if empty)
- [ ] **📄 Upload Documents** → then send a photo of any lab report / prescription →
      "Analyzing document..." → success message; it appears in Doctor → Documents
- [ ] **👩‍⚕️ Doctor Messages** → shows messages (send one from Doctor → Send Message first)
- [ ] **💬 Send Message** → type something → shows up in doctor dashboard
- [ ] Type "what should I eat for dinner?" → personalized AI nutrition advice
- [ ] **📅 Appointment** → book by voice (Hindi works best) → date, time, symptoms →
      confirmation message
- [ ] Check **amirnasirkhan25@gmail.com** → doctor email with Confirm / Reschedule buttons
- [ ] Click **Confirm** → success page → your phone gets the Telegram confirmation
- [ ] Book another appointment → click **Reschedule** in the email → pick new date/time →
      phone gets the reschedule notification

> For alerts to reach the mother, her profile must carry YOUR chat id — registering
> via /start from your phone does this automatically.

## Web (already auto-verified, worth showing)

- [ ] Login page → sign in as **asha**
- [ ] New Assessment → pick Anjali Singh → BP 165/112, HR 108, Hb 6.8, symptoms:
      severe headache + vision changes → Submit → **CRITICAL risk score** from the
      LangGraph AI pipeline
- [ ] **Offline demo:** DevTools → Network → Offline → submit another assessment →
      "saved offline" + pending-sync chip → go back Online → watch it sync (idempotent —
      re-syncs never duplicate)
- [ ] AI Assistant (RAG chatbot) → ask "danger signs during pregnancy" → cited answer
- [ ] Login as **doctor** → review the critical assessment, AI Case Assistant → Analyze
- [ ] Login as **admin** → analytics now show the risk distribution + trend

## If something misbehaves

| Symptom | Fix |
|---|---|
| App won't start | Supabase paused — open dashboard; check `.env` exists |
| AI returns "rule-based fallback" | Groq rate limit — wait 60s and retry |
| Voice replies missing | `ffmpeg -version` must work in the same terminal |
| Bot silent | Only ONE bot process may run; kill duplicates |
| Model id retired | Swap `LLM_MODEL` in `.env` (see console.groq.com/docs/models) |
