"""
POC verification — storage (S3/LocalStack), Bedrock LLM, Bedrock embedding.

  python -m app.scripts.poc_verify
"""

import asyncio
import os
import sys

from loguru import logger

from app.database import async_session_factory
from app.ai.registry import ProviderRegistry
from app.services.storage_service import storage_service


async def verify_storage() -> tuple[bool, str]:
    try:
        await storage_service.ensure_bucket()
        key = "poc/healthcheck.txt"
        storage_service.upload_file(key, b"arkon-poc-ok", "text/plain")
        data = storage_service.download_file(key)
        storage_service.delete_object(key)
        if data != b"arkon-poc-ok":
            return False, "round-trip bytes mismatch"
        return True, f"OK — bucket={os.environ.get('MINIO_BUCKET', 'arkon-files')}"
    except Exception as e:
        return False, str(e)


async def verify_ai() -> dict[str, tuple[bool, str]]:
    async with async_session_factory() as session:
        registry = ProviderRegistry(session)
        return await registry.test_all()


async def main() -> int:
    logger.info("=== Arkon AWS POC verify ===")
    ok_storage, msg_storage = await verify_storage()
    logger.info(f"storage: {'PASS' if ok_storage else 'FAIL'} — {msg_storage}")

    verify_ai_flag = os.environ.get("POC_VERIFY_AI", "0").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    all_ok = ok_storage
    if verify_ai_flag:
        ai = await verify_ai()
        for cap, (ok, msg) in ai.items():
            logger.info(f"{cap}: {'PASS' if ok else 'FAIL'} — {msg}")
            if cap in ("llm", "embedding"):
                all_ok = all_ok and ok
    else:
        logger.info("AI verify skipped (set POC_VERIFY_AI=1 to enable).")

    if not all_ok:
        logger.error(
            "POC verify failed. Check AWS credentials, Bedrock model access, "
            "and LocalStack (docker compose -f docker-compose.yml "
            "-f docker-compose.localstack.yml)."
        )
        return 1
    logger.success("POC verify passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
