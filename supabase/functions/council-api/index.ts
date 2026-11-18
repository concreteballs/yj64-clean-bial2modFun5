import { createClient } from "npm:@supabase/supabase-js@2.58.0";

const VERSION = "yj64.council-api.v1";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_KEY =
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ??
  (() => {
    try {
      return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}").default ?? "";
    } catch {
      return "";
    }
  })();

const db = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

const sha256 = async (value: string) => {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
};

const stable = (value: unknown): string => {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return "{" + Object.keys(obj).sort().map((k) => JSON.stringify(k) + ":" + stable(obj[k])).join(",") + "}";
  }
  return JSON.stringify(value);
};

const validId = (v: unknown) =>
  typeof v === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(v);

const validRequest = (v: any): string | null => {
  if (!v || typeof v !== "object" || Array.isArray(v)) return "body_must_be_object";
  const allowed = ["protocol_version", "agent_id", "correlation_id", "idempotency_key", "mode", "task", "limits", "voting"];
  if (Object.keys(v).some((k) => !allowed.includes(k))) return "unknown_request_field";
  if (v.protocol_version !== VERSION) return "invalid_protocol_version";
  if (!validId(v.agent_id) || !validId(v.correlation_id)) return "invalid_identifier";
  if (typeof v.idempotency_key !== "string" || v.idempotency_key.length < 8 || v.idempotency_key.length > 256) return "invalid_idempotency_key";
  if (!["consensus", "critique"].includes(v.mode)) return "invalid_mode";
  if (!v.task || typeof v.task !== "object" || Array.isArray(v.task)) return "invalid_task";
  if (Object.keys(v.task).some((k) => !["title", "prompt", "context", "evidence_refs"].includes(k))) return "unknown_task_field";
  if (typeof v.task.title !== "string" || v.task.title.length < 1 || v.task.title.length > 500) return "invalid_task_title";
  if (typeof v.task.prompt !== "string" || v.task.prompt.length < 1 || v.task.prompt.length > 50000) return "invalid_task_prompt";
  if (!v.task.context || typeof v.task.context !== "object" || Array.isArray(v.task.context)) return "invalid_task_context";
  if (!Array.isArray(v.task.evidence_refs) || v.task.evidence_refs.length > 100 || v.task.evidence_refs.some((x: unknown) => typeof x !== "string" || x.length < 1 || x.length > 2048)) return "invalid_evidence_refs";
  if (!v.limits || typeof v.limits !== "object" || Array.isArray(v.limits)) return "invalid_limits";
  if (Object.keys(v.limits).some((k) => !["max_rounds", "timeout_seconds", "max_output_tokens", "minimum_critique_rounds", "allow_early_stop"].includes(k))) return "unknown_limits_field";
  const n = v.limits;
  if (!Number.isInteger(n.max_rounds) || n.max_rounds < 1 || n.max_rounds > 10) return "invalid_max_rounds";
  if (!Number.isInteger(n.timeout_seconds) || n.timeout_seconds < 30 || n.timeout_seconds > 86400) return "invalid_timeout_seconds";
  if (!Number.isInteger(n.max_output_tokens) || n.max_output_tokens < 256 || n.max_output_tokens > 100000) return "invalid_max_output_tokens";
  if (n.minimum_critique_rounds !== 1 || typeof n.allow_early_stop !== "boolean") return "invalid_critique_limits";
  if (!v.voting || typeof v.voting !== "object" || Array.isArray(v.voting) ||
      Object.keys(v.voting).some((k) => !["enabled", "weighted"].includes(k)) ||
      typeof v.voting.enabled !== "boolean" || typeof v.voting.weighted !== "boolean") return "invalid_voting";
  return null;
};

const privateField = /^(individual_votes|ballots|private_ratings|competence_scores)$/i;
const hasPrivateFields = (v: any, depth = 0): boolean => {
  if (depth > 16) return true;
  if (Array.isArray(v)) return v.some((x) => hasPrivateFields(x, depth + 1));
  if (v && typeof v === "object") return Object.entries(v).some(([k, x]) => privateField.test(k) || hasPrivateFields(x, depth + 1));
  return false;
};

async function authenticate(req: Request, requiredScope: string) {
  const auth = req.headers.get("authorization") ?? "";
  const match = auth.match(/^Bearer ([^\s]{16,4096})$/);
  if (!match) return { error: json({ error: "unauthorized" }, 401) } as const;
  const tokenHash = await sha256(match[1]);
  const { data, error } = await db.from("yj64_council_api_agents")
    .select("agent_id,scopes,enabled")
    .eq("token_hash", tokenHash)
    .eq("enabled", true)
    .maybeSingle();
  if (error || !data || !Array.isArray(data.scopes) || !data.scopes.includes(requiredScope)) {
    return { error: json({ error: "unauthorized_or_scope_missing" }, 401) } as const;
  }
  await db.from("yj64_council_api_agents").update({ last_used_at: new Date().toISOString() }).eq("agent_id", data.agent_id);
  return { agent: data } as const;
}

async function recordEvent(requestId: string, agentId: string, eventType: string, details: Record<string, unknown> = {}) {
  await db.from("yj64_council_api_events").insert({
    request_id: requestId, agent_id: agentId, event_type: eventType, details,
  });
}

function statusPayload(row: any) {
  return {
    protocol_version: VERSION,
    request_id: row.request_id,
    session_id: row.session_id,
    status: row.status,
    ...(row.progress && Object.keys(row.progress).length ? { progress: row.progress } : {}),
    updated_at: row.updated_at,
  };
}

Deno.serve(async (req: Request) => {
  if (!SUPABASE_URL || !SUPABASE_KEY) return json({ error: "server_configuration_missing" }, 503);
  const url = new URL(req.url);
  let path = url.pathname;
  const marker = "/functions/v1/council-api";
  const markerIndex = path.indexOf(marker);
  if (markerIndex >= 0) path = path.slice(markerIndex + marker.length) || "/";
  if (req.method === "GET" && path === "/health") {
    const { error } = await db.from("yj64_council_api_requests").select("request_id").limit(1);
    if (error) return json({ status: "degraded", api: "up", database: "unavailable", council_engine: "not_connected", ready_for_requests: false }, 503);
    return json({ status: "ok", api: "up", database: "up", council_engine: "not_connected", worker: "not_deployed", ready_for_requests: false });
  }

  const versionHeader = req.headers.get("x-yj64-protocol-version");
  if (versionHeader !== VERSION) return json({ error: "unsupported_protocol_version" }, 400);

  const submitPath = "/api/v1/external-agents/council/requests";
  if (req.method === "POST" && path === submitPath) {
    if (Deno.env.get("YJ64_COUNCIL_WORKER_ENABLED") !== "true" ||
        Deno.env.get("YJ64_COUNCIL_ENGINE_ADAPTER") !== "ready") {
      return json({ error: "council_engine_not_ready", message: "Request intake is disabled until the real Council worker and server-side engine adapter are deployed." }, 503);
    }
    const auth = await authenticate(req, "council:submit");
    if ("error" in auth) return auth.error;
    const length = Number(req.headers.get("content-length") ?? "0");
    if (length > 128 * 1024) return json({ error: "payload_too_large" }, 413);
    let body: any;
    try { body = await req.json(); } catch { return json({ error: "invalid_json" }, 400); }
    const validation = validRequest(body);
    if (validation) return json({ error: "invalid_request", message: validation }, 400);
    if (new TextEncoder().encode(JSON.stringify(body)).length > 128 * 1024) return json({ error: "payload_too_large" }, 413);
    if (body.agent_id !== auth.agent.agent_id) return json({ error: "agent_identity_mismatch" }, 403);
    const idemHeader = req.headers.get("idempotency-key");
    if (!idemHeader || idemHeader !== body.idempotency_key) return json({ error: "idempotency_header_mismatch" }, 400);
    const requestHash = await sha256(stable(body));
    const { data: existing } = await db.from("yj64_council_api_requests").select("*")
      .eq("agent_id", auth.agent.agent_id).eq("idempotency_key", body.idempotency_key).maybeSingle();
    if (existing) {
      if (existing.request_hash !== requestHash) return json({ error: "idempotency_conflict" }, 409);
      if (!["accepted", "running"].includes(existing.status)) {
        return json({ error: "idempotency_replay_terminal", request_id: existing.request_id, status: existing.status }, 409);
      }
      return json({ protocol_version: VERSION, request_id: existing.request_id, session_id: existing.session_id, status: existing.status }, 202);
    }
    const { data, error } = await db.from("yj64_council_api_requests").insert({
      agent_id: auth.agent.agent_id,
      correlation_id: body.correlation_id,
      idempotency_key: body.idempotency_key,
      request_hash: requestHash,
      protocol_version: VERSION,
      mode: body.mode,
      task: body.task,
      limits: body.limits,
      voting: body.voting,
      status: "accepted",
    }).select("request_id,session_id,status").single();
    if (error || !data) {
      if (error?.code === "23505") return json({ error: "idempotency_race_retry" }, 409);
      return json({ error: "request_persistence_failed" }, 503);
    }
    await recordEvent(data.request_id, auth.agent.agent_id, "request_accepted", { correlation_id: body.correlation_id, mode: body.mode });
    return json({ protocol_version: VERSION, request_id: data.request_id, session_id: data.session_id, status: "accepted" }, 202);
  }

  const match = path.match(/^\/api\/v1\/external-agents\/council\/requests\/([0-9a-f-]{36})(\/result|\/cancel)?$/i);
  if (!match) return json({ error: "not_found" }, 404);
  const requestId = match[1];
  const suffix = match[2] ?? "";
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) return json({ error: "invalid_request_id" }, 400);

  if (req.method === "GET" && suffix === "") {
    const auth = await authenticate(req, "council:read");
    if ("error" in auth) return auth.error;
    const { data, error } = await db.from("yj64_council_api_requests").select("*").eq("request_id", requestId).eq("agent_id", auth.agent.agent_id).maybeSingle();
    if (error || !data) return json({ error: "not_found" }, 404);
    return json(statusPayload(data));
  }

  if (req.method === "GET" && suffix === "/result") {
    const auth = await authenticate(req, "council:read");
    if ("error" in auth) return auth.error;
    const { data, error } = await db.from("yj64_council_api_requests").select("*").eq("request_id", requestId).eq("agent_id", auth.agent.agent_id).maybeSingle();
    if (error || !data) return json({ error: "not_found" }, 404);
    if (data.status === "completed" && data.result) {
      const result = data.result;
      const requiredArrays = ["claims", "participant_positions", "dissent", "evidence", "unresolved_questions"];
      const valid = result.protocol_version === VERSION &&
        result.request_id === data.request_id && result.session_id === data.session_id &&
        result.status === "completed" &&
        ["consensus", "qualified_consensus", "unresolved_disagreement", "insufficient_evidence"].includes(result.outcome) &&
        typeof result.summary === "string" && result.summary.length > 0 && result.summary.length <= 50000 &&
        requiredArrays.every((key) => Array.isArray(result[key])) && !hasPrivateFields(result);
      if (!valid) return json({ error: "stored_council_result_failed_validation" }, 500);
      return json(result);
    }
    if (["blocked", "failed", "cancelled"].includes(data.status)) return json({ error: data.status, message: data.error_message ?? "Council request ended without a result" }, 409);
    return json(statusPayload(data), 202);
  }

  if (req.method === "POST" && suffix === "/cancel") {
    const auth = await authenticate(req, "council:cancel");
    if ("error" in auth) return auth.error;
    let body: any;
    try { body = await req.json(); } catch { return json({ error: "invalid_json" }, 400); }
    if (!body || body.protocol_version !== VERSION || body.agent_id !== auth.agent.agent_id || Object.keys(body).some((k) => !["protocol_version", "agent_id"].includes(k))) {
      return json({ error: "invalid_cancel_request" }, 400);
    }
    const { data: current } = await db.from("yj64_council_api_requests").select("request_id,agent_id,status")
      .eq("request_id", requestId).eq("agent_id", auth.agent.agent_id).maybeSingle();
    if (!current) return json({ error: "not_found" }, 404);
    if (["completed", "blocked", "failed", "cancelled"].includes(current.status)) {
      return json({ protocol_version: VERSION, request_id: requestId, status: current.status });
    }
    const { data: updated } = await db.from("yj64_council_api_requests")
      .update({ status: "cancelled", cancel_requested: true, completed_at: new Date().toISOString(), updated_at: new Date().toISOString(), lease_expires_at: null })
      .eq("request_id", requestId).eq("agent_id", auth.agent.agent_id).in("status", ["accepted", "running"])
      .select("status").maybeSingle();
    if (updated) {
      await recordEvent(requestId, auth.agent.agent_id, "request_cancelled", {});
      return json({ protocol_version: VERSION, request_id: requestId, status: "cancelled" });
    }
    const { data: after } = await db.from("yj64_council_api_requests").select("status")
      .eq("request_id", requestId).eq("agent_id", auth.agent.agent_id).maybeSingle();
    if (!after || !["completed", "blocked", "failed", "cancelled"].includes(after.status)) return json({ error: "cancel_state_race_retry" }, 409);
    return json({ protocol_version: VERSION, request_id: requestId, status: after.status });
  }

  return json({ error: "method_not_allowed" }, 405);
});
