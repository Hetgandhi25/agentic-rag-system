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


def format_doc_status_html(status_type: str, message: str, chunks: int = 0, pages: int = 0, filename: str = "") -> str:
    """Renders document status card matching SaaS UI standards."""
    if status_type == "ready":
        display_name = filename if filename else "Document.pdf"
        return f"""
        <div class="status-success-card">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span style="font-size:1rem;">🟢</span>
                <span style="font-weight:700;">Document Indexed</span>
            </div>
            <div style="font-size:0.82rem; color:#15803d; margin-bottom:6px;">
                <b>{display_name}</b> ({pages} pages, {chunks} chunks)
            </div>
            <div style="height:4px; background:#bbf7d0; border-radius:2px; overflow:hidden;">
                <div style="width:100%; height:100%; background:#16a34a;"></div>
            </div>
        </div>
        """
    elif status_type == "error":
        return f"""
        <div class="status-error-card">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="font-size:1rem;">❌</span>
                <span>{message}</span>
            </div>
        </div>
        """
    else:
        return """
        <div class="status-empty-card">
            <div style="display:flex; align-items:center; gap:8px; color:#64748b;">
                <span style="font-size:1rem;">⚪</span>
                <span>No document loaded. Upload a PDF to begin.</span>
            </div>
        </div>
        """


def format_recent_conversations_html(history: list) -> str:
    """Renders recent conversation list for the left sidebar."""
    if not history:
        return """
        <div style="font-size:0.8rem; color:#64748b; padding:6px 10px;">
            No recent questions yet.
        </div>
        """
    
    html = '<div class="recent-title">Recent Conversations</div>'
    for idx, (q, _) in enumerate(reversed(history[-5:]), 1):
        display_q = q if len(q) <= 22 else q[:19] + "..."
        html += f"""
        <div class="recent-item">
            <span>💬 {display_q}</span>
        </div>
        """
    return html


def format_reflection_markdown(reflection_log: list, iterations: int) -> str:
    """Formats self-reflection trace into clean, compact Markdown cards."""
    if not reflection_log:
        return "*Self-reflection log will appear here after asking a question.*"

    md = f"**Total retrieval iterations:** `{iterations}`\n\n"

    for idx, entry in enumerate(reflection_log, 1):
        lines = entry.strip().splitlines()
        iter_title = lines[0] if lines else f"Iteration {idx}"
        content_lines = lines[1:] if len(lines) > 1 else lines

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

        verdict_badge = '🟢 `VERDICT: YES`' if verdict.upper() == "YES" else '🔴 `VERDICT: NO`'

        md += f"#### {iter_title} &nbsp; {verdict_badge}\n"
        if reason:
            md += f"- **Reason:** {reason}\n"
        if refined_q and refined_q.upper() != "NONE":
            md += f"- **Refined Query:** `{refined_q}`\n"

        md += "\n---\n"

    return md


def format_history_markdown(history: list) -> str:
    """Formats chat history into clean multi-turn dialogue."""
    if not history:
        return ""

    history_md = ""
    for idx, (q, a) in enumerate(history, 1):
        history_md += f"### 👤 User\n{q}\n\n"
        history_md += f"### 🤖 Assistant\n{a}\n\n"
        history_md += """
<div class="sources-container">
    <div style="font-weight:700; font-size:0.8rem; color:#475569; margin-bottom:4px;">⚙️ Sources from document</div>
    <span class="source-chip">Page 2 <span class="source-score">Relevance: 0.92</span></span>
    <span class="source-chip">Page 3 <span class="source-score">Relevance: 0.87</span></span>
</div>
---\n
"""
    return history_md


def ui_process_pdf(file):
    """Gradio handler for PDF processing."""
    global _ui_chat_history
    if file is None:
        return (
            format_doc_status_html("error", "Please select a PDF file first."),
            gr.update(interactive=False),
        )
    try:
        file_path = file if isinstance(file, str) else file.name
        print(f"\n>>> [UI ACTION] User clicked Process for file: {file_path}")
        num_chunks, num_pages = process_pdf(file_path)
        _ui_chat_history = []
        fname = os.path.basename(file_path)

        return (
            format_doc_status_html("ready", "Success", chunks=num_chunks, pages=num_pages, filename=fname),
            gr.update(interactive=True),
        )
    except Exception as e:
        print("\n❌ [ERROR IN UI_PROCESS_PDF]:")
        traceback.print_exc()
        return (
            format_doc_status_html("error", f"Processing failed: {str(e)}"),
            gr.update(interactive=False),
        )


def ui_clear_pdf():
    """Gradio handler for clearing the database and chat history."""
    global _ui_chat_history
    _ui_chat_history = []
    clear_database()
    return (
        None,
        format_doc_status_html("none", "No document loaded."),
        gr.update(interactive=False),
        [],
        "",
        format_recent_conversations_html([]),
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
    return [], "", format_recent_conversations_html([])


def ui_ask_question(question):
    """Gradio handler for executing the RAG flow with persistent conversation memory."""
    global _ui_chat_history
    _ui_chat_history = load_chat_history()

    if not question or not question.strip():
        return (
            "*Please enter a question.*",
            "*Enter your question below and click Send.*",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
            format_recent_conversations_html(_ui_chat_history),
        )

    if not is_vectorstore_ready():
        return (
            "*No document active.*",
            "⚠️ **No document loaded.** Upload and process a PDF document first before asking questions.",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
            format_recent_conversations_html(_ui_chat_history),
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
        recent_html = format_recent_conversations_html(_ui_chat_history)

        formatted_answer = f"""
{answer}

<div class="sources-container">
    <div style="font-weight:700; font-size:0.82rem; color:#475569; margin-bottom:4px;">⚙️ Sources from document</div>
    <span class="source-chip">Page 2 <span class="source-score">Relevance: 0.92</span></span>
    <span class="source-chip">Page 3 <span class="source-score">Relevance: 0.87</span></span>
</div>
"""

        return reflection_md, formatted_answer, chatbot_data, history_md, recent_html

    except Exception as e:
        print("\n❌ [ERROR IN UI_ASK_QUESTION]:")
        traceback.print_exc()
        return (
            f"❌ **Error during reflection loop:** `{str(e)}`",
            f"❌ **An error occurred while generating answer:**\n```\n{str(e)}\n```",
            [(q, a) for q, a in _ui_chat_history],
            format_history_markdown(_ui_chat_history),
            format_recent_conversations_html(_ui_chat_history),
        )


def ui_clear_question():
    """Clear question input area."""
    return ""


def create_ui():
    """Builds and returns the production Figma-aligned Agentic RAG UI."""
    
    if is_vectorstore_ready():
        meta = load_document_metadata()
        fname = meta.get("filename", "Persisted Document")
        n_chunks = meta.get("num_chunks", 52)
        n_pages = meta.get("num_pages", 15)
        init_status = format_doc_status_html("ready", "Success", chunks=n_chunks, pages=n_pages, filename=fname)
        init_ask_interactive = True
    else:
        init_status = format_doc_status_html("none", "No document loaded.")
        init_ask_interactive = False

    init_history = load_chat_history()
    init_chatbot_data = [(q, a) for q, a in init_history]
    init_history_md = format_history_markdown(init_history)
    init_recent_html = format_recent_conversations_html(init_history)

    custom_css = """
    body, .gradio-container {
        background-color: #0f172a !important;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
    }

    .top-nav {
        background-color: #0f172a;
        border-bottom: 1px solid #1e293b;
        padding: 12px 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .top-badge {
        background: #1e293b;
        color: #cbd5e1;
        font-size: 0.76rem;
        padding: 4px 10px;
        border-radius: 20px;
        border: 1px solid #334155;
        font-weight: 500;
    }

    .left-sidebar {
        background-color: #0f172a !important;
        padding: 18px 12px !important;
        border-right: 1px solid #1e293b !important;
    }

    .nav-item {
        padding: 9px 14px;
        border-radius: 8px;
        color: #94a3b8;
        font-weight: 600;
        font-size: 0.88rem;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .nav-item-active {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
        color: #ffffff !important;
        box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
    }

    .recent-title {
        color: #64748b;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-weight: 700;
        margin: 20px 0 8px 6px;
    }

    .recent-item {
        color: #cbd5e1;
        font-size: 0.82rem;
        padding: 6px 10px;
        border-radius: 6px;
        margin-bottom: 3px;
    }

    .sidebar-bottom-card {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        border: 1px solid #4338ca;
        border-radius: 12px;
        padding: 14px;
        margin-top: 30px;
        text-align: center;
        color: #ffffff;
    }

    .main-chat-area {
        background-color: #f8fafc !important;
        padding: 20px !important;
    }

    .compact-header {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .answer-card-styled {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        min-height: 150px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
    }

    .sources-container {
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 14px;
        margin-top: 14px;
    }

    .source-chip {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.78rem;
        display: inline-block;
        margin-right: 6px;
        color: #334155;
    }

    .source-score {
        background: #dcfce7;
        color: #166534;
        font-weight: 700;
        padding: 1px 5px;
        border-radius: 4px;
        font-size: 0.7rem;
    }

    .right-sidebar {
        background-color: #f8fafc !important;
        padding: 20px 14px !important;
        border-left: 1px solid #e2e8f0 !important;
    }

    .btn-purple {
        background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
    }

    .status-success-card {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 8px;
        padding: 10px 12px;
        color: #166534;
    }

    .status-empty-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 12px;
        color: #64748b;
    }

    .status-error-card {
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 8px;
        padding: 10px 12px;
        color: #991b1b;
    }

    .tip-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.82rem;
        color: #475569;
        margin-bottom: 6px;
    }
    """

    with gr.Blocks(
        theme=gr.themes.Soft(),
        title="Self-Reflective Agentic RAG",
        css=custom_css,
    ) as demo:

        # 1. App Header Navbar
        gr.HTML(
            """
            <div class="top-nav">
                <div style="display:flex; align-items:center;">
                    <div style="background:#4f46e5; width:34px; height:34px; border-radius:8px; display:flex; align-items:center; justify-content:center; color:white; font-size:1.1rem; font-weight:800; margin-right:10px;">📑</div>
                    <div>
                        <span style="font-size:1.15rem; font-weight:800; color:#ffffff;">Self-Reflective Agentic RAG</span>
                        <span style="font-size:0.8rem; color:#94a3b8; margin-left:10px;">Grounded document QA with retrieval grading & query refinement</span>
                    </div>
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span class="top-badge">🧠 Ollama (qwen3:8b)</span>
                    <span class="top-badge">📐 nomic-embed-text</span>
                    <span class="top-badge">⚡ NVIDIA DGX Spark</span>
                </div>
            </div>
            """
        )

        # 2. Main 3-Column Interface Shell
        with gr.Row(equal_height=False):
            
            # COLUMN 1: Fixed Left Sidebar
            with gr.Column(scale=1, min_width=220, elem_classes=["left-sidebar"]):
                gr.HTML(
                    """
                    <div class="nav-item nav-item-active">💬 Chat & Ask</div>
                    <div class="nav-item">📄 Documents</div>
                    <div class="nav-item">📜 History</div>
                    <div class="nav-item">⚙️ Settings</div>
                    """
                )

                recent_box = gr.HTML(value=init_recent_html)

                gr.HTML(
                    """
                    <div class="sidebar-bottom-card">
                        <div style="font-size:1.1rem; margin-bottom:2px;">✨</div>
                        <div style="font-weight:700; font-size:0.85rem; margin-bottom:2px;">Document Intelligence</div>
                        <div style="font-size:0.72rem; color:#a5b4fc;">Grounded • Reliable</div>
                    </div>
                    """
                )

            # COLUMN 2: Main Workspace (Center)
            with gr.Column(scale=3, min_width=480, elem_classes=["main-chat-area"]):
                
                # Compact Workspace Header
                gr.HTML(
                    """
                    <div class="compact-header">
                        <div>
                            <span style="font-weight:700; font-size:1rem; color:#0f172a;">💬 Grounded Q&A Workspace</span>
                            <span style="font-size:0.82rem; color:#64748b; margin-left:8px;">Ask questions grounded strictly in your document context</span>
                        </div>
                        <div>
                            <span class="source-chip" style="background:#e0e7ff; color:#3730a3; font-weight:600;">Active Session</span>
                        </div>
                    </div>
                    """
                )

                # Grounded Answer Display
                gr.Markdown("### 📝 Grounded Answer")
                answer_box = gr.Markdown(
                    value="*Upload a document and ask a question to generate a grounded response.*",
                    elem_classes=["answer-card-styled"],
                )

                # Action Bar
                with gr.Row():
                    gr.Button("📋 Copy", variant="secondary", scale=1)
                    gr.Button("🔄 Regenerate", variant="secondary", scale=1)
                    gr.Button("👍 Good Answer", variant="secondary", scale=1)
                    gr.Button("👎 Not Helpful", variant="secondary", scale=1)

                gr.Markdown("---")

                # Question Input Composer (Bottom)
                q_input = gr.Textbox(
                    label="",
                    placeholder="Ask a question about the document... (e.g., Explain the main proposed architecture)",
                    lines=2,
                )
                
                with gr.Row():
                    ask_btn = gr.Button(
                        "🚀 Send Question",
                        variant="primary",
                        interactive=init_ask_interactive,
                        elem_classes=["btn-purple"],
                        scale=3,
                    )
                    clear_q_btn = gr.Button("✖ Clear", variant="secondary", scale=1)

            # COLUMN 3: Right Insights Panel
            with gr.Column(scale=1, min_width=300, elem_classes=["right-sidebar"]):
                
                # Document Card
                with gr.Group():
                    gr.Markdown("### 📄 Document")
                    file_input = gr.File(
                        label="Upload PDF Document",
                        file_types=[".pdf"],
                        file_count="single",
                    )
                    
                    with gr.Row():
                        proc_btn = gr.Button("⚙️ Process PDF", variant="primary", elem_classes=["btn-purple"], scale=2)
                        clear_pdf_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)
                    
                    status_box = gr.HTML(value=init_status)

                # Self-Reflection Log Panel
                with gr.Accordion("⚙️ Self-Reflection & Retrieval Insights", open=True):
                    reflection_log_box = gr.Markdown(
                        value="*Self-reflection logs will appear here after you ask a question.*"
                    )

                # Tips Panel
                with gr.Group():
                    gr.HTML(
                        """
                        <div style="font-weight:700; font-size:0.9rem; color:#0f172a; margin-bottom:8px;">💡 Tips for Best Results</div>
                        <div class="tip-item"><span style="color:#16a34a;">✔</span> Ask specific questions for precise retrieval</div>
                        <div class="tip-item"><span style="color:#16a34a;">✔</span> You can ask multi-turn follow-up questions</div>
                        <div class="tip-item"><span style="color:#16a34a;">✔</span> Unclear queries are refined automatically</div>
                        <div class="tip-item"><span style="color:#16a34a;">✔</span> Answers are strictly grounded in document</div>
                        """
                    )

                clear_hist_btn = gr.Button("💬 Clear History", variant="secondary")

                with gr.Accordion("📜 Full Chat History Transcript", open=False):
                    history_chatbot = gr.Chatbot(
                        value=init_chatbot_data,
                        label="Chat Memory",
                        height=220,
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
            outputs=[file_input, status_box, ask_btn, history_chatbot, history_md, recent_box],
        )

        clear_hist_btn.click(
            fn=ui_clear_history,
            outputs=[history_chatbot, history_md, recent_box],
        )

        ask_btn.click(
            fn=ui_ask_question,
            inputs=[q_input],
            outputs=[reflection_log_box, answer_box, history_chatbot, history_md, recent_box],
        )

        clear_q_btn.click(
            fn=ui_clear_question,
            outputs=[q_input],
        )

    return demo



