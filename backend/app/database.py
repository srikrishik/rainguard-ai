
from collections.abc import Mapping
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import Settings


class DatabaseUnavailableError(RuntimeError):
    """Raised when MongoDB cannot serve an application operation."""


class MongoConnection:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: MongoClient[Mapping[str, Any]] | None = None
        self._database: Database[Mapping[str, Any]] | None = None

    def connect(self) -> None:
        if not self._settings.mongodb_uri or not self._settings.database_name:
            return

        self._client = MongoClient(
            self._settings.mongodb_uri,
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
        )
        self._database = self._client[self._settings.database_name]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None

    @property
    def database(self) -> Database[Mapping[str, Any]]:
        if self._database is None:
            raise DatabaseUnavailableError
        return self._database

    def ping(self) -> bool:
        try:
            self.database.command("ping")
            return True
        except (DatabaseUnavailableError, PyMongoError):
            return False

    def ensure_indexes(self) -> None:
        try:
            database = self.database

            # Existing indexes
            database["societies"].create_index(
                [("name", ASCENDING)],
                unique=True,
            )
            database["assets"].create_index(
                [("society_id", ASCENDING)]
            )
            database["incidents"].create_index(
                [
                    ("asset_id", ASCENDING),
                    ("occurred_at", DESCENDING),
                ]
            )

            # Phase 4: inspection history by asset
            database["inspections"].create_index(
                [
                    ("asset_id", ASCENDING),
                    ("created_at", DESCENDING),
                ]
            )
            database["risk_assessments"].create_index(
                [
                    ("asset_id", ASCENDING),
                    ("assessed_at", DESCENDING),
                ]
            )

        except PyMongoError as exc:
            raise DatabaseUnavailableError from exc
