from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException, Request, status
from bson import ObjectId
from bson.errors import InvalidId

from app.config import get_settings
from app.database import DatabaseUnavailableError, MongoConnection
from app.gemma_service import (
    MAX_IMAGE_BYTES,
    SUPPORTED_IMAGE_TYPES,
    GemmaService,
    GemmaServiceError,
)
from app.repositories import (
    AssetRepository,
    IncidentRepository,
    InspectionRepository,
    RiskAssessmentRepository,
)
from app.risk_service import assess_asset_risk
from app.schemas import (
    AssetCreate,
    AssetResponse,
    GemmaReport,
    IncidentResponse,
    InspectionResponse,
    RiskAssessmentResponse,
)

settings = get_settings()
logger = logging.getLogger(__name__)

def _is_jpeg(data: bytes) -> bool:
    return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")


def _is_png(data: bytes) -> bool:
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        and b"IEND" in data[-16:]
    )


def _is_webp(data: bytes) -> bool:
    return (
        len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
        and int.from_bytes(data[4:8], "little") + 8 <= len(data)
    )


IMAGE_SIGNATURES = {
    "image/jpeg": _is_jpeg,
    "image/png": _is_png,
    "image/webp": _is_webp,
}


@asynccontextmanager
async def lifespan(application: FastAPI):
    connection = MongoConnection(settings)
    connection.connect()
    gemma = GemmaService(settings)
    try:
        connection.ensure_indexes()
    except DatabaseUnavailableError:
        pass
    application.state.mongo = connection
    application.state.gemma = gemma
    try:
        yield
    finally:
        gemma.close()
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


def _inspection_response(document: dict[str, Any]) -> InspectionResponse:
    report = document.get("report")
    return InspectionResponse(
        id=str(document["_id"]),
        asset_id=str(document["asset_id"]),
        status=document["status"],
        created_at=document["created_at"],
        updated_at=document.get("updated_at"),
        content_type=document.get("content_type"),
        byte_size=document.get("byte_size"),
        sha256=document.get("sha256"),
        report=GemmaReport.model_validate(report) if report else None,
        error_code=document.get("error_code"),
    )


def _risk_response(document: dict[str, Any]) -> RiskAssessmentResponse:
    return RiskAssessmentResponse(
        id=str(document["_id"]),
        asset_id=str(document["asset_id"]),
        assessed_at=document["assessed_at"],
        priority=document["priority"],
        score=document["score"],
        evidence=document["evidence"],
        data_quality_warnings=document["data_quality_warnings"],
        requires_human_review=True,
        method=document["method"],
        method_version=document["method_version"],
    )


def _gemma_service(request: Request) -> GemmaService:
    service = getattr(request.app.state, "gemma", None)
    if not isinstance(service, GemmaService):
        raise HTTPException(status_code=503, detail="image analysis unavailable")
    return service


async def _read_image(file: UploadFile) -> tuple[bytes, str]:
    content_type = file.content_type or ""
    if content_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="unsupported image type; upload JPEG, PNG, or WebP",
        )

    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="image file is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="image exceeds the 5 MB limit")
    signature_check = IMAGE_SIGNATURES[content_type]
    if not signature_check(image_bytes):
        raise HTTPException(status_code=400, detail="image content does not match its type")
    return image_bytes, content_type


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


@app.get(
    "/assets/{asset_id}/inspections",
    response_model=list[InspectionResponse],
)
def get_asset_inspections(
    asset_id: str, request: Request
) -> list[InspectionResponse]:
    object_id = _object_id(asset_id)
    try:
        inspections = InspectionRepository(_connection(request).database).list_for_asset(
            object_id
        )
        return [_inspection_response(inspection) for inspection in inspections]
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/assets/{asset_id}/risk-assessments",
    response_model=RiskAssessmentResponse,
    status_code=201,
)
def create_asset_risk_assessment(
    asset_id: str, request: Request
) -> RiskAssessmentResponse:
    object_id = _object_id(asset_id)
    try:
        database = _connection(request).database
        asset = AssetRepository(database).get(object_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        incidents = IncidentRepository(database).list_for_asset(object_id)
        inspections = InspectionRepository(database).list_for_asset(object_id)
        document = assess_asset_risk(
            str(object_id),
            incidents,
            inspections,
        )
        document["asset_id"] = object_id
        document["_id"] = ObjectId()
        created = RiskAssessmentRepository(database).create(document)
        return _risk_response(created)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get(
    "/assets/{asset_id}/risk-assessments/latest",
    response_model=RiskAssessmentResponse,
)
def get_latest_asset_risk_assessment(
    asset_id: str, request: Request
) -> RiskAssessmentResponse:
    object_id = _object_id(asset_id)
    try:
        database = _connection(request).database
        if AssetRepository(database).get(object_id) is None:
            raise HTTPException(status_code=404, detail="asset not found")
        assessment = RiskAssessmentRepository(database).get_latest_for_asset(object_id)
        if assessment is None:
            raise HTTPException(status_code=404, detail="risk assessment not found")
        return _risk_response(assessment)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/assets/{asset_id}/inspections",
    response_model=InspectionResponse,
    status_code=201,
)
async def create_asset_inspection(
    asset_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> InspectionResponse:
    object_id = _object_id(asset_id)
    image_bytes, content_type = await _read_image(file)
    connection = _connection(request)
    try:
        database = connection.database
        asset = AssetRepository(database).get(object_id)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    now = datetime.now(timezone.utc)
    inspection_id = ObjectId()
    document = {
        "_id": inspection_id,
        "asset_id": object_id,
        "status": "pending",
        "content_type": content_type,
        "byte_size": len(image_bytes),
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "created_at": now,
        "updated_at": now,
    }
    inspections = InspectionRepository(database)
    try:
        created = inspections.create(document)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc

    try:
        report = _gemma_service(request).analyze_image(
            image_bytes,
            content_type,
            asset,
        )
    except GemmaServiceError as exc:
        failed_at = datetime.now(timezone.utc)
        try:
            inspections.update(
                inspection_id,
                {
                    "status": "failed",
                    "error_code": exc.code,
                    "updated_at": failed_at,
                },
            )
        except DatabaseUnavailableError as update_exc:
            logger.error("Inspection %s failure state could not be saved", inspection_id)
            raise HTTPException(
                status_code=503,
                detail="inspection result could not be saved",
            ) from update_exc
        _raise_inspection_error(
            429 if exc.code == "provider_quota_exceeded" else 502,
            exc.code,
        )
    except Exception as exc:
        logger.error("Inspection %s provider call failed", inspection_id)
        try:
            inspections.update(
                inspection_id,
                {
                    "status": "failed",
                    "error_code": "provider_unavailable",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
        except DatabaseUnavailableError as update_exc:
            logger.error("Inspection %s failure state could not be saved", inspection_id)
            raise HTTPException(
                status_code=503,
                detail="inspection result could not be saved",
            ) from update_exc
        raise HTTPException(
            status_code=502,
            detail="image analysis is temporarily unavailable",
        ) from exc

    completed_at = datetime.now(timezone.utc)
    report = report.model_copy(update={"requires_human_review": True})
    try:
        inspections.update(
            inspection_id,
            {
                "status": "completed",
                "report": report.model_dump(),
                "updated_at": completed_at,
            },
        )
    except DatabaseUnavailableError as exc:
        logger.error("Inspection %s completed state could not be saved", inspection_id)
        raise HTTPException(
            status_code=503,
            detail="inspection result could not be saved",
        ) from exc
    return _inspection_response(
        {**created, "status": "completed", "report": report.model_dump(), "updated_at": completed_at}
    )


def _raise_inspection_error(http_status: int, error_code: str) -> None:
    messages = {
        "provider_quota_exceeded": "image analysis quota or rate limit was reached",
        "provider_auth_error": "image analysis authentication failed",
    }
    raise HTTPException(
        status_code=http_status,
        detail=messages.get(error_code, "image analysis failed"),
    )


@app.get("/inspections/{inspection_id}", response_model=InspectionResponse)
def get_inspection(inspection_id: str, request: Request) -> InspectionResponse:
    inspection_object_id = _object_id(inspection_id)
    try:
        inspection = InspectionRepository(_connection(request).database).get(
            inspection_object_id
        )
        if inspection is None:
            raise HTTPException(status_code=404, detail="inspection not found")
        return _inspection_response(inspection)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
