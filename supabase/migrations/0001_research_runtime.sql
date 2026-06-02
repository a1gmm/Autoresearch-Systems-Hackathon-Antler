create table if not exists research_runs (
  run_id text primary key,
  status text not null default 'queued',
  attempt int not null default 1,
  input jsonb,
  artifacts jsonb not null default '{}'::jsonb,
  scope_pack jsonb,
  plan jsonb,
  jurisdiction_stack jsonb,
  task_count int not null default 0,
  determinations jsonb,
  verdicts jsonb not null default '[]'::jsonb,
  result jsonb,
  events jsonb not null default '[]'::jsonb,
  status_reason text,
  report_markdown text,
  trace_events jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create table if not exists research_evidence (
  run_id text not null references research_runs(run_id) on delete cascade,
  evidence_id text,
  hypothesis_id text not null,
  bundle jsonb not null,
  created_at timestamptz not null default now(),
  primary key (run_id, evidence_id)
);

alter table research_runs add column if not exists attempt int not null default 1;
alter table research_runs add column if not exists artifacts jsonb not null default '{}'::jsonb;
alter table research_runs add column if not exists verdicts jsonb not null default '[]'::jsonb;
alter table research_runs add column if not exists result jsonb;
alter table research_runs add column if not exists events jsonb not null default '[]'::jsonb;
alter table research_runs add column if not exists status_reason text;

alter table research_evidence add column if not exists evidence_id text;
update research_evidence
set evidence_id = hypothesis_id
where evidence_id is null;
alter table research_evidence alter column evidence_id set not null;
alter table research_evidence drop constraint if exists research_evidence_pkey;
alter table research_evidence add primary key (run_id, evidence_id);

create index if not exists research_evidence_hypothesis_idx
  on research_evidence (run_id, hypothesis_id);

alter table research_runs enable row level security;
alter table research_evidence enable row level security;

-- Read-only access for the public anon role so the UI can subscribe via Realtime.
-- All writes use the service key, which bypasses RLS.
create policy "anon read runs" on research_runs for select to anon using (true);
create policy "anon read evidence" on research_evidence for select to anon using (true);

alter publication supabase_realtime add table research_runs;
alter publication supabase_realtime add table research_evidence;
