import time
import pytest
from fastapi.testclient import TestClient
from src.api import app
from src.models import Document, Session
from src.database import Base, engine, SessionLocal
import uuid
import json

client = TestClient(app)

def test_full_title_audit():
    # 1. "New Conversation" is the default.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    doc = Document(id=str(uuid.uuid4()), filename="test.pdf")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Session 1: test greeting
    resp1 = client.post("/api/sessions", json={"document_id": doc.id})
    sess1 = resp1.json()["session"]
    assert sess1["title"] == "New Conversation"
    
    # 2. Greetings/gibberish do not generate titles.
    start = time.time()
    res1 = client.post("/api/chat_stream", json={"session_id": sess1["id"], "question": "hi"})
    lat_greet = time.time() - start
    
    r1 = client.get(f"/api/sessions/{sess1['id']}")
    assert r1.json()["session"]["title"] == "New Conversation"
    
    # 4. A meaningful message after "Hi/Hello/OK" replaces the default title.
    start = time.time()
    res2 = client.post("/api/chat_stream", json={"session_id": sess1["id"], "question": "What is the capital of France?"})
    lat_meaningful_after_greet = time.time() - start
    
    r2 = client.get(f"/api/sessions/{sess1['id']}")
    title2 = r2.json()["session"]["title"]
    assert title2 != "New Conversation"
    assert len(title2.split()) <= 6
    print(f"Title 1: {title2}")
    
    # 5. The title is generated only once and never changes on follow-ups
    res3 = client.post("/api/chat_stream", json={"session_id": sess1["id"], "question": "What about Germany?"})
    
    r3 = client.get(f"/api/sessions/{sess1['id']}")
    assert r3.json()["session"]["title"] == title2
    
    # 3. The first meaningful message generates a concise 2–6 word title.
    resp2 = client.post("/api/sessions", json={"document_id": doc.id})
    sess2 = resp2.json()["session"]
    
    start = time.time()
    res4 = client.post("/api/chat_stream", json={"session_id": sess2["id"], "question": "Explain the architecture of the system"})
    lat_meaningful_direct = time.time() - start
    
    r4 = client.get(f"/api/sessions/{sess2['id']}")
    title4 = r4.json()["session"]["title"]
    assert title4 != "New Conversation"
    print(f"Title 2: {title4}")
    
    print("\n--- Latency Report ---")
    print(f"Greeting Latency: {lat_greet:.3f}s")
    print(f"Meaningful After Greet Latency: {lat_meaningful_after_greet:.3f}s")
    print(f"Meaningful Direct Latency: {lat_meaningful_direct:.3f}s")
    print(f"-> Title generation overhead: ~{abs(lat_meaningful_direct - lat_greet):.3f}s")
    
    print("\nAll verifications passed!")
    
if __name__ == "__main__":
    test_full_title_audit()
