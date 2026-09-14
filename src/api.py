import os
import shutil
import json
import asyncio
import logging
import queue
import threading
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy import text
import time
from sqlalchemy.orm import Session as DBSession
from langchain_core.callbacks import BaseCallbackHandler

from src.database import engine, Base, SessionLocal, get_db
from src.models import Document, Session, Message
from src.document_processor import process_pdf, delete_document
from src.graph import app as rag_app

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ─── DB Schema Migration ──────────────────────────────────────────────────────

def _migrate_schema():
    """
    Idempotent migration: ensure sessions.document_id is nullable (SET NULL on delete).
    SQLite does not support ALTER COLUMN, so we detect the old schema and
    recreate the table if needed — safely, by renaming + copying data.
    """
    with engine.connect() as conn:
        # Check current sessions table schema
        result = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
        if not result:
            # Table does not exist yet — Base.metadata.create_all() will create it correctly
            return

        col_info = {row[1]: row for row in result}  # name → row
        doc_id_col = col_info.get("document_id")
        if doc_id_col is None:
            return  # Unexpected schema, let SQLAlchemy handle it

        # row[3] is "notnull": 1 = NOT NULL, 0 = nullable
        is_not_null = doc_id_col[3] == 1

        if is_not_null:
            logger.info("[MIGRATION] sessions.document_id is NOT NULL. Migrating to nullable...")
            conn.execute(text("PRAGMA foreign_keys=off;"))
            conn.execute(text("BEGIN TRANSACTION;"))
            conn.execute(text("ALTER TABLE sessions RENAME TO _sessions_old;"))
            conn.execute(text("""
                CREATE TABLE sessions (
                    id VARCHAR NOT NULL, 
                    title VARCHAR NOT NULL, 
                    document_id VARCHAR, 
                    created_at DATETIME, 
                    updated_at DATETIME, 
                    PRIMARY KEY (id), 
                    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE SET NULL
                );
            """))
            conn.execute(text("""
                INSERT INTO sessions (id, title, document_id, created_at, updated_at)
                SELECT id, title, document_id, created_at, updated_at FROM _sessions_old;
            """))
            conn.execute(text("DROP TABLE _sessions_old;"))
            conn.execute(text("COMMIT;"))
            conn.execute(text("PRAGMA foreign_keys=on;"))
            logger.info("[MIGRATION] Migration complete.")
        else:
            logger.info("[MIGRATION] sessions.document_id already nullable — no migration needed.")

        # Add metrics column to messages if missing
        msg_result = conn.execute(text("PRAGMA table_info(messages)")).fetchall()
        if msg_result:
            msg_col_info = {row[1]: row for row in msg_result}
            if "metrics" not in msg_col_info:
                logger.info("[MIGRATION] messages.metrics missing. Migrating...")
                conn.execute(text("ALTER TABLE messages ADD COLUMN metrics JSON;"))
                conn.commit()
                logger.info("[MIGRATION] Added metrics column.")


# Run migration then create any missing tables
_migrate_schema()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Self-Reflective Agentic RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    document_id: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    question: str


class FeedbackRequest(BaseModel):
    message_id: str
    feedback: int


class RegenerateRequest(BaseModel):
    session_id: str


# ─── Document API ────────────────────────────────────────────────────────────

@app.get("/api/documents")
def get_documents(db: DBSession = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return {
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "num_pages": d.num_pages,
                "num_chunks": d.num_chunks,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    os.makedirs("tmp", exist_ok=True)
    safe_name = os.path.basename(file.filename)
    temp_file_path = os.path.join("tmp", safe_name)

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        doc_info = await asyncio.to_thread(process_pdf, temp_file_path, safe_name)
        return {"success": True, "document": doc_info}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@app.delete("/api/documents/{document_id}")
def api_delete_document(document_id: str, db: DBSession = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Null out document_id on associated sessions BEFORE deleting doc,
    # so sessions (and their messages) survive the deletion.
    # SQLite's ON DELETE SET NULL requires PRAGMA foreign_keys=ON which is
    # not always reliable in SQLite, so we do it explicitly here.
    db.query(Session).filter(Session.document_id == document_id).update(
        {"document_id": None}, synchronize_session="fetch"
    )
    db.commit()

    try:
        delete_document(document_id)
    except Exception as e:
        logger.error(f"Delete document error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True}


# ─── Session API ─────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def get_sessions(db: DBSession = Depends(get_db)):
    sessions = db.query(Session).order_by(Session.updated_at.desc()).all()
    result = []
    for s in sessions:
        # Resolve document filename for UI display; None if document was deleted
        doc_filename = None
        if s.document_id:
            doc = db.query(Document).filter(Document.id == s.document_id).first()
            if doc:
                doc_filename = doc.filename

        result.append({
            "id": s.id,
            "title": s.title,
            "document_id": s.document_id,
            "document_filename": doc_filename,
            "document_deleted": s.document_id is None and s.title != "New Chat",
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return {"sessions": result}


@app.post("/api/sessions")
def create_session(req: CreateSessionRequest, db: DBSession = Depends(get_db)):
    doc_id = None
    if req.document_id:
        doc = db.query(Document).filter(Document.id == req.document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        doc_id = doc.id

    session = Session(document_id=doc_id, title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session": {
            "id": session.id,
            "title": session.title,
            "document_id": session.document_id,
            "document_deleted": False,
        }
    }


class UpdateSessionRequest(BaseModel):
    document_id: str

@app.put("/api/sessions/{session_id}")
def update_session(session_id: str, req: UpdateSessionRequest, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    doc = db.query(Document).filter(Document.id == req.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    session.document_id = doc.id
    db.commit()
    db.refresh(session)
    return {
        "session": {
            "id": session.id,
            "title": session.title,
            "document_id": session.document_id,
            "document_filename": doc.filename,
            "document_deleted": False,
        }
    }



@app.get("/api/sessions/{session_id}")
def get_session_details(session_id: str, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )

    doc_filename = None
    doc_deleted = False
    
    if session.document_id:
        doc = db.query(Document).filter(Document.id == session.document_id).first()
        if doc:
            doc_filename = doc.filename
        else:
            doc_deleted = True
    else:
        # If there are messages but no document_id, the document was deleted.
        # If there are no messages, it's just an empty session waiting for a document.
        if len(messages) > 0:
            doc_deleted = True

    return {
        "session": {
            "id": session.id,
            "title": session.title,
            "document_id": session.document_id,
            "document_filename": doc_filename,
            "document_deleted": doc_deleted,
        },
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "metrics": m.metrics,
                "feedback": m.feedback,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, db: DBSession = Depends(get_db)):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"success": True}


# ─── Feedback API ─────────────────────────────────────────────────────────────

@app.post("/api/feedback")
def set_feedback(req: FeedbackRequest, db: DBSession = Depends(get_db)):
    msg = db.query(Message).filter(Message.id == req.message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.feedback = req.feedback
    db.commit()
    return {"success": True, "feedback": msg.feedback}


# ─── Regenerate API ───────────────────────────────────────────────────────────

@app.post("/api/regenerate")
def regenerate(req: RegenerateRequest, db: DBSession = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter(Message.session_id == req.session_id)
        .order_by(Message.created_at.desc())
        .all()
    )
    if not messages:
        raise HTTPException(status_code=400, detail="No messages in this session")

    last_msg = messages[0]  # most recent
    if last_msg.role == "ai":
        db.delete(last_msg)
        db.commit()
        # Return the last user question
        last_user = next((m for m in messages if m.role == "user"), None)
        return {"success": True, "last_question": last_user.content if last_user else ""}

    return {"success": True, "last_question": last_msg.content}


# ─── Streaming Chat API ───────────────────────────────────────────────────────

class TokenStreamCallback(BaseCallbackHandler):
    def __init__(self, event_queue: queue.Queue):
        self.event_queue = event_queue

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.event_queue.put({"event": "token", "data": json.dumps(token)})


def _stream_langgraph_to_queue(inputs: dict, event_queue: queue.Queue):
    """
    Run the LangGraph pipeline synchronously in a worker thread.
    Each node update is pushed to event_queue as a dict {"event": ..., "data": ...}.
    Sends {"event": "__done__", "data": final_state} when complete.
    Sends {"event": "__error__", "data": error_str} on failure.
    """
    try:
        final_state = dict(inputs)
        callback = TokenStreamCallback(event_queue)
        
        for chunk in rag_app.stream(inputs, stream_mode="updates", config={"callbacks": [callback]}):
            for node, state_update in chunk.items():
                final_state.update(state_update)
                # Emit node-specific status events
                if node == "retrieve":
                    n_chunks = len(state_update.get("sources", []))
                    event_queue.put({"event": "status", "data": f"Retrieved {n_chunks} chunks from document"})
                elif node == "grade_retrieval":
                    event_queue.put({"event": "status", "data": "Evaluating retrieval quality..."})
                    if "reflection_log" in state_update:
                        event_queue.put({"event": "log", "data": json.dumps(state_update["reflection_log"])})
                elif node == "increment_iterations":
                    pass  # Transparent node — no event needed
                elif node == "rewrite_query":
                    refined = state_update.get("refined_query", "")
                    event_queue.put({"event": "status", "data": f"Refining query: {refined[:80]}"})
                elif node == "generate":
                    event_queue.put({"event": "status", "data": "Generating grounded answer..."})

        event_queue.put({"event": "__done__", "data": final_state})
    except Exception as e:
        logger.error(f"LangGraph thread error: {e}", exc_info=True)
        event_queue.put({"event": "__error__", "data": str(e)})


@app.post("/api/chat_stream")
async def chat_stream(req: ChatRequest, request: Request):
    """
    SSE endpoint that streams real-time status updates while LangGraph runs
    in a worker thread. Status events are emitted from the thread via a queue
    that the async generator polls — this avoids blocking the asyncio event loop.
    """
    total_start_time = time.time()
    
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Load session data using a dedicated DB connection
    db = SessionLocal()
    try:
        session = db.query(Session).filter(Session.id == req.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Reject chat if document was deleted (read-only mode)
        if not session.document_id:
            raise HTTPException(
                status_code=400,
                detail="This conversation's document has been deleted. New questions cannot be answered. The chat history is preserved for reference."
            )

        doc = db.query(Document).filter(Document.id == session.document_id).first()
        if not doc:
            # document_id set but doc gone (shouldn't happen after migration, but be safe)
            # Null out and reject
            session.document_id = None
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="This conversation's document has been deleted. New questions cannot be answered."
            )

        # Update title from first question
        if session.title == "New Chat":
            session.title = question[:50] + ("..." if len(question) > 50 else "")
            db.commit()

        # Build chat history from prior messages (pair up user+ai turns)
        prev_messages = (
            db.query(Message)
            .filter(Message.session_id == req.session_id)
            .order_by(Message.created_at.asc())
            .all()
        )
        chat_history = []
        pending_user = ""
        for m in prev_messages:
            if m.role == "user":
                pending_user = m.content
            elif m.role == "ai" and pending_user:
                chat_history.append((pending_user, m.content))
                pending_user = ""

        # Persist user message immediately so refresh restores it
        user_msg = Message(session_id=session.id, role="user", content=question)
        db.add(user_msg)
        db.commit()

        # Capture needed values before closing DB
        session_id = session.id
        document_id = session.document_id
    finally:
        db.close()

    # LangGraph inputs — iterations starts at 0; the router increments it
    inputs = {
        "session_id": session_id,
        "document_id": document_id,
        "question": question,
        "refined_query": "",
        "context": "",
        "sources": [],
        "reflection": "",
        "answer": "",
        "iterations": 0,
        "reflection_log": [],
        "chat_history": chat_history,
    }

    async def event_generator():
        yield {"event": "status", "data": "Starting agent..."}

        # Queue for thread → async communication
        event_queue: queue.Queue = queue.Queue()

        # Start LangGraph in a background thread
        thread = threading.Thread(
            target=_stream_langgraph_to_queue,
            args=(inputs, event_queue),
            daemon=True,
        )
        thread.start()

        final_state = None
        error_str = None

        # Poll the queue and yield events to SSE client
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(f"Client disconnected for session {session_id}")
                break

            # Non-blocking queue read with short sleep to yield control
            try:
                item = event_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.5)
                yield {"event": "ping", "data": ""}
                continue

            if item["event"] == "__done__":
                final_state = item["data"]
                break
            elif item["event"] == "__error__":
                error_str = item["data"]
                break
            else:
                # Forward intermediate events (status, log, etc.) to client
                if item["event"] == "token":
                    # Drip-feed tokens letter-by-letter for a typewriter effect
                    token_str = json.loads(item["data"])
                    for char in token_str:
                        yield {"event": "token", "data": json.dumps(char)}
                        await asyncio.sleep(0.01)  # 10ms delay per character
                else:
                    yield item

        # Wait for thread to finish (it should have already)
        thread.join(timeout=5)

        if error_str:
            err_db = SessionLocal()
            try:
                err_content = f"⚠️ An error occurred during processing: {error_str}. Please try again."
                err_ai_msg = Message(session_id=session_id, role="ai", content=err_content)
                err_db.add(err_ai_msg)
                err_db.commit()
                err_db.refresh(err_ai_msg)
                err_msg_id = err_ai_msg.id
            finally:
                err_db.close()
            yield {"event": "error", "data": error_str}
            yield {"event": "answer", "data": json.dumps(err_content)}
            yield {"event": "message_id", "data": err_msg_id}
            yield {"event": "done", "data": "true"}
            return

        if not final_state:
            # Client disconnected before completion — nothing to emit
            return

        # Get the final answer and sources
        answer = final_state.get("answer", "").strip()
        sources = final_state.get("sources", [])
        reflection_log = final_state.get("reflection_log", [])
        all_no = bool(reflection_log) and all(
            "VERDICT: NO" in entry.upper() for entry in reflection_log
        )

        if not answer:
            answer = (
                "The document does not appear to contain sufficient information to answer this question. "
                "Please try rephrasing or ask about a different aspect."
            )

        metrics = final_state.get("metrics", {})
        metrics["total_time"] = time.time() - total_start_time

        # Persist AI message
        save_db = SessionLocal()
        ai_msg_id = "unsaved"
        try:
            ai_msg = Message(
                session_id=session_id,
                role="ai",
                content=answer,
                # Only store sources if context was actually used (not all-NO)
                sources=sources if not all_no else [],
                metrics=metrics,
            )
            save_db.add(ai_msg)
            sess_obj = save_db.query(Session).filter(Session.id == session_id).first()
            if sess_obj:
                sess_obj.updated_at = datetime.utcnow()
            save_db.commit()
            save_db.refresh(ai_msg)
            ai_msg_id = ai_msg.id
        except Exception as e:
            logger.error(f"DB save error for session {session_id}: {e}", exc_info=True)
        finally:
            save_db.close()

        # Emit final reflection log (deduplicated — it was already sent incrementally)
        if reflection_log:
            yield {"event": "log", "data": json.dumps(reflection_log)}

        # Only emit sources when context was actually used
        if sources and not all_no:
            yield {"event": "sources", "data": json.dumps(sources)}

        yield {"event": "all_no", "data": json.dumps(all_no)}
        yield {"event": "message_id", "data": ai_msg_id}
        yield {"event": "answer", "data": json.dumps(answer)}
        yield {"event": "metrics", "data": json.dumps(metrics)}
        
        yield {"event": "done", "data": "true"}

    return EventSourceResponse(event_generator())


# ─── React SPA Static Serving ─────────────────────────────────────────────────

DIST_DIR = "frontend/dist"
if os.path.exists(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        response = FileResponse(os.path.join(DIST_DIR, "index.html"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
