import concurrent.futures
from src.tools.jira_client import JiraClient
from src.tools.vector_tools import get_history_store
from langchain_core.documents import Document
import uuid

def execute_jira_task(issue_key: str, drafted_response: str) -> str:
    jira = JiraClient()
    try:
        jira.post_comment(issue_key, f"AI Agent Resolution:\n\n{drafted_response}")
        resolution_resp = jira.resolve_ticket(issue_key)
        if resolution_resp.get("status") == "success":
            return "Comment posted and ticket transitioned to Completed."
        else:
            return f"Comment posted, but transition failed: {resolution_resp.get('message')}"
    except Exception as e:
        return f"Error: {str(e)}"

def execute_qdrant_task(issue_key: str, synthesized_text: str) -> str:
    try:
        store = get_history_store()
        doc = Document(
            page_content=synthesized_text, 
            metadata={
                "ticket_id": issue_key, 
                "category": "AI Resolved",
                "record_id": str(uuid.uuid4())
            }
        )
        store.add_documents([doc])
        return "Success"
    except Exception as e:
        return f"Error: {str(e)}"

def run_feedback_agent(issue_key: str, customer_complaint: str, investigation_summary: str, action_summary: str, drafted_response: str) -> dict:
    """
    Closes the loop by posting the drafted response to Jira and upserting the resolution into Qdrant for continuous learning.
    Executes tasks in parallel using ThreadPoolExecutor.
    """
    # 1. Pure Python string concatenation (no LLM)
    synthesized_text = (
        f"Original Complaint:\n{customer_complaint}\n\n"
        f"Resolution:\n{drafted_response}"
    )
    
    # 2. Parallel Execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_jira = executor.submit(execute_jira_task, issue_key, drafted_response)
        future_qdrant = executor.submit(execute_qdrant_task, issue_key, synthesized_text)
        
        jira_status = future_jira.result()
        qdrant_status = future_qdrant.result()
        
    return {
        "synthesized_text": synthesized_text,
        "jira_status": jira_status,
        "qdrant_status": qdrant_status
    }

def run_finalizer_node(state: dict) -> dict:
    """LangGraph node wrapper for the Resolution Finalizer."""
    result = run_feedback_agent(
        issue_key=state.get("ticket_key", ""),
        customer_complaint=state.get("raw_complaint", ""), # Use RAW complaint for Qdrant history
        investigation_summary="", # Ignored now
        action_summary="", # Ignored now
        drafted_response=state.get("drafted_response", "")
    )
    
    return {
        "final_status": f"Jira: {result['jira_status']} | Qdrant: {result['qdrant_status']}"
    }
