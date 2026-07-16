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
    result = save_session(run_agent(text))
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


def supervisor_decide(session_id: str, decision: str, note: str) -> tuple[str, list[list[str]]]:
    sid = (session_id or "").strip()
    if not sid:
        return "Enter a session_id from the queue.", _queue_rows()
    try:
        updated = decide_hitl(sid, decision, note=note or "")
    except (KeyError, ValueError) as exc:
        return f"Error: {exc}", _queue_rows()
    return json.dumps(updated, indent=2), _queue_rows()


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
                "Queue shows `pending_approval` and `escalated` sessions from this UI process."
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
                label="HITL queue",
            )
            refresh = gr.Button("Refresh queue")
            session_id = gr.Textbox(label="session_id")
            detail = gr.Code(label="Session detail", language="json")
            note = gr.Textbox(label="Supervisor note", placeholder="Optional note")
            with gr.Row():
                approve = gr.Button("Approve", variant="primary")
                reject = gr.Button("Reject", variant="stop")

            refresh.click(refresh_queue, outputs=queue)
            demo.load(refresh_queue, outputs=queue)
            session_id.blur(load_session_detail, inputs=session_id, outputs=detail)
            approve.click(
                lambda sid, n: supervisor_decide(sid, "approve", n),
                inputs=[session_id, note],
                outputs=[detail, queue],
            )
            reject.click(
                lambda sid, n: supervisor_decide(sid, "reject", n),
                inputs=[session_id, note],
                outputs=[detail, queue],
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
