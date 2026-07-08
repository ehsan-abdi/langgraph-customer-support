from langchain_core.prompts import PromptTemplate
from src.core.llm import get_llm
from pydantic import BaseModel, Field

class ValidationResult(BaseModel):
    is_valid: bool = Field(description="True if the drafted response is 100% accurate and safe. False if it contains hallucinations, bad instructions, financial advice, or misses the point.")
    feedback: str = Field(description="If valid, say 'Approved'. If invalid, provide specific reasons for rejection. Do NOT provide suggestions on how to improve or rewrite it.")

def run_validation_agent(customer_complaint: str, investigation_summary: str, investigation_documents: str, action_summary: str, drafted_response: str) -> ValidationResult:
    """
    Evaluates the Response Generation Agent's draft for accuracy, hallucinations, and safety.
    Uses Groq's Llama 3.3 for cross-model verification.
    """
    llm = get_llm(provider="groq", model_name="llama-3.3-70b-versatile", temperature=0.0)
    structured_llm = llm.with_structured_output(ValidationResult)
    
    prompt = PromptTemplate.from_template(
        "You are the Validation & Safety Agent for Aura Bank.\n"
        "Your job is to critically evaluate an email drafted by another AI agent.\n\n"
        "CRITICAL RULES:\n"
        "1. Grounding & Accuracy: Verify that the draft is factually grounded in the provided Source Investigation Documents. It must not hallucinate policies, rules, or numbers. It is OK if the response contradicts the customer (e.g. if the customer claims a charge happened, but the investigation found nothing, the response should reflect the investigation).\n"
        "2. Completeness: Did the agent address the core of the customer's request?\n"
        "3. Safety: Does the response hallucinate actions that were NOT listed in the Action Summary? (e.g., if the Action Summary says an account was suspended, it's correct for the email to say so. But if the Action Summary is empty, the email must NOT promise a refund or suspension).\n"
        "4. No Financial Advice: Strictly forbid providing financial advice in the response. If the response contains investment or financial strategy advice, reject it immediately.\n\n"
        "Customer's Original Complaint:\n{complaint}\n\n"
        "Investigation Summary:\n{investigation}\n\n"
        "Source Investigation Documents:\n{investigation_documents}\n\n"
        "Action Summary:\n{action}\n\n"
        "AI Agent's Drafted Response:\n{response}\n\n"
        "Evaluate the draft based ONLY on the provided context summaries and source documents. If it aligns with the investigation and actions taken, set is_valid to true. If there are massive, ungrounded hallucinations or financial advice, set is_valid to false and provide rejection reasons ONLY."
    )
    
    chain = prompt | structured_llm
    return chain.invoke({
        "complaint": customer_complaint, 
        "investigation": investigation_summary,
        "investigation_documents": investigation_documents,
        "action": action_summary,
        "response": drafted_response
    })

def run_validation_node(state: dict) -> dict:
    """LangGraph node wrapper for the Validation Agent."""
    
    result = run_validation_agent(
        customer_complaint=state.get("masked_complaint", ""),
        investigation_summary=state.get("investigation_summary", ""),
        investigation_documents=state.get("investigation_documents", "None provided."),
        action_summary=state.get("action_summary", "No action executed."),
        drafted_response=state.get("drafted_response", "")
    )
    
    current_iterations = state.get("validation_iterations", 0)
    
    return {
        "is_valid": result.is_valid,
        "validation_feedback": result.feedback,
        "validation_iterations": current_iterations + 1
    }
