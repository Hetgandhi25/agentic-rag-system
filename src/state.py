from typing import TypedDict, List

class GraphState(TypedDict):
    """
    Shared state passed between every LangGraph node throughout the retrieval-validation loop.
    """
    question: str          # Original user question — never mutated
    refined_query: str     # Current search query (rewritten if needed)
    context: str           # Retrieved chunks joined as string
    reflection: str        # Latest grading output from the LLM
    answer: str            # Final generated answer
    iterations: int        # How many retrieval loops have run
    reflection_log: List[str]  # Full history of every grading step
