"""Service-account KB API — ``/api/v1/*`` with MCP bearer auth.

Automation clients (LangGraph ingest, KB verify gates) call these routes with the
same ``Authorization: Bearer ark_…`` tokens as Claude Desktop MCP.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import agent_kb_ingest, agent_kb_service
from app.services.mcp_auth_service import MCPAuthService, ResolvedIdentity

router = APIRouter()


async def require_mcp_bearer(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> ResolvedIdentity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    identity = await MCPAuthService(db).verify_token(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return identity


@router.get("/wiki/search")
async def wiki_search(
    query: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=50),
    systems: str | None = Query(
        None,
        description="Comma-separated system tokens (post-filter), e.g. t24,payment",
    ),
    doc_type: str | None = Query(
        None,
        description="Post-filter doc_type from page metadata, e.g. Policy, ArchDoc",
    ),
    knowledge_type_slugs: str | None = Query(
        None,
        description="Comma-separated knowledge type slugs (post-filter)",
    ),
    channel: str | None = Query(
        None,
        description="Query expansion channel: policy | arch | incident",
    ),
    hybrid: bool = Query(
        False,
        description="RRF fusion of vector + keyword search (opt-in)",
    ),
    debug: bool = Query(False, description="Include latency, embedding spec, scope hints"),
    identity: ResolvedIdentity = Depends(require_mcp_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await agent_kb_service.search_wiki_hits(
        db,
        identity,
        query,
        top_k,
        systems=systems,
        doc_type=doc_type,
        knowledge_type_slugs=knowledge_type_slugs,
        channel=channel,
        hybrid=hybrid,
        debug=debug,
    )


@router.get("/wiki/read/{slug:path}")
async def wiki_read(
    slug: str,
    identity: ResolvedIdentity = Depends(require_mcp_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _ = identity
    decoded = unquote(slug)
    payload = await agent_kb_service.read_wiki_page_payload(db, decoded)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Wiki page not found: {decoded}")
    return payload


@router.get("/source/{source_ref:path}")
async def get_source(
    source_ref: str,
    identity: ResolvedIdentity = Depends(require_mcp_bearer),
) -> dict[str, Any]:
    _ = identity
    return agent_kb_service.resolve_source_ref_payload(unquote(source_ref))


class BridgeWriteItem(BaseModel):
    source_ref: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    sidecar: dict[str, Any] | None = None


class BridgeWriteRequest(BaseModel):
    items: list[BridgeWriteItem] = Field(default_factory=list)
    origin: str = "sync-sources"


@router.post("/sources/write")
async def sources_write(
    body: BridgeWriteRequest,
    identity: ResolvedIdentity = Depends(require_mcp_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Batch ingest for automation (sync-sources) — MCP bearer, not portal JWT."""
    if not identity.is_admin and not identity.has_any_permission(
        "doc:create", "doc:create:all", "doc:create:own_dept",
    ):
        raise HTTPException(status_code=403, detail="doc:create permission required")
    payload = [item.model_dump() for item in body.items]
    return await agent_kb_ingest.write_bridge_items(
        db, identity, payload, origin=body.origin,
    )
