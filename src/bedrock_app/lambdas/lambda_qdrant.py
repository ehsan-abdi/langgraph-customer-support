"""
AuraBank-QdrantSearch Lambda
============================
Provides two operations to the Resolution Agent:
  - search_historical_tickets(query) → semantic search over 10,684 past support tickets
  - search_confluence_kb(query)      → semantic search over 8 internal Confluence docs

Approach: pure stdlib urllib — zero extra packages, no Lambda layer needed.
  1. Call OpenAI REST API  → get text-embedding-3-small vector for the query
  2. Call Qdrant REST API  → cosine-similarity search on the collection
  3. Format and return top results

Env vars (injected at deploy time):
  OPENAI_API_KEY   — for embeddings
  QDRANT_URL       — Qdrant Cloud cluster base URL
  QDRANT_API_KEY   — Qdrant Cloud API key
"""

import json
import os
import re
import urllib.request
import urllib.error

# ── Config ────────────────────────────────────────────────────────────────────
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY", "")
QDRANT_URL  = os.environ.get("QDRANT_URL", "").rstrip("/")
QDRANT_KEY  = os.environ.get("QDRANT_API_KEY", "")
EMBED_MODEL = "text-embedding-3-small"

COLLECTION_TICKETS    = "historical_tickets"
COLLECTION_CONFLUENCE = "confluence_docs"
TOP_K = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_embedding(text: str) -> list:
    """Call OpenAI Embeddings API and return the vector."""
    payload = json.dumps({"input": text[:8000], "model": EMBED_MODEL}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())["data"][0]["embedding"]


def _search_qdrant(collection: str, vector: list, limit: int = TOP_K) -> list:
    """Search a Qdrant collection using its REST API."""
    payload = json.dumps({
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "with_vector": False,
    }).encode()
    req = urllib.request.Request(
        f"{QDRANT_URL}/collections/{collection}/points/search",
        data=payload,
        headers={
            "api-key": QDRANT_KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read()).get("result", [])


def _strip_html(html: str) -> str:
    """Remove HTML/XML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Search functions ──────────────────────────────────────────────────────────

def search_historical_tickets(query: str) -> str:
    """Embed query, search historical_tickets, return formatted top results."""
    vector = _get_embedding(query)
    hits   = _search_qdrant(COLLECTION_TICKETS, vector)

    if not hits:
        return "No relevant historical tickets found."

    lines = [f"Top {len(hits)} similar historical support tickets:\n"]
    for i, hit in enumerate(hits, 1):
        payload  = hit.get("payload", {})
        content  = payload.get("page_content", "")
        score    = hit.get("score", 0.0)
        # Extract ticket ID and issue from the structured text block
        ticket_id = ""
        issue_line = ""
        for line in content.splitlines():
            if line.startswith("Ticket ID:"):
                ticket_id = line.split(":", 1)[-1].strip()
            if line.startswith("Issue:"):
                issue_line = line.split(":", 1)[-1].strip()
        # Truncate full content for brevity
        snippet = content[:400].replace("\n", " ")
        lines.append(
            f"[{i}] Ticket {ticket_id} | Issue: {issue_line} | "
            f"Relevance: {score:.2f}\n"
            f"    {snippet}...\n"
        )
    return "\n".join(lines)


def search_confluence_kb(query: str) -> str:
    """Embed query, search confluence_docs, return formatted top results."""
    vector = _get_embedding(query)
    hits   = _search_qdrant(COLLECTION_CONFLUENCE, vector)

    if not hits:
        return "No relevant Confluence documents found."

    lines = [f"Top {len(hits)} relevant internal knowledge base documents:\n"]
    for i, hit in enumerate(hits, 1):
        payload = hit.get("payload", {})
        title   = payload.get("title", "Untitled")
        source  = payload.get("source", "")
        content = _strip_html(payload.get("content", ""))
        score   = hit.get("score", 0.0)
        snippet = content[:500]
        lines.append(
            f"[{i}] {title} | Source: {source} | Relevance: {score:.2f}\n"
            f"    {snippet}...\n"
        )
    return "\n".join(lines)


# ── Bedrock Action Group handler ───────────────────────────────────────────────

def lambda_handler(event, context):
    """
    Bedrock Agent Action Group invocation format:
      event = {
        "actionGroup": "QdrantSearchActionGroup",
        "apiPath": "/search_historical_tickets" | "/search_confluence_kb",
        "httpMethod": "POST",
        "requestBody": {
          "content": {
            "application/json": {
              "properties": [{"name": "query", "type": "string", "value": "..."}]
            }
          }
        }
      }
    """
    action_group = event.get("actionGroup", "")
    api_path     = event.get("apiPath", "")
    http_method  = event.get("httpMethod", "POST")

    # Extract query from request body
    props = (
        event
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("properties", [])
    )
    query = next((p["value"] for p in props if p["name"] == "query"), "")

    # Dispatch
    try:
        if api_path == "/search_historical_tickets":
            result = search_historical_tickets(query)
        elif api_path == "/search_confluence_kb":
            result = search_confluence_kb(query)
        else:
            result = f"Unknown operation: {api_path}"
        status_code = 200
    except Exception as exc:
        result = f"Search error: {exc}"
        status_code = 500

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": http_method,
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps({"result": result})
                }
            },
        },
    }
