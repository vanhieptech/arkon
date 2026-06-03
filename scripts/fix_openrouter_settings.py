#!/usr/bin/env python3
"""One-shot: align Arkon Settings for OpenRouter + retry failed MRP sources."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.ai.openrouter_compat import OPENROUTER_BASE_URL
from app.database import async_session_factory
from app.database.models import Source
from app.services.config_service import (
    ACTIVE_EMBEDDING_MODEL_KEY,
    ACTIVE_LLM_MODEL_KEY,
    ACTIVE_VISION_MODEL_KEY,
    ConfigService,
)
from app.worker import get_arq_pool


async def main() -> int:
    async with async_session_factory() as session:
        svc = ConfigService(session)
        updates = {
            "llm_base_url": OPENROUTER_BASE_URL,
            "embedding_base_url": OPENROUTER_BASE_URL,
            "vision_base_url": OPENROUTER_BASE_URL,
            ACTIVE_LLM_MODEL_KEY: "openrouter/owl-alpha",
            ACTIVE_EMBEDDING_MODEL_KEY: "openrouter/qwen3-embedding-8b",
            ACTIVE_VISION_MODEL_KEY: "openrouter/owl-alpha",
        }
        for key, value in updates.items():
            await svc.set(key, value)
            print(f"set {key}={value}")
        await session.commit()

        # Retry sources stuck in error from MAP 401 failures.
        stmt = select(Source.id, Source.title, Source.status).where(
            Source.status.in_(("error", "processing"))
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            print("no error/processing sources to retry")
            return 0

        pool = await get_arq_pool()
        for source_id, title, status in rows:
            job = await pool.enqueue_job("ingest_map_reduce_task", str(source_id))
            print(f"retry queued source={source_id} status={status} title={title!r} job={getattr(job, 'job_id', None)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
