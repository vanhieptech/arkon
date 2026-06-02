"""
POC bootstrap — set active Bedrock LLM + embedding in app_config.

Run after migrations:
  python -m app.scripts.poc_configure

Or set POC_CONFIGURE_BEDROCK=1 in .env.docker (entrypoint runs this once).
"""

import asyncio
import os

from loguru import logger

from app.database import async_session_factory
from app.services.config_service import (
    ACTIVE_EMBEDDING_MODEL_KEY,
    ACTIVE_LLM_MODEL_KEY,
    ConfigService,
)


async def configure_bedrock_poc() -> None:
    llm_spec = os.environ.get("POC_LLM_SPEC_ID", "bedrock/claude-3-5-sonnet")
    emb_spec = os.environ.get("POC_EMBEDDING_SPEC_ID", "bedrock/titan-embed-v2")

    from app.ai.embedding_catalog import EMBEDDING_CATALOG
    from app.ai.llm_catalog import LLM_CATALOG

    if llm_spec not in LLM_CATALOG:
        raise ValueError(f"Unknown POC_LLM_SPEC_ID={llm_spec!r}")
    if emb_spec not in EMBEDDING_CATALOG:
        raise ValueError(f"Unknown POC_EMBEDDING_SPEC_ID={emb_spec!r}")

    async with async_session_factory() as session:
        svc = ConfigService(session)
        await svc.set(ACTIVE_LLM_MODEL_KEY, llm_spec)
        await svc.set(ACTIVE_EMBEDDING_MODEL_KEY, emb_spec)
        await session.commit()

    logger.success(
        f"POC configured: LLM={llm_spec}, embedding={emb_spec} "
        f"(region={os.environ.get('AWS_REGION', 'us-east-1')})"
    )


async def main() -> None:
    await configure_bedrock_poc()


if __name__ == "__main__":
    asyncio.run(main())
