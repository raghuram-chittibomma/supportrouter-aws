"""CLI smoke tests without Bedrock."""

from supportrouter.cli import handle_message


def test_handle_message_order_demo():
    result = handle_message("Where is my order #VE-1001?")
    assert result["task_type"] == "order_status"
    assert result["model_id"] == "amazon.nova-micro"
    assert result["routing_table_version"] == "seed-v0.1.0"
    assert result["status"] == "resolved"
    assert "session_id" in result
    assert "answer" in result
