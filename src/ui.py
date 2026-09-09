import gradio as gr
import os
import traceback
import json
from src.document_processor import (
    process_pdf,
    clear_database,
    get_db,
    is_vectorstore_ready,
    load_chat_history,
    save_chat_history,
    load_document_metadata,
    CHAT_HISTORY_FILE,
)
from src.graph import app

_ui_chat_history = load_chat_history()


def format_status_html(status_type: str, message: str) -> str:
    """Helper to render styled HTML status badges."""
    badge_class = "status-none"
    if status_type == "ready":
        badge_class = "status-ready"
    elif status_type == "error":
        badge_class = "status-error"
    elif status_type == "processing":
        badge_class = "status-none"

    return f'<div class="status-badge {badge_class}">{message}</div>'


def format_reflection_markdown(reflection_log: list, iterations: int) -> str:
    """Format reflection log into structured, highly readable Markdown."""
    if not reflection_log:
        return "*No reflection log data available yet. Ask a question to trigger the self-reflection loop.*"

    md = f"### 🔄 Self-Reflection & Retrieval Quality Trace\n"
    md += f"**Total Iterations:** `{iterations}`\n\n"

    for idx, entry in enumerate(reflection_log, 1):
        lines = entry.strip().splitlines()
        iter_title = lines[0] if lines else f"Iteration {idx}"
        content_lines = lines[1:] if len(lines) > 1 else lines

        md += f"#### 🔁 {iter_title}\n"
        verdict = "UNKNOWN"
        reason = ""
        refined_q = ""

        for line in content_lines:
            line_str = line.strip()
            if line_str.upper().startswith("VERDICT:"):
                verdict = line_str.split(":", 1)[1].strip()
            elif line_str.upper().startswith("REASON:"):
                reason = line_str.split(":", 1)[1].strip()
            elif line_str.upper().startswith("REFINED_QUERY:"):
                refined_q = line_str.split(":", 1)[1].strip()

        if verdict.upper() == "YES":
            md += f"- **Verdict:** 🟢 **YES** *(Context Relevant & Sufficient)*\n"
        elif verdict.upper() == "NO":
            md += f"- **Verdict:** 🔴 **NO** *(Context Insufficient — Triggering Query Rewrite)*\n"
        else:
            md += f"- **Verdict:** `{verdict}`\n"

        if reason:
            md += f"- **Reason:** {reason}\n"
        if refined_q and refined_q.upper() != "NONE":
            md += f"- **Refined Query:** `{refined_q}`\n"

        md += "\n---\n"

    return md


def format_history_markdown(history: list) -> str:
    """Format chat history into clean Markdown cards."""
    if not history:
        return "*No conversation history recorded yet.*"

    history_md = "### 📜 Conversation History\n\n"
    for idx, (q, a) in enumerate(history, 1):
        history_md += f"**Turn {idx} — User:** {q}\n\n> 🤖 **Assistant:** {a}\n\n---\n"
    return history_md


def ui_process_pdf(file):
    """Gradio handler for PDF processing."""
    global _ui_chat_history
    if file is None:
        return (
            format_status_html("error", "⚠️ No file selected. Please select a PDF file first."),
            gr.update(interactive=False),
        )
    try:
        file_path = file if isinstance(file, str) else file.name
        print(f"\n>>> [UI ACTION] User clicked Process for file: {file_path}")
        num_chunks, num_pages = process_pdf(file_path)
        _ui_chat_history = []
        fname = os.path.basename(file_path)

        return (
            format_status_html("ready", f"🟢 Ready — <b>{num_chunks}</b> chunks indexed from <b>{fname}</b> ({num_pages} pages)."),
            gr.update(interactive=True),
        )
    except Exception as e:
        print("\n❌ [ERROR IN UI_PROCESS_PDF]:")
        traceback.print_exc()
        return (
            format_status_html("error", f"❌ Processing failed: {str(e)}"),
            gr.update(interactive=False),
        )


def ui_clear_pdf():
    """Gradio handler for clearing the database and chat history."""
    global _ui_chat_history
    _ui_chat_history = []
    clear_database()
    return (
        None,
        format_status_html("none", "⚪ No document loaded. Upload a PDF to get started."),
        gr.update(interactive=False),
        [],
        "*No conversation history recorded yet.*",
    )


def ui_clear_history():
    """Clear chat history only."""
    global _ui_chat_history
    _ui_chat_history = []
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            os.remove(CHAT_HISTORY_FILE)
        except Exception:
            pass
    return [], "*No conversation history recorded yet.*"


def ui_ask_question(question):
    """Gradio handler for executing the RAG flow with persistent conversation memory."""
    global _ui_chat_history
    _ui_chat_history = load_chat_history()

    if not question or not question.strip():
        return (
            "*Please enter a question to execute the RAG pipeline.*",
            "*Enter your question above and click Ask.*",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
        )

    if not is_vectorstore_ready():
        return (
            "*No document active.*",
            "⚠️ **No document loaded.** Upload and process a PDF document first before asking questions.",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
        )

    try:
        result = app.invoke({
            "question": question.strip(),
            "refined_query": "",
            "context": "",
            "reflection": "",
            "answer": "",
            "iterations": 0,
            "reflection_log": [],
            "chat_history": _ui_chat_history,
        })

        reflection_log = result.get("reflection_log", [])
        iterations = result.get("iterations", 0)
        answer = result.get("answer", "No answer was generated.")
        _ui_chat_history = result.get("chat_history", [])
        save_chat_history(_ui_chat_history)

        reflection_md = format_reflection_markdown(reflection_log, iterations)
        history_md = format_history_markdown(_ui_chat_history)
        chatbot_data = [(q, a) for q, a in _ui_chat_history]

        return reflection_md, answer, chatbot_data, history_md

    except Exception as e:
        print("\n❌ [ERROR IN UI_ASK_QUESTION]:")
        traceback.print_exc()
        return (
            f"❌ **Error during reflection loop:** `{str(e)}`",
            f"❌ **An error occurred while generating answer:**\n```\n{str(e)}\n```",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
        )


def ui_clear_question():
    """Clear question input and output areas."""
    return "", "*Self-reflection log will appear here after asking a question.*", "*Ask a question to get started.*"


def create_ui():
    """Builds and returns the modern Agentic RAG Gradio UI."""
    
    # Check initial vectorstore readiness
    if is_vectorstore_ready():
        meta = load_document_metadata()
        fname = meta.get("filename", "Persisted Document")
        n_chunks = meta.get("num_chunks", "?")
        n_pages = meta.get("num_pages", "?")
        init_status = format_status_html("ready", f"🟢 Ready — <b>{n_chunks}</b> chunks indexed from <b>{fname}</b> ({n_pages} pages).")
        init_ask_interactive = True
    else:
        init_status = format_status_html("none", "⚪ No document loaded. Upload a PDF to get started.")
        init_ask_interactive = False

    init_history = load_chat_history()
    init_chatbot_data = [(q, a) for q, a in init_history]
    init_history_md = format_history_markdown(init_history)

    custom_css = """
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }
    
    .header-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #1e1b4b 100%);
        color: #ffffff;
        padding: 24px 30px;
        border-radius: 16px;
        margin-bottom: 16px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
    }
    
    .header-banner h1 {
        font-size: 2.1rem !important;
        font-weight: 800 !important;
        color: #ffffff !important;
        margin-bottom: 6px !important;
        letter-spacing: -0.02em;
    }
    
    .header-banner p {
        font-size: 1.02rem !important;
        color: #94a3b8 !important;
        margin-bottom: 12px !important;
        line-height: 1.5;
    }
    
    .tech-pill-container {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 10px;
    }
    
    .tech-pill {
        background: rgba(255, 255, 255, 0.12);
        color: #e2e8f0;
        font-size: 0.8rem;
        padding: 4px 12px;
        border-radius: 20px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        font-weight: 500;
    }
    
    .flow-banner {
        background: var(--background-fill-secondary);
        border: 1px solid var(--border-color-primary);
        border-radius: 12px;
        padding: 12px 20px;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }

    .flow-step {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.9rem;
        font-weight: 600;
        color: var(--body-text-color);
    }

    .flow-step-num {
        background: #3b82f6;
        color: white;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 700;
    }

    .flow-arrow {
        color: #94a3b8;
        font-weight: bold;
    }

    .status-badge {
        padding: 10px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        margin-top: 8px;
        line-height: 1.4;
    }

    .status-none {
        background: #f1f5f9;
        color: #475569;
        border: 1px solid #cbd5e1;
    }

    .status-ready {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
    }

    .status-error {
        background: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
    }

    .answer-box-styled {
        background: var(--background-fill-secondary);
        border: 1px solid var(--border-color-primary);
        border-left: 4px solid #3b82f6;
        border-radius: 10px;
        padding: 20px;
        min-height: 140px;
    }
    """

    with gr.Blocks(
        theme=gr.themes.Soft(),
        title="Self-Reflective Agentic RAG",
        css=custom_css,
    ) as demo:

        # 1. Top Header Banner
        gr.HTML(
            """
            <div class="header-banner">
                <h1>🔄 Self-Reflective Agentic RAG</h1>
                <p>Adaptive PDF Question Answering with Self-Correction, Automated Retrieval Quality Grading, and Iterative Query Refinement.</p>
                <div class="tech-pill-container">
                    <span class="tech-pill">🧠 Ollama qwen3:8b</span>
                    <span class="tech-pill">📐 nomic-embed-text</span>
                    <span class="tech-pill">🔀 LangGraph State Flow</span>
                    <span class="tech-pill">⚡ NVIDIA DGX Spark Accelerated</span>
                </div>
            </div>
            """
        )

        # 2. Main Workflow Step-by-Step Guidance Banner
        gr.HTML(
            """
            <div class="flow-banner">
                <div class="flow-step"><span class="flow-step-num">1</span> Upload PDF Document</div>
                <span class="flow-arrow">➔</span>
                <div class="flow-step"><span class="flow-step-num">2</span> Click Process Document</div>
                <span class="flow-arrow">➔</span>
                <div class="flow-step"><span class="flow-step-num">3</span> Ask your Question</div>
                <span class="flow-arrow">➔</span>
                <div class="flow-step"><span class="flow-step-num">4</span> Review Grounded Answer</div>
            </div>
            """
        )

        # 3. Main Dashboard Layout (2 Columns)
        with gr.Row(equal_height=False):
            # Left Sidebar: Document Management & Status
            with gr.Column(scale=1, min_width=320):
                gr.Markdown("### 📄 Document Hub")
                file_input = gr.File(
                    label="Upload PDF Document",
                    file_types=[".pdf"],
                    file_count="single",
                )
                
                with gr.Row():
                    proc_btn = gr.Button("⚙️ Process Document", variant="primary", scale=2)
                    clear_pdf_btn = gr.Button("🗑️ Clear Document", variant="secondary", scale=1)
                
                gr.Markdown("#### 📊 System Status")
                status_box = gr.HTML(value=init_status)

                gr.Markdown("---")
                gr.Markdown("#### ⚙️ Session Controls")
                clear_hist_btn = gr.Button("💬 Clear Chat History", variant="secondary")

            # Right Main Panel: Question, Answer, Reflection & History
            with gr.Column(scale=2):
                gr.Markdown("### 💬 Ask a Question")
                q_input = gr.Textbox(
                    label="Your Question",
                    placeholder="Enter your question about the uploaded document (e.g., 'What is the main proposed architecture?')...",
                    lines=3,
                )
                
                with gr.Row():
                    ask_btn = gr.Button(
                        "🔍 Ask Question",
                        variant="primary",
                        interactive=init_ask_interactive,
                        scale=3,
                    )
                    clear_q_btn = gr.Button("✖ Clear Question", variant="secondary", scale=1)

                gr.Markdown("---")

                # Answer Section
                gr.Markdown("### 📝 Grounded Answer")
                answer_box = gr.Markdown(
                    value="*Ask a question to get started.*",
                    elem_classes=["answer-box-styled"],
                )

                gr.Markdown("---")

                # Self-Reflection Accordion (Collapsible)
                with gr.Accordion("🔄 Self-Reflection & Retrieval Grading Details", open=False):
                    gr.Markdown(
                        "_The Self-Reflection loop evaluates retrieved context for relevance and sufficiency before answering. "
                        "If context fails validation, the LLM reformulates the query and repeats retrieval._"
                    )
                    reflection_log_box = gr.Markdown(
                        value="*Self-reflection log will appear here after asking a question.*"
                    )

                # Conversation History Accordion (Collapsible)
                with gr.Accordion("📜 Conversation History & Memory", open=False):
                    history_chatbot = gr.Chatbot(
                        value=init_chatbot_data,
                        label="Interactive Chat History",
                        height=280,
                    )
                    history_md = gr.Markdown(value=init_history_md)

        # Event Handlers
        proc_btn.click(
            fn=ui_process_pdf,
            inputs=[file_input],
            outputs=[status_box, ask_btn],
        )

        clear_pdf_btn.click(
            fn=ui_clear_pdf,
            outputs=[file_input, status_box, ask_btn, history_chatbot, history_md],
        )

        clear_hist_btn.click(
            fn=ui_clear_history,
            outputs=[history_chatbot, history_md],
        )

        ask_btn.click(
            fn=ui_ask_question,
            inputs=[q_input],
            outputs=[reflection_log_box, answer_box, history_chatbot, history_md],
        )

        clear_q_btn.click(
            fn=ui_clear_question,
            outputs=[q_input, reflection_log_box, answer_box],
        )

    return demo

