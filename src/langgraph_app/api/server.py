from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from src.langgraph_app.graph.workflow import build_graph

app = FastAPI(title="Aura Bank API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StartTicketRequest(BaseModel):
    ticket_key: str
    raw_complaint: str

class SubmitTicketRequest(BaseModel):
    raw_complaint: str

# Global state
active_websockets = []
graph_app = build_graph()

from src.tools.jira_client import JiraClient

@app.post("/api/ticket/submit")
async def submit_ticket(req: SubmitTicketRequest):
    try:
        jira = JiraClient()
        project_key = os.environ.get("JIRA_PROJECT_KEY", "AURA")
        
        # We'll use a short snippet of the complaint for the summary
        summary = req.raw_complaint.split('\n')[-1][:50] + "..." if len(req.raw_complaint) > 50 else req.raw_complaint.split('\n')[-1]
        if not summary.strip():
            summary = "New Customer Support Ticket"
            
        resp = jira.create_ticket(
            project_key=project_key,
            summary=f"Complaint: {summary}",
            description=req.raw_complaint
        )
        return {"status": "success", "ticket_key": resp.get("key")}
    except Exception as e:
        # Provide a 500 status on failure but send the error message for debugging
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ticket/latest")
async def get_latest_ticket():
    try:
        jira = JiraClient()
        project_key = os.environ.get("JIRA_PROJECT_KEY", "AURA")
        
        tickets = jira.fetch_unresolved_tickets(project_key=project_key, limit=1)
        if not tickets:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="No unresolved tickets found in Jira.")
            
        latest = tickets[0]
        ticket_key = latest["key"]
        
        # Jira doc format can be deeply nested. We'll extract text from paragraphs.
        description_doc = latest["fields"].get("description")
        raw_complaint = ""
        if description_doc and "content" in description_doc:
            for block in description_doc["content"]:
                if block["type"] == "paragraph" and "content" in block:
                    for text_node in block["content"]:
                        raw_complaint += text_node.get("text", "")
                    raw_complaint += "\n\n"
                    
        return {
            "ticket_key": ticket_key, 
            "raw_complaint": raw_complaint.strip()
        }
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ticket/start")
async def start_ticket(req: StartTicketRequest):
    """
    Start the LangGraph pipeline. Wait, usually we run the pipeline inside the websocket
    or we return success and let the client connect to WS?
    For this demo, we'll run a background task that streams events to all connected websockets.
    """
    import uuid
    thread_id = f"e2e_{req.ticket_key}_{uuid.uuid4().hex[:8]}"
    thread = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "ticket_key": req.ticket_key,
        "raw_complaint": req.raw_complaint,
    }
    
    # Run the graph asynchronously so we don't block the HTTP response
    asyncio.create_task(run_graph_and_stream(initial_state, thread))
    return {"status": "started", "thread_id": thread["configurable"]["thread_id"]}

async def run_graph_and_stream(state_input, thread):
    """Executes the graph and pushes events to all connected WebSockets."""
    try:
        # LangGraph app.stream() yields updates. 
        # Since it's synchronous right now, we wrap it.
        # Wait, app.astream() is the async version.
        async for event in graph_app.astream(state_input, thread):
            # Send event to all websockets
            for ws in active_websockets:
                await ws.send_json({"type": "node_update", "data": event})
                
        # After loop, check if interrupted
        state = graph_app.get_state(thread)
        if state.next:
            for ws in active_websockets:
                await ws.send_json({"type": "interrupted", "node": state.next[0], "state": state.values})
        else:
            for ws in active_websockets:
                await ws.send_json({"type": "completed", "state": state.values})
                
    except Exception as e:
        for ws in active_websockets:
            await ws.send_json({"type": "error", "message": str(e)})

@app.websocket("/api/ticket/stream")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # We can accept messages here if needed
    except WebSocketDisconnect:
        active_websockets.remove(websocket)

class ResumeRequest(BaseModel):
    thread_id: str
    node: str
    updates: dict

@app.post("/api/ticket/resume")
async def resume_ticket(req: ResumeRequest):
    """Resumes the graph after a HITL interaction."""
    thread = {"configurable": {"thread_id": req.thread_id}}
    graph_app.update_state(thread, req.updates, as_node=req.node)
    
    # Manually broadcast that the HITL node is stable so UI updates it
    for ws in active_websockets:
        await ws.send_json({"type": "node_update", "data": {req.node: req.updates}})
        
    state = graph_app.get_state(thread)
    interrupt_nodes = ["hitl_manual_resolution", "hitl_approve_action", "hitl_final_review"]
    
    # If the routing explicitly placed us on another interrupt node, DO NOT call astream, 
    # as that tells LangGraph to forcefully execute the interrupted node.
    if state.next and state.next[0] in interrupt_nodes:
        for ws in active_websockets:
            await ws.send_json({"type": "interrupted", "node": state.next[0], "state": state.values})
        return {"status": "interrupted_again"}
    
    # Resume streaming normally
    asyncio.create_task(run_graph_and_stream(None, thread))
    return {"status": "resumed"}

# --- SPA Static Serving ---
from fastapi.responses import FileResponse

WEB_DIST_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web", "dist")

if os.path.exists(WEB_DIST_PATH):
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Ignore API requests that fall through
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="API route not found")
            
        file_path = os.path.join(WEB_DIST_PATH, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(WEB_DIST_PATH, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
