
import base64
import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import GemmaReport

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _parse_report_text(response_text: str) -> GemmaReport:
    """Parse raw or completely fenced JSON without accepting surrounding prose."""
    normalized = response_text.strip()
    lines = normalized.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        normalized = "\n".join(lines[1:-1]).strip()
    return GemmaReport.model_validate(json.loads(normalized))


class StructuredOutputError(ValueError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


def _extract_report(parts: Any) -> GemmaReport:
    if not isinstance(parts, list):
        raise StructuredOutputError("response_envelope")

    report_texts = [
        part["text"]
        for part in parts
        if (
            isinstance(part, dict)
            and isinstance(part.get("text"), str)
            and not part.get("thought", False)
        )
    ]
    if not report_texts:
        raise StructuredOutputError("response_envelope")

    categories: list[str] = []
    for response_text in report_texts:
        try:
            return _parse_report_text(response_text)
        except json.JSONDecodeError:
            categories.append("report_json_decode")
        except ValidationError:
            categories.append("report_validation")

    if categories and all(category == "report_validation" for category in categories):
        raise StructuredOutputError("report_validation")
    if categories and all(category == "report_json_decode" for category in categories):
        raise StructuredOutputError("report_json_decode")
    raise StructuredOutputError("report_content_invalid")


def _response_structure(payload: Any) -> dict[str, Any]:
    """Describe response shape without including provider-generated content."""
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}

    structure: dict[str, Any] = {
        "payload_type": "object",
        "top_level_keys": sorted(str(key) for key in payload),
    }
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        structure["candidates_type"] = type(candidates).__name__
        return structure

    structure["candidate_count"] = len(candidates)
    if not candidates or not isinstance(candidates[0], dict):
        structure["first_candidate_type"] = (
            type(candidates[0]).__name__ if candidates else "missing"
        )
        return structure

    candidate = candidates[0]
    structure["candidate_keys"] = sorted(str(key) for key in candidate)
    content = candidate.get("content")
    if not isinstance(content, dict):
        structure["content_type"] = type(content).__name__
        return structure

    structure["content_keys"] = sorted(str(key) for key in content)
    parts = content.get("parts")
    structure["parts_type"] = type(parts).__name__
    if isinstance(parts, list):
        structure["part_count"] = len(parts)
        if parts and isinstance(parts[0], dict):
            structure["first_part_keys"] = sorted(str(key) for key in parts[0])
    return structure


class GemmaServiceError(RuntimeError):
    """Safe, user-facing category for a hosted Gemma failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class GemmaService:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def analyze_image(
        self,
        image_bytes: bytes,
        content_type: str,
        asset_context: dict[str, Any],
    ) -> GemmaReport:
        if not image_bytes:
            raise GemmaServiceError("invalid_image", "The image is empty.")

        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise GemmaServiceError(
                "image_too_large",
                "The image exceeds the 5 MB upload limit.",
            )

        if content_type not in SUPPORTED_IMAGE_TYPES:
            raise GemmaServiceError(
                "unsupported_image_type",
                "Upload a JPEG, PNG, or WebP image.",
            )

        if not self.settings.gemma_api_key:
            raise GemmaServiceError(
                "provider_not_configured",
                "The image analysis service is not configured.",
            )

        if not self.settings.gemma_api_url or not self.settings.gemma_model_id:
            raise GemmaServiceError(
                "provider_not_configured",
                "The image analysis service is not configured.",
            )

        prompt = {
            "task": (
                "Inspect this maintenance photo for visible drainage or "
                "stormwater concerns. Report only what can reasonably be "
                "observed. Do not infer hidden conditions or predict flooding "
                "from the image alone. Recommendations are advisory and must "
                "be reviewed by a person."
            ),
            "asset": {
                "name": str(asset_context.get("name", ""))[:200],
                "location": str(asset_context.get("location") or "")[:500],
                "description": str(asset_context.get("description") or "")[:1000],
            },
            "required_json_schema": {
                "summary": "string",
                "observations": [
                    {
                        "description": "string",
                        "concern": "low | moderate | high | unknown",
                    }
                ],
                "severity": "low | moderate | high | unknown",
                "confidence": "low | medium | high | unknown",
                "recommended_actions": ["string"],
                "requires_human_review": True,
            },
            "rules": [
                "Return only a JSON object matching the requested structure.",
                "Use unknown when the photo does not support a conclusion.",
                "Always set requires_human_review to true.",
            ],
        }

        request_body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": json.dumps(prompt)},
                        {
                            "inline_data": {
                                "mime_type": content_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        try:
            response = self.client.post(
                self.settings.gemma_api_url,
                headers={
                    "x-goog-api-key": self.settings.gemma_api_key,
                    "Content-Type": "application/json",
                },
                json=request_body,
            )
        except httpx.TimeoutException as exc:
            raise GemmaServiceError(
                "provider_timeout",
                "Image analysis timed out. Please try again.",
            ) from exc
        except httpx.RequestError as exc:
            raise GemmaServiceError(
                "provider_unavailable",
                "Image analysis is temporarily unavailable.",
            ) from exc

        if response.status_code in (401, 403):
            raise GemmaServiceError(
                "provider_auth_error",
                "Image analysis authentication failed.",
            )

        if response.status_code == 429:
            raise GemmaServiceError(
                "provider_quota_exceeded",
                "Image analysis quota or rate limit was reached.",
            )

        if response.status_code >= 500:
            raise GemmaServiceError(
                "provider_unavailable",
                "Image analysis is temporarily unavailable.",
            )

        if response.status_code >= 400:
            raise GemmaServiceError(
                "provider_request_rejected",
                "The image analysis provider rejected the request.",
            )

        response_content_type = response.headers.get("content-type", "missing")
        try:
            payload = response.json()
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Gemma response rejected: status=%s content_type=%s "
                "structure=unparseable category=response_json_decode",
                response.status_code,
                response_content_type,
            )
            raise GemmaServiceError(
                "invalid_provider_response",
                "Image analysis returned an invalid report.",
            ) from exc

        structure = _response_structure(payload)
        logger.info(
            "Gemma response received: status=%s content_type=%s structure=%s",
            response.status_code,
            response_content_type,
            structure,
        )
        try:
            candidates = payload["candidates"]
            parts = candidates[0]["content"]["parts"]
            report = _extract_report(parts)
        except (KeyError, IndexError, TypeError, StopIteration) as exc:
            logger.warning(
                "Gemma response rejected: status=%s content_type=%s "
                "structure=%s category=response_envelope",
                response.status_code,
                response_content_type,
                structure,
            )
            raise GemmaServiceError(
                "invalid_provider_response",
                "Image analysis returned an invalid report.",
            ) from exc
        except StructuredOutputError as exc:
            logger.warning(
                "Gemma response rejected: status=%s content_type=%s "
                "structure=%s category=%s",
                response.status_code,
                response_content_type,
                structure,
                exc.category,
            )
            raise GemmaServiceError(
                "invalid_provider_response",
                "Image analysis returned an invalid report.",
            ) from exc

        # Human review is mandatory, even if the model says otherwise.
        return report.model_copy(update={"requires_human_review": True})
