"""CLI smoke tests without Bedrock."""

import json

from supportrouter.cli import handle_message, main
from supportrouter.sessions import clear_sessions, list_sessions


def setup_function():
    clear_sessions()


def test_handle_message_order_demo():
    result = handle_message("Where is my order #VE-1001?")
    assert result["task_type"] == "order_status"
    assert result["model_id"] == "amazon.nova-micro"
    assert result["routing_table_version"] == "seed-v0.1.0"
    assert result["status"] == "resolved"
    assert "session_id" in result
    assert "answer" in result


def test_handle_message_passes_session_id():
    result = handle_message("Any update on VE-1001?", session_id="sess-cli-1")
    assert result["session_id"] == "sess-cli-1"
    assert any(item["session_id"] == "sess-cli-1" for item in list_sessions())


def test_main_accepts_session_id_flag(capsys):
    exit_code = main(["--session-id", "sess-cli-2", "Where is my order VE-1001?"])
    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["session_id"] == "sess-cli-2"


def test_cli_list_pending_and_decide(capsys):
    pending = handle_message("I want a refund for order VE-1003", session_id="hitl-1")
    assert pending["status"] == "pending_approval"

    assert main(["list-pending"]) == 0
    queue = json.loads(capsys.readouterr().out)
    assert queue[0]["session_id"] == "hitl-1"

    assert main(["decide", "hitl-1", "approve", "--note", "ok"]) == 0
    decided = json.loads(capsys.readouterr().out)
    assert decided["status"] == "resolved"
    assert decided["approval_status"] == "approved"
    assert "not_executed" in decided["execution_note"]
