from langchain_core.prompts import PromptTemplate
from src.core.llm import get_llm
from langchain_core.output_parsers import StrOutputParser

class ResponseResult:
    def __init__(self, drafted_response: str):
        self.drafted_response = drafted_response

def run_response_agent(customer_complaint: str, investigation_summary: str, action_summary: str) -> ResponseResult:
    """
    Drafts an empathetic, professional response to the customer.
    It takes the original complaint, the context from the investigation, and the actions taken.
    """
    llm = get_llm(model_name="gpt-4o-mini", temperature=0.7)
    
    prompt = PromptTemplate.from_template(
        "You are the Aura Bank Customer Support Response Generation Agent.\n"
        "Your job is to draft a clear and professional response to the customer.\n"
        "You must address their original complaint, explain what was discovered during the investigation, and clearly state what actions were taken.\n"
        "TONE GUIDELINES:\n"
        "- Use strictly natural human language. Avoid robotic, overly cheerful, or typical 'AI-generated' tones.\n"
        "- Be sympathetic, but avoid being overly sympathetic or overly apologizing.\n"
        "- ONLY apologize if there was a clear mistake or oversight by the bank.\n"
        "- Do NOT ask the customer to confirm actions that have already been executed.\n"
        "- ALWAYS end the message with exactly this sentence: 'If you feel that the enquiry or complaint is not resolved, please contact us again or call us on 0800 123 4567.'\n"
        "- Keep the tone strictly professional and in clear British English.\n\n"
        "Customer Complaint:\n{complaint}\n\n"
        "Investigation Summary:\n{investigation}\n\n"
        "Action Execution Summary:\n{actions}\n\n"
        "Draft the final response to be sent to the customer. Do not include signature blocks like '[Your Name]'."
    )
    
    chain = prompt | llm | StrOutputParser()
    result_text = chain.invoke({
        "complaint": customer_complaint, 
        "investigation": investigation_summary, 
        "actions": action_summary
    })
    return ResponseResult(drafted_response=result_text)

def run_response_node(state: dict) -> dict:
    """LangGraph node wrapper for the Response Generation Agent."""
    
    # Validation loop context
    rejection_feedback = ""
    if state.get("is_valid") == False and state.get("validation_feedback"):
        rejection_feedback = f"\n\n[SYSTEM INSTRUCTION: Your previous draft was rejected. Reason: {state.get('validation_feedback')}. Please rewrite the response to address this.]"
    
    result = run_response_agent(
        customer_complaint=state.get("masked_complaint", "") + rejection_feedback,
        investigation_summary=state.get("investigation_summary", ""),
        action_summary=state.get("action_summary", "No action was required or taken.")
    )
    
    return {
        "drafted_response": result.drafted_response
    }
