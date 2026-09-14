from typing import TypedDict, List, Tuple, Any

class GraphState(TypedDict):
    """
    Shared state passed between every LangGraph node throughout the retrieval-validation loop.
    """
    session_id: str                # Current chat session ID
    document_id: str               # Selected document to query against
    question: str                  # Original user question
    refined_query: str             # Current search query (rewritten if needed)
    context: str                   # Retrieved chunks joined as string
    sources: List[dict]            # Retrieved chunks metadata
    reflection: str                # Latest grading output from the LLM
    answer: str                    # Final generated answer
    iterations: int                # How many retrieval loops have run
    reflection_log: List[str]      # Full history of every grading step
    chat_history: List[Tuple[str, str]] # Previous history for context
    metrics: dict                  # Timing metrics (retrieval_time, llm_time)
