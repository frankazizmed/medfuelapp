-- MedFuel Supabase / Postgres production hardening
-- =================================================
--
-- This file documents the row-level security and audit posture intended for
-- production deployments. It is not executed automatically; run it after
-- migrating the SQLAlchemy schema onto a Postgres target and confirming
-- column names match the ORM definitions in src/medfuel/db/orm.py.
--
-- Assumptions
--   - One Supabase project per environment.
--   - Application traffic comes through a service role connection that bypasses
--     RLS; interactive Studio / dashboard users authenticate via auth.uid().
--   - All write paths still emit audit_events rows from the application layer.
--
-- After applying, verify with:
--   select schemaname, tablename, rowsecurity
--   from pg_tables where schemaname='public' order by tablename;

-- ----- Required extensions --------------------------------------------------
create extension if not exists pgcrypto;
-- pgvector becomes relevant once Phase 4 introduces embeddings; safe to enable
-- early since the SQLAlchemy schema does not reference it yet.
-- create extension if not exists vector;

-- ----- Enable RLS on every application table -------------------------------
alter table if exists companies            enable row level security;
alter table if exists jobs                 enable row level security;
alter table if exists source_documents     enable row level security;
alter table if exists assets               enable row level security;
alter table if exists extractions          enable row level security;
alter table if exists regulatory_events    enable row level security;
alter table if exists claims               enable row level security;
alter table if exists citations            enable row level security;
alter table if exists report_runs          enable row level security;
alter table if exists audit_events         enable row level security;

-- ----- Service-role bypass policy template ---------------------------------
-- Application backend connects with the service role (which bypasses RLS by
-- default in Supabase). Interactive (anon / authenticated) users get
-- read-only access scoped to the authenticated user's organization via a
-- helper function. Adjust to your tenancy model.

create or replace function public.current_org_id() returns text
language sql stable as $$
  select coalesce(
    (auth.jwt() ->> 'org_id')::text,
    'public'
  );
$$;

-- Example: read access to report runs for the org that ran them.
-- (Requires adding org_id columns to your tables as part of multi-tenancy
-- rollout — left here as a template, not enabled by default.)
--
-- create policy "report_runs_read_own_org"
--   on report_runs for select
--   using (org_id = public.current_org_id());

-- ----- Audit insert policy --------------------------------------------------
-- audit_events should be append-only. Block update/delete even for the
-- service role.

create policy "audit_events_insert_only"
  on audit_events for insert with check (true);

create policy "audit_events_no_update"
  on audit_events for update using (false);

create policy "audit_events_no_delete"
  on audit_events for delete using (false);

-- ----- Storage hardening ----------------------------------------------------
-- Force SSL for client connections (settings change, not RLS).
-- alter database <your_db> set ssl = on;

-- ----- Useful indexes for hot read paths -----------------------------------
create index if not exists ix_source_documents_company_source
  on source_documents (company_id, source_type);
create index if not exists ix_claims_event_signal
  on claims (event_id, signal_score desc);
create index if not exists ix_events_company_type_date
  on regulatory_events (company_id, event_type, event_date desc);

-- ----- Audit trail constraints ----------------------------------------------
-- Defense-in-depth: prevent accidental backfilling of audit timestamps.
alter table if exists audit_events
  alter column at set default now();

-- ----- Notes ----------------------------------------------------------------
-- 1. The application's DocumentRegistry already emits audit rows for every
--    insert / duplicate-skip / job-status transition. RLS does not replace
--    those; they are the primary audit surface and remain authoritative.
-- 2. For HIPAA scope, route any PHI-bearing uploads through a redaction step
--    BEFORE persistence — RLS protects access, not data minimization.
-- 3. The pgvector enable is left commented; uncomment once Phase 4 wires the
--    embedding pipeline. See src/medfuel/db/orm.py for the future
--    DocumentChunkRow table.
