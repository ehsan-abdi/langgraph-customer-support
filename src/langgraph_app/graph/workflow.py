from langgraph.graph import StateGraph, START, END
from typing import Literal
from src.core.state import SupportState

from langgraph.checkpoint.memory import MemorySaver

# -----------------------------------------
# Node Functions
# -----------------------------------------
from src.langgraph_app.agents.ingestion_agent import run_ingestion_node as ingestion_node
from src.langgraph_app.agents.triage_agent import run_triage_node as triage_node
from src.langgraph_app.agents.investigation_agent import run_investigation_node as investigation_node
from src.langgraph_app.agents.action_agent import run_action_node as action_node
from src.langgraph_app.agents.response_agent import run_response_node as response_node
from src.langgraph_app.agents.validation_agent import run_validation_node as validation_node
from src.langgraph_app.agents.feedback_agent import run_finalizer_node as finalizer_node

# HITL Nodes (Used as breakpoints for interrupt_before)
def hitl_manual_resolution(state: SupportState) -> SupportState: return state
def hitl_approve_action(state: SupportState) -> SupportState: return state
def hitl_final_review(state: SupportState) -> SupportState: return state

# -----------------------------------------
# Routing Edges
# -----------------------------------------
def route_after_triage(state: SupportState) -> Literal["hitl_manual_resolution", "investigation_node"]:
    if state.get("priority") == "Urgent":
        return "hitl_manual_resolution"
    return "investigation_node"

def route_after_investigation(state: SupportState) -> Literal["hitl_approve_action", "response_node"]:
    if state.get("action_required"):
        return "hitl_approve_action"
    return "response_node"

def route_after_action_approval(state: SupportState) -> Literal["action_node", "hitl_manual_resolution"]:
    if state.get("action_approved"):
        return "action_node"
    return "hitl_manual_resolution"

def route_after_validation(state: SupportState) -> Literal["investigation_node", "hitl_manual_resolution", "hitl_final_review", "finalizer_node"]:
    if not state.get("is_valid"):
        # Max 3 attempts means if iterations >= 3, we fail out
        if state.get("validation_iterations", 0) >= 3:
            return "hitl_manual_resolution"
        return "investigation_node"
    else:
        # Valid response
        if state.get("priority") == "High":
            return "hitl_final_review"
        return "finalizer_node"

def route_after_final_review(state: SupportState) -> Literal["finalizer_node", "hitl_manual_resolution"]:
    if state.get("final_review_approved"):
        return "finalizer_node"
    return "hitl_manual_resolution"

# -----------------------------------------
# Graph Assembly
# -----------------------------------------
def build_graph():
    workflow = StateGraph(SupportState)

    # Add Nodes
    workflow.add_node("ingestion_node", ingestion_node)
    workflow.add_node("triage_node", triage_node)
    workflow.add_node("investigation_node", investigation_node)
    workflow.add_node("action_node", action_node)
    workflow.add_node("response_node", response_node)
    workflow.add_node("validation_node", validation_node)
    workflow.add_node("finalizer_node", finalizer_node)
    
    workflow.add_node("hitl_manual_resolution", hitl_manual_resolution)
    workflow.add_node("hitl_approve_action", hitl_approve_action)
    workflow.add_node("hitl_final_review", hitl_final_review)

    # Set Entry Point
    workflow.add_edge(START, "ingestion_node")
    workflow.add_edge("ingestion_node", "triage_node")

    # Routing from Triage
    workflow.add_conditional_edges("triage_node", route_after_triage)

    # Routing from Investigation
    workflow.add_conditional_edges("investigation_node", route_after_investigation)

    # Routing from Action Approval
    workflow.add_conditional_edges("hitl_approve_action", route_after_action_approval)
    
    # Action executes -> Response Gen
    workflow.add_edge("action_node", "response_node")

    # Response Gen -> Validation
    workflow.add_edge("response_node", "validation_node")

    # Routing from Validation
    workflow.add_conditional_edges("validation_node", route_after_validation)

    # Routing from Final Review
    workflow.add_conditional_edges("hitl_final_review", route_after_final_review)

    # Resolution paths converge to Finalizer
    workflow.add_edge("hitl_manual_resolution", "finalizer_node")
    workflow.add_edge("finalizer_node", END)

    # Compile with memory to enable state persistence across human interruptions
    checkpointer = MemorySaver()
    app = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=[
            "hitl_manual_resolution", 
            "hitl_approve_action", 
            "hitl_final_review"
        ]
    )

    return app
