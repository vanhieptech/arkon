"""Ingest automation payloads (sync bridge) using MCP bearer identity."""

from __future__ import annotations

import re
import uuid
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ScopeType, Source
from app.database.repository import Repository
from app.services.mcp_auth_service import ResolvedIdentity
from app.services.storage_service import storage_service
from app.worker import get_arq_pool

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(source_ref: str) -> str:
    base = _SAFE_NAME.sub("_", source_ref.strip())[:200] or "document"
    return f"{base}.md"


async def write_bridge_items(
    db: AsyncSession,
    identity: ResolvedIdentity,
    items: list[dict[str, Any]],
    *,
    origin: str,
) -> dict[str, Any]:
    """Accept markdown documents from sync-sources and enqueue wiki ingestion."""
    if not items:
        return {"accepted": 0, "source_ids": [], "origin": origin}

    repo = Repository(db)
    source_ids: list[str] = []
    accepted = 0

    for raw in items:
        source_ref = str(raw.get("source_ref", "")).strip()
        content = raw.get("content")
        if not source_ref or not isinstance(content, str) or not content.strip():
            continue

        sidecar = raw.get("sidecar") if isinstance(raw.get("sidecar"), dict) else {}
        doc_type = str(sidecar.get("doc_type", "")).strip() if sidecar else ""
        label = str(sidecar.get("title", "")).strip() if sidecar else ""
        if not label and source_ref.startswith("pdf:"):
            path_part = source_ref.removeprefix("pdf:").split("#", 1)[0]
            label = path_part.rsplit("/", 1)[-1].replace(".pdf", "").replace("-", " ")
        if not label:
            label = source_ref
        title = f"{doc_type} :: {label}" if doc_type else label
        file_name = _safe_filename(source_ref)
        file_data = content.encode("utf-8")

        source = Source(
            title=title[:500],
            source_type="file",
            file_name=file_name,
            file_size=len(file_data),
            status="pending",
            progress=0,
            progress_message=f"Queued from {origin}…",
            contributed_by_employee_id=identity.employee_id,
            scope_type=ScopeType.GLOBAL.value,
        )
        source = await repo.create(source)
        await db.flush()

        minio_key = f"sources/{source.id}/original/{file_name}"
        storage_service.upload_file(
            object_name=minio_key,
            data=file_data,
            content_type="text/markdown",
        )
        source.minio_key = minio_key
        await db.flush()

        pool = await get_arq_pool()
        job = await pool.enqueue_job("ingest_file_task", str(source.id))
        if job:
            source.job_id = job.job_id
        await db.flush()

        source_ids.append(str(source.id))
        accepted += 1
        logger.info(
            "agent_kb ingest queued source {} ref={} employee={}",
            source.id,
            source_ref,
            identity.employee_id,
        )

    await db.commit()
    return {"accepted": accepted, "source_ids": source_ids, "origin": origin}
