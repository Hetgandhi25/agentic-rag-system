import pytest
from src.title_utils import generate_title, _is_greeting

def test_is_greeting():
    assert _is_greeting("hi")
    assert _is_greeting("HELLO")
    assert _is_greeting("ok")
    assert _is_greeting("thanks")
    assert _is_greeting("?")
    assert _is_greeting("   ")
    assert not _is_greeting("What is RAG?")
    assert not _is_greeting("Explain the architecture")

def test_generate_title_greeting():
    assert generate_title("hi") == "New Conversation"
    assert generate_title("ok") == "New Conversation"

def test_generate_title_meaningful(monkeypatch):
    import src.title_utils
    monkeypatch.setattr(src.title_utils, "invoke_llm", lambda llm, prompt: "RAG Architecture Explanation")

    title = generate_title("Explain how RAG works")
    assert title != "New Conversation"
    assert len(title.split()) <= 6
    assert title == "RAG Architecture Explanation"
