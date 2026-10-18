from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.repositories import (
    AssetRepository,
    DatabaseUnavailableError,
    InspectionMissionRepository,
    MaintenanceTaskRepository,
)
from app.schemas import MaintenanceTaskCreate
from app.temporal_workflows import MaintenanceTaskWorkflowInput


def _validation_error(message: str) -> ApplicationError:
    return ApplicationError(message, type="ValidationError", non_retryable=True)


class MaintenanceTaskActivities:
    def __init__(self, database: Any) -> None:
        self.database = database

    @activity.defn(name="create_maintenance_task")
    def create_maintenance_task(
        self, input: MaintenanceTaskWorkflowInput
    ) -> dict[str, str]:
        try:
            payload = MaintenanceTaskCreate.model_validate(input)
            asset_id = ObjectId(payload.asset_id)
            mission_id = ObjectId(payload.mission_id)
        except (ValidationError, InvalidId, TypeError, ValueError) as exc:
            raise _validation_error("invalid maintenance task input") from exc

        try:
            if AssetRepository(self.database).get(asset_id) is None:
                raise _validation_error("asset not found")

            mission_repository = InspectionMissionRepository(self.database)
            mission = mission_repository.get(mission_id)
            if mission is None or mission.get("asset_id") != asset_id:
                raise _validation_error("inspection mission not found")

            finding = next(
                (
                    item
                    for item in mission.get("findings", [])
                    if item.get("id") == payload.finding_id
                ),
                None,
            )
            if finding is None:
                raise _validation_error("finding not found")
            if not finding.get("approved", False):
                raise _validation_error("finding requires human approval")

            now = datetime.now(timezone.utc)
            document = {
                "_id": ObjectId(),
                "asset_id": asset_id,
                "mission_id": mission_id,
                "finding_id": payload.finding_id,
                "description": payload.description,
                "priority": payload.priority,
                "assignee": payload.assignee,
                "due_date": payload.due_date,
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "completion_notes": payload.completion_notes,
                "evidence_refs": payload.evidence_refs,
                "reinspection_required": False,
                "reinspection_status": "not_required",
            }
            task = MaintenanceTaskRepository(self.database).create(document)
        except DatabaseUnavailableError:
            raise

        task_id = task.get("_id")
        if not isinstance(task_id, ObjectId):
            raise _validation_error("maintenance task response is invalid")
        return {"task_id": str(task_id), "status": str(task.get("status", "pending"))}
