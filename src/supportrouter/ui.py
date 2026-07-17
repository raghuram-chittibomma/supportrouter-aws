"""Thin Gradio demo UI for VoltEdge SupportRouter (local, dormancy-safe)."""

from __future__ import annotations

import argparse
import json
from typing import Any

import gradio as gr

from supportrouter.graph import run_agent
from supportrouter.sessions import (
    decide_hitl,
    get_approval_request,
    list_sessions,
    save_session,
)

GUARDRAIL_REDACTED_MESSAGE = "[redacted: guardrail-blocked input]"


def format_customer_reply(result: dict[str, Any]) -> str:
    citations = result.get("citations") or []
    cite_lines = (
        "\n".join(f"- `{c.get('doc_id')}`: {c.get('excerpt', '')[:120]}" for c in citations)
        or "_None_"
    )
    return (
        f"{result.get('answer') or ''}\n\n"
        f"---\n"
        f"**status:** `{result.get('status')}`  \n"
        f"**confidence:** `{result.get('confidence')}`  \n"
        f"**task_type:** `{result.get('task_type')}`  \n"
        f"**model_id:** `{result.get('model_id')}`  \n"
        f"**session_id:** `{result.get('session_id')}`  \n"
        f"**hitl_reason:** {result.get('hitl_reason') or '_n/a_'}  \n"
        f"**citations:**\n{cite_lines}\n"
    )


def customer_chat(message: str, history: list) -> tuple[list, str]:
    history = history or []
    text = (message or "").strip()
    if not text:
        return history, ""
    result = run_agent(text)
    input_action = ((result.get("guardrail") or {}).get("input") or {}).get("action")
    stored_message = (
        GUARDRAIL_REDACTED_MESSAGE if input_action == "blocked" else text
    )
    result["message"] = stored_message
    result = save_session(result)
    reply = format_customer_reply(result)
    history = history + [
        {"role": "user", "content": stored_message},
        {"role": "assistant", "content": reply},
    ]
    return history, ""


def _queue_rows() -> list[list[str]]:
    """Pending refund approvals that support Approve/Reject."""
    rows: list[list[str]] = []
    for s in list_sessions(statuses={"pending_approval"}):
        rows.append(
            [
                str(s.get("session_id") or ""),
                str(s.get("status") or ""),
                str(s.get("task_type") or ""),
                str(s.get("refund_amount_usd") if s.get("refund_amount_usd") is not None else ""),
                str(s.get("approval_id") or ""),
                str(s.get("approval_status") or ""),
                str(s.get("hitl_reason") or ""),
                (s.get("message") or "")[:80],
            ]
        )
    return rows


def _escalation_rows() -> list[list[str]]:
    """Read-only low-confidence escalations for supervisor awareness."""
    rows: list[list[str]] = []
    for session in list_sessions(statuses={"escalated"}):
        rows.append(
            [
                str(session.get("session_id") or ""),
                str(session.get("task_type") or ""),
                str(session.get("confidence") if session.get("confidence") is not None else ""),
                str(session.get("hitl_reason") or ""),
                (session.get("message") or "")[:80],
            ]
        )
    return rows


def refresh_queue() -> tuple[list[list[str]], str, str]:
    """Refresh the queue and clear any stale row selection."""
    return _queue_rows(), "", "Click a queue row to select a session."


def load_session_detail(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        return "Click a queue row to select a session."
    matches = [s for s in list_sessions() if s.get("session_id") == sid]
    if not matches:
        return f"Session not found: {sid}"
    session = matches[0]
    approval_id = session.get("approval_id")
    approval = get_approval_request(approval_id) if approval_id else None
    return json.dumps({"session": session, "approval_request": approval}, indent=2)


def session_id_from_select_event(evt: Any) -> str:
    """Extract session_id from Gradio SelectData (Dataframe click)."""
    if evt is None:
        return ""
    # Preferred: full row payload (Gradio Dataframe SelectData.row_value)
    row_value = getattr(evt, "row_value", None)
    if isinstance(row_value, (list, tuple)) and row_value:
        return str(row_value[0]).strip()
    # Fallback: row index into live queue
    index = getattr(evt, "index", None)
    row_idx: int | None = None
    if isinstance(index, (list, tuple)) and index:
        row_idx = int(index[0])
    elif isinstance(index, int):
        row_idx = index
    if row_idx is not None:
        rows = _queue_rows()
        if 0 <= row_idx < len(rows) and rows[row_idx]:
            return str(rows[row_idx][0]).strip()
    # Fallback: clicked cell is session_id column
    value = getattr(evt, "value", None)
    if value is not None and isinstance(index, (list, tuple)) and len(index) > 1 and index[1] == 0:
        return str(value).strip()
    if value is not None and isinstance(value, str) and len(value) >= 8:
        # UUID-ish cell click
        return value.strip()
    return ""


def on_queue_select(evt: gr.SelectData) -> tuple[str, str]:
    """Populate the selected session field from any clicked queue cell."""
    sid = session_id_from_select_event(evt)
    if not sid:
        return "", "Could not read session_id from the selected row."
    return sid, load_session_detail(sid)


def supervisor_decide(
    session_id: str, decision: str, note: str
) -> tuple[str, list[list[str]], str]:
    sid = (session_id or "").strip()
    if not sid:
        return (
            "Click a queue row, then Approve or Reject.",
            _queue_rows(),
            "",
        )
    try:
        updated = decide_hitl(sid, decision, note=note or "")
    except (KeyError, ValueError) as exc:
        return f"Error: {exc}", _queue_rows(), sid
    approval_id = updated.get("approval_id")
    approval = get_approval_request(approval_id) if approval_id else None
    return (
        json.dumps({"session": updated, "approval_request": approval}, indent=2),
        _queue_rows(),
        "",
    )


def build_ui():
    with gr.Blocks(title="SupportRouter — VoltEdge Demo") as demo:
        gr.Markdown(
            """
            # SupportRouter — VoltEdge Electronics (synthetic)
            Thin local demo UI. **No Bedrock / no always-on hosting** in this slice.
            Cost note: not measured (local process only).
            """
        )
        with gr.Tab("Customer chat"):
            chatbot = gr.Chatbot(label="Support chat", height=420)
            msg = gr.Textbox(
                label="Message",
                placeholder="Where is my order #VE-1001?  |  I want a refund for order VE-1003",
            )
            send = gr.Button("Send", variant="primary")
            send.click(customer_chat, inputs=[msg, chatbot], outputs=[chatbot, msg])
            msg.submit(customer_chat, inputs=[msg, chatbot], outputs=[chatbot, msg])

        with gr.Tab("Supervisor (HITL)"):
            gr.Markdown(
                "1. Click **Refresh queue** after customer messages that need HITL.  \n"
                "2. **Click any cell in a queue row** to select that session.  \n"
                "3. **Approve** or **Reject** pending refund approvals.  \n"
                "Escalated sessions are view-only in this local slice."
            )
            refresh = gr.Button("Refresh queue", variant="secondary")
            queue = gr.Dataframe(
                headers=[
                    "session_id",
                    "status",
                    "task_type",
                    "refund_usd",
                    "approval_id",
                    "approval_status",
                    "hitl_reason",
                    "message",
                ],
                datatype=["str"] * 8,
                interactive=False,
                wrap=True,
                label="HITL queue (click a cell to select that row)",
            )
            escalations = gr.Dataframe(
                headers=[
                    "session_id",
                    "task_type",
                    "confidence",
                    "reason",
                    "message",
                ],
                value=[],
                datatype=["str"] * 5,
                interactive=False,
                wrap=True,
                label="Escalations (read-only in local v0.1)",
            )
            session_id = gr.Textbox(
                label="Selected session_id for Approve / Reject",
                interactive=False,
                placeholder="Click a queue row to select",
            )
            detail = gr.Code(label="Session detail", language="json")
            note = gr.Textbox(label="Supervisor note", placeholder="Optional note")
            with gr.Row():
                approve = gr.Button("Approve", variant="primary")
                reject = gr.Button("Reject", variant="stop")

            refresh.click(
                refresh_queue,
                outputs=[queue, session_id, detail],
            )
            refresh.click(_escalation_rows, outputs=[escalations])
            demo.load(
                refresh_queue,
                outputs=[queue, session_id, detail],
            )
            demo.load(_escalation_rows, outputs=[escalations])
            queue.select(
                on_queue_select,
                outputs=[session_id, detail],
            )
            approve.click(
                lambda sid, n: supervisor_decide(sid, "approve", n),
                inputs=[session_id, note],
                outputs=[detail, queue, session_id],
            )
            reject.click(
                lambda sid, n: supervisor_decide(sid, "reject", n),
                inputs=[session_id, note],
                outputs=[detail, queue, session_id],
            )

    return demo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SupportRouter thin Gradio demo UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true", help="Gradio share link (optional)")
    args = parser.parse_args(argv)
    demo = build_ui()
    demo.launch(server_name=args.host, server_port=args.port, share=args.share)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
