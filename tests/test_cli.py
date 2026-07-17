"""CLI smoke tests without Bedrock."""

from supportrouter.cli import handle_message, main


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


def test_main_accepts_session_id_flag(capsys):
    import json

    exit_code = main(["--session-id", "sess-cli-2", "Where is my order VE-1001?"])
    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["session_id"] == "sess-cli-2"
