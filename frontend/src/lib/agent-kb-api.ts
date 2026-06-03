/**
 * Agent KB API v1 — MCP bearer only (same contract as LangGraph / Claude MCP).
 * Do not use portal JWT on these routes.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL !== undefined
    ? process.env.NEXT_PUBLIC_API_URL
    : "http://localhost:5055";

const LAB_TOKEN_KEY = "arkon_retrieval_lab_token";

export type WikiHit = {
  source_ref: string;
  title: string;
  snippet: string;
  rank: number;
  metadata: {
    slug?: string;
    page_type?: string;
    knowledge_type_slugs?: string[];
    systems?: string[];
    doc_type?: string;
  };
};

export type WikiSearchResponse = {
  query: string;
  hits: WikiHit[];
  debug?: {
    latency_ms: number;
    embedding_spec_id: string | null;
    expanded_query?: string;
    fetch_k?: number;
    filters_applied?: boolean;
    filter_relaxed?: boolean;
    hybrid?: boolean;
    legs?: { vector: number; keyword: number };
    scope_hint?: Record<string, unknown>;
    empty_reason?: string | null;
  };
};

export type WikiReadResponse = {
  slug: string;
  title: string;
  content: string;
  source_ref: string;
  metadata: Record<string, unknown>;
};

export function getLabToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(LAB_TOKEN_KEY) || "";
}

export function setLabToken(token: string) {
  localStorage.setItem(LAB_TOKEN_KEY, token.trim());
}

export function clearLabToken() {
  localStorage.removeItem(LAB_TOKEN_KEY);
}

async function agentKbFetch<T>(
  path: string,
  token: string,
  init?: RequestInit
): Promise<{ data: T; latencyMs: number }> {
  const started = performance.now();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });
  const latencyMs = Math.round(performance.now() - started);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const text = await res.text();
  const data = (text ? JSON.parse(text) : {}) as T;
  return { data, latencyMs };
}

export async function searchWiki(
  token: string,
  params: {
    query: string;
    top_k: number;
    systems?: string;
    doc_type?: string;
    knowledge_type_slugs?: string;
    channel?: string;
    hybrid?: boolean;
    debug?: boolean;
  }
): Promise<{ data: WikiSearchResponse; latencyMs: number }> {
  const qs = new URLSearchParams({
    query: params.query,
    top_k: String(params.top_k),
  });
  if (params.systems) qs.set("systems", params.systems);
  if (params.doc_type) qs.set("doc_type", params.doc_type);
  if (params.knowledge_type_slugs) {
    qs.set("knowledge_type_slugs", params.knowledge_type_slugs);
  }
  if (params.channel) qs.set("channel", params.channel);
  if (params.hybrid) qs.set("hybrid", "true");
  if (params.debug) qs.set("debug", "true");
  return agentKbFetch<WikiSearchResponse>(`/api/v1/wiki/search?${qs}`, token);
}

export async function readWikiPage(
  token: string,
  slug: string
): Promise<{ data: WikiReadResponse; latencyMs: number }> {
  const encoded = encodeURIComponent(slug);
  return agentKbFetch<WikiReadResponse>(`/api/v1/wiki/read/${encoded}`, token);
}

export async function resolveSourceRef(
  token: string,
  sourceRef: string
): Promise<{ data: Record<string, unknown>; latencyMs: number }> {
  const encoded = encodeURIComponent(sourceRef);
  return agentKbFetch<Record<string, unknown>>(
    `/api/v1/source/${encoded}`,
    token
  );
}
