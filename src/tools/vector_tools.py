import os
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from dotenv import load_dotenv

# Ensure we override any stale system variables to securely hit the EU cluster if needed
load_dotenv(override=True)

# We deliberately reuse the same embedding model defined in Phase 1 Ingestion
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

def _get_confluence_store():
    client = QdrantClient(
        url=os.environ.get("QDRANT_CONFLUENCE_URL"),
        api_key=os.environ.get("QDRANT_CONFLUENCE_API_KEY"),
    )
    return QdrantVectorStore(
        client=client,
        collection_name="confluence",
        embedding=embeddings,
    )

def get_history_store():
    client = QdrantClient(
        url=os.environ.get("QDRANT_HISTORY_URL"),
        api_key=os.environ.get("QDRANT_HISTORY_API_KEY"),
    )
    return QdrantVectorStore(
        client=client,
        collection_name="historical_tickets",
        embedding=embeddings,
    )

@tool
def search_confluence_kb(query: str) -> str:
    """
    Searches the Aura Bank internal Confluence Knowledge Base for standard 
    operating procedures, product limits, fees, and general FAQs.
    IMPORTANT: Do not oversimplify the query (e.g., do not just search 'forgot PIN'). 
    You must include the specific context (e.g., 'forgot mobile banking app passcode' vs 'forgot debit card pin').
    """
    try:
        store = _get_confluence_store()
        # Retrieve the top 10 most semantically relevant documents
        docs = store.similarity_search(query, k=10)
        if not docs:
            return "No relevant internal documentation found."
        
        results = []
        for i, doc in enumerate(docs):
            title = doc.metadata.get("title", "Unknown Policy")
            url = doc.metadata.get("url", "")
            results.append(f"--- Document {i+1} ---\nTitle: {title}\nURL: {url}\nContent: {doc.page_content}")
            
        return "\n\n".join(results)
    except Exception as e:
        return f"Error querying Confluence KB: {str(e)}"

@tool
def search_historical_tickets(query: str) -> str:
    """
    Searches the Aura Bank historical support ticket database for previous 
    resolutions, refunds, or technical workarounds to similar customer issues.
    IMPORTANT: You may search this in parallel with the Confluence KB, or use it as a fallback if Confluence does not provide a satisfactory resolution.
    """
    try:
        store = get_history_store()
        # Retrieve the top 10 most semantically relevant historical tickets
        docs = store.similarity_search(query, k=10)
        if not docs:
            return "No relevant historical tickets found."
            
        results = []
        for i, doc in enumerate(docs):
            ticket_id = doc.metadata.get("ticket_id", "Unknown")
            category = doc.metadata.get("category", "Unknown")
            results.append(f"--- Ticket {ticket_id} ({category}) ---\nContent: {doc.page_content}")
            
        return "\n\n".join(results)
    except Exception as e:
        return f"Error querying Historical Tickets: {str(e)}"
