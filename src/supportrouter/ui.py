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


def refresh_queue() -> list[list[str]]:
    return _queue_rows()


def load_session_detail(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        return "Select a session from the queue."
    matches = [s for s in list_sessions() if s.get("session_id") == sid]
    if not matches:
        return f"Session not found: {sid}"
    return json.dumps(matches[0], indent=2)


def _row_index_from_select(evt: Any) -> int | None:
    if evt is None:
        return None
    index = getattr(evt, "index", None)
    if isinstance(index, (list, tuple)) and index:
        return int(index[0])
    if isinstance(index, int):
        return index
    return None


def _session_id_from_queue_data(data: Any, row_idx: int) -> str:
    """Extract session_id (column 0) from Gradio dataframe value at row_idx."""
    if data is None or row_idx < 0:
        return ""
    # pandas DataFrame
    if hasattr(data, "iloc"):
        try:
            return str(data.iloc[row_idx, 0])
        except Exception:
            return ""
    # list of lists / list of dicts
    if isinstance(data, list) and row_idx < len(data):
        row = data[row_idx]
        if isinstance(row, dict):
            return str(row.get("session_id") or next(iter(row.values()), "") or "")
        if isinstance(row, (list, tuple)) and row:
            return str(row[0])
    # dict-of-columns (Gradio sometimes)
    if isinstance(data, dict):
        col = data.get("session_id") or data.get("data")
        if isinstance(col, list) and row_idx < len(col):
            cell = col[row_idx]
            if isinstance(cell, (list, tuple)) and cell:
                return str(cell[0])
            return str(cell)
    return ""


def on_queue_select(evt: Any) -> tuple[str, str]:
    """When supervisor clicks a HITL queue row, fill session_id and show detail."""
    row_idx = _row_index_from_select(evt)
    if row_idx is None:
        return "", "Select a session from the queue."
    rows = _queue_rows()
    sid = ""
    if 0 <= row_idx < len(rows):
        sid = str(rows[row_idx][0]).strip()
    if not sid:
        # Fallback: cell value when user clicked the session_id column
        value = getattr(evt, "value", None)
        if value is not None and getattr(evt, "index", None) is not None:
            index = evt.index
            col = index[1] if isinstance(index, (list, tuple)) and len(index) > 1 else 0
            if col == 0:
                sid = str(value).strip()
    if not sid:
        return "", "Could not read session_id from selected row."
    return sid, load_session_detail(sid)


def supervisor_decide(
    session_id: str, decision: str, note: str
) -> tuple[str, list[list[str]], str]:
    sid = (session_id or "").strip()
    if not sid:
        return (
            "Select a session from the HITL queue (click a row), then Approve or Reject.",
            _queue_rows(),
            "",
        )
    try:
        updated = decide_hitl(sid, decision, note=note or "")
    except (KeyError, ValueError) as exc:
        return f"Error: {exc}", _queue_rows(), sid
    # Clear selection after decision; queue refresh drops resolved items.
    return json.dumps(updated, indent=2), _queue_rows(), ""


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
                "Queue shows `pending_approval` and `escalated` sessions. "
                "**Click a row** to select it for Approve / Reject."
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
                interactive=True,
                wrap=True,
                label="HITL queue (click a row to select)",
            )
            refresh = gr.Button("Refresh queue")
            session_id = gr.Textbox(
                label="Selected session_id",
                interactive=False,
                placeholder="Click a queue row to select",
            )
            detail = gr.Code(label="Session detail", language="json")
            note = gr.Textbox(label="Supervisor note", placeholder="Optional note")
            with gr.Row():
                approve = gr.Button("Approve", variant="primary")
                reject = gr.Button("Reject", variant="stop")

            refresh.click(refresh_queue, outputs=queue)
            demo.load(refresh_queue, outputs=queue)
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
