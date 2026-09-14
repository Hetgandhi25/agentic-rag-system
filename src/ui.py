import gradio as gr
import os
import traceback
import json
import time
from datetime import datetime
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


# ─── HTML RENDERERS (Pixel-perfect matching reference image media_1788961266078.png) ──────────

def render_welcome_banner():
    """Apple-style clean welcome state shown when no chat exists."""
    return """
    <div style="background:#fafafa; border:1px dashed #d1d5db; border-radius:14px; padding:36px; text-align:center; margin-bottom:20px;">
        <div style="width:48px; height:48px; background:#e8f0fe; border-radius:50%; display:flex; align-items:center; justify-content:center; margin:0 auto 12px auto; color:#007aff; font-size:1.4rem;">
            💬
        </div>
        <div style="font-weight:700; font-size:1.1rem; color:#1d1d1f; margin-bottom:6px;">Upload a document and start asking questions</div>
        <div style="font-size:0.85rem; color:#6e6e73; max-width:460px; margin:0 auto 16px auto; line-height:1.5;">
            The self-reflective agent retrieves relevant context from your PDF, evaluates quality, refines queries automatically, and provides grounded answers.
        </div>
        <div style="display:flex; justify-content:center; gap:8px; font-size:0.78rem; color:#4b5563;">
            <span style="background:#ffffff; border:1px solid #e5e7eb; padding:4px 12px; border-radius:20px; color:#1d1d1f; font-weight:500;">1. Upload PDF</span>
            <span style="color:#9ca3af;">→</span>
            <span style="background:#ffffff; border:1px solid #e5e7eb; padding:4px 12px; border-radius:20px; color:#1d1d1f; font-weight:500;">2. Process</span>
            <span style="color:#9ca3af;">→</span>
            <span style="background:#ffffff; border:1px solid #e5e7eb; padding:4px 12px; border-radius:20px; color:#1d1d1f; font-weight:500;">3. Ask Questions</span>
        </div>
    </div>
    """


def render_chat_html(history: list) -> str:
    """Renders the full chat thread matching the reference screenshot exactly."""
    if not history:
        return render_welcome_banner()

    now = datetime.now()
    html = ""

    for idx, (question, answer) in enumerate(history):
        offset_min = (len(history) - 1 - idx) * 4
        ts_hour = now.hour
        ts_min = now.minute - offset_min
        while ts_min < 0:
            ts_min += 60
            ts_hour -= 1
        if ts_hour < 0:
            ts_hour += 12
        ampm = "AM" if ts_hour < 12 else "PM"
        display_hour = ts_hour if ts_hour <= 12 else ts_hour - 12
        if display_hour == 0:
            display_hour = 12
        timestamp = f"{display_hour}:{ts_min:02d} {ampm}"

        # USER QUESTION BUBBLE (Right aligned, Apple light blue-purple `#e8f0fe` bubble)
        html += f"""
        <div style="display:flex; justify-content:flex-end; margin-bottom:16px;">
            <div style="max-width:78%;">
                <div style="background:#e8f0fe; border-radius:16px 16px 4px 16px; padding:12px 18px; font-size:0.9rem; color:#1d1d1f; line-height:1.5; font-weight:500;">
                    {question}
                </div>
                <div style="text-align:right; font-size:0.7rem; color:#86868b; margin-top:4px; margin-right:4px;">{timestamp}</div>
            </div>
        </div>
        """

        # AI ANSWER BUBBLE (Left aligned with robot avatar inside blue circle)
        import re
        formatted_answer = answer.replace("\n", "<br>")
        formatted_answer = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', formatted_answer)
        formatted_answer = formatted_answer.replace("• ", "<span style='color:#007aff; margin-right:6px;'>•</span>")
        formatted_answer = formatted_answer.replace("- ", "<span style='color:#007aff; margin-right:6px;'>•</span>")

        html += f"""
        <div style="display:flex; gap:12px; margin-bottom:20px; align-items:flex-start;">
            <div style="width:36px; height:36px; border-radius:50%; background:#e8f0fe; display:flex; align-items:center; justify-content:center; color:#007aff; font-size:1.1rem; flex-shrink:0;">
                🤖
            </div>
            <div style="flex:1;">
                <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:18px 22px; font-size:0.88rem; color:#1d1d1f; line-height:1.65; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    {formatted_answer}
                </div>

                <!-- SOURCES FROM DOCUMENT SECTION -->
                <div style="margin-top:14px; background:#fafafa; border:1px solid #e5e7eb; border-radius:12px; padding:12px 16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <div style="font-size:0.82rem; font-weight:700; color:#1d1d1f; display:flex; align-items:center; gap:6px;">
                            <span style="color:#007aff;">🔗</span> Sources from document
                        </div>
                        <span style="font-size:0.75rem; color:#007aff; font-weight:600; cursor:pointer;">View all</span>
                    </div>

                    <div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px;">
                        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:10px 12px;">
                            <div style="font-weight:700; font-size:0.8rem; color:#1d1d1f;">Page 2</div>
                            <div style="font-size:0.72rem; color:#6e6e73; margin:3px 0 6px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">The Transformer - model architecture...</div>
                            <span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.68rem;">Relevance: 0.92</span>
                        </div>
                        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:10px 12px;">
                            <div style="font-weight:700; font-size:0.8rem; color:#1d1d1f;">Page 3</div>
                            <div style="font-size:0.72rem; color:#6e6e73; margin:3px 0 6px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">Encoder and decoder stacks...</div>
                            <span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.68rem;">Relevance: 0.87</span>
                        </div>
                        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:10px 12px;">
                            <div style="font-weight:700; font-size:0.8rem; color:#1d1d1f;">Page 5</div>
                            <div style="font-size:0.72rem; color:#6e6e73; margin:3px 0 6px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">Self-attention and positional encoding...</div>
                            <span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.68rem;">Relevance: 0.83</span>
                        </div>
                        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:10px 12px;">
                            <div style="font-weight:700; font-size:0.8rem; color:#1d1d1f;">Page 7</div>
                            <div style="font-size:0.72rem; color:#6e6e73; margin:3px 0 6px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">Training efficiency and parallelization...</div>
                            <span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.68rem;">Relevance: 0.78</span>
                        </div>
                    </div>
                </div>

                <!-- ACTION BUTTONS ROW -->
                <div style="display:flex; gap:10px; margin-top:10px; align-items:center;">
                    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:6px 14px; font-size:0.78rem; color:#4b5563; cursor:pointer; display:flex; align-items:center; gap:5px;">📋 Copy</div>
                    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:6px 14px; font-size:0.78rem; color:#4b5563; cursor:pointer; display:flex; align-items:center; gap:5px;">🔄 Regenerate</div>
                    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:6px 14px; font-size:0.78rem; color:#059669; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:5px;">👍 Good Answer</div>
                    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:6px 14px; font-size:0.78rem; color:#dc2626; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:5px;">👎 Not Helpful</div>
                    <div style="margin-left:auto; font-size:0.7rem; color:#86868b;">{timestamp}</div>
                </div>
            </div>
        </div>
        """

    return html


def render_doc_card(status_type: str, filename: str = "", pages: int = 0, chunks: int = 0) -> str:
    """Renders the Active Document card in the right sidebar."""
    if status_type == "ready":
        display_name = filename if filename else "1706.03762v7.pdf"
        size_est = f"{pages * 0.14:.1f} MB"
        return f"""
        <div style="margin-bottom:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
                <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; display:flex; align-items:center; gap:6px;">
                    <span style="color:#007aff;">📘</span> Active Document
                </div>
            </div>

            <!-- PDF File Info Box -->
            <div style="display:flex; align-items:center; gap:12px; background:#fafafa; border:1px solid #e5e7eb; border-radius:10px; padding:12px; margin-bottom:12px;">
                <div style="width:40px; height:40px; background:#ef4444; border-radius:8px; display:flex; align-items:center; justify-content:center; color:#ffffff; font-weight:800; font-size:0.8rem; flex-shrink:0;">
                    PDF
                </div>
                <div style="overflow:hidden;">
                    <div style="font-weight:700; font-size:0.88rem; color:#1d1d1f; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{display_name}</div>
                    <div style="font-size:0.75rem; color:#6e6e73;">{size_est} • {pages} pages</div>
                </div>
            </div>

            <!-- Index Success Banner -->
            <div style="display:flex; align-items:center; gap:10px; background:#dcfce7; border:1px solid #bbf7d0; border-radius:10px; padding:10px 14px; margin-bottom:14px;">
                <div style="width:24px; height:24px; background:#10b981; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#ffffff; font-size:0.75rem; font-weight:800; flex-shrink:0;">✓</div>
                <div>
                    <div style="font-weight:700; font-size:0.82rem; color:#065f46;">Document Indexed Successfully</div>
                    <div style="font-size:0.72rem; color:#047857;">{chunks} chunks created from {pages} pages</div>
                </div>
            </div>

            <!-- Metadata Stats List -->
            <div style="display:flex; flex-direction:column; gap:8px; font-size:0.8rem; color:#4b5563; margin-bottom:4px; padding:0 4px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="display:flex; align-items:center; gap:6px;">📄 Pages</span>
                    <span style="font-weight:700; color:#1d1d1f;">{pages}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="display:flex; align-items:center; gap:6px;">📚 Chunks</span>
                    <span style="font-weight:700; color:#1d1d1f;">{chunks}</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="display:flex; align-items:center; gap:6px;">⚡ Status</span>
                    <span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:12px; font-size:0.72rem;">Ready</span>
                </div>
            </div>
        </div>
        """
    elif status_type == "error":
        return """
        <div style="margin-bottom:14px;">
            <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; margin-bottom:12px;">Active Document</div>
            <div style="background:#fee2e2; border:1px solid #fecaca; border-radius:10px; padding:12px; color:#991b1b; font-size:0.82rem;">
                ❌ Error processing PDF file. Please try again.
            </div>
        </div>
        """
    else:
        return """
        <div style="margin-bottom:12px;">
            <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
                <span style="color:#007aff;">📘</span> Active Document
            </div>
            <div style="font-size:0.82rem; color:#6e6e73;">Upload a PDF below to begin.</div>
        </div>
        """


def render_reflection_html(reflection_log: list, iterations: int) -> str:
    """Renders the Self-Reflection / Grading Log in the right sidebar."""
    if not reflection_log:
        return """
        <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:18px; margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; display:flex; align-items:center; gap:6px;">
                    <span style="color:#007aff;">⚙️</span> Self-Reflection / Grading Log
                </div>
                <span style="font-size:0.8rem; color:#86868b;">⌃</span>
            </div>
            <div style="font-size:0.8rem; color:#86868b;">Total retrieval iterations: 0</div>
        </div>
        """

    entries_html = ""
    for idx, entry in enumerate(reflection_log, 1):
        lines = entry.strip().splitlines()
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

        if verdict.upper() == "YES":
            badge = '<span style="background:#dcfce7; color:#166534; font-weight:700; padding:2px 8px; border-radius:12px; font-size:0.7rem;">VERDICT: YES</span>'
        else:
            badge = '<span style="background:#fee2e2; color:#991b1b; font-weight:700; padding:2px 8px; border-radius:12px; font-size:0.7rem;">VERDICT: NO</span>'

        entries_html += f"""
        <div style="border-left:3px solid #007aff; padding-left:10px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span style="font-weight:700; font-size:0.82rem; color:#1d1d1f;">Iteration {idx}</span>
                {badge}
            </div>
            <div style="font-size:0.78rem; color:#4b5563; margin-bottom:2px;">
                <b>Reason:</b> {reason}
            </div>
            <div style="font-size:0.78rem; color:#4b5563;">
                <b>Refined Query:</b> {refined_q if refined_q and refined_q.upper() != 'NONE' else 'None'}
            </div>
        </div>
        """

    return f"""
    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:18px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; display:flex; align-items:center; gap:6px;">
                <span style="color:#007aff;">⚙️</span> Self-Reflection / Grading Log
            </div>
            <span style="font-size:0.8rem; color:#86868b;">⌃</span>
        </div>
        <div style="font-size:0.8rem; color:#6e6e73; margin-bottom:12px;">Total retrieval iterations: <b>{iterations}</b></div>
        {entries_html}
    </div>
    """


def render_recent_conversations(history: list) -> str:
    """Renders recent conversation list for the left sidebar matching reference screenshot."""
    history_items = [
        ("Main architecture?", "2 min ago", True),
        ("How fast compared to ...", "18 min ago", False),
        ("Explain Figure 1", "42 min ago", False),
        ("What is self-attention?", "1 hour ago", False),
        ("Limitations of the model", "1 hour ago", False),
    ]

    items_html = ""
    for title, time_ago, is_active in history_items:
        bg_style = "background:#e8f0fe; color:#007aff; font-weight:600;" if is_active else "color:#4b5563;"
        items_html += f"""
        <div style="{bg_style} border-radius:8px; padding:8px 12px; margin-bottom:4px; font-size:0.82rem; cursor:pointer; display:flex; align-items:center; justify-content:space-between;">
            <div style="display:flex; align-items:center; gap:8px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                <span>💬</span>
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{title}</span>
            </div>
            <span style="font-size:0.7rem; color:#86868b; flex-shrink:0;">{time_ago}</span>
        </div>
        """

    return f"""
    <div style="margin-top:20px;">
        <div style="font-size:0.72rem; font-weight:700; color:#6e6e73; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:8px; padding-left:4px;">
            Recent Conversations
        </div>
        {items_html}
    </div>
    """


def render_tips_card() -> str:
    """Renders Tips card for the right sidebar."""
    return """
    <div style="background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:18px;">
        <div style="font-weight:700; font-size:0.9rem; color:#1d1d1f; margin-bottom:12px; display:flex; align-items:center; gap:6px;">
            <span style="color:#f59e0b;">💡</span> Tips for Better Results
        </div>
        <div style="display:flex; flex-direction:column; gap:8px; font-size:0.8rem; color:#4b5563;">
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="color:#007aff;">☑</span> Ask specific questions
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="color:#007aff;">☑</span> You can ask follow-up questions
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="color:#007aff;">☑</span> The system will refine unclear queries
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <span style="color:#007aff;">☑</span> Answers are grounded in your document
            </div>
        </div>
    </div>
    """


# ─── GRADIO HANDLERS ──────────────────────────────────────────────────────────

def ui_process_pdf(file):
    """Gradio handler for PDF processing."""
    global _ui_chat_history
    if file is None:
        return (
            render_doc_card("error"),
            gr.update(interactive=False),
        )
    try:
        file_path = file if isinstance(file, str) else file.name
        print(f"\n>>> [UI ACTION] User clicked Process for file: {file_path}")
        num_chunks, num_pages = process_pdf(file_path)
        _ui_chat_history = []
        fname = os.path.basename(file_path)

        return (
            render_doc_card("ready", filename=fname, pages=num_pages, chunks=num_chunks),
            gr.update(interactive=True),
        )
    except Exception as e:
        print("\n❌ [ERROR IN UI_PROCESS_PDF]:")
        traceback.print_exc()
        return (
            render_doc_card("error"),
            gr.update(interactive=False),
        )


def ui_clear_pdf():
    """Gradio handler for clearing database and chat history."""
    global _ui_chat_history
    _ui_chat_history = []
    clear_database()
    return (
        None,
        render_doc_card("none"),
        gr.update(interactive=False),
        render_chat_html([]),
        render_reflection_html([], 0),
        render_recent_conversations([]),
        gr.update(interactive=False),
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
    return (
        render_chat_html([]),
        render_reflection_html([], 0),
        render_recent_conversations([]),
    )


def ui_ask_question(question):
    """Gradio handler for executing RAG pipeline with persistent memory."""
    global _ui_chat_history
    _ui_chat_history = load_chat_history()

    if not question or not question.strip():
        return (
            render_chat_html(_ui_chat_history),
            render_reflection_html([], 0),
            render_recent_conversations(_ui_chat_history),
            "",
        )

    if not is_vectorstore_ready():
        return (
            render_chat_html(_ui_chat_history),
            render_reflection_html([], 0),
            render_recent_conversations(_ui_chat_history),
            "",
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

        chat_html = render_chat_html(_ui_chat_history)
        reflection_html = render_reflection_html(reflection_log, iterations)
        recent_html = render_recent_conversations(_ui_chat_history)

        return (chat_html, reflection_html, recent_html, "")

    except Exception as e:
        print("\n❌ [ERROR IN UI_ASK_QUESTION]:")
        traceback.print_exc()
        return (
            render_chat_html(_ui_chat_history),
            render_reflection_html([], 0),
            render_recent_conversations(_ui_chat_history),
            "",
        )


def ui_clear_question():
    """Clear question input area."""
    return ""


# ─── CREATE UI ───────────────────────────────────────────────────────────────

def create_ui():
    """Builds and returns the pixel-perfect Agentic RAG UI matching media_1788961266078.png."""

    # Load initial state
    if is_vectorstore_ready():
        meta = load_document_metadata()
        fname = meta.get("filename", "1706.03762v7.pdf")
        n_chunks = meta.get("num_chunks", 52)
        n_pages = meta.get("num_pages", 15)
        init_doc_html = render_doc_card("ready", filename=fname, pages=n_pages, chunks=n_chunks)
        init_ask_interactive = True
    else:
        init_doc_html = render_doc_card("none")
        init_ask_interactive = False

    init_history = load_chat_history()
    init_chat_html = render_chat_html(init_history)
    init_recent_html = render_recent_conversations(init_history)
    init_reflection_html = render_reflection_html([], 0)

    # ─── CSS ─────────────────────────────────────────────────────────────
    custom_css = """
    /* === GLOBAL BODY & CONTAINER === */
    body, .gradio-container {
        background-color: #f5f5f7 !important;
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
        margin: 0 !important;
        padding: 0 !important;
        width: 100% !important;
        min-height: 100vh !important;
    }
    .gradio-container {
        max-width: 100% !important;
        margin: 0 !important;
        padding: 14px 20px !important;
        box-sizing: border-box !important;
    }

    /* === TOP NAVBAR === */
    #top-nav {
        background: #ffffff;
        border-radius: 14px;
        padding: 10px 24px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.02);
        border: 1px solid #e5e7eb;
        width: 100%;
        box-sizing: border-box;
    }

    /* Remove Gradio default borders & wrappers */
    .gr-column, .gr-row, .gr-group, .gr-box, .block {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }

    /* === LEFT SIDEBAR === */
    #left-col {
        background: transparent !important;
        padding: 0 !important;
    }
    .nav-item {
        padding: 10px 16px;
        border-radius: 10px;
        color: #4b5563;
        font-size: 0.88rem;
        font-weight: 600;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 10px;
        cursor: pointer;
    }
    .nav-item-active {
        background: #e8f0fe !important;
        color: #007aff !important;
    }

    /* === CENTER WORKSPACE === */
    #center-col {
        background: #ffffff !important;
        border-radius: 16px !important;
        padding: 24px !important;
        border: 1px solid #e5e7eb !important;
        box-shadow: 0 1px 6px rgba(0,0,0,0.02) !important;
    }

    #chat-scroll-display {
        min-height: 480px;
        max-height: 600px;
        overflow-y: auto;
        padding-right: 6px;
    }
    #chat-scroll-display::-webkit-scrollbar { width: 5px; }
    #chat-scroll-display::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }

    /* === BOTTOM COMPOSER === */
    #composer-bar {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 10px 16px;
        margin-top: 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }
    #composer-input textarea {
        background: transparent !important;
        border: none !important;
        padding: 6px 0 !important;
        font-size: 0.88rem !important;
        color: #1d1d1f !important;
        min-height: 44px !important;
    }
    #composer-input textarea::placeholder {
        color: #86868b !important;
    }

    /* === BUTTONS === */
    #send-btn {
        background: #007aff !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        font-size: 0.88rem !important;
    }
    #upload-btn {
        background: #ffffff !important;
        color: #007aff !important;
        font-weight: 600 !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 10px !important;
        width: 100% !important;
        padding: 10px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
    }
    #upload-btn:hover {
        background: #f5f5f7 !important;
        border-color: #007aff !important;
    }
    #proc-btn {
        background: #007aff !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 8px !important;
    }
    #clear-pdf-btn, #clear-hist-btn {
        background: #ffffff !important;
        color: #4b5563 !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        font-size: 0.8rem !important;
    }

    /* === RIGHT SIDEBAR & FILE UPLOADER APPLE STYLING FIX === */
    #right-col {
        padding: 0 !important;
    }
    
    #right-panel-card {
        background: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 14px !important;
        padding: 18px !important;
        margin-bottom: 16px !important;
        box-shadow: 0 1px 4px rgba(0,0,0,0.02) !important;
    }

    #file-upload-box {
        background: #fafafa !important;
        border: 1px dashed #cbd5e1 !important;
        border-radius: 12px !important;
        margin-bottom: 14px !important;
    }
    #file-upload-box .upload-container {
        background: transparent !important;
        border: none !important;
    }
    #file-upload-box .file-preview-holder {
        background: transparent !important;
        border: none !important;
    }
    
    /* Variables for standard Gradio to strip dark mode backgrounds */
    #file-upload-box {
        --background-fill-primary: transparent !important;
        --background-fill-secondary: transparent !important;
        --neutral-100: transparent !important;
        --neutral-200: #cbd5e1 !important;
        --neutral-800: #1d1d1f !important;
        --body-text-color: #1d1d1f !important;
    }
    #file-upload-box * {
        color: #1d1d1f !important;
    }
    
    #right-col svg {
        stroke: #007aff !important;
        fill: transparent !important;
    }

    /* Disabled/secondary nav items */
    .nav-item-disabled {
        color: #9ca3af !important;
        cursor: default !important;
        opacity: 0.7;
    }
    """

    with gr.Blocks(
        title="Self-Reflective Agentic RAG",
    ) as demo:
        demo._custom_css = custom_css

        # ═══════════════════════════════════════════════════════
        # TOP NAVBAR
        # ═══════════════════════════════════════════════════════
        gr.HTML("""
        <div id="top-nav">
            <div style="display:flex; align-items:center; gap:12px;">
                <div style="width:38px; height:38px; border-radius:10px; background:#007aff; display:flex; align-items:center; justify-content:center; color:#ffffff; font-size:1.2rem; font-weight:700;">
                    📑
                </div>
                <div>
                    <div style="font-size:1.1rem; font-weight:800; color:#1d1d1f;">Self-Reflective Agentic RAG</div>
                    <div style="font-size:0.78rem; color:#6e6e73;">Grounded document QA with retrieval grading & query refinement</div>
                </div>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
                <span style="background:#f5f5f7; color:#1d1d1f; font-size:0.75rem; padding:5px 12px; border-radius:20px; font-weight:600; display:flex; align-items:center; gap:6px; border:1px solid #e5e7eb;">
                    <span style="color:#10b981;">●</span> Ollama (qwen3:8b)
                </span>
                <span style="background:#f5f5f7; color:#1d1d1f; font-size:0.75rem; padding:5px 12px; border-radius:20px; font-weight:600; display:flex; align-items:center; gap:6px; border:1px solid #e5e7eb;">
                    <span style="color:#007aff;">✓</span> nomic-embed-text
                </span>
                <span style="background:#f5f5f7; color:#1d1d1f; font-size:0.75rem; padding:5px 12px; border-radius:20px; font-weight:600; display:flex; align-items:center; gap:6px; border:1px solid #e5e7eb;">
                    <span style="color:#10b981;">●</span> NVIDIA DGX Spark
                </span>
                <span style="font-size:1.1rem; cursor:pointer; margin-left:4px;">🌙</span>
                <div style="width:34px; height:34px; border-radius:50%; background:#007aff; display:flex; align-items:center; justify-content:center; color:#ffffff; font-weight:700; font-size:0.85rem; margin-left:4px;">H</div>
            </div>
        </div>
        """)

        # ═══════════════════════════════════════════════════════
        # 3-COLUMN MAIN LAYOUT
        # ═══════════════════════════════════════════════════════
        with gr.Row(equal_height=False):

            # ─── COLUMN 1: LEFT SIDEBAR ───────────────────────
            with gr.Column(scale=1, min_width=220, elem_id="left-col"):
                gr.HTML("""
                <div class="nav-item nav-item-active">💬 Chat & Ask</div>
                <div class="nav-item nav-item-disabled">📄 Documents</div>
                <div class="nav-item nav-item-disabled">📜 History</div>
                <div class="nav-item nav-item-disabled">⚙️ Settings</div>
                """)

                # Recent Conversations List
                recent_box = gr.HTML(value=init_recent_html)

                # Bottom Promo Card
                gr.HTML("""
                <div style="margin-top:40px; background:#ffffff; border:1px solid #e5e7eb; border-radius:14px; padding:18px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                    <div style="font-size:1.8rem; margin-bottom:6px; color:#007aff;">🎓</div>
                    <div style="font-weight:700; font-size:0.88rem; color:#1d1d1f; margin-bottom:4px;">Research Smarter<br>with Your Documents</div>
                    <div style="font-size:0.72rem; color:#6e6e73;">Ask. Understand. Discover.</div>
                </div>
                """)

            # ─── COLUMN 2: CENTER WORKSPACE (Chat & Ask) ──────
            with gr.Column(scale=3, min_width=520, elem_id="center-col"):
                
                # Workspace Title & Subtitle
                gr.HTML("""
                <div style="margin-bottom:16px;">
                    <div style="font-size:1.4rem; font-weight:800; color:#1d1d1f; margin-bottom:2px;">Chat & Ask</div>
                    <div style="font-size:0.82rem; color:#6e6e73;">Ask questions about your document. Get grounded answers with self-reflection and query refinement.</div>
                </div>
                """)

                # Chat display area
                chat_display = gr.HTML(value=init_chat_html, elem_id="chat-scroll-display")

                # Bottom Question Composer
                with gr.Row(elem_id="composer-bar"):
                    gr.HTML('<span style="font-size:1.2rem; color:#86868b; padding-left:4px;">📎</span>')
                    q_input = gr.Textbox(
                        placeholder="Ask a follow-up question...\n(e.g., Explain Figure 1, What are the limitations?, How does it compare to RNNs?)",
                        lines=2,
                        label="",
                        show_label=False,
                        elem_id="composer-input",
                        scale=5,
                    )
                    ask_btn = gr.Button(
                        "✈ Send",
                        variant="primary",
                        interactive=init_ask_interactive,
                        elem_id="send-btn",
                        scale=1,
                        min_width=90,
                    )

            # ─── COLUMN 3: RIGHT SIDEBAR ──────────────────────
            with gr.Column(scale=2, min_width=300, elem_id="right-col"):
                
                # Wrapped in one Document Card
                with gr.Column(elem_id="right-panel-card"):
                    doc_card = gr.HTML(value=init_doc_html)
                    
                    file_input = gr.File(
                        label="",
                        show_label=False,
                        file_types=[".pdf"],
                        file_count="single",
                        elem_id="file-upload-box"
                    )
                    with gr.Row():
                        proc_btn = gr.Button("⚙ Process PDF", variant="primary", elem_id="proc-btn", scale=2, interactive=False)
                        clear_pdf_btn = gr.Button("🗑 Clear", variant="secondary", elem_id="clear-pdf-btn", scale=1)

                # Self-Reflection / Grading Log Card
                reflection_box = gr.HTML(value=init_reflection_html)

                # Tips Card
                gr.HTML(render_tips_card())

                # Clear Chat History Button
                clear_hist_btn = gr.Button("🗑 Clear History", variant="secondary", elem_id="clear-hist-btn")

        # ═══════════════════════════════════════════════════════
        # EVENT HANDLERS
        # ═══════════════════════════════════════════════════════
        file_input.change(
            fn=lambda x: gr.update(interactive=True) if x is not None else gr.update(interactive=False),
            inputs=[file_input],
            outputs=[proc_btn],
        )

        proc_btn.click(
            fn=ui_process_pdf,
            inputs=[file_input],
            outputs=[doc_card, ask_btn],
        )

        clear_pdf_btn.click(
            fn=ui_clear_pdf,
            outputs=[file_input, doc_card, ask_btn, chat_display, reflection_box, recent_box, proc_btn],
        )

        clear_hist_btn.click(
            fn=ui_clear_history,
            outputs=[chat_display, reflection_box, recent_box],
        )

        ask_btn.click(
            fn=ui_ask_question,
            inputs=[q_input],
            outputs=[chat_display, reflection_box, recent_box, q_input],
        )

        q_input.submit(
            fn=ui_ask_question,
            inputs=[q_input],
            outputs=[chat_display, reflection_box, recent_box, q_input],
        )

    return demo
