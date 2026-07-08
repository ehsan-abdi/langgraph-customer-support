import os
import sys
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.core.llm import get_llm
from src.security.pii_vault import PIIVault

load_dotenv(override=True)

class TicketExtraction(BaseModel):
    """Pydantic Schema for the structured output of the LLM."""
    customer_name: Optional[str] = Field(description="The customer's name if provided. Null if omitted.")
    account_number: Optional[str] = Field(description="The exact account token (e.g., <ACCOUNT_ABC>) if an account number is provided. Null if omitted.")
    sort_code: Optional[str] = Field(description="The exact sort code token (e.g., <SORT_CODE_ABC>) if provided. Null if omitted.")
    customer_email: Optional[str] = Field(description="The exact email token (e.g., <EMAIL_ABCDEFGH>) if an email is provided in the text. Null if omitted.")
    category: str = Field(description="The category of the issue (e.g., Current Account, Savings, Credit Card, Mortgage, Mobile App, Fraud).")
    tone: str = Field(description="The emotional tone of the customer (e.g., Neutral, Angry, Anxious, Frustrated).")
    summary: str = Field(description="A cleaned-up version of the raw text preserving the core issue description exactly. Do NOT summarize or remove content.")

class IngestionResult(BaseModel):
    """The final structured object returned by the Ingestion Agent to the Graph State."""
    original_text: str
    masked_text: str
    customer_name: Optional[str]
    account_number: Optional[str]
    sort_code: Optional[str]
    customer_email: Optional[str]
    category: str
    tone: str
    summary: str
    pii_vault_map: dict

def run_ingestion_agent(raw_message: str) -> IngestionResult:
    """
    Acts as the secure front-door middleware for Aura Bank.
    1. Masks all PII using the PIIVault.
    2. Uses GPT-4o-mini to extract structured metadata from the masked text.
    3. Safely unmasks the email token so the Database Agent can perform lookups later.
    """
    # 1. Mask PII to ensure the LLM never sees raw sensitive data
    vault = PIIVault()
    masked_text = vault.mask(raw_message)
    
    # 2. Extract Data using LLM Structured Output
    llm = get_llm(model_name="gpt-4o-mini", temperature=0.0)
    structured_llm = llm.with_structured_output(TicketExtraction)
    
    prompt = ChatPromptTemplate.from_messages([
        (
            "system", 
            "You are the intake routing agent for Aura Bank. Extract the required details from the customer message. "
            "Do NOT summarize or remove any content from the core issue description; just clean it up if there are English or Grammar errors. "
            "The text has been passed through a PII vault and may contain secure tokens like <EMAIL_ABCDEFGH>. "
            "If you detect an email token, output the exact token string including the angle brackets."
        ),
        ("human", "{masked_text}")
    ])
    
    chain = prompt | structured_llm
    extraction: TicketExtraction = chain.invoke({"masked_text": masked_text})
    
    # 3. Unmask specifically the required PII so the DB Agent can query it
    unmasked_email = vault.unmask(extraction.customer_email) if extraction.customer_email else None
    unmasked_name = vault.unmask(extraction.customer_name) if extraction.customer_name else None
    unmasked_acc = vault.unmask(extraction.account_number) if extraction.account_number else None
    unmasked_sort = vault.unmask(extraction.sort_code) if extraction.sort_code else None
        
    return IngestionResult(
        original_text=raw_message,
        masked_text=masked_text,
        customer_name=unmasked_name,
        account_number=unmasked_acc,
        sort_code=unmasked_sort,
        customer_email=unmasked_email,
        category=extraction.category,
        tone=extraction.tone,
        summary=extraction.summary,
        pii_vault_map=vault.vault
    )

def run_ingestion_node(state: dict) -> dict:
    """LangGraph node wrapper for the Ingestion Agent."""
    raw_message = state.get("raw_complaint", "")
    result = run_ingestion_agent(raw_message)
    
    return {
        "masked_complaint": result.summary, # Piped as the primary text downstream
        "customer_email": result.customer_email,
        "customer_name": result.customer_name,
        "account_number": result.account_number,
        "sort_code": result.sort_code,
        "pii_vault_map": result.pii_vault_map,
    }

