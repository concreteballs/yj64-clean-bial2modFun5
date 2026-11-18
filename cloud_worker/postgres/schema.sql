-- Standalone PostgreSQL schema for the YJ-64 Council queue.
-- This mirrors the data contract of the Supabase migrations without Supabase roles,
-- RLS policies, PostgREST, or RPC functions. Apply before switching the worker backend.

CREATE TABLE IF NOT EXISTS public.yj64_council_api_agents (
    agent_id text PRIMARY KEY
        CHECK (agent_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    token_hash text NOT NULL UNIQUE
        CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    scopes text[] NOT NULL DEFAULT ARRAY[
        'council:submit', 'council:read', 'council:cancel'
    ]::text[],
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.yj64_council_api_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL DEFAULT gen_random_uuid(),
    agent_id text NOT NULL REFERENCES public.yj64_council_api_agents(agent_id),
    correlation_id text NOT NULL
        CHECK (correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    idempotency_key text NOT NULL
        CHECK (char_length(idempotency_key) BETWEEN 8 AND 256),
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    protocol_version text NOT NULL
        CHECK (protocol_version = 'yj64.council-api.v1'),
    mode text NOT NULL CHECK (mode IN ('consensus', 'critique')),
    task jsonb NOT NULL CHECK (jsonb_typeof(task) = 'object'),
    limits jsonb NOT NULL CHECK (jsonb_typeof(limits) = 'object'),
    voting jsonb NOT NULL CHECK (jsonb_typeof(voting) = 'object'),
    status text NOT NULL DEFAULT 'accepted'
        CHECK (status IN ('accepted', 'running', 'completed', 'blocked', 'failed', 'cancelled')),
    progress jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(progress) = 'object'),
    result jsonb,
    error_code text,
    error_message text,
    cancel_requested boolean NOT NULL DEFAULT false,
    worker_id text,
    lease_expires_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 20),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (agent_id, idempotency_key),
    CHECK (
        status <> 'completed'
        OR (result IS NOT NULL AND jsonb_typeof(result) = 'object')
    )
);

CREATE INDEX IF NOT EXISTS yj64_council_api_requests_agent_created_idx
    ON public.yj64_council_api_requests(agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS yj64_council_api_requests_worker_claim_idx
    ON public.yj64_council_api_requests(status, lease_expires_at, created_at)
    WHERE status IN ('accepted', 'running');

CREATE TABLE IF NOT EXISTS public.yj64_council_api_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid REFERENCES public.yj64_council_api_requests(request_id) ON DELETE CASCADE,
    agent_id text NOT NULL,
    event_type text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(details) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS yj64_council_api_events_request_idx
    ON public.yj64_council_api_events(request_id, created_at);

CREATE TABLE IF NOT EXISTS public.yj64_council_api_workers (
    worker_id text PRIMARY KEY CHECK (char_length(worker_id) BETWEEN 1 AND 128),
    status text NOT NULL CHECK (status IN ('running', 'stopping')),
    version text NOT NULL,
    routes text[] NOT NULL DEFAULT '{}'::text[],
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS yj64_council_api_workers_heartbeat_idx
    ON public.yj64_council_api_workers(status, last_seen_at DESC);
