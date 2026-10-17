
import base64
import json

import httpx
import pytest

from app.config import Settings
from app.gemma_service import GemmaService, GemmaServiceError
from app.schemas import GemmaReport


VALID_REPORT = {
    "summary": "Standing water and debris are visible near the drain.",
    "observations": [
        {
            "description": "Debris is visible near the drain opening.",
            "concern": "moderate",
        }
    ],
    "severity": "moderate",
    "confidence": "medium",
    "recommended_actions": [
        "Have maintenance staff inspect and clear the drain if safe."
    ],
    "requires_human_review": True,
}


def make_settings() -> Settings:
    return Settings(
        gemma_api_key="test-key",
        gemma_api_url=(
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemma-4-26b-a4b-it:generateContent"
        ),
        gemma_model_id="gemma-4-26b-a4b-it",
    )


def make_response(report: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(report)}]
                    }
                }
            ]
        },
    )


def make_parts_response(parts: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": parts,
                        "role": "model",
                    },
                    "finishReason": "STOP",
                }
            ]
        },
    )


def make_service(handler) -> GemmaService:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GemmaService(settings=make_settings(), client=client)


def test_successful_image_analysis_sends_image_and_validates_report():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        image_part = payload["contents"][0]["parts"][1]["inline_data"]

        assert image_part["mime_type"] == "image/png"
        assert base64.b64decode(image_part["data"]) == b"fake-png-bytes"
        assert request.headers["x-goog-api-key"] == "test-key"

        return make_response(VALID_REPORT)

    service = make_service(handler)
    report = service.analyze_image(
        b"fake-png-bytes",
        "image/png",
        {"name": "Gate 2 Stormwater Drain"},
    )

    assert report.summary == VALID_REPORT["summary"]
    assert report.requires_human_review is True


def test_thought_part_is_ignored_in_favor_of_final_report():
    service = make_service(
        lambda request: make_parts_response(
            [
                {"text": "Internal reasoning that is not a report.", "thought": True},
                {"text": json.dumps(VALID_REPORT)},
            ]
        )
    )

    report = service.analyze_image(b"image", "image/png", {})

    assert report == GemmaReport.model_validate(VALID_REPORT)
    assert report.requires_human_review is True


def test_multiple_non_thought_text_parts_use_first_valid_report():
    service = make_service(
        lambda request: make_parts_response(
            [
                {"text": "A preliminary response, not JSON."},
                {"text": json.dumps(VALID_REPORT)},
            ]
        )
    )

    report = service.analyze_image(b"image", "image/png", {})

    assert report.summary == VALID_REPORT["summary"]


def test_empty_image_is_rejected_before_provider_call():
    service = make_service(
        lambda request: pytest.fail("Provider should not be called")
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"", "image/png", {})

    assert exc_info.value.code == "invalid_image"


def test_unsupported_content_type_is_rejected():
    service = make_service(
        lambda request: pytest.fail("Provider should not be called")
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"some bytes", "image/gif", {})

    assert exc_info.value.code == "unsupported_image_type"


def test_quota_error_is_sanitized():
    service = make_service(
        lambda request: httpx.Response(429, json={"error": {"message": "private"}})
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "provider_quota_exceeded"
    assert "private" not in str(exc_info.value)


def test_authentication_error_is_sanitized():
    service = make_service(
        lambda request: httpx.Response(403, json={"error": {"message": "private"}})
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "provider_auth_error"
    assert "private" not in str(exc_info.value)


def test_timeout_is_mapped_to_safe_error():
    def handler(request):
        raise httpx.ReadTimeout("private timeout details")

    service = make_service(handler)

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "provider_timeout"
    assert "private" not in str(exc_info.value)


def test_provider_failure_is_mapped_to_safe_error():
    service = make_service(
        lambda request: httpx.Response(503, json={"error": {"message": "private"}})
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "provider_unavailable"
    assert "private" not in str(exc_info.value)


def test_invalid_model_report_is_rejected():
    service = make_service(
        lambda request: make_response({"summary": "Incomplete response"})
    )

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "invalid_provider_response"


def test_unexpected_response_envelope_is_logged_without_provider_content(caplog):
    service = make_service(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"unexpected": {"private": "provider detail"}},
        )
    )

    with caplog.at_level("WARNING"):
        with pytest.raises(GemmaServiceError) as exc_info:
            service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "invalid_provider_response"
    assert "category=response_envelope" in caplog.text
    assert "status=200" in caplog.text
    assert "content_type=application/json" in caplog.text
    assert "private" not in caplog.text
    assert "provider detail" not in caplog.text


def test_invalid_report_json_is_logged_as_decode_failure(caplog):
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "not json"}],
                    }
                }
            ]
        },
    )
    service = make_service(lambda request: response)

    with caplog.at_level("WARNING"):
        with pytest.raises(GemmaServiceError) as exc_info:
            service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "invalid_provider_response"
    assert "category=report_json_decode" in caplog.text
    assert "'first_part_keys': ['text']" in caplog.text
    assert "not json" not in caplog.text


def test_invalid_report_schema_is_logged_as_validation_failure(caplog):
    service = make_service(lambda request: make_response({"summary": "Incomplete"}))

    with caplog.at_level("WARNING"):
        with pytest.raises(GemmaServiceError) as exc_info:
            service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "invalid_provider_response"
    assert "category=report_validation" in caplog.text
    assert "Incomplete" not in caplog.text


def test_json_code_fence_is_accepted_without_relaxing_report_validation():
    def handler(request: httpx.Request) -> httpx.Response:
        response = make_response(VALID_REPORT)
        response_json = response.json()
        response_json["candidates"][0]["content"]["parts"][0]["text"] = (
            "```json\n"
            + json.dumps(VALID_REPORT)
            + "\n```"
        )
        return httpx.Response(200, json=response_json)

    service = make_service(handler)

    report = service.analyze_image(b"image", "image/png", {})

    assert report == GemmaReport.model_validate(VALID_REPORT)


@pytest.mark.parametrize(
    "response_text",
    [
        "The image shows a drain.",
        "```json\n{\"summary\": \"missing fields\"}\n```",
        '{"summary": "valid JSON in the wrong response envelope"} extra',
    ],
)
def test_non_structured_or_incomplete_model_text_is_rejected(response_text):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": response_text}],
                        }
                    }
                ]
            },
        )

    service = make_service(handler)

    with pytest.raises(GemmaServiceError) as exc_info:
        service.analyze_image(b"image", "image/png", {})

    assert exc_info.value.code == "invalid_provider_response"


def test_model_cannot_disable_human_review():
    report_data = {**VALID_REPORT, "requires_human_review": False}
    service = make_service(lambda request: make_response(report_data))

    report = service.analyze_image(b"image", "image/png", {})

    assert report.requires_human_review is True
