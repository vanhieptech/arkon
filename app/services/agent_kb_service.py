"""Programmatic KB access for service-account (MCP bearer) clients.

Shared by HTTP ``/api/v1/*`` and MCP wiki tools — one embed + semantic search path,
two response shapes (JSON hits vs markdown for Claude).
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import wiki_service
from app.services.mcp_auth_service import ResolvedIdentity

RRF_K = 60

_CHANNEL_QUERY_SUFFIX: dict[str, str] = {
    "policy": "policy runbook requirement governance checklist",
    "arch": "architecture integration FSD BRD API dependency",
    "incident": "incident postmortem operational release risk",
}

_SYSTEM_SLUG_TOKENS = (
    "payment",
    "payments",
    "t24",
    "dwh",
    "coc",
    "core-banking",
    "integration",
)

_DOC_TYPE_TITLE_RE = re.compile(
    r"^(Policy|Requirement|Runbook|BRD|FSD|ArchDoc|DAB|IncidentEmail)\s*::\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SearchFilters:
    systems: tuple[str, ...] = ()
    doc_type: str | None = None
    knowledge_type_slugs: tuple[str, ...] = ()
    channel: str | None = None


def expand_search_query(query: str, channel: str | None) -> str:
    """Light query expansion for channel-aware retrieval (Wave A)."""
    if not channel:
        return query.strip()
    suffix = _CHANNEL_QUERY_SUFFIX.get(channel.strip().lower(), "")
    if not suffix:
        return query.strip()
    return f"{query.strip()} {suffix}"


def infer_systems_from_slug(slug: str) -> list[str]:
    slug_lower = slug.lower().replace("-", "/")
    found: list[str] = []
    for token in _SYSTEM_SLUG_TOKENS:
        if token.replace("-", "") in slug_lower.replace("-", ""):
            found.append(token)
    if slug_lower.startswith("system/"):
        part = slug_lower.split("/", 2)[1] if "/" in slug_lower else ""
        if part:
            found.append(part.replace("/", "-"))
    return sorted(set(found))


def infer_doc_type(page: Any) -> str | None:
    title = str(getattr(page, "title", "") or "")
    match = _DOC_TYPE_TITLE_RE.match(title)
    if match:
        return match.group(1)
    slug = str(getattr(page, "slug", "") or "").lower()
    if "incident" in slug or "postmortem" in slug:
        return "IncidentEmail"
    if slug.startswith("integration/"):
        return "ArchDoc"
    if any(tok in slug for tok in ("policy", "runbook", "checklist")):
        return "Policy"
    return None


def page_hit_metadata(page: Any) -> dict[str, Any]:
    slug = str(getattr(page, "slug", "") or "")
    meta: dict[str, Any] = {
        "slug": slug,
        "page_type": getattr(page, "page_type", None),
        "knowledge_type_slugs": list(getattr(page, "knowledge_type_slugs", None) or []),
    }
    systems = infer_systems_from_slug(slug)
    if systems:
        meta["systems"] = systems
    doc_type = infer_doc_type(page)
    if doc_type:
        meta["doc_type"] = doc_type
    return meta


def build_snippet(page: Any, query: str, *, max_len: int = 500) -> str:
    summary = (getattr(page, "summary", None) or "").strip()
    if len(summary) >= 120:
        return summary[:max_len]

    content = (getattr(page, "content_md", None) or "").strip()
    if not content:
        return summary[:max_len]

    terms = [t.lower() for t in re.split(r"\W+", query) if len(t) > 2][:6]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    best = summary
    best_score = 0
    for para in paragraphs[:40]:
        lower = para.lower()
        score = sum(1 for t in terms if t in lower)
        if score > best_score:
            best_score = score
            best = para
    if not best and paragraphs:
        best = paragraphs[0]
    return (best or summary)[:max_len]


def _system_tokens(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


def _kt_tokens(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(s.strip().lower() for s in raw.split(",") if s.strip())


def hit_passes_filters(
    page: Any,
    similarity: float,
    filters: SearchFilters,
) -> bool:
    meta = page_hit_metadata(page)
    if filters.knowledge_type_slugs:
        present = {s.lower() for s in meta.get("knowledge_type_slugs") or []}
        if not present.intersection(filters.knowledge_type_slugs):
            return False
    if filters.doc_type:
        if str(meta.get("doc_type", "")).lower() != filters.doc_type.lower():
            return False
    if filters.systems:
        present = {s.lower() for s in meta.get("systems") or []}
        if not present.intersection(filters.systems):
            slug = str(meta.get("slug", "")).lower()
            if not any(tok in slug for tok in filters.systems):
                return False
    _ = similarity
    return True


def wiki_hit_dict(page: Any, similarity: float, *, query: str = "") -> dict[str, Any]:
    """Structured hit for LangGraph / automation HTTP clients."""
    rank = max(0, min(100, int(round(float(similarity) * 100))))
    slug = str(getattr(page, "slug", "") or "")
    return {
        "source_ref": f"arkon:wiki:{slug}",
        "title": getattr(page, "title", None) or slug,
        "snippet": build_snippet(page, query),
        "rank": rank,
        "metadata": page_hit_metadata(page),
    }


def rrf_merge(
    *ranked_lists: list[tuple[Any, float]],
    k: int = RRF_K,
) -> list[tuple[Any, float]]:
    """Reciprocal rank fusion across ranked (page, score) lists."""
    scores: dict[str, float] = {}
    pages: dict[str, Any] = {}
    for ranked in ranked_lists:
        for rank_idx, (page, _) in enumerate(ranked, start=1):
            slug = str(getattr(page, "slug", "") or "")
            if not slug:
                continue
            pages[slug] = page
            scores[slug] = scores.get(slug, 0.0) + 1.0 / (k + rank_idx)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [(pages[slug], score) for slug, score in ordered]


def relaxed_filters(filters: SearchFilters) -> SearchFilters:
    """Drop strict metadata filters; keep channel expansion (D-68-13)."""
    return SearchFilters(
        systems=(),
        doc_type=None,
        knowledge_type_slugs=(),
        channel=filters.channel,
    )


def _has_strict_metadata_filters(filters: SearchFilters) -> bool:
    return bool(filters.systems or filters.doc_type or filters.knowledge_type_slugs)


def apply_post_filters(
    raw_hits: list[tuple[Any, float]],
    filters: SearchFilters,
    top_k: int,
) -> list[tuple[Any, float]]:
    filtered: list[tuple[Any, float]] = []
    for page, sim in raw_hits:
        if hit_passes_filters(page, sim, filters):
            filtered.append((page, sim))
        if len(filtered) >= top_k:
            break
    return filtered


def project_scope_ids(identity: ResolvedIdentity) -> list[uuid.UUID] | None:
    raw = getattr(identity, "project_ids", None) or []
    if not raw:
        return None
    return [uuid.UUID(str(p)) for p in raw]


async def embed_search_query(db: AsyncSession, query: str) -> list[float] | None:
    """Return query embedding, or None if provider missing or embed fails."""
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    embedding_provider = await registry.get_embedding(task="search_query")
    if embedding_provider is None:
        return None
    try:
        return await embedding_provider.embed(query)
    except Exception as exc:
        logger.warning("wiki search embed failed: {}", exc)
        return None


async def active_embedding_spec_id(db: AsyncSession) -> str | None:
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    return await registry.get_active_embedding_spec_id()


async def semantic_search_pages(
    db: AsyncSession,
    identity: ResolvedIdentity,
    query_embedding: list[float],
    top_k: int,
) -> list[tuple[Any, float]]:
    """Wiki pages in scope for the given MCP/service identity."""
    top_k = min(max(1, top_k), 50)
    return await wiki_service.search_pages_semantic(
        db,
        query_embedding=query_embedding,
        top_k=top_k,
        allowed_kt_slugs=identity.allowed_knowledge_types,
        department_ids=identity.department_ids or None,
        project_ids=project_scope_ids(identity),
        all_scopes=identity.is_admin,
    )


async def keyword_search_pages(
    db: AsyncSession,
    identity: ResolvedIdentity,
    query: str,
    top_k: int,
) -> list[tuple[Any, float]]:
    top_k = min(max(1, top_k), 50)
    return await wiki_service.search_pages_keyword(
        db,
        query=query,
        top_k=top_k,
        allowed_kt_slugs=identity.allowed_knowledge_types,
        department_ids=identity.department_ids or None,
        project_ids=project_scope_ids(identity),
        all_scopes=identity.is_admin,
    )


def _fetch_top_k(top_k: int, filters: SearchFilters, *, hybrid: bool = False) -> int:
    if hybrid or _has_strict_metadata_filters(filters):
        return min(50, max(top_k * 3, 30))
    return top_k


async def _retrieve_ranked_hits(
    db: AsyncSession,
    identity: ResolvedIdentity,
    expanded_query: str,
    query_embedding: list[float],
    fetch_k: int,
    *,
    hybrid: bool,
) -> tuple[list[tuple[Any, float]], dict[str, int]]:
    vector_hits = await semantic_search_pages(db, identity, query_embedding, fetch_k)
    if not hybrid:
        return vector_hits, {"vector": len(vector_hits), "keyword": 0}

    keyword_hits = await keyword_search_pages(db, identity, expanded_query, fetch_k)
    fused = rrf_merge(vector_hits, keyword_hits)
    return fused, {"vector": len(vector_hits), "keyword": len(keyword_hits)}


async def search_wiki_hits(
    db: AsyncSession,
    identity: ResolvedIdentity,
    query: str,
    top_k: int = 5,
    *,
    systems: str | None = None,
    doc_type: str | None = None,
    knowledge_type_slugs: str | None = None,
    channel: str | None = None,
    hybrid: bool = False,
    debug: bool = False,
) -> dict[str, Any]:
    """JSON search payload for ``GET /api/v1/wiki/search``."""
    started = time.monotonic()
    filters = SearchFilters(
        systems=_system_tokens(systems),
        doc_type=doc_type.strip() if doc_type else None,
        knowledge_type_slugs=_kt_tokens(knowledge_type_slugs),
        channel=channel.strip().lower() if channel else None,
    )
    expanded_query = expand_search_query(query, filters.channel)
    spec_id = await active_embedding_spec_id(db)

    query_embedding = await embed_search_query(db, expanded_query)
    if query_embedding is None:
        payload: dict[str, Any] = {"query": query, "hits": []}
        if debug:
            payload["debug"] = {
                "latency_ms": int((time.monotonic() - started) * 1000),
                "embedding_spec_id": spec_id,
                "expanded_query": expanded_query,
                "empty_reason": "embedding_not_configured",
                "scope_hint": _scope_hint(identity),
                "hybrid": hybrid,
            }
        return payload

    fetch_k = _fetch_top_k(top_k, filters, hybrid=hybrid)
    raw_hits, leg_counts = await _retrieve_ranked_hits(
        db,
        identity,
        expanded_query,
        query_embedding,
        fetch_k,
        hybrid=hybrid,
    )

    filtered = apply_post_filters(raw_hits, filters, top_k)
    filter_relaxed = False
    if (
        not filtered
        and raw_hits
        and _has_strict_metadata_filters(filters)
    ):
        filtered = apply_post_filters(raw_hits, relaxed_filters(filters), top_k)
        filter_relaxed = bool(filtered)

    latency_ms = int((time.monotonic() - started) * 1000)
    if latency_ms > 2000:
        logger.warning(
            "slow wiki search query={!r} latency_ms={} hits={} hybrid={}",
            query[:80],
            latency_ms,
            len(filtered),
            hybrid,
        )

    result: dict[str, Any] = {
        "query": query,
        "hits": [wiki_hit_dict(page, sim, query=query) for page, sim in filtered],
    }
    if debug:
        result["debug"] = {
            "latency_ms": latency_ms,
            "embedding_spec_id": spec_id,
            "expanded_query": expanded_query,
            "fetch_k": fetch_k,
            "hybrid": hybrid,
            "legs": leg_counts,
            "filters_applied": _has_strict_metadata_filters(filters),
            "filter_relaxed": filter_relaxed,
            "scope_hint": _scope_hint(identity),
            "empty_reason": None if filtered else "no_matches_in_scope",
        }
    return result


def _scope_hint(identity: ResolvedIdentity) -> dict[str, Any]:
    return {
        "is_admin": identity.is_admin,
        "allowed_knowledge_types": list(identity.allowed_knowledge_types or []),
        "department_count": len(identity.department_ids or []),
        "project_count": len(getattr(identity, "project_ids", None) or []),
    }


async def read_wiki_page_payload(
    db: AsyncSession,
    slug: str,
) -> dict[str, Any] | None:
    """Full wiki page body for automation clients."""
    page = await wiki_service.get_page_by_slug_any_scope(db, slug)
    if page is None:
        return None
    return {
        "slug": page.slug,
        "title": page.title,
        "content": page.content_md or "",
        "source_ref": f"arkon:wiki:{page.slug}",
        "metadata": page_hit_metadata(page),
    }


def resolve_source_ref_payload(source_ref: str) -> dict[str, Any]:
    """Lightweight source_ref drill-down (wiki slugs → read endpoint hint)."""
    if source_ref.startswith("arkon:wiki:"):
        slug = source_ref.removeprefix("arkon:wiki:")
        return {
            "source_ref": source_ref,
            "kind": "wiki",
            "slug": slug,
            "message": "Use /api/v1/wiki/read/{slug} for wiki page bodies.",
        }
    return {
        "source_ref": source_ref,
        "kind": "external",
        "message": "Raw source bodies are ingested into Arkon wiki; use wiki search/read.",
    }
