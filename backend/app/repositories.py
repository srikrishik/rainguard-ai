
from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.database import DatabaseUnavailableError


class SocietyRepository:
    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["societies"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or {
                **document,
                "_id": result.inserted_id,
            }
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get(self, society_id: ObjectId) -> dict[str, Any] | None:
        try:
            return self.collection.find_one({"_id": society_id})
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class AssetRepository:
    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["assets"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or {
                **document,
                "_id": result.inserted_id,
            }
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get(self, asset_id: ObjectId) -> dict[str, Any] | None:
        try:
            return self.collection.find_one({"_id": asset_id})
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class IncidentRepository:
    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["incidents"]

    def list_for_asset(self, asset_id: ObjectId) -> list[dict[str, Any]]:
        try:
            return list(
                self.collection.find({"asset_id": asset_id}).sort("occurred_at", -1)
            )
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class InspectionRepository:
    """Persist inspection records and their analysis status."""

    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["inspections"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or {
                **document,
                "_id": result.inserted_id,
            }
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def update(self, inspection_id: ObjectId, updates: dict[str, Any]) -> None:
        try:
            result = self.collection.update_one(
                {"_id": inspection_id},
                {"$set": updates},
            )
            if result.matched_count == 0:
                raise DatabaseUnavailableError("Inspection record not found")
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get(self, inspection_id: ObjectId) -> dict[str, Any] | None:
        try:
            return self.collection.find_one({"_id": inspection_id})
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def list_for_asset(self, asset_id: ObjectId) -> list[dict[str, Any]]:
        try:
            return list(
                self.collection.find({"asset_id": asset_id}).sort("created_at", -1)
            )
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class RiskAssessmentRepository:
    """Persist point-in-time baseline risk assessments."""

    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["risk_assessments"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or {
                **document,
                "_id": result.inserted_id,
            }
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get_latest_for_asset(self, asset_id: ObjectId) -> dict[str, Any] | None:
        try:
            records = list(
                self.collection.find({"asset_id": asset_id}).sort("assessed_at", -1)
            )
            return records[0] if records else None
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class InspectionMissionRepository:
    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["inspection_missions"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or document
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get(self, mission_id: ObjectId) -> dict[str, Any] | None:
        try:
            return self.collection.find_one({"_id": mission_id})
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def update(self, mission_id: ObjectId, updates: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.update_one(
                {"_id": mission_id},
                {"$set": updates},
            )
            if result.matched_count == 0:
                raise DatabaseUnavailableError("Mission record not found")
            return self.collection.find_one({"_id": mission_id}) or {}
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def list_for_asset(self, asset_id: ObjectId) -> list[dict[str, Any]]:
        try:
            return list(
                self.collection.find({"asset_id": asset_id}).sort("created_at", -1)
            )
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc


class MaintenanceTaskRepository:
    def __init__(self, database: Database[Mapping[str, Any]]) -> None:
        self.collection = database["maintenance_tasks"]

    def create(self, document: dict[str, Any]) -> dict[str, Any]:
        try:
            duplicate = self.collection.find_one(
                {"mission_id": document["mission_id"], "finding_id": document["finding_id"]}
            )
            if duplicate is not None:
                return duplicate
            result = self.collection.insert_one(document)
            return self.collection.find_one({"_id": result.inserted_id}) or document
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def get(self, task_id: ObjectId) -> dict[str, Any] | None:
        try:
            return self.collection.find_one({"_id": task_id})
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def update(self, task_id: ObjectId, updates: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.collection.update_one(
                {"_id": task_id},
                {"$set": updates},
            )
            if result.matched_count == 0:
                raise DatabaseUnavailableError("Task record not found")
            return self.collection.find_one({"_id": task_id}) or {}
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def list_for_asset(self, asset_id: ObjectId) -> list[dict[str, Any]]:
        try:
            return list(
                self.collection.find({"asset_id": asset_id}).sort("updated_at", -1)
            )
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc

    def list_all(self) -> list[dict[str, Any]]:
        try:
            return list(self.collection.find({}).sort("updated_at", -1))
        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc
