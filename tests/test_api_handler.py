"""Unit tests for the HTTP chat adapter (issue #20)."""

from __future__ import annotations

import base64
import json

import pytest

from supportrouter import api


def _event(body: str | None, *, is_base64: bool = False) -> dict:
    return {
        "requestContext": {"http": {"method": "POST", "path": "/chat"}},
        "isBase64Encoded": is_base64,
        "body": body,
    }


def test_valid_message_returns_200_with_agent_fields() -> None:
    event = _event(json.dumps({"message": "Where is my order VE-1001?"}))
    response = api.handle_chat_request(event, None)

    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    body = json.loads(response["body"])
    for field in ("answer", "citations", "confidence", "status", "correlation_id"):
        assert field in body
    assert response["headers"]["x-correlation-id"] == body["correlation_id"]


def test_session_id_is_passed_through() -> None:
    event = _event(json.dumps({"message": "hello", "session_id": "sess-123"}))
    response = api.handle_chat_request(event, None)
    body = json.loads(response["body"])
    assert body["session_id"] == "sess-123"


def test_base64_encoded_body_is_decoded() -> None:
    raw = json.dumps({"message": "Return order VE-1001"}).encode("utf-8")
    event = _event(base64.b64encode(raw).decode("ascii"), is_base64=True)
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 200


@pytest.mark.parametrize(
    "body",
    [
        None,
        "not json",
        json.dumps([1, 2, 3]),
        json.dumps({"message": ""}),
        json.dumps({"message": "   "}),
        json.dumps({"message": 42}),
        json.dumps({"nope": "hi"}),
    ],
)
def test_bad_requests_return_400(body: str | None) -> None:
    response = api.handle_chat_request(_event(body), None)
    assert response["statusCode"] == 400
    parsed = json.loads(response["body"])
    assert "error" in parsed
    assert "correlation_id" in parsed


def test_oversized_message_returns_400() -> None:
    big = "a" * (api.MAX_MESSAGE_CHARS + 1)
    response = api.handle_chat_request(_event(json.dumps({"message": big})), None)
    assert response["statusCode"] == 400


def test_oversized_session_id_returns_400() -> None:
    sid = "s" * (api.MAX_SESSION_ID_CHARS + 1)
    event = _event(json.dumps({"message": "hi", "session_id": sid}))
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 400


def test_oversized_body_returns_400() -> None:
    filler = "a" * (api.MAX_BODY_BYTES + 100)
    event = _event(json.dumps({"message": "hi", "extra": filler}))
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 400


def test_message_is_stripped_before_agent() -> None:
    response = api.handle_chat_request(
        _event(json.dumps({"message": "  Where is my order VE-1001?  "})), None
    )
    assert response["statusCode"] == 200


def test_public_response_excludes_internal_fields() -> None:
    response = api.handle_chat_request(
        _event(json.dumps({"message": "Where is my order VE-1001?"})), None
    )
    body = json.loads(response["body"])
    for internal in ("notes", "classifier_rationale", "prompt_cache", "usage"):
        assert internal not in body


def test_blank_session_id_rejected() -> None:
    event = _event(json.dumps({"message": "hi", "session_id": "  "}))
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 400


def test_invalid_base64_returns_400() -> None:
    event = _event("!!!not-base64!!!", is_base64=True)
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 400


def test_guardrail_rejected_message_returns_422() -> None:
    # SSN input is blocked by the local input guardrail (status -> rejected).
    event = _event(json.dumps({"message": "my ssn is 123-45-6789"}))
    response = api.handle_chat_request(event, None)
    assert response["statusCode"] == 422
    body = json.loads(response["body"])
    assert body["status"] == "rejected"


def test_internal_error_returns_500_without_leaking(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(api, "run_agent", boom)
    response = api.handle_chat_request(
        _event(json.dumps({"message": "hello"})), None
    )
    assert response["statusCode"] == 500
    body = json.loads(response["body"])
    assert "secret internal detail" not in json.dumps(body)
    assert body["error"] == "Internal error handling support request"
    assert "correlation_id" in body


def test_handler_alias_is_callable() -> None:
    assert api.handler is api.handle_chat_request
