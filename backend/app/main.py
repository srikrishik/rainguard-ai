from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, Request, status
from bson import ObjectId
from bson.errors import InvalidId

from app.config import get_settings
from app.database import DatabaseUnavailableError, MongoConnection
from app.repositories import AssetRepository, IncidentRepository
from app.schemas import AssetCreate, AssetResponse, IncidentResponse

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    connection = MongoConnection(settings)
    connection.connect()
    try:
        connection.ensure_indexes()
    except DatabaseUnavailableError:
        pass
    application.state.mongo = connection
    try:
        yield
    finally:
        connection.close()


app = FastAPI(title="RainGuard AI API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rainguard-api"}


@app.get("/ready")
def ready(request: Request) -> dict[str, str]:
    connection = _connection(request)
    if not connection.ping():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    try:
        connection.ensure_indexes()
    except DatabaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from exc
    return {"status": "ready", "service": "rainguard-api"}


def _connection(request: Request) -> MongoConnection:
    connection = getattr(request.app.state, "mongo", None)
    if not isinstance(connection, MongoConnection):
        raise HTTPException(status_code=503, detail="database unavailable")
    return connection


def _object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail="invalid asset id") from exc


def _asset_response(document: dict[str, Any]) -> AssetResponse:
    return AssetResponse(
        id=str(document["_id"]),
        society_id=document["society_id"],
        name=document["name"],
        location=document.get("location"),
        description=document.get("description"),
    )


@app.post("/assets", response_model=AssetResponse, status_code=201)
def create_asset(payload: AssetCreate, request: Request) -> AssetResponse:
    try:
        document = payload.model_dump(exclude_none=True)
        document["created_at"] = datetime.now(timezone.utc)
        created = AssetRepository(_connection(request).database).create(document)
        return _asset_response(created)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/assets/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: str, request: Request) -> AssetResponse:
    try:
        asset = AssetRepository(_connection(request).database).get(_object_id(asset_id))
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return _asset_response(asset)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/assets/{asset_id}/incidents", response_model=list[IncidentResponse])
def get_asset_incidents(
    asset_id: str, request: Request
) -> list[IncidentResponse]:
    try:
        incidents = IncidentRepository(_connection(request).database).list_for_asset(
            _object_id(asset_id)
        )
        return [
            IncidentResponse(
                id=str(incident["_id"]),
                asset_id=str(incident["asset_id"]),
                occurred_at=incident["occurred_at"],
                summary=incident["summary"],
            )
            for incident in incidents
        ]
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
