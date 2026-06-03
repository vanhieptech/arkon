"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { WikiPageSummary } from "@/types/wiki";
import {
  clearLabToken,
  getLabToken,
  readWikiPage,
  resolveSourceRef,
  searchWiki,
  setLabToken,
  type WikiHit,
  type WikiSearchResponse,
} from "@/lib/agent-kb-api";

const SAMPLE_QUERIES = [
  { label: "T24 core banking", query: "T24 core banking runbook rollback" },
  { label: "Payment integration", query: "payment gateway integration API FSD" },
  { label: "DWH cross-system", query: "DWH data warehouse payment T24 lineage" },
  { label: "CR policy gate", query: "change request policy rollout checklist" },
  { label: "Incident history", query: "payment incident postmortem residual risk" },
];

export default function RetrievalLabPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [query, setQuery] = React.useState("");
  const [topK, setTopK] = React.useState(10);
  const [channel, setChannel] = React.useState("");
  const [systems, setSystems] = React.useState("");
  const [docType, setDocType] = React.useState("");
  const [hybrid, setHybrid] = React.useState(false);
  const [useSavedToken, setUseSavedToken] = React.useState(true);
  const [tokenInput, setTokenInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<WikiSearchResponse | null>(null);
  const [clientLatencyMs, setClientLatencyMs] = React.useState<number | null>(null);
  const [readPayload, setReadPayload] = React.useState<string | null>(null);
  const [sourcePayload, setSourcePayload] = React.useState<string | null>(null);

  const [portalPages, setPortalPages] = React.useState<WikiPageSummary[]>([]);

  React.useEffect(() => {
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, router]);

  React.useEffect(() => {
    const saved = getLabToken();
    if (saved) setTokenInput(saved);
    api<WikiPageSummary[]>("/api/wiki/pages?limit=300")
      .then((d) => setPortalPages(Array.isArray(d) ? d : []))
      .catch(() => setPortalPages([]));
  }, []);

  const effectiveToken = useSavedToken ? getLabToken() : tokenInput.trim();

  const keywordHits = React.useMemo(() => {
    if (!query.trim()) return [];
    const q = query.toLowerCase();
    return portalPages
      .filter(
        (p) =>
          p.page_type !== "index" &&
          p.page_type !== "log" &&
          (p.title.toLowerCase().includes(q) ||
            p.slug.toLowerCase().includes(q) ||
            (p.summary || "").toLowerCase().includes(q))
      )
      .slice(0, topK);
  }, [portalPages, query, topK]);

  const runSearch = async () => {
    if (!effectiveToken) {
      setError("Paste or save an MCP bearer token (Profile → MCP Token).");
      return;
    }
    if (!query.trim()) {
      setError("Enter a search query.");
      return;
    }
    setLoading(true);
    setError(null);
    setReadPayload(null);
    setSourcePayload(null);
    try {
      const { data, latencyMs } = await searchWiki(effectiveToken, {
        query: query.trim(),
        top_k: topK,
        systems: systems.trim() || undefined,
        doc_type: docType.trim() || undefined,
        channel: channel.trim() || undefined,
        hybrid,
        debug: true,
      });
      setResult(data);
      setClientLatencyMs(latencyMs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveToken = () => {
    if (!tokenInput.trim()) return;
    setLabToken(tokenInput.trim());
    setUseSavedToken(true);
  };

  if (!user || user.role !== "admin") {
    return (
      <div className="flex items-center justify-center py-16">
        <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
          progress_activity
        </span>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Agent Retrieval Lab"
        description="Test semantic wiki search with the same /api/v1 contract as LangGraph agents and Claude MCP."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="query">Query</Label>
            <Input
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. T24 payment integration"
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {SAMPLE_QUERIES.map((s) => (
              <Button
                key={s.label}
                variant="outline"
                size="sm"
                type="button"
                onClick={() => setQuery(s.query)}
              >
                {s.label}
              </Button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="topk">top_k (1–50)</Label>
              <Input
                id="topk"
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value) || 5)}
              />
            </div>
            <div>
              <Label htmlFor="channel">Channel</Label>
              <select
                id="channel"
                className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
              >
                <option value="">—</option>
                <option value="policy">policy</option>
                <option value="arch">arch</option>
                <option value="incident">incident</option>
              </select>
            </div>
            <div>
              <Label htmlFor="systems">systems (comma)</Label>
              <Input
                id="systems"
                value={systems}
                onChange={(e) => setSystems(e.target.value)}
                placeholder="t24,payment"
              />
            </div>
            <div>
              <Label htmlFor="doctype">doc_type</Label>
              <Input
                id="doctype"
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                placeholder="Policy"
              />
            </div>
            <div className="col-span-2 flex items-center gap-2">
              <input
                id="hybrid"
                type="checkbox"
                checked={hybrid}
                onChange={(e) => setHybrid(e.target.checked)}
                className="rounded border-input"
              />
              <Label htmlFor="hybrid" className="cursor-pointer font-normal">
                hybrid=1 (RRF vector + keyword)
              </Label>
            </div>
          </div>

          <div className="border rounded-lg p-3 flex flex-col gap-2 bg-muted/30">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                MCP bearer token
              </Label>
              <div className="flex items-center gap-2 text-xs">
                <span>Use saved</span>
                <Switch checked={useSavedToken} onCheckedChange={setUseSavedToken} />
              </div>
            </div>
            <Input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="ark_…"
            />
            <div className="flex gap-2">
              <Button variant="outline" size="sm" type="button" onClick={handleSaveToken}>
                Save token
              </Button>
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => {
                  clearLabToken();
                  setTokenInput("");
                }}
              >
                Clear saved
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Uses <code className="text-xs">Authorization: Bearer</code> on{" "}
              <code className="text-xs">/api/v1/wiki/search</code> — not portal JWT.
              Generate at Profile → MCP Token.
            </p>
          </div>

          <Button onClick={runSearch} disabled={loading}>
            {loading ? "Searching…" : "Run agent search"}
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </Card>

        <Card className="p-4 flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Debug</h3>
          {result?.debug ? (
            <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-auto max-h-48">
              {JSON.stringify(
                {
                  ...result.debug,
                  client_latency_ms: clientLatencyMs,
                },
                null,
                2
              )}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground">Run a search to see debug metadata.</p>
          )}
          {result?.debug?.empty_reason === "embedding_not_configured" && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
              Embedding provider not configured — configure in Settings → Embedding.
            </p>
          )}
          {result && (result.hits?.length ?? 0) === 0 && result.debug?.scope_hint && (
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">
              Few or no hits may mean your MCP token scope is limited — try a service admin
              token or request access to the listed knowledge types / departments.
            </p>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2 mt-6">
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Agent semantic hits</h3>
            <Badge variant="secondary">{result?.hits?.length ?? 0}</Badge>
          </div>
          {!result?.hits?.length && result && (
            <p className="text-sm text-muted-foreground">No hits in token scope.</p>
          )}
          <ul className="space-y-3">
            {(result?.hits || []).map((hit: WikiHit) => (
              <li key={hit.source_ref} className="border rounded-lg p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">{hit.title}</p>
                    <p className="text-xs text-muted-foreground font-mono">{hit.source_ref}</p>
                  </div>
                  <Badge>{hit.rank}</Badge>
                </div>
                <p className="text-xs mt-2 text-muted-foreground line-clamp-3">{hit.snippet}</p>
                <pre className="text-[10px] mt-2 bg-muted/40 rounded p-2 overflow-auto">
                  {JSON.stringify(hit.metadata, null, 2)}
                </pre>
                <div className="flex gap-2 mt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    type="button"
                    onClick={async () => {
                      const slug = hit.metadata?.slug;
                      if (!slug || !effectiveToken) return;
                      try {
                        const { data } = await readWikiPage(effectiveToken, slug);
                        setReadPayload(JSON.stringify(data, null, 2));
                      } catch (e) {
                        setReadPayload(String(e));
                      }
                    }}
                  >
                    Read full page
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    onClick={async () => {
                      if (!effectiveToken) return;
                      try {
                        const { data } = await resolveSourceRef(
                          effectiveToken,
                          hit.source_ref
                        );
                        setSourcePayload(JSON.stringify(data, null, 2));
                      } catch (e) {
                        setSourcePayload(String(e));
                      }
                    }}
                  >
                    Resolve source_ref
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Portal keyword (gap)</h3>
            <Badge variant="outline">{keywordHits.length}</Badge>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            Same query filtered client-side on cached wiki titles — not semantic.
          </p>
          <ul className="space-y-2">
            {keywordHits.map((p) => (
              <li key={p.slug} className="text-sm border-b border-border/50 pb-2">
                <span className="font-medium">{p.title}</span>
                <span className="text-xs text-muted-foreground block font-mono">{p.slug}</span>
              </li>
            ))}
            {!keywordHits.length && query && (
              <li className="text-sm text-muted-foreground">No keyword matches.</li>
            )}
          </ul>
        </Card>
      </div>

      {(readPayload || sourcePayload) && (
        <Card className="p-4 mt-6">
          <h3 className="text-sm font-semibold mb-2">Action response</h3>
          <pre className="text-xs bg-muted/50 rounded-lg p-3 overflow-auto max-h-96 whitespace-pre-wrap">
            {readPayload || sourcePayload}
          </pre>
        </Card>
      )}
    </>
  );
}
