import re
import time
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from src.state import GraphState
from src.config import (
    MODEL_PAI_BASE_URL,
    MODEL_PAI_API_KEY,
    MODEL_PAI_MODEL,
    MAX_ITERATIONS,
)
from src.document_processor import get_vectorstore

# ─── vLLM / OpenAI-compatible client ─────────────────────────────────────────

# vLLM-specific extra body parameters (injected raw into the HTTP JSON body).
# These CANNOT go in model_kwargs because the openai SDK's Completions.create()
# performs strict kwarg validation and will raise TypeError for unknown keys.
# Passing them via extra_body bypasses SDK validation entirely.
_VLLM_EXTRA_BODY = {
    "top_k": 20,
    "min_p": 0.0,
    "repetition_penalty": 1.0,
    "chat_template_kwargs": {"enable_thinking": False},
}


def get_llm() -> ChatOpenAI:
    """
    Returns a LangChain ChatOpenAI client pointed at the vLLM gateway
    (Qwen3.8-27B served via OpenAI-compatible API at http://192.168.100.10:8000).

    Sampling follows HuggingFace's recommended Qwen3 instruct params.
    Thinking is DISABLED (enable_thinking=False) via extra_body so the model
    responds in plain instruct style with no <think> blocks.

    NOTE: vLLM-specific params (top_k, min_p, etc.) are passed via extra_body
    on each .invoke() call, NOT via model_kwargs, to avoid the openai SDK's
    strict Completions.create() parameter validation rejecting unknown kwargs.
    """
    return ChatOpenAI(
        model=MODEL_PAI_MODEL,
        base_url=MODEL_PAI_BASE_URL.rstrip("/"),  # already contains /v1 per config
        api_key=MODEL_PAI_API_KEY,
        temperature=0.7,
        top_p=0.8,
        presence_penalty=1.5,
        max_tokens=2048,
        timeout=60.0,  # 60s timeout to prevent hanging
        streaming=True, # Enable streaming tokens
        # No model_kwargs here — vLLM extras go through extra_body at call time
    )


def invoke_llm(llm: ChatOpenAI, prompt: str, config: RunnableConfig = None) -> str:
    """
    Invoke the LLM with vLLM extra_body params injected at call time.
    This is the correct way to pass vLLM-specific keys (top_k, min_p,
    chat_template_kwargs) without triggering the openai SDK TypeError.
    """
    bound = llm.bind(extra_body=_VLLM_EXTRA_BODY)
    response = bound.invoke(prompt, config=config)
    return extract_text(response)


# ─── Safety: strip any stray <think> blocks ──────────────────────────────────
# enable_thinking=False should prevent these, but kept as a safety net in case
# the server is switched to a thinking-enabled config or model.

def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from model output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_text(response) -> str:
    """Safely extract a plain string from an LLM response, stripping think-tags."""
    content = response.content
    if isinstance(content, str):
        raw = content.strip()
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", ""))
        raw = " ".join(parts).strip()
    else:
        raw = str(content).strip()

    return strip_think_tags(raw)


# ─── RAG Pipeline Nodes ───────────────────────────────────────────────────────

def retrieve(state: GraphState) -> dict:
    """
    Retrieve top-k chunks using the current query and document_id filter.
    k grows with iteration count to cast a wider net on refinement rounds.
    NOTE: 'iterations' is NOT incremented here — managed by the router.
    """
    start_time = time.time()
    print("\n--- [NODE: RETRIEVE] ---", flush=True)
    query = state.get("refined_query") or state["question"]
    doc_id = state.get("document_id")
    iteration = state.get("iterations", 0)

    # Increase k on later iterations to cast a wider net
    k = min(4 + iteration * 2, 10)
    print(f"Searching vectorstore for: '{query}' in doc: {doc_id} (k={k})", flush=True)

    vectorstore = get_vectorstore()
    filter_dict = {"document_id": doc_id} if doc_id else None
    
    # 1. Quick intent classification on first iteration
    is_broad = False
    if iteration == 0 and not state.get("refined_query"):
        intent_prompt = f"Is this question asking for a broad summary/overview of the entire document, or asking for specific details/facts?\nQuestion: '{query}'\nReply ONLY with 'BROAD' or 'SPECIFIC'."
        llm = get_llm()
        intent = invoke_llm(llm, intent_prompt).strip().upper()
        if "BROAD" in intent:
            is_broad = True
            print("Detected BROAD summary request. Retrieving representative chunks.", flush=True)

    results = []
    
    if is_broad and doc_id:
        # Fetch the first few chunks of the document to provide a solid abstract/overview
        try:
            col_data = vectorstore._collection.get(where=filter_dict, limit=50)
            docs_from_col = []
            if col_data and col_data["documents"]:
                for idx, txt in enumerate(col_data["documents"]):
                    meta = col_data["metadatas"][idx] if col_data["metadatas"] else {}
                    # Mock a tuple (Document, distance) where distance is 0.0 (perfect match)
                    from langchain_core.documents import Document
                    docs_from_col.append((Document(page_content=txt, metadata=meta), 0.0))
                
                # Sort by page number if available to ensure we get the true start of the document
                docs_from_col.sort(key=lambda x: x[0].metadata.get("page", 0))
                results = docs_from_col[:6] # Take top 6 representative chunks
        except Exception as e:
            print(f"Fallback to semantic search due to get() error: {e}")
            is_broad = False

    # 2. Normal Semantic Search for specific facts (or fallback)
    if not results:
        results = vectorstore.similarity_search_with_score(
            query,
            k=k,
            filter=filter_dict,
        )

    context_parts = []
    sources = []

    for i, (doc, distance) in enumerate(results):
        context_parts.append(f"[Chunk {i + 1}]:\n{doc.page_content}")

        # Chroma uses cosine distance (0=identical, 2=opposite).
        relevance = max(0.0, min(1.0, round(1.0 - (distance / 2.0), 2)))

        # PyPDFLoader page metadata is 0-indexed; add 1 for display
        page_num = doc.metadata.get("page", 0)
        if isinstance(page_num, int):
            page_num += 1

        sources.append({
            "page": page_num,
            "filename": doc.metadata.get("filename", "Unknown"),
            "rel": "BROAD" if is_broad else f"{relevance:.2f}",
            "text": doc.page_content.replace('\n', ' ').strip()[:150] + "...",
        })

    context = "\n\n".join(context_parts)
    print(f"Retrieved {len(results)} chunks.", flush=True)

    end_time = time.time()
    metrics = state.get("metrics", {})
    metrics["retrieval_time"] = metrics.get("retrieval_time", 0.0) + (end_time - start_time)

    return {
        "context": context,
        "sources": sources,
        "metrics": metrics,
        "refined_query": query,
        # Do NOT touch 'iterations' here — router owns the counter
    }


def grade_retrieval(state: GraphState) -> dict:
    """
    LLM judges whether the retrieved context is relevant and sufficient.
    Uses refined_query (the actual query used for retrieval), not the original question.
    """
    start_time = time.time()
    print("\n--- [NODE: GRADE_RETRIEVAL] ---", flush=True)
    print(f"Evaluating context with {MODEL_PAI_MODEL} via vLLM...", flush=True)
    llm = get_llm()

    # Use the refined query that was actually used to retrieve context
    active_query = state.get("refined_query") or state["question"]

    history_str = ""
    chat_history = state.get("chat_history", [])
    if chat_history:
        history_lines = []
        for q, a in chat_history[-3:]:
            history_lines.append(f"User: {q}\nAssistant: {a}")
        history_str = "\nPrevious Conversation History:\n" + "\n".join(history_lines) + "\n"

    prompt = f"""You are a strict retrieval quality judge for a RAG system.

Your job: decide if the retrieved context is good enough to answer the query accurately, \
taking into account the conversation history.

{history_str}
Original Question: {state['question']}
Search Query Used: {active_query}

Retrieved Context:
{state['context']}

Evaluate the context on three criteria:
1. INTENT & RELEVANCE — What is the user actually asking? If they are asking for a broad document summary (e.g., "what is this document about", "summarize the pdf", "tell me details about this document"), any retrieved context that gives a general idea of the document's contents IS relevant and sufficient.
2. SUFFICIENCY — Does the context contain enough detail for a helpful answer? For specific questions, demand specific facts. For broad/summary questions, a representative sample or high-level overview is SUFFICIENT. Do not demand the entire document.
3. CONSISTENCY — Are there contradictions or gaps between chunks?

Reply in this EXACT format (no extra lines, no preamble):
VERDICT: YES
REASON: <one sentence>
REFINED_QUERY: NONE

OR if context is entirely irrelevant to the user's specific question:
VERDICT: NO
REASON: <one sentence explaining what specific information is missing>
REFINED_QUERY: <a better, more specific search query; resolve any pronouns>"""

    content = invoke_llm(llm, prompt)
    print(f"Grading Result:\n{content}", flush=True)

    current_iter = state.get("iterations", 1)
    log_entry = f"Iteration {current_iter}\n{content}"
    reflection_log = list(state.get("reflection_log", [])) + [log_entry]

    end_time = time.time()
    metrics = state.get("metrics", {})
    metrics["llm_time"] = metrics.get("llm_time", 0.0) + (end_time - start_time)

    return {
        "reflection": content,
        "reflection_log": reflection_log,
        "metrics": metrics,
    }


def rewrite_query(state: GraphState) -> dict:
    """
    Extract the REFINED_QUERY from the grader's output.
    If absent or malformed, ask the LLM to generate a meaningful replacement
    rather than silently repeating the same query.
    """
    print("\n--- [NODE: REWRITE_QUERY] ---", flush=True)
    reflection = state.get("reflection", "")
    refined = None

    for line in reflection.splitlines():
        line = line.strip()
        if line.upper().startswith("REFINED_QUERY:"):
            candidate = line.split(":", 1)[1].strip()
            if candidate and candidate.upper() != "NONE" and len(candidate) > 5:
                refined = candidate
                break

    if refined is None:
        print("REFINED_QUERY not found — generating fallback via vLLM...", flush=True)
        llm = get_llm()
        original_q = state["question"]
        context_snippet = (state.get("context") or "")[:500]
        reason_line = ""
        for line in reflection.splitlines():
            if line.strip().upper().startswith("REASON:"):
                reason_line = line.split(":", 1)[1].strip()
                break

        fallback_prompt = f"""A RAG retrieval step failed to find sufficient context.

Original question: {original_q}
Retrieval failure reason: {reason_line or 'Context was insufficient'}
Partial context found (for keyword hints):
{context_snippet}

Write ONE improved search query (max 20 words) that is more specific and \
different from the original question. Return ONLY the query text, nothing else."""

        refined = invoke_llm(llm, fallback_prompt).strip().strip('"').strip("'")
        if not refined or len(refined) < 5:
            refined = original_q + " detailed steps process"

    print(f"New refined query: '{refined}'", flush=True)
    return {"refined_query": refined}


def generate(state: GraphState, config: RunnableConfig = None) -> dict:
    """
    Generate the final answer grounded strictly in the validated context.

    If all grading iterations returned NO (no useful context was ever found),
    emit an honest 'not found in document' message instead of hallucinating.
    """
    start_time = time.time()
    print("\n--- [NODE: GENERATE] ---", flush=True)

    reflection_log = state.get("reflection_log", [])
    iterations = state.get("iterations", 1)
    context = state.get("context", "").strip()

    # Detect if every grading verdict was NO
    all_verdicts_no = bool(reflection_log) and all(
        "VERDICT: NO" in entry.upper() for entry in reflection_log
    )

    if all_verdicts_no and iterations >= MAX_ITERATIONS:
        last_reason = ""
        for line in reflection_log[-1].splitlines():
            if line.strip().upper().startswith("REASON:"):
                last_reason = line.split(":", 1)[1].strip()
                break

        not_found_answer = (
            f"After {iterations} retrieval attempt(s), the system could not find sufficient "
            f"information in the document to answer this question.\n\n"
            f"**Last retrieval assessment:** {last_reason}\n\n"
            f"Please try:\n"
            f"- Rephrasing your question with more specific terminology from the document\n"
            f"- Asking about a specific section, step, or component\n"
            f"- Checking that the uploaded document covers this topic"
        )
        print("All verdicts were NO — returning honest 'not found' message.", flush=True)
        end_time = time.time()
        metrics = state.get("metrics", {})
        metrics["llm_time"] = metrics.get("llm_time", 0.0) + (end_time - start_time)
        return {"answer": not_found_answer, "metrics": metrics}

    print(f"Generating final answer with {MODEL_PAI_MODEL} via vLLM...", flush=True)
    llm = get_llm()

    history_str = ""
    chat_history = state.get("chat_history", [])
    if chat_history:
        history_lines = []
        for q, a in chat_history[-3:]:
            history_lines.append(f"User: {q}\nAssistant: {a}")
        history_str = "\n\nPrevious Conversation History:\n" + "\n---\n".join(history_lines) + "\n"

    prompt = f"""You are a precise, helpful assistant. Answer the question using ONLY the provided context and conversation history.
If the context is insufficient for a complete answer, clearly state what is missing — do not hallucinate or use outside knowledge.

Question: {state['question']}
{history_str}
Validated Context:
{context}

Write a clear, structured answer grounded strictly in the context above. \
Use bullet points or numbered steps where appropriate for clarity."""

    answer = invoke_llm(llm, prompt, config=config)
    print("Generation complete.", flush=True)

    end_time = time.time()
    metrics = state.get("metrics", {})
    metrics["llm_time"] = metrics.get("llm_time", 0.0) + (end_time - start_time)

    return {"answer": answer, "metrics": metrics}
