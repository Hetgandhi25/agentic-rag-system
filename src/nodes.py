from langchain_ollama import ChatOllama
from src.state import GraphState
from src.config import OLLAMA_MODEL, OLLAMA_BASE_URL
from src.document_processor import get_db

def get_llm():
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0, # Deterministic grading
    )

def extract_text(response) -> str:
    """Safely extract a plain string from an LLM response."""
    content = response.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", ""))
        return " ".join(parts).strip()
    return str(content).strip()

def retrieve(state: GraphState) -> dict:
    """Retrieve top-k chunks using the current query."""
    print("\n--- [NODE: RETRIEVE] ---", flush=True)
    query = state.get("refined_query") or state["question"]
    print(f"Searching vectorstore for: '{query}'", flush=True)
    db = get_db()
    docs = db.similarity_search(query, k=4)
    context = "\n\n".join(
        [f"[Chunk {i + 1}]:\n{d.page_content}" for i, d in enumerate(docs)]
    )
    print(f"Retrieved {len(docs)} chunks.", flush=True)
    return {
        "context": context,
        "refined_query": query,
        "iterations": state.get("iterations", 0) + 1,
    }

def grade_retrieval(state: GraphState) -> dict:
    """LLM judges whether the retrieved context is relevant and sufficient."""
    print("\n--- [NODE: GRADE_RETRIEVAL] ---", flush=True)
    print("Evaluating context with qwen3:8b...", flush=True)
    llm = get_llm()
    prompt = f"""You are a strict retrieval quality judge for a RAG system.

Your job: decide if the retrieved context is good enough to answer the question accurately.

Question: {state['question']}

Retrieved Context:
{state['context']}

Evaluate the context on three criteria:
1. RELEVANCE — Does it directly address the question?
2. SUFFICIENCY — Does it contain enough detail for a complete answer?
3. CONSISTENCY — Are there contradictions between chunks?

Reply in this EXACT format (no extra lines):
VERDICT: YES
REASON: <one sentence>
REFINED_QUERY: NONE

OR if context is not good enough:
VERDICT: NO
REASON: <one sentence explaining what is missing or wrong>
REFINED_QUERY: <a better, more specific search query to find the missing information>"""

    response = llm.invoke(prompt)
    content = extract_text(response)
    print(f"Grading Result:\n{content}", flush=True)

    log_entry = f"Iteration {state.get('iterations', 1)}\n{content}"
    reflection_log = list(state.get("reflection_log", [])) + [log_entry]

    return {
        "reflection": content,
        "reflection_log": reflection_log,
    }

def rewrite_query(state: GraphState) -> dict:
    """Extract the REFINED_QUERY from the grader's output."""
    print("\n--- [NODE: REWRITE_QUERY] ---", flush=True)
    reflection = state.get("reflection", "")
    refined = state["question"]  # safe fallback

    for line in reflection.splitlines():
        line = line.strip()
        if line.upper().startswith("REFINED_QUERY:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate and candidate.upper() != "NONE":
                refined = candidate
                break

    print(f"New refined query: '{refined}'", flush=True)
    return {"refined_query": refined}

def generate(state: GraphState) -> dict:
    """Generate the final answer grounded strictly in the validated context and conversation history."""
    print("\n--- [NODE: GENERATE] ---", flush=True)
    print("Generating final answer with qwen3:8b...", flush=True)
    llm = get_llm()

    history_str = ""
    chat_history = state.get("chat_history", [])
    if chat_history:
        history_lines = []
        for q, a in chat_history[-3:]:
            history_lines.append(f"User: {q}\nAssistant: {a}")
        history_str = "\n\nPrevious Conversation History:\n" + "\n---\n".join(history_lines) + "\n"

    prompt = f"""You are a precise, helpful assistant. Answer the question using ONLY the provided context and conversation history.
If the context is insufficient for a complete answer, clearly state what is missing — do not hallucinate.

Question: {state['question']}
{history_str}
Validated Context:
{state['context']}

Write a clear, structured answer grounded in the context above."""

    response = llm.invoke(prompt)
    answer = extract_text(response)
    print("Generation complete.", flush=True)

    updated_history = list(chat_history) + [(state['question'], answer)]
    return {
        "answer": answer,
        "chat_history": updated_history,
    }
