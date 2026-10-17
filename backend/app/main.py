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
    InspectionMissionRepository,
    InspectionRepository,
    MaintenanceTaskRepository,
    RiskAssessmentRepository,
)
from app.risk_service import assess_asset_risk
from app.schemas import (
    AssetCreate,
    AssetResponse,
    GemmaReport,
    IncidentResponse,
    InspectionResponse,
    InspectionMissionResponse,
    MaintenanceTaskCreate,
    MaintenanceTaskResponse,
    MaintenanceTaskUpdate,
    MissionFindingCreate,
    MissionUpdate,
    ReinspectionCreate,
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
    allow_methods=["GET", "POST", "PATCH"],
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


def _mission_response(document: dict[str, Any]) -> InspectionMissionResponse:
    return InspectionMissionResponse(
        id=str(document["_id"]),
        asset_id=str(document["asset_id"]),
        status=document["status"],
        checklist=document["checklist"],
        notes=document.get("notes"),
        findings=document.get("findings", []),
        inspection_ids=[str(value) for value in document.get("inspection_ids", [])],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


def _utc_response_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_response(document: dict[str, Any]) -> MaintenanceTaskResponse:
    return MaintenanceTaskResponse(
        id=str(document["_id"]),
        asset_id=str(document["asset_id"]),
        mission_id=str(document["mission_id"]),
        finding_id=str(document["finding_id"]),
        description=document["description"],
        priority=document["priority"],
        assignee=document.get("assignee"),
        due_date=document.get("due_date"),
        status=document["status"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
        completion_notes=document.get("completion_notes"),
        evidence_refs=document.get("evidence_refs", []),
        reinspection_required=document.get("reinspection_required", False),
        reinspection_status=document.get("reinspection_status", "not_required"),
        reinspection_notes=document.get("reinspection_notes"),
        reinspection_due_at=_utc_response_datetime(
            document.get("reinspection_due_at")
        ),
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


@app.get("/assets", response_model=list[AssetResponse])
def list_assets(request: Request) -> list[AssetResponse]:
    try:
        assets = AssetRepository(_connection(request).database).list_all()
        return [_asset_response(asset) for asset in assets]
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


def _record_object_id(value: str, label: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=400, detail=f"invalid {label} id") from exc


def _mission_checklist(asset: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"id": "opening-clear", "prompt": "Is the drain opening clear?", "completed": False},
        {"id": "debris-obstruction", "prompt": "Is debris obstructing water flow?", "completed": False},
        {"id": "standing-water", "prompt": "Is standing water present nearby?", "completed": False},
        {"id": "visible-damage", "prompt": "Are there visible signs of blockage or damage?", "completed": False},
        {"id": "photographs", "prompt": "Are photographs required to document the condition?", "completed": False},
        {"id": "maintenance-attention", "prompt": "Does the issue require maintenance-team attention?", "completed": False},
    ]


@app.post(
    "/assets/{asset_id}/inspection-missions",
    response_model=InspectionMissionResponse,
    status_code=201,
)
def create_inspection_mission(
    asset_id: str, request: Request
) -> InspectionMissionResponse:
    object_id = _object_id(asset_id)
    try:
        database = _connection(request).database
        if AssetRepository(database).get(object_id) is None:
            raise HTTPException(status_code=404, detail="asset not found")
        now = datetime.now(timezone.utc)
        document = {
            "_id": ObjectId(),
            "asset_id": object_id,
            "status": "planned",
            "checklist": _mission_checklist({}),
            "findings": [],
            "inspection_ids": [],
            "created_at": now,
            "updated_at": now,
        }
        created = InspectionMissionRepository(database).create(document)
        return _mission_response(created)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get(
    "/assets/{asset_id}/inspection-missions",
    response_model=list[InspectionMissionResponse],
)
def list_asset_missions(asset_id: str, request: Request) -> list[InspectionMissionResponse]:
    object_id = _object_id(asset_id)
    try:
        missions = InspectionMissionRepository(_connection(request).database).list_for_asset(
            object_id
        )
        return [_mission_response(mission) for mission in missions]
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/inspection-missions/{mission_id}", response_model=InspectionMissionResponse)
def get_inspection_mission(mission_id: str, request: Request) -> InspectionMissionResponse:
    object_id = _record_object_id(mission_id, "mission")
    try:
        mission = InspectionMissionRepository(_connection(request).database).get(object_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="inspection mission not found")
        return _mission_response(mission)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.patch("/inspection-missions/{mission_id}", response_model=InspectionMissionResponse)
def update_inspection_mission(
    mission_id: str, payload: MissionUpdate, request: Request
) -> InspectionMissionResponse:
    object_id = _record_object_id(mission_id, "mission")
    try:
        repository = InspectionMissionRepository(_connection(request).database)
        mission = repository.get(object_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="inspection mission not found")
        updates = payload.model_dump(exclude_none=True)
        if "checklist" in updates:
            known = {item["id"] for item in mission["checklist"]}
            if {item["id"] for item in updates["checklist"]} != known:
                raise HTTPException(status_code=422, detail="checklist items do not match mission")
        if "status" in updates:
            current = mission["status"]
            allowed = {
                "planned": {"planned", "in_progress"},
                "in_progress": {"in_progress", "completed"},
                "completed": {"completed"},
            }
            if updates["status"] not in allowed[current]:
                raise HTTPException(status_code=422, detail="invalid mission status transition")
        updates["updated_at"] = datetime.now(timezone.utc)
        return _mission_response(repository.update(object_id, updates))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/inspection-missions/{mission_id}/findings",
    response_model=InspectionMissionResponse,
    status_code=201,
)
def add_mission_finding(
    mission_id: str, payload: MissionFindingCreate, request: Request
) -> InspectionMissionResponse:
    mission_object_id = _record_object_id(mission_id, "mission")
    try:
        database = _connection(request).database
        repository = InspectionMissionRepository(database)
        mission = repository.get(mission_object_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="inspection mission not found")
        if payload.checklist_item_id not in {item["id"] for item in mission["checklist"]}:
            raise HTTPException(status_code=422, detail="checklist item does not exist")
        if payload.inspection_id is not None:
            _record_object_id(payload.inspection_id, "inspection")
        finding = {
            "id": str(ObjectId()),
            "checklist_item_id": payload.checklist_item_id,
            "description": payload.description,
            "inspection_id": payload.inspection_id,
            "evidence_refs": payload.evidence_refs,
            "approved": False,
            "created_at": datetime.now(timezone.utc),
        }
        findings = [*mission.get("findings", []), finding]
        updated = repository.update(
            mission_object_id,
            {"findings": findings, "status": "in_progress", "updated_at": datetime.now(timezone.utc)},
        )
        return _mission_response(updated)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/inspection-missions/{mission_id}/findings/{finding_id}/approve",
    response_model=InspectionMissionResponse,
)
def approve_mission_finding(
    mission_id: str, finding_id: str, request: Request
) -> InspectionMissionResponse:
    mission_object_id = _record_object_id(mission_id, "mission")
    try:
        repository = InspectionMissionRepository(_connection(request).database)
        mission = repository.get(mission_object_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="inspection mission not found")
        findings = mission.get("findings", [])
        if not any(finding["id"] == finding_id for finding in findings):
            raise HTTPException(status_code=404, detail="finding not found")
        for finding in findings:
            if finding["id"] == finding_id:
                finding["approved"] = True
                finding["approved_at"] = datetime.now(timezone.utc)
        return _mission_response(
            repository.update(
                mission_object_id,
                {"findings": findings, "updated_at": datetime.now(timezone.utc)},
            )
        )
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/maintenance-tasks",
    response_model=MaintenanceTaskResponse,
    status_code=201,
)
def create_maintenance_task(
    payload: MaintenanceTaskCreate, request: Request
) -> MaintenanceTaskResponse:
    asset_object_id = _object_id(payload.asset_id)
    mission_object_id = _record_object_id(payload.mission_id, "mission")
    try:
        database = _connection(request).database
        if AssetRepository(database).get(asset_object_id) is None:
            raise HTTPException(status_code=404, detail="asset not found")
        mission = InspectionMissionRepository(database).get(mission_object_id)
        if mission is None or mission["asset_id"] != asset_object_id:
            raise HTTPException(status_code=404, detail="inspection mission not found")
        finding = next(
            (item for item in mission.get("findings", []) if item["id"] == payload.finding_id),
            None,
        )
        if finding is None:
            raise HTTPException(status_code=404, detail="finding not found")
        if not finding.get("approved", False):
            raise HTTPException(status_code=409, detail="finding requires human approval")
        now = datetime.now(timezone.utc)
        document = {
            "_id": ObjectId(),
            "asset_id": asset_object_id,
            "mission_id": mission_object_id,
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
        task = MaintenanceTaskRepository(database).create(document)
        return _task_response(task)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/maintenance-tasks", response_model=list[MaintenanceTaskResponse])
def list_maintenance_tasks(request: Request) -> list[MaintenanceTaskResponse]:
    try:
        tasks = MaintenanceTaskRepository(_connection(request).database).list_all()
        return [_task_response(task) for task in tasks]
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get(
    "/assets/{asset_id}/maintenance-tasks",
    response_model=list[MaintenanceTaskResponse],
)
def list_asset_maintenance_tasks(
    asset_id: str, request: Request
) -> list[MaintenanceTaskResponse]:
    object_id = _object_id(asset_id)
    try:
        tasks = MaintenanceTaskRepository(_connection(request).database).list_for_asset(
            object_id
        )
        return [_task_response(task) for task in tasks]
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.get("/maintenance-tasks/{task_id}", response_model=MaintenanceTaskResponse)
def get_maintenance_task(task_id: str, request: Request) -> MaintenanceTaskResponse:
    object_id = _record_object_id(task_id, "task")
    try:
        task = MaintenanceTaskRepository(_connection(request).database).get(object_id)
        if task is None:
            raise HTTPException(status_code=404, detail="maintenance task not found")
        return _task_response(task)
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.patch("/maintenance-tasks/{task_id}", response_model=MaintenanceTaskResponse)
def update_maintenance_task(
    task_id: str, payload: MaintenanceTaskUpdate, request: Request
) -> MaintenanceTaskResponse:
    object_id = _record_object_id(task_id, "task")
    try:
        repository = MaintenanceTaskRepository(_connection(request).database)
        task = repository.get(object_id)
        if task is None:
            raise HTTPException(status_code=404, detail="maintenance task not found")
        updates = payload.model_dump(exclude_none=True)
        if "status" in updates:
            current = task["status"]
            allowed = {
                "pending": {"pending", "in_progress"},
                "in_progress": {"in_progress", "completed"},
                "completed": {"completed"},
            }
            if updates["status"] not in allowed[current]:
                raise HTTPException(status_code=422, detail="invalid task status transition")
        updates["updated_at"] = datetime.now(timezone.utc)
        return _task_response(repository.update(object_id, updates))
    except DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc


@app.post(
    "/maintenance-tasks/{task_id}/reinspection",
    response_model=MaintenanceTaskResponse,
)
def schedule_reinspection(
    task_id: str, payload: ReinspectionCreate, request: Request
) -> MaintenanceTaskResponse:
    object_id = _record_object_id(task_id, "task")
    try:
        repository = MaintenanceTaskRepository(_connection(request).database)
        if repository.get(object_id) is None:
            raise HTTPException(status_code=404, detail="maintenance task not found")
        updates = {
            "reinspection_required": True,
            "reinspection_status": "scheduled",
            "reinspection_notes": payload.notes,
            "updated_at": datetime.now(timezone.utc),
        }
        if payload.reinspection_due_at is not None:
            updates["reinspection_due_at"] = payload.reinspection_due_at
        return _task_response(repository.update(object_id, updates))
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
