from langgraph.graph import StateGraph, END
from src.state import GraphState
from src.config import MAX_ITERATIONS
from src.nodes import retrieve, grade_retrieval, rewrite_query, generate

def should_continue(state: GraphState) -> str:
    """
    Route to 'generate' if context passed grading or max iterations reached.
    Route to 'rewrite' otherwise to refine the query and re-retrieve.
    """
    iterations = state.get("iterations", 0)
    if iterations >= MAX_ITERATIONS:
        return "generate"  # forced exit — generate with best context so far

    reflection = state.get("reflection", "")
    for line in reflection.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            if "YES" in line.upper():
                return "generate"
            break

    return "rewrite"

def build_graph():
    """Builds and compiles the LangGraph workflow."""
    workflow = StateGraph(GraphState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_retrieval", grade_retrieval)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("generate", generate)

    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "grade_retrieval")
    workflow.add_conditional_edges(
        "grade_retrieval",
        should_continue,
        {
            "generate": "generate",
            "rewrite": "rewrite_query",
        },
    )
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_edge("generate", END)

    return workflow.compile()

# Global compiled graph instance
app = build_graph()
