import operator
from typing import TypedDict, Optional, Annotated

class SupportState(TypedDict):
    """The global graph state for the Aura Bank Support Pipeline."""
    
    # 1. Base Ticket Context
    ticket_key: str
    raw_complaint: str              # Original text for Finalizer Node
    masked_complaint: str           # PII-masked text for LLMs
    customer_email: Optional[str]   # Unmasked email for DB queries
    customer_name: Optional[str]    # Unmasked name for strict DB lookups
    account_number: Optional[str]   # Unmasked account number for DB queries
    sort_code: Optional[str]        # Unmasked sort code for DB queries
    pii_vault_map: dict             # Vault mapping to re-inject PII if necessary
    
    # 2. Triage & Routing
    priority: str                   # Urgent, High, Normal, Low
    department: str
    
    # 3. Investigation
    investigation_summary: str
    investigation_documents: str    # Raw text of Confluence/Historical docs retrieved
    action_required: bool
    account_id_to_mutate: Optional[str]
    
    # 4. Action Execution
    action_summary: str
    
    # 5. Response Drafting
    drafted_response: str
    
    # 6. Validation & Safety
    is_valid: bool
    validation_feedback: str
    validation_iterations: int      # Counter tracking attempts (Max 3)
    
    # 7. HITL Flags (Set by Streamlit UI during interrupt)
    action_approved: bool
    final_review_approved: bool
    
    # 8. Final Output (Feedback / Upsert)
    final_status: str               # Status message from Finalizer Node
