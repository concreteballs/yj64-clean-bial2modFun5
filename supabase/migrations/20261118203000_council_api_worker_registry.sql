-- Track live Council worker instances so API readiness never relies on a static flag alone.
create table if not exists public.yj64_council_api_workers (
  worker_id text primary key check (char_length(worker_id) between 1 and 128),
  status text not null check (status in ('running','stopping')),
  version text not null,
  routes text[] not null default '{}'::text[],
  last_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.yj64_council_api_workers enable row level security;
revoke all on public.yj64_council_api_workers from anon, authenticated;
grant all on public.yj64_council_api_workers to service_role;
create index if not exists yj64_council_api_workers_heartbeat_idx
  on public.yj64_council_api_workers(status, last_seen_at desc);
