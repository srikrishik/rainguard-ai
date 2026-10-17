from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas import RiskAssessmentResponse


METHOD = "rule_based_asset_risk_baseline"
METHOD_VERSION = "phase-5a-v1"
RECENT_INCIDENT_DAYS = 30
RECENT_INSPECTION_DAYS = 90


def _as_utc(value: Any) -> datetime | None:
    """Normalize database timestamps for safe point-in-time comparisons."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _completed_inspections(inspections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        inspection
        for inspection in inspections
        if inspection.get("status") == "completed" and inspection.get("report")
    ]


def assess_asset_risk(
    asset_id: str,
    incidents: list[dict[str, Any]],
    inspections: list[dict[str, Any]],
    assessed_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a transparent, provisional assessment using only point-in-time data."""
    assessed_at = _as_utc(assessed_at) or datetime.now(timezone.utc)
    cutoff = assessed_at - timedelta(days=RECENT_INCIDENT_DAYS)
    inspection_cutoff = assessed_at - timedelta(days=RECENT_INSPECTION_DAYS)
    evidence: list[str] = []
    warnings: list[str] = []
    score = 0

    recent_incidents = [
        incident
        for incident in incidents
        if (occurred_at := _as_utc(incident.get("occurred_at"))) is not None
        and occurred_at >= cutoff
        and occurred_at <= assessed_at
    ]
    if recent_incidents:
        evidence.append(
            f"{len(recent_incidents)} incident(s) recorded in the last "
            f"{RECENT_INCIDENT_DAYS} days"
        )
        score += 4 if len(recent_incidents) >= 2 else 2
    elif incidents:
        evidence.append("No incidents recorded in the recent assessment window")
        warnings.append("Incident history exists, but no recent incident was found")
    else:
        warnings.append("No incident history is available")

    completed = _completed_inspections(inspections)
    if completed:
        latest = max(
            completed,
            key=lambda inspection: (
                _as_utc(inspection.get("created_at")) or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
        )
        report = latest["report"]
        severity = report.get("severity", "unknown")
        if severity == "high":
            score += 4
            evidence.append("Latest completed inspection reports high severity")
        elif severity == "moderate":
            score += 2
            evidence.append("Latest completed inspection reports moderate severity")
        elif severity == "low":
            evidence.append("Latest completed inspection reports low severity")
        else:
            warnings.append("Latest completed inspection has unknown severity")

        concerns = {
            observation.get("concern")
            for observation in report.get("observations", [])
        }
        if "high" in concerns:
            score += 2
            evidence.append("Latest completed inspection contains a high concern observation")
        elif "moderate" in concerns:
            score += 1
            evidence.append(
                "Latest completed inspection contains a moderate concern observation"
            )

        created_at = _as_utc(latest.get("created_at"))
        if created_at is None or created_at < inspection_cutoff:
            warnings.append(
                f"No completed inspection is available within the last "
                f"{RECENT_INSPECTION_DAYS} days"
            )
    else:
        warnings.append("No completed inspection evidence is available")

    if not evidence:
        warnings.append("Insufficient evidence for a low-priority classification")

    if score >= 5:
        priority, ordinal = "high", 3
    elif score >= 2:
        priority, ordinal = "medium", 2
    else:
        priority, ordinal = "low", 1

    if not completed and not recent_incidents:
        priority, ordinal = "medium", 2
        evidence.append("Priority held at medium because available evidence is incomplete")

    return {
        "asset_id": asset_id,
        "assessed_at": assessed_at,
        "priority": priority,
        "score": score,
        "evidence": evidence,
        "data_quality_warnings": warnings,
        "requires_human_review": True,
        "method": METHOD,
        "method_version": METHOD_VERSION,
    }
