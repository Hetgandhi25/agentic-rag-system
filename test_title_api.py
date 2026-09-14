import pytest
from fastapi.testclient import TestClient
from src.api import app, get_db
from src.database import Base, engine, SessionLocal
from src.models import Session, Message, Document
import uuid

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_rag_app(monkeypatch):
    import src.api
    
    def dummy_stream(inputs, stream_mode, config):
        yield {"dummy_node": {"answer": "Dummy answer", "sources": []}}
        
    monkeypatch.setattr(src.api.rag_app, "stream", dummy_stream)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield

@pytest.fixture
def mock_document():
    db = SessionLocal()
    doc = Document(id=str(uuid.uuid4()), filename="test.pdf")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_id = doc.id
    db.close()
    return doc_id

def test_new_session_title():
    # Create new session
    response = client.post("/api/sessions", json={"document_id": None})
    assert response.status_code == 200
    data = response.json()["session"]
    assert data["title"] == "New Conversation"

def test_greeting_keeps_default_title(mock_document):
    # Create session
    resp = client.post("/api/sessions", json={"document_id": mock_document})
    session_id = resp.json()["session"]["id"]
    
    # Send greeting via chat_stream
    response = client.post("/api/chat_stream", json={"session_id": session_id, "question": "hi"})
    assert response.status_code == 200
            
    # Fetch session details
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.json()["session"]["title"] == "New Conversation"

def test_meaningful_query_updates_title(mock_document, monkeypatch):
    import src.title_utils
    monkeypatch.setattr(src.title_utils, "invoke_llm", lambda llm, prompt: "The Capital of France")

    # Create session
    resp = client.post("/api/sessions", json={"document_id": mock_document})
    session_id = resp.json()["session"]["id"]
    
    # Send meaningful query
    response = client.post("/api/chat_stream", json={"session_id": session_id, "question": "What is the capital of France?"})
    assert response.status_code == 200
            
    import time
    time.sleep(1)
    # Fetch session details
    resp = client.get(f"/api/sessions/{session_id}")
    title = resp.json()["session"]["title"]
    assert title != "New Conversation"
    assert title == "The Capital of France"

def test_title_not_overwritten(mock_document, monkeypatch):
    import src.title_utils
    
    def mock_invoke_llm(llm, prompt):
        if "What is the capital of France?" in prompt:
            return "First Title"
        return "Second Title"
        
    monkeypatch.setattr(src.title_utils, "invoke_llm", mock_invoke_llm)

    # Create session
    resp = client.post("/api/sessions", json={"document_id": mock_document})
    session_id = resp.json()["session"]["id"]
    
    # Send meaningful query
    response = client.post("/api/chat_stream", json={"session_id": session_id, "question": "What is the capital of France?"})
    assert response.status_code == 200
            
    import time
    time.sleep(1)
    # Fetch session details to get the title
    resp = client.get(f"/api/sessions/{session_id}")
    initial_title = resp.json()["session"]["title"]
    assert initial_title == "First Title"
    
    # Send another query
    response = client.post("/api/chat_stream", json={"session_id": session_id, "question": "What about Germany?"})
    assert response.status_code == 200
            
    # Title should be the same
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.json()["session"]["title"] == initial_title
