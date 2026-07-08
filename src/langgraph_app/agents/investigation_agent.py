import os
import sys
import re
from dotenv import load_dotenv

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.core.llm import get_llm
from src.tools.db_tools import get_customer_profile, get_account_balances, get_recent_transactions
from src.tools.vector_tools import search_confluence_kb, search_historical_tickets

load_dotenv(override=True)

def get_investigation_executor():
    """
    Returns a LangGraph compiled ReAct agent configured with our internal database and vector store tools.
    """
    llm = get_llm(model_name="gpt-4o-mini", temperature=0.0)
    
    tools = [
        get_customer_profile,
        get_account_balances,
        get_recent_transactions,
        search_confluence_kb,
        search_historical_tickets
    ]
    
    prompt_text = (
        "You are the Investigation Agent for Aura Bank. Your goal is to gather all necessary context to resolve the customer's issue.\n\n"
        "INSTRUCTIONS:\n"
        "1. You MUST look up the customer's profile using their full name, account number, and sort code using get_customer_profile. If there is an identity mismatch warning, you must halt and ask the customer for verification.\n"
        "2. Evaluate the ticket to decide whether to search Confluence, Historical Tickets, or both. For general policies, fees, or account terms and conditions, search Confluence. For complex bugs, app issues, or distress, search Historical Tickets. If one database does not yield satisfactory results, you should fallback and search the other. You may also search both simultaneously if the issue warrants it.\n"
        "3. CRITICAL SEARCH RULE: When generating search queries for the vector databases, DO NOT oversimplify. Use detailed, specific queries based on the customer's exact phrasing (e.g., use 'unlock mobile banking app passcode' instead of just 'forgot PIN').\n"
        "4. If the customer mentions a specific charge or transaction, you MUST use `get_recent_transactions` to verify it. If the customer does not specify which account the charge occurred on, you MUST check ALL of their accounts (Current, Credit Card, etc.) until you find it.\n"
        "5. You are encouraged to execute tools in parallel where possible.\n"
        "6. STRUCTURE RULE: Your visible summary must be beautifully written in smooth, natural human language without markdown bullet points. You MUST structure it into exactly three paragraphs: 1) Outline the issue the customer raised. 2) Explain the investigative work carried out. 3) State the suggested action to be approved.\n"
        "7. DO NOT ask the customer for confirmation if they have already explicitly requested an action (e.g. card suspension, refund).\n"
        "8. DO NOT use conversational filler like 'If Joanne requires further assistance, let me know!'. Maintain a professional, natural tone.\n"
        "9. CRITICAL: If proposing a database mutation (refund or suspension), DO NOT put the account ID in the paragraph text. Instead, append exactly `[ACCOUNT_ID: <36-char-uuid>]` at the VERY END of your entire output.\n"
        "10. CRITICAL: At the very end of your output, you MUST also include a strict flag: exactly `[ACTION_REQUIRED: TRUE]` if a mutation is needed, or `[ACTION_REQUIRED: FALSE]` if none is needed."
    )
    
    agent = create_react_agent(llm, tools=tools, prompt=prompt_text)
    return agent

def run_investigation_node(state: dict) -> dict:
    """LangGraph node wrapper for the Investigation Agent."""
    from langchain_core.messages import HumanMessage
    
    executor = get_investigation_executor()
    
    # Pass the masked complaint and explicit unmasked identity for strict checking
    prompt = (
        f"Customer Name: {state.get('customer_name', 'Not Provided')}\n"
        f"Account Number: {state.get('account_number', 'Not Provided')}\n"
        f"Sort Code: {state.get('sort_code', 'Not Provided')}\n"
        f"Customer Complaint:\n{state.get('masked_complaint')}"
    )
    
    if state.get("is_valid") == False and state.get("validation_feedback"):
         prompt += f"\n\n[SYSTEM REJECTION FEEDBACK FROM PREVIOUS ATTEMPT: {state.get('validation_feedback')}]\nPlease re-investigate and correct the proposed resolution."
    
    response = executor.invoke({"messages": [HumanMessage(content=prompt)]})
    messages = response.get("messages", [])
    
    final_summary = messages[-1].content if messages else "No output"
    
    # Extract the raw context from tool calls so Validation Agent can see what was retrieved
    docs_retrieved = []
    tool_messages = [m for m in messages if getattr(m, 'type', '') == 'tool']
    for m in tool_messages:
        docs_retrieved.append(f"--- Tool Output ({m.name}) ---\n{m.content}")
        
    investigation_documents = "\n\n".join(docs_retrieved)
    
    # Parse the Action Required flag
    action_required = False
    matches = re.findall(r"\[ACTION_REQUIRED:\s*(TRUE|FALSE)\]", final_summary.upper())
    if matches:
        action_required = (matches[-1] == "TRUE")
    else:
        action_required = "[ACTION_REQUIRED: TRUE]" in final_summary.upper()
        
    # Parse Account ID if present
    account_id = None
    acc_matches = re.findall(r"\[ACCOUNT_ID:\s*([a-zA-Z0-9-]+)\]", final_summary.upper())
    if acc_matches:
        account_id = acc_matches[-1].lower()
        
    # Strip system tags to leave a clean human-readable summary
    clean_summary = re.sub(r"\[ACTION_REQUIRED:\s*(TRUE|FALSE)\]", "", final_summary, flags=re.IGNORECASE)
    clean_summary = re.sub(r"\[ACCOUNT_ID:\s*[a-zA-Z0-9-]+\]", "", clean_summary, flags=re.IGNORECASE)
    clean_summary = clean_summary.strip()
        
    return {
        "investigation_summary": clean_summary,
        "investigation_documents": investigation_documents,
        "action_required": action_required,
        "account_id_to_mutate": account_id
    }
