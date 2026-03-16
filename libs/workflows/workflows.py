from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from libs.workflows.activities import (
        build_digest_activity,
        deepdive_activity,
        fetch_and_upsert_entry_activity,
        list_unread_miniflux_activity,
        refresh_miniflux_activity,
        score_entry_activity,
        send_alert_activity,
        send_digest_activity,
        should_push_activity,
        summarize_entry_activity,
        verify_entry_activity,
    )


@workflow.defn
class IngestBatchWorkflow:
    @workflow.run
    async def run(self) -> list[int]:
        await workflow.execute_activity(
            refresh_miniflux_activity,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        raw_entries = await workflow.execute_activity(
            list_unread_miniflux_activity,
            100,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        entry_ids: list[int] = []
        for row in raw_entries:
            entry_id = await workflow.execute_activity(
                fetch_and_upsert_entry_activity,
                row,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            entry_ids.append(entry_id)
            await workflow.start_child_workflow(
                ProcessEntryWorkflow.run,
                entry_id,
                id=f"process-entry-{entry_id}-{workflow.info().run_id[:8]}",
                task_queue="process",
            )
        return entry_ids


@workflow.defn
class ProcessEntryWorkflow:
    @workflow.run
    async def run(self, entry_id: int) -> dict[str, Any]:
        summary = await workflow.execute_activity(
            summarize_entry_activity,
            entry_id,
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="process",
        )
        score = await workflow.execute_activity(
            score_entry_activity,
            entry_id,
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="process",
        )

        grade = str(score.get("grade", "C"))
        if grade == "A":
            await workflow.start_child_workflow(
                VerifyEntryWorkflow.run,
                entry_id,
                id=f"verify-entry-{entry_id}-{workflow.info().run_id[:8]}",
                task_queue="verify",
            )

        should_push = await workflow.execute_activity(
            should_push_activity,
            entry_id,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=2),
            task_queue="push",
        )

        if should_push:
            await workflow.start_child_workflow(
                PushAlertWorkflow.run,
                entry_id,
                id=f"push-entry-{entry_id}-{workflow.info().run_id[:8]}",
                task_queue="push",
            )

        return {"entry_id": entry_id, "summary": summary, "score": score}


@workflow.defn
class VerifyEntryWorkflow:
    @workflow.run
    async def run(self, entry_id: int) -> dict[str, Any]:
        result = await workflow.execute_activity(
            verify_entry_activity,
            entry_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="verify",
        )
        return result


@workflow.defn
class PushAlertWorkflow:
    @workflow.run
    async def run(self, entry_id: int) -> None:
        await workflow.execute_activity(
            send_alert_activity,
            entry_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="push",
        )


@workflow.defn
class DailyDigestWorkflow:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        digest = await workflow.execute_activity(
            build_digest_activity,
            start_to_close_timeout=timedelta(minutes=8),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="digest",
        )
        await workflow.execute_activity(
            send_digest_activity,
            str(digest.get("markdown", "")),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="digest",
        )
        return digest


@workflow.defn
class DeepDiveWorkflow:
    @workflow.run
    async def run(self, entry_id: int, requestor_chat_id: int, requestor_user_id: int) -> None:
        del requestor_user_id
        await workflow.execute_activity(
            deepdive_activity,
            args=[entry_id, requestor_chat_id],
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3),
            task_queue="deepdive",
        )
