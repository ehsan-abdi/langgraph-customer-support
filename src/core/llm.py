import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

# Ensure environment variables are loaded and override any stale system variables
load_dotenv(override=True)

def get_llm(provider: str = "openai", model_name: str = "gpt-4o-mini", temperature: float = 0.0):
    """
    Initializes and returns a LangChain chat model instance.
    
    Args:
        provider: 'openai' or 'groq'
        model_name: The specific model string to use (e.g., 'gpt-4o-mini' or 'llama-3.3-70b-versatile')
        temperature: Sampling temperature
    """
    if provider.lower() == "openai":
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY")
        )
    elif provider.lower() == "groq":
        return ChatGroq(
            model_name=model_name,
            temperature=temperature,
            api_key=os.getenv("GROQ_API_KEY")
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
