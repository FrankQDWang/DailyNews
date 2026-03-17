from __future__ import annotations
# ruff: noqa: E402, I001

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from temporalio.client import Client
from temporalio.worker import Worker

from libs.core.logging import configure_logging
from libs.core.settings import get_settings
from libs.workflows.activities import (
    build_digest_activity,
    deepdive_activity,
    fetch_and_upsert_entry_activity,
    list_unread_miniflux_activity,
    mark_entry_read_activity,
    prepare_ingest_batch_activity,
    refresh_miniflux_activity,
    score_entry_activity,
    send_alert_activity,
    send_digest_activity,
    should_push_activity,
    summarize_entry_activity,
    verify_entry_activity,
)
from libs.workflows.workflows import (
    DailyDigestWorkflow,
    DeepDiveWorkflow,
    IngestBatchWorkflow,
    ProcessEntryWorkflow,
    PushAlertWorkflow,
    VerifyEntryWorkflow,
)


async def _start_workers() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    workers = [
        Worker(
            client,
            task_queue=settings.temporal_task_queue_ingest,
            workflows=[IngestBatchWorkflow],
            activities=[
                refresh_miniflux_activity,
                list_unread_miniflux_activity,
                prepare_ingest_batch_activity,
                fetch_and_upsert_entry_activity,
                mark_entry_read_activity,
            ],
        ),
        Worker(
            client,
            task_queue=settings.temporal_task_queue_process,
            workflows=[ProcessEntryWorkflow],
            activities=[summarize_entry_activity, score_entry_activity, mark_entry_read_activity],
        ),
        Worker(
            client,
            task_queue=settings.temporal_task_queue_verify,
            workflows=[VerifyEntryWorkflow],
            activities=[verify_entry_activity],
        ),
        Worker(
            client,
            task_queue=settings.temporal_task_queue_push,
            workflows=[PushAlertWorkflow],
            activities=[should_push_activity, send_alert_activity],
        ),
        Worker(
            client,
            task_queue=settings.temporal_task_queue_digest,
            workflows=[DailyDigestWorkflow],
            activities=[build_digest_activity, send_digest_activity],
        ),
        Worker(
            client,
            task_queue=settings.temporal_task_queue_deepdive,
            workflows=[DeepDiveWorkflow],
            activities=[deepdive_activity],
        ),
    ]

    await asyncio.gather(*(worker.run() for worker in workers))


if __name__ == "__main__":
    configure_logging()
    asyncio.run(_start_workers())
