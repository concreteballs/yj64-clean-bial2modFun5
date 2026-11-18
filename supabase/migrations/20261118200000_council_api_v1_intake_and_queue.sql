-- Council API v1: isolated request intake, idempotency, audit and worker leasing.
-- No existing YJ64 core queue tables are modified.
create table if not exists public.yj64_council_api_agents (
  agent_id text primary key check (agent_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  scopes text[] not null default array['council:submit','council:read','council:cancel']::text[],
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  last_used_at timestamptz
);
create table if not exists public.yj64_council_api_requests (
  request_id uuid primary key default gen_random_uuid(),
  session_id uuid not null default gen_random_uuid(),
  agent_id text not null references public.yj64_council_api_agents(agent_id),
  correlation_id text not null check (correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 256),
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  protocol_version text not null check (protocol_version = 'yj64.council-api.v1'),
  mode text not null check (mode in ('consensus','critique')),
  task jsonb not null check (jsonb_typeof(task) = 'object'),
  limits jsonb not null check (jsonb_typeof(limits) = 'object'),
  voting jsonb not null check (jsonb_typeof(voting) = 'object'),
  status text not null default 'accepted' check (status in ('accepted','running','completed','blocked','failed','cancelled')),
  progress jsonb not null default '{}'::jsonb check (jsonb_typeof(progress) = 'object'),
  result jsonb,
  error_code text,
  error_message text,
  cancel_requested boolean not null default false,
  worker_id text,
  lease_expires_at timestamptz,
  attempts integer not null default 0 check (attempts >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 20),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (agent_id, idempotency_key),
  check ((status <> 'completed') or (result is not null and jsonb_typeof(result) = 'object'))
);
create index if not exists yj64_council_api_requests_agent_created_idx on public.yj64_council_api_requests(agent_id, created_at desc);
create index if not exists yj64_council_api_requests_worker_claim_idx on public.yj64_council_api_requests(status, lease_expires_at, created_at) where status in ('accepted','running');
create table if not exists public.yj64_council_api_events (
  event_id bigint generated always as identity primary key,
  request_id uuid references public.yj64_council_api_requests(request_id) on delete cascade,
  agent_id text not null,
  event_type text not null,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  created_at timestamptz not null default now()
);
create index if not exists yj64_council_api_events_request_idx on public.yj64_council_api_events(request_id, created_at);
alter table public.yj64_council_api_agents enable row level security;
alter table public.yj64_council_api_requests enable row level security;
alter table public.yj64_council_api_events enable row level security;
revoke all on public.yj64_council_api_agents from anon, authenticated;
revoke all on public.yj64_council_api_requests from anon, authenticated;
revoke all on public.yj64_council_api_events from anon, authenticated;
grant all on public.yj64_council_api_agents to service_role;
grant all on public.yj64_council_api_requests to service_role;
grant all on public.yj64_council_api_events to service_role;
create or replace function public.yj64_claim_council_api_request(p_worker_id text, p_lease_seconds integer default 120)
returns setof public.yj64_council_api_requests
language plpgsql security definer set search_path = public, pg_temp
as $$
begin
  if p_worker_id is null or length(p_worker_id) < 1 or length(p_worker_id) > 128 then raise exception 'invalid_worker_id'; end if;
  if p_lease_seconds < 15 or p_lease_seconds > 900 then raise exception 'invalid_lease_seconds'; end if;
  return query
  with candidate as (
    select request_id from public.yj64_council_api_requests
    where cancel_requested = false and (
      status = 'accepted' or (status = 'running' and lease_expires_at < now() and attempts < max_attempts)
    )
    order by created_at for update skip locked limit 1
  )
  update public.yj64_council_api_requests r
  set status='running', worker_id=p_worker_id,
      lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
      attempts=r.attempts+1, updated_at=now()
  from candidate where r.request_id=candidate.request_id returning r.*;
end;
$$;
revoke all on function public.yj64_claim_council_api_request(text, integer) from public, anon, authenticated;
grant execute on function public.yj64_claim_council_api_request(text, integer) to service_role;
