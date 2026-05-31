create table if not exists research_runs (
  run_id text primary key,
  status text not null default 'queued',
  input jsonb,
  scope_pack jsonb,
  plan jsonb,
  jurisdiction_stack jsonb,
  task_count int not null default 0,
  determinations jsonb,
  report_markdown text,
  trace_events jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists research_evidence (
  run_id text not null references research_runs(run_id) on delete cascade,
  hypothesis_id text not null,
  bundle jsonb not null,
  created_at timestamptz not null default now(),
  primary key (run_id, hypothesis_id)
);

alter table research_runs enable row level security;
alter table research_evidence enable row level security;

-- Read-only access for the public anon role so the UI can subscribe via Realtime.
-- All writes use the service key, which bypasses RLS. (drop-then-create = safe to re-run.)
drop policy if exists "anon read runs" on research_runs;
create policy "anon read runs" on research_runs for select to anon using (true);
drop policy if exists "anon read evidence" on research_evidence;
create policy "anon read evidence" on research_evidence for select to anon using (true);

-- Add to the Realtime publication only if not already a member (safe to re-run).
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'research_runs') then
    alter publication supabase_realtime add table research_runs;
  end if;
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'research_evidence') then
    alter publication supabase_realtime add table research_evidence;
  end if;
end $$;
