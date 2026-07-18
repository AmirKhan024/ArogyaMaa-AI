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
4. Optional but impressive: put YOUR Telegram chat id on the demo doctor/ASHA
   (Admin → Doctor Panel / ASHA Network → the Telegram Chat ID field, get yours from
   @userinfobot) — then risk alerts also arrive on your phone as the "doctor".

## Telegram (needs your phone) — walk this once

Bot: **@arogyamaa_ai_bot**

### Registration (redesigned: ~12 steps, grouped, with progress)
- [ ] `/start` → welcome + menu → **📝 Register**
- [ ] Choose **English** (or हिंदी — everything follows your choice)
- [ ] Each question shows **🌸 Step x/y** progress + arrives as text AND a voice note
- [ ] Answer the grouped questions naturally by voice — e.g. for "tell me about
      yourself": *"Sunita, 15 June 1998, Rampur"* (one answer fills name+DOB+village)
- [ ] For pregnancy dates say just ONE thing (e.g. *"about 10 weeks"*) — EDD and LMP
      are computed automatically
- [ ] Say *"none"* to the medical-background question — all four sub-fields fill as No
- [ ] Try answering by voice AND typing at the same time — the bot politely says
      "One moment 🙏" and NEVER duplicates or skips questions
- [ ] Final **summary card** shows everything → tap **✏️ Something is wrong** → say
      *"my village is Sitapur"* → summary updates → **✅ Yes, I agree**
- [ ] Completion message includes what happens next (no more talking-to-a-wall)

### After registration
- [ ] Admin dashboard → Maternal Portfolio → your name shows **TELEGRAM** badge →
      **Assign** an ASHA + doctor to yourself
- [ ] ASHA/doctor dashboards → patient profile now shows your real answers
      (village, EDD, week, substance use under "Lifestyle & Safety")

### Messages (now two-way)
- [ ] Bot: **💬 Send Message** → type something → reply says "sent to your care team ✅"
- [ ] Doctor dashboard → **Messages** → your message is in the Inbox with a NEW badge →
      **Reply** → it arrives on your phone instantly
- [ ] ASHA dashboard → Notifications → same message with "Message from Mother" badge

### Appointments (full loop)
- [ ] Bot: **📅 Appointment** → **➕ Book new** → answer date/time/symptoms by voice
      (prompts follow your language now)
- [ ] **📅 → 📋 My appointments** → see it as 🟡 Waiting for doctor (+ Cancel button)
- [ ] Doctor dashboard → **Appointments** → Confirm / Reschedule / Cancel from the page →
      your phone gets the notification in your language
- [ ] The email path still works too: check **amirnasirkhan25@gmail.com** for the
      confirm/reschedule email on every new booking
- [ ] After doctor confirms → **📋 My appointments** shows 🟢 Confirmed

### Everything else
- [ ] **📄 Upload Documents** → send a lab-report photo → AI reads and analyzes it →
      appears in Doctor → My Patients → Documents
- [ ] **🩺 Health Summary** → latest assessment + risk (submit one from ASHA first)
- [ ] Type "what should I eat for dinner?" → personalized nutrition advice

## Web (auto-verified, worth showing)

- [ ] ASHA → New Assessment → BP 165/112, HR 108, Hb 6.8 + severe headache →
      **CRITICAL risk with a real score** (try BP 87/98 → politely rejected)
- [ ] **Offline demo:** DevTools → Network → Offline → submit → pending-sync chip →
      back Online → syncs exactly once
- [ ] Doctor → Assessments → **View Full Details** → real dates/vitals/AI reasoning
- [ ] Admin → System Overview → live risk distribution + trend charts
- [ ] ASHA → AI Assistant → ask "danger signs during pregnancy" → cited answer

## If something misbehaves

| Symptom | Fix |
|---|---|
| App won't start | Supabase paused — open dashboard; check `.env` exists |
| AI shows "rule-based" scores | Groq rate limit — normal; the app degrades gracefully |
| Voice replies missing | `ffmpeg -version` must work in the same terminal |
| Bot silent | Only ONE bot instance may run; kill duplicates |
| Model id retired | Swap `LLM_MODEL` in `.env` (console.groq.com/docs/models) |
