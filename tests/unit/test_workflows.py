from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from typing import Any, cast

from temporalio.workflow import ParentClosePolicy


def _base_env() -> dict[str, str]:
    return {
        "ASSISTANT_DB_URL": "postgresql+asyncpg://u:p@localhost:5432/db",
        "TEMPORAL_HOST": "localhost:7233",
        "DEEPSEEK_API_KEY": "x",
        "MINIFLUX_BASE_URL": "https://example.com",
        "MINIFLUX_API_TOKEN": "token",
        "TELEGRAM_BOT_TOKEN": "x",
        "TELEGRAM_WEBHOOK_SECRET": "secret",
        "TELEGRAM_TARGET_CHAT_ID": "-10001",
        "TELEGRAM_ADMIN_USER_IDS": "[1, 2, 3]",
        "INTERNAL_API_TOKEN": "internal",
    }


def _load_workflows_module(monkeypatch: Any) -> Any:
    for key, value in _base_env().items():
        monkeypatch.setenv(key, value)

    for module_name in ("libs.workflows.workflows", "libs.workflows.activities", "libs.core.db.session"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("libs.workflows.workflows")


async def test_ingest_batch_workflow_abandons_process_children(monkeypatch: Any) -> None:
    workflow_module = _load_workflows_module(monkeypatch)
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


async def test_process_entry_workflow_short_circuits_on_preflight_deferred(monkeypatch: Any) -> None:
    workflow_module = _load_workflows_module(monkeypatch)
    workflow_module_any = cast(Any, workflow_module)
    workflow_api = workflow_module_any.workflow

    async def fake_execute_activity(activity: object, *args: object, **kwargs: object) -> object:
        del args, kwargs
        if activity is workflow_module_any.prepare_entry_content_activity:
            return {
                "status": "fetch_deferred",
                "reason": "blocked:http_status:500",
                "marked_read": True,
                "content_fetch_state": "blocked",
            }
        raise AssertionError(f"unexpected activity: {activity}")

    monkeypatch.setattr(workflow_api, "execute_activity", fake_execute_activity)

    result = await workflow_module.ProcessEntryWorkflow().run(42)

    assert result == {
        "entry_id": 42,
        "preflight_status": "fetch_deferred",
        "preflight_reason": "blocked:http_status:500",
        "marked_read": True,
        "summary": None,
        "score": None,
        "push_decision_reason": None,
        "verification": None,
    }
