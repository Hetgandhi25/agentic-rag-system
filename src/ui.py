import gradio as gr
import os
from src.document_processor import process_pdf, clear_database
from src.graph import app
from src.config import CHROMA_DB_PATH

def ui_process_pdf(file):
    """Gradio handler for PDF processing."""
    if file is None:
        return (
            gr.update(value="⚠️ No file selected. Please upload a PDF first."),
            gr.update(interactive=False),
        )
    try:
        file_path = file if isinstance(file, str) else file.name
        num_chunks, num_pages = process_pdf(file_path)

        return (
            gr.update(value=f"✅ Ready — {num_chunks} chunks indexed from {num_pages} pages."),
            gr.update(interactive=True),
        )
    except Exception as e:
        return (
            gr.update(value=f"❌ Processing failed: {str(e)}"),
            gr.update(interactive=False),
        )

def ui_clear_pdf():
    """Gradio handler for clearing the database."""
    clear_database()
    return (
        None,
        gr.update(value="🗑️ Document cleared. Upload a new PDF to continue."),
        gr.update(interactive=False),
    )

def ui_ask_question(question):
    """Gradio handler for executing the RAG flow."""
    if not question or not question.strip():
        return gr.update(value=""), gr.update(value="*Ask a question to get started.*")

    if not os.path.exists(CHROMA_DB_PATH):
        return (
            gr.update(value="⚠️ No document loaded. Upload and process a PDF first."),
            gr.update(value=""),
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
        })

        reflection_log = result.get("reflection_log", [])
        iterations = result.get("iterations", 0)
        answer = result.get("answer", "No answer was generated.")

        separator = "\n" + "─" * 60 + "\n"
        log_text = f"Total retrieval iterations: {iterations}\n" + separator
        log_text += separator.join(reflection_log) if reflection_log else "No reflection data."

        return gr.update(value=log_text), gr.update(value=answer)

    except Exception as e:
        return (
            gr.update(value=f"❌ Error during inference: {str(e)}"),
            gr.update(value=""),
        )

def ui_clear_question():
    """Clear question output."""
    return "", gr.update(value=""), gr.update(value="*Ask a question to get started.*")

def create_ui():
    """Builds and returns the Gradio UI."""
    with gr.Blocks(
        theme=gr.themes.Soft(),
        title="Agentic RAG System",
        css="""
            .header-box { text-align: center; padding: 8px 0 4px 0; }
            .section-label { font-weight: 600; margin-bottom: 4px; }
        """,
    ) as demo:
        gr.Markdown(
            """
            <div class="header-box">
            # 🔄 Self-Reflective Agentic RAG
            **Powered by Ollama (Qwen 3) · nomic-embed-text · LangGraph**
            </div>
            > This system doesn't answer right after retrieval. It **grades** the retrieved context for relevance and sufficiency,
            > **rewrites the query** if context is lacking, and only generates an answer once the context passes validation —
            > reducing hallucinations through an iterative retrieval loop.
            """,
            elem_classes="header-box",
        )
        gr.Markdown("---")

        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### 📄 Document")
                file_input = gr.File(
                    label="Upload PDF",
                    file_types=[".pdf"],
                    file_count="single",
                )
                with gr.Row():
                    proc_btn = gr.Button("⚙️ Process", variant="primary", scale=2)
                    clear_pdf_btn = gr.Button("🗑️ Clear", variant="secondary", scale=1)
                status_box = gr.Textbox(
                    label="Status",
                    value="No document loaded.",
                    interactive=False,
                    lines=2,
                )

            with gr.Column(scale=2):
                gr.Markdown("### 💬 Ask a Question")
                q_input = gr.Textbox(
                    label="Question",
                    placeholder="What does the document say about…?",
                    lines=3,
                )
                with gr.Row():
                    ask_btn = gr.Button(
                        "🔍 Ask",
                        variant="primary",
                        interactive=False,
                        scale=3,
                    )
                    clear_q_btn = gr.Button("✖ Clear", variant="secondary", scale=1)

        gr.Markdown("---")

        with gr.Accordion("🔄 Self-Reflection Loop  (retrieval grading & query refinement)", open=False):
            gr.Markdown(
                "_Each iteration shows the LLM's verdict on the retrieved context. "
                "A `NO` verdict triggers query rewriting and a new retrieval attempt._"
            )
            reflection_log_box = gr.Textbox(
                label="Grading Log",
                lines=12,
                interactive=False,
                placeholder="Reflection logs will appear here after you ask a question.",
            )

        gr.Markdown("### 📝 Answer")
        answer_box = gr.Markdown(value="*Ask a question to get started.*")

        proc_btn.click(fn=ui_process_pdf, inputs=[file_input], outputs=[status_box, ask_btn])
        clear_pdf_btn.click(fn=ui_clear_pdf, outputs=[file_input, status_box, ask_btn])
        ask_btn.click(fn=ui_ask_question, inputs=[q_input], outputs=[reflection_log_box, answer_box])
        clear_q_btn.click(fn=ui_clear_question, outputs=[q_input, reflection_log_box, answer_box])

    return demo
