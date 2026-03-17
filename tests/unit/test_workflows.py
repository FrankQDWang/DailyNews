from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from temporalio.workflow import ParentClosePolicy

from libs.workflows import workflows as workflow_module


async def test_ingest_batch_workflow_abandons_process_children(monkeypatch: Any) -> None:
    workflow_module_any = cast(Any, workflow_module)
    workflow_api = workflow_module_any.workflow
    started_children: list[dict[str, Any]] = []

    async def fake_execute_activity(activity: object, *args: object, **kwargs: object) -> object:
        del kwargs
        if activity is workflow_module_any.refresh_miniflux_activity:
            return None
        if activity is workflow_module_any.prepare_ingest_batch_activity:
            assert args == ()
            return {
                "actionable_entry_ids": [101, 202],
                "marked_read_count": 0,
                "scanned_count": 300,
                "actionable_count": 2,
                "skipped_terminal_count": 0,
                "skipped_cooldown_count": 0,
                "skipped_blocked_count": 0,
            }
        raise AssertionError(f"unexpected activity: {activity}")

    async def fake_start_child_workflow(run_method: object, entry_id: int, **kwargs: object) -> None:
        started_children.append(
            {
                "run_method": run_method,
                "entry_id": entry_id,
                **kwargs,
            }
        )

    monkeypatch.setattr(workflow_api, "execute_activity", fake_execute_activity)
    monkeypatch.setattr(workflow_api, "start_child_workflow", fake_start_child_workflow)
    monkeypatch.setattr(workflow_api, "info", lambda: SimpleNamespace(run_id="abcd1234run"))

    result = await workflow_module.IngestBatchWorkflow().run()

    assert result == [101, 202]
    assert [child["entry_id"] for child in started_children] == [101, 202]
    assert all(child["task_queue"] == "process" for child in started_children)
    assert all(child["parent_close_policy"] == ParentClosePolicy.ABANDON for child in started_children)
    assert [child["id"] for child in started_children] == [
        "process-entry-101-abcd1234",
        "process-entry-202-abcd1234",
    ]
