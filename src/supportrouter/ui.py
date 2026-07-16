"""Thin Gradio demo UI for VoltEdge SupportRouter (local, dormancy-safe)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from supportrouter.graph import run_agent
from supportrouter.sessions import decide_hitl, list_sessions, save_session


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
    result["message"] = text
    save_session(result)
    reply = format_customer_reply(result)
    history = history + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ]
    return history, ""


def _queue_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for s in list_sessions(statuses={"pending_approval", "escalated"}):
        rows.append(
            [
                str(s.get("session_id") or ""),
                str(s.get("status") or ""),
                str(s.get("task_type") or ""),
                str(s.get("refund_amount_usd") if s.get("refund_amount_usd") is not None else ""),
                str(s.get("hitl_reason") or ""),
                (s.get("message") or "")[:80],
            ]
        )
    return rows


def _session_choices() -> list[str]:
    return [row[0] for row in _queue_rows() if row and row[0]]


def refresh_queue():
    """Return queue table + dropdown choices/value for Gradio updates."""
    import gradio as gr

    rows = _queue_rows()
    choices = [r[0] for r in rows if r and r[0]]
    value = choices[0] if choices else None
    return (
        rows,
        gr.update(choices=choices, value=value),
        value or "",
        load_session_detail(value or ""),
    )


def load_session_detail(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        return "Select a session from the dropdown or click a queue row."
    matches = [s for s in list_sessions() if s.get("session_id") == sid]
    if not matches:
        return f"Session not found: {sid}"
    return json.dumps(matches[0], indent=2)


def on_session_dropdown(session_id: str) -> tuple[str, str]:
    sid = (session_id or "").strip()
    return sid, load_session_detail(sid)


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


def on_queue_select(evt: Any) -> tuple[str, str, Any]:
    """Dataframe click → fill dropdown + session_id + detail."""
    import gradio as gr

    sid = session_id_from_select_event(evt)
    if not sid:
        return (
            "",
            "Could not read session_id from click. Use the dropdown instead.",
            gr.update(),
        )
    return sid, load_session_detail(sid), gr.update(value=sid)


def supervisor_decide(
    session_id: str, decision: str, note: str
) -> tuple[str, list[list[str]], Any, str]:
    import gradio as gr

    sid = (session_id or "").strip()
    if not sid:
        rows = _queue_rows()
        choices = [r[0] for r in rows if r and r[0]]
        return (
            "Select a session (dropdown or click a queue row), then Approve or Reject.",
            rows,
            gr.update(choices=choices, value=None),
            "",
        )
    try:
        updated = decide_hitl(sid, decision, note=note or "")
    except (KeyError, ValueError) as exc:
        rows = _queue_rows()
        choices = [r[0] for r in rows if r and r[0]]
        return (
            f"Error: {exc}",
            rows,
            gr.update(choices=choices, value=sid),
            sid,
        )
    rows = _queue_rows()
    choices = [r[0] for r in rows if r and r[0]]
    next_value = choices[0] if choices else None
    return (
        json.dumps(updated, indent=2),
        rows,
        gr.update(choices=choices, value=next_value),
        next_value or "",
    )


def build_ui():
    import gradio as gr

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
                "2. **Choose a session** from the dropdown (or click a table cell).  \n"
                "3. **Approve** or **Reject**."
            )
            refresh = gr.Button("Refresh queue", variant="secondary")
            session_dd = gr.Dropdown(
                label="Select session for Approve / Reject",
                choices=[],
                interactive=True,
                allow_custom_value=False,
            )
            session_id = gr.Textbox(
                label="Selected session_id",
                interactive=False,
                placeholder="Pick a session above",
            )
            queue = gr.Dataframe(
                headers=[
                    "session_id",
                    "status",
                    "task_type",
                    "refund_usd",
                    "hitl_reason",
                    "message",
                ],
                datatype=["str"] * 6,
                interactive=False,
                wrap=True,
                label="HITL queue (click a cell to select that row)",
            )
            detail = gr.Code(label="Session detail", language="json")
            note = gr.Textbox(label="Supervisor note", placeholder="Optional note")
            with gr.Row():
                approve = gr.Button("Approve", variant="primary")
                reject = gr.Button("Reject", variant="stop")

            refresh.click(
                refresh_queue,
                outputs=[queue, session_dd, session_id, detail],
            )
            demo.load(
                refresh_queue,
                outputs=[queue, session_dd, session_id, detail],
            )
            session_dd.change(
                on_session_dropdown,
                inputs=[session_dd],
                outputs=[session_id, detail],
            )

            # Type hint gr.SelectData is required for Gradio to inject event payload.
            def _on_table_select(evt: gr.SelectData):
                return on_queue_select(evt)

            queue.select(
                _on_table_select,
                outputs=[session_id, detail, session_dd],
            )
            approve.click(
                lambda sid, n: supervisor_decide(sid, "approve", n),
                inputs=[session_id, note],
                outputs=[detail, queue, session_dd, session_id],
            )
            reject.click(
                lambda sid, n: supervisor_decide(sid, "reject", n),
                inputs=[session_id, note],
                outputs=[detail, queue, session_dd, session_id],
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
