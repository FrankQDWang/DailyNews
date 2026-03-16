from __future__ import annotations
# ruff: noqa: E402, I001

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temporalio.client import Client

from libs.core.logging import configure_logging
from libs.core.settings import get_settings
from libs.workflows.workflows import IngestBatchWorkflow


async def _run() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    workflow_id = f"cron-ingest-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    await client.start_workflow(
        IngestBatchWorkflow.run,
        id=workflow_id,
        task_queue=settings.temporal_task_queue_ingest,
    )


if __name__ == "__main__":
    configure_logging()
    asyncio.run(_run())
