-- Round 2: care-team Telegram delivery + appointment linkage/indexes.
-- Idempotent; apply via Supabase SQL editor or psycopg (session pooler :5432).

alter table asha_workers add column if not exists telegram_chat_id text;
alter table doctors      add column if not exists telegram_chat_id text;

alter table appointments add column if not exists mother_id uuid;
alter table appointments add column if not exists preferred_language text;

create index if not exists idx_appointments_chat_id on appointments (telegram_chat_id);
create index if not exists idx_appointments_status  on appointments (status);

-- AI risk alerts become first-class notifications visible in dashboards.
alter table notifications add column if not exists is_alert boolean default false;
alter table notifications add column if not exists alert_type text;
alter table notifications add column if not exists related_assessment_id uuid;
alter table notifications add column if not exists sender_name text;
