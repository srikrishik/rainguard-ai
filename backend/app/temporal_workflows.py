from datetime import timedelta
from typing import TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy


class MaintenanceTaskWorkflowInput(TypedDict):
    asset_id: str
    mission_id: str
    finding_id: str
    description: str
    priority: str
    assignee: str | None
    due_date: str | None
    completion_notes: str | None
    evidence_refs: list[str]


class MaintenanceTaskWorkflowResult(TypedDict):
    task_id: str
    status: str


MAINTENANCE_TASK_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    non_retryable_error_types=("ValidationError",),
)


@workflow.defn(name="maintenance-task-orchestration")
class MaintenanceTaskWorkflow:
    @workflow.run
    async def run(
        self, input: MaintenanceTaskWorkflowInput
    ) -> MaintenanceTaskWorkflowResult:
        return await workflow.execute_activity(
            "create_maintenance_task",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=MAINTENANCE_TASK_RETRY_POLICY,
        )
