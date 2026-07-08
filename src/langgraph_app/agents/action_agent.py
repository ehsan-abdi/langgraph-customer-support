import os
import sys
from dotenv import load_dotenv

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.core.llm import get_llm
from src.tools.db_tools import suspend_account_or_card, issue_refund
from src.tools.jira_client import JiraClient

load_dotenv(override=True)

# We need a tool to post comments to Jira
from langchain_core.tools import tool

@tool
def post_jira_comment(ticket_key: str, comment: str) -> str:
    """
    Posts a public comment to the Jira ticket to inform the customer of the action taken.
    Requires the Jira ticket_key (e.g. AURA-12) and the comment text.
    """
    try:
        client = JiraClient()
        response = client.post_comment(ticket_key, comment)
        return f"Successfully posted comment to {ticket_key}: {response}"
    except Exception as e:
        return f"Failed to post comment to Jira: {str(e)}"

def get_action_executor():
    """
    Returns a compiled LangGraph ReAct agent that has access to database mutation tools.
    """
    llm = get_llm(model_name="gpt-4o-mini", temperature=0.0)
    
    tools = [
        suspend_account_or_card,
        issue_refund
    ]
    
    prompt_text = (
        "You are the Action Execution Agent for Aura Bank. Your sole responsibility is to execute "
        "the resolutions proposed by the Investigation Agent.\n\n"
        "INSTRUCTIONS:\n"
        "1. You will receive the investigation context, proposed resolution, and the Jira ticket ID.\n"
        "2. If a card suspension is proposed, execute the `suspend_account_or_card` tool with the correct account ID.\n"
        "3. If a refund is proposed, execute the `issue_refund` tool with the correct account ID and amount.\n"
        "4. You MUST NOT post any public comments to Jira or communicate with the customer. The customer's response will be drafted by the Response Generation Agent, independently reviewed by the Validation Agent, and eventually securely posted by the Feedback & Learning component.\n"
        "5. Output a final success message summarizing the actions performed. Note: Human authorization is handled by the Supervisor graph, so assume you are authorized to act on the inputs provided."
    )
    
    # Checkpointer and interrupt removed because the parent LangGraph workflow handles HITL routing natively.
    agent = create_react_agent(llm, tools=tools, prompt=prompt_text)
    return agent

def run_action_node(state: dict) -> dict:
    """LangGraph node wrapper for the Action Agent."""
    from langchain_core.messages import HumanMessage
    
    executor = get_action_executor()
    
    prompt = f"Ticket Key: {state.get('ticket_key')}\n\nAccount ID to Mutate (if applicable): {state.get('account_id_to_mutate')}\n\nContext & Proposed Action:\n{state.get('investigation_summary')}"
    
    response = executor.invoke({"messages": [HumanMessage(content=prompt)]})
    messages = response.get("messages", [])
    
    final_output = messages[-1].content if messages else "No action executed."
    
    return {
        "action_summary": final_output
    }
