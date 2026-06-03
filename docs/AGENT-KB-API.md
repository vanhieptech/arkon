# Agent KB API (HTTP v1)

Automation clients (LangGraph, `sync-sources`, Claude MCP) use **one semantic retrieval path** implemented in `app/services/agent_kb_service.py`.

## Authentication

All routes require an MCP service token:

```http
Authorization: Bearer ark_…
```

Tokens are scoped by knowledge type, department, and workspace membership — same rules as MCP `search_wiki`. Portal JWT is **not** accepted on `/api/v1/*`.

## Endpoints

### `GET /api/v1/wiki/search`

Semantic search over compiled wiki pages.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | yes | Natural language query (min 1 char) |
| `top_k` | no | 1–50, default 5 |
| `systems` | no | Comma-separated post-filter (e.g. `t24,payment`) |
| `doc_type` | no | Post-filter: `Policy`, `ArchDoc`, `FSD`, … |
| `knowledge_type_slugs` | no | Comma-separated KT slugs |
| `channel` | no | Query expansion: `policy`, `arch`, `incident` |
| `hybrid` | no | `true` → RRF fusion of vector + keyword (ILIKE) legs |
| `debug` | no | `true` → latency, embedding spec, scope hints |

**Response (stable contract for hackathon `ArkonClient`):**

```json
{
  "query": "T24 rollback",
  "hits": [
    {
      "source_ref": "arkon:wiki:system/t24",
      "title": "T24 Core Banking",
      "snippet": "…",
      "rank": 87,
      "metadata": {
        "slug": "system/t24",
        "page_type": "concept",
        "knowledge_type_slugs": ["architecture"],
        "systems": ["t24"],
        "doc_type": "ArchDoc"
      }
    }
  ],
  "debug": {
    "latency_ms": 412,
    "embedding_spec_id": "openai/qwen3-embedding-8b",
    "expanded_query": "T24 rollback policy runbook …",
    "hybrid": false,
    "legs": { "vector": 15, "keyword": 0 },
    "filters_applied": true,
    "filter_relaxed": false,
    "empty_reason": null
  }
}
```

When strict `systems` / `doc_type` filters eliminate all hits but the raw candidate set is non-empty, the server retries without metadata filters (channel expansion kept) and sets `debug.filter_relaxed=true`.

When embedding is unavailable, `hits` is `[]` and `debug.empty_reason` is `embedding_not_configured` (if `debug=true`).

### `GET /api/v1/wiki/read/{slug}`

Full markdown body for a wiki slug (URL-encoded path allowed).

### `GET /api/v1/source/{source_ref}`

Lightweight drill-down hint (wiki slugs → use read endpoint).

### `POST /api/v1/sources/write`

Batch ingest for `sync-sources` bridge (requires `doc:create` or admin).

## Operator UI

**Retrieval Lab** (`/admin/retrieval-lab`) calls the same search/read/source endpoints with a saved MCP bearer token — use it to verify retrieval without Claude Desktop.

## MCP parity

`search_wiki` and `read_wiki_page` MCP tools call the same embed + `search_pages_semantic` stack. HTTP returns structured JSON; MCP returns markdown for Claude.

## Related

- Hackathon client: `src/arkon/client.py`
- Operator runbook: hackathon `docs/OPERATOR-RUNBOOK.md` (Phase 68 section)
