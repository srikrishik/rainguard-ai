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
