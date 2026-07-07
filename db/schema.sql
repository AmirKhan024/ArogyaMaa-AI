-- ArogyaMaa-AI — Postgres schema (Supabase-compatible)
-- Run once in the Supabase SQL editor (or: psql "$DATABASE_URL" -f db/schema.sql).
--
-- Design notes:
--   * UUID primary keys (gen_random_uuid via pgcrypto). Repositories alias the PK to a
--     string `_id` for back-compat with the previous MongoDB code.
--   * Nested Mongo sub-documents (vitals, ai_evaluation, performance_stats, medical_history,
--     current_pregnancy, treatment_plan, file_metadata, doctor_review, assigned_mothers[],
--     embedded message arrays, etc.) are stored as JSONB to preserve return shapes.
--   * The `messages` collection was dual-shaped in Mongo, so it is split here into
--     `message_threads` (per-mother chat) and `notifications` (standalone alerts).

create extension if not exists "pgcrypto";

-- ── ASHA workers ───────────────────────────────────────────────────────────────
create table if not exists asha_workers (
  id                uuid primary key default gen_random_uuid(),
  username          text unique,
  password_hash     text,
  name              text,
  phone             text,
  area              text,
  district          text,
  state             text,
  active            boolean default true,
  assigned_mothers  jsonb default '[]'::jsonb,
  performance_stats jsonb default '{}'::jsonb,
  joined_at         timestamptz default now()
);

-- ── Doctors ────────────────────────────────────────────────────────────────────
create table if not exists doctors (
  id                uuid primary key default gen_random_uuid(),
  username          text unique,
  password_hash     text,
  name              text,
  specialization    text,
  phone             text,
  qualification     text,
  hospital          text,
  availability      jsonb default '{}'::jsonb,
  active            boolean default true,
  assigned_mothers  jsonb default '[]'::jsonb,
  performance_stats jsonb default '{}'::jsonb,
  joined_at         timestamptz default now()
);

-- ── Mothers ────────────────────────────────────────────────────────────────────
create table if not exists mothers (
  id                  uuid primary key default gen_random_uuid(),
  telegram_chat_id    text unique,
  telegram_username   text,
  name                text,
  age                 int,
  phone               text,
  risk_level          text,
  assigned_asha_id    uuid references asha_workers(id),
  assigned_doctor_id  uuid references doctors(id),
  medical_history     jsonb default '{}'::jsonb,
  current_pregnancy   jsonb default '{}'::jsonb,
  address             jsonb default '{}'::jsonb,
  extra               jsonb default '{}'::jsonb,   -- registration-finalize + misc fields
  registered_at       timestamptz default now(),
  last_active         timestamptz default now(),
  active              boolean default true
);
create index if not exists idx_mothers_asha   on mothers(assigned_asha_id);
create index if not exists idx_mothers_doctor  on mothers(assigned_doctor_id);

-- ── Assessments (single source of truth for health assessments) ────────────────
create table if not exists assessments (
  id                             uuid primary key default gen_random_uuid(),
  mother_id                      uuid references mothers(id),
  asha_id                        uuid references asha_workers(id),
  vitals                         jsonb default '{}'::jsonb,
  symptoms                       jsonb default '[]'::jsonb,
  asha_notes                     text,
  gestational_age_at_assessment  int,
  assessment_number              int,
  ai_evaluation                  jsonb,
  alerts_sent                    jsonb default '[]'::jsonb,
  documents_uploaded             jsonb default '[]'::jsonb,
  reviewed_by_doctor             boolean default false,
  consultation_id                uuid,
  doctor_reviewed_at             timestamptz,
  client_uuid                    text unique,   -- offline idempotency (Phase 4)
  timestamp                      timestamptz default now()
);
create index if not exists idx_assessments_mother on assessments(mother_id);
create index if not exists idx_assessments_asha   on assessments(asha_id);

-- ── Consultations (doctor's authoritative input) ───────────────────────────────
create table if not exists consultations (
  id                     uuid primary key default gen_random_uuid(),
  assessment_id          uuid references assessments(id),
  mother_id              uuid references mothers(id),
  doctor_id              uuid references doctors(id),
  diagnosis              text,
  clinical_observations  text,
  updated_vitals         jsonb default '{}'::jsonb,
  treatment_plan         jsonb default '{}'::jsonb,
  next_visit_date        timestamptz,
  overrides_ai_assessment boolean default false,
  doctor_risk_assessment text,
  override_reason        text,
  consultation_notes     text,
  message_sent_to_mother text,
  message_sent_at        timestamptz,
  consultation_date      timestamptz default now()
);
create index if not exists idx_consultations_mother on consultations(mother_id);
create index if not exists idx_consultations_doctor on consultations(doctor_id);

-- ── Documents (lab reports, scans, prescriptions) ──────────────────────────────
create table if not exists documents (
  id                   uuid primary key default gen_random_uuid(),
  mother_id            uuid references mothers(id),
  uploaded_by          text,
  uploaded_by_id       uuid,
  document_type        text,
  file_metadata        jsonb default '{}'::jsonb,
  telegram_file_id     text,
  extracted_text       text,
  ai_analysis          jsonb,
  linked_to_assessment uuid,
  visible_to           jsonb default '["mother","asha","doctor","admin"]'::jsonb,
  doctor_review        jsonb,
  uploaded_at          timestamptz default now()
);
create index if not exists idx_documents_mother on documents(mother_id);

-- ── Message threads (per-mother chat history) ──────────────────────────────────
create table if not exists message_threads (
  id               uuid primary key default gen_random_uuid(),
  mother_id        uuid unique references mothers(id),
  messages         jsonb default '[]'::jsonb,
  created_at       timestamptz default now(),
  last_message_at  timestamptz default now(),
  total_messages   int default 0
);

-- ── Notifications (standalone alerts to ASHA / doctor) ─────────────────────────
create table if not exists notifications (
  id                uuid primary key default gen_random_uuid(),
  mother_id         uuid,
  mother_name       text,
  telegram_chat_id  text,
  to_asha_id        uuid,
  to_doctor_id      uuid,
  message_type      text,
  content           text,
  message           text,
  subject           text,
  read              boolean default false,
  from_doctor       boolean default false,
  doctor_name       text,
  document_id       uuid,
  timestamp         timestamptz default now()
);
create index if not exists idx_notifications_asha   on notifications(to_asha_id);
create index if not exists idx_notifications_doctor on notifications(to_doctor_id);

-- ── Registration sessions (in-progress Telegram registration) ──────────────────
create table if not exists registration_sessions (
  id                uuid primary key default gen_random_uuid(),
  telegram_chat_id  text unique,
  data              jsonb default '{}'::jsonb,
  updated_at        timestamptz default now()
);

-- ── RAG chat threads (ASHA medical chatbot history) ────────────────────────────
create table if not exists rag_chat_threads (
  id          uuid primary key default gen_random_uuid(),
  asha_id     text,
  title       text,
  messages    jsonb default '[]'::jsonb,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);
create index if not exists idx_rag_threads_asha on rag_chat_threads(asha_id);

-- ── Appointments (was Excel-backed) ────────────────────────────────────────────
create table if not exists appointments (
  id                uuid primary key default gen_random_uuid(),
  appointment_id    text unique,
  security_token    text,
  patient_name      text,
  patient_age       text,
  patient_phone     text,
  telegram_chat_id  text,
  preferred_date    text,
  preferred_time    text,
  symptoms          text,
  status            text default 'Pending',
  confirmed_date    text,
  confirmed_time    text,
  doctor_notes      text,
  created_at        text,
  updated_at        text
);
