from langgraph.graph import StateGraph, END
from src.state import GraphState
from src.config import MAX_ITERATIONS
from src.nodes import retrieve, grade_retrieval, rewrite_query, generate, analyze_query, generate_conversational

def route_after_analysis(state: GraphState) -> str:
    """
    Route based on the intent classified by analyze_query.
    """
    intent = state.get("intent", "DOC_SPECIFIC")
    if intent in ["CONVERSATIONAL", "HISTORY"]:
        return "generate_conversational"
    return "retrieve"

def should_continue(state: GraphState) -> str:
    """
    Called after grade_retrieval.

    - Increments 'iterations' to count completed retrieve→grade cycles.
    - Routes to 'generate' if:
        a) The grader returned VERDICT: YES (good context found), OR
        b) We have exhausted MAX_ITERATIONS attempts (force generate with
           honest 'not found' fallback handled inside generate()).
    - Routes to 'rewrite' otherwise to refine the query and re-retrieve.
    """
    # Increment the completed-cycle counter HERE, not inside retrieve().
    # This ensures 'iterations' in state always means "how many grade rounds ran."
    completed = state.get("iterations", 0) + 1

    print(f"\n--- [ROUTER] (completed iterations: {completed}/{MAX_ITERATIONS}) ---")

    reflection = state.get("reflection", "")
    verdict_yes = False
    out_of_scope = False
    
    for line in reflection.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            if "YES" in line.upper():
                verdict_yes = True
            elif "OUT_OF_SCOPE" in line.upper():
                out_of_scope = True
            break

    if verdict_yes:
        print("Verdict was YES. Routing to generate.")
        return "generate"
        
    if out_of_scope:
        print("Verdict was OUT_OF_SCOPE. Routing directly to generate.")
        return "generate"

    if completed >= MAX_ITERATIONS:
        print(f"Max iterations ({MAX_ITERATIONS}) reached with NO verdict. Routing to generate (will emit 'not found' message).")
        return "generate"

    print("Verdict was NO. Routing to rewrite_query.")
    return "rewrite"


def increment_iterations(state: GraphState) -> dict:
    """
    Thin node that commits the iteration counter increment decided in should_continue().
    LangGraph conditional edges can't write to state directly, so we use a dedicated node.
    """
    return {"iterations": state.get("iterations", 0) + 1}


def build_graph():
    """Builds and compiles the LangGraph workflow."""
    workflow = StateGraph(GraphState)

    workflow.add_node("analyze_query", analyze_query)
    workflow.add_node("generate_conversational", generate_conversational)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_retrieval", grade_retrieval)
    workflow.add_node("increment_iterations", increment_iterations)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("generate", generate)

    workflow.set_entry_point("analyze_query")
    
    workflow.add_conditional_edges(
        "analyze_query",
        route_after_analysis,
        {
            "generate_conversational": "generate_conversational",
            "retrieve": "retrieve"
        }
    )

    workflow.add_edge("generate_conversational", END)
    
    workflow.add_edge("retrieve", "grade_retrieval")
    workflow.add_conditional_edges(
        "grade_retrieval",
        should_continue,
        {
            "generate": "increment_iterations",
            "rewrite": "increment_iterations",
        },
    )
    # After incrementing, route to the correct next node
    # We need a second conditional to pick generate vs rewrite
    workflow.add_conditional_edges(
        "increment_iterations",
        _route_after_increment,
        {
            "generate": "generate",
            "rewrite": "rewrite_query",
        },
    )
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_edge("generate", END)

    return workflow.compile()


def _route_after_increment(state: GraphState) -> str:
    """
    Re-evaluate routing after the iterations counter has been committed to state.
    Mirrors the logic in should_continue() using the now-updated counter.
    """
    completed = state.get("iterations", 1)
    reflection = state.get("reflection", "")

    for line in reflection.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            if "YES" in line.upper() or "OUT_OF_SCOPE" in line.upper():
                return "generate"
            break

    if completed >= MAX_ITERATIONS:
        return "generate"

    return "rewrite"


# Global compiled graph instance
app = build_graph()
