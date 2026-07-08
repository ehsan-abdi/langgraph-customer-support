import streamlit as st
import os
import sys
from dotenv import load_dotenv

# Ensure the src module can be imported from the project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.core.llm import get_llm
import importlib
for mod in list(sys.modules.keys()):
    if mod.startswith('src.tools') or mod.startswith('src.langgraph_app.agents'):
        importlib.reload(sys.modules[mod])

from src.tools.jira_client import JiraClient
from langchain_core.messages import HumanMessage, AIMessage

# Force load environment variables for the UI
load_dotenv(override=True)

st.set_page_config(page_title="Aura Bank - Agent Playground", page_icon="🏦", layout="wide")

st.title("🏦 Aura Bank - End-to-End Simulation")
st.markdown("This playground allows you to simulate a customer complaint, push it to your live Jira board, and then instantly fetch it as an Agent for isolated processing.")

# Initialize the Jira Client safely
try:
    jira = JiraClient()
    jira_project = os.environ.get("JIRA_PROJECT_KEY", "AURA")
except Exception as e:
    st.error(f"Jira Configuration Error: {e}")
    st.stop()

# Build the dual-portal tabs
tab1, tab2 = st.tabs(["👤 Customer Portal", "🤖 Agent Testing Portal"])

# ==========================================
# TAB 1: CUSTOMER PORTAL
# ==========================================
with tab1:
    st.header("Submit a Support Ticket")
    st.markdown("Acting as a customer, please submit a complaint. This will securely push a new ticket to your live Jira board.")
    
    with st.form("customer_complaint_form"):
        cust_email = st.text_input("Email Address", placeholder="e.g. john.doe@example.com")
        cust_summary = st.text_input("Issue Summary", placeholder="e.g. Unfair Overdraft Fee")
        cust_desc = st.text_area("Detailed Complaint", placeholder="e.g. I am incredibly frustrated that you charged me £50...", height=150)
        
        submitted = st.form_submit_button("Submit Complaint to Jira")
        
        if submitted:
            if not cust_email or not cust_summary or not cust_desc:
                st.warning("Please fill out all fields.")
            else:
                with st.spinner("Pushing to Atlassian Cloud..."):
                    try:
                        response = jira.create_ticket(
                            project_key=jira_project,
                            summary=cust_summary,
                            description=cust_desc,
                            customer_email=cust_email
                        )
                        st.success(f"Ticket officially created in Jira! Ticket Key: **{response.get('key')}**")
                        st.info("Head over to the **Agent Testing Portal** tab to fetch it and run it through the LangGraph agents!")
                    except Exception as e:
                        st.error(f"Jira API Error: {str(e)}")

# ==========================================
# TAB 2: AGENT TESTING PORTAL
# ==========================================
with tab2:
    st.header("Isolated Agent Test Harness")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("1. Fetch Live Ticket")
        if st.button("📥 Fetch Latest Unresolved Ticket"):
            with st.spinner("Querying Jira via JQL..."):
                try:
                    tickets = jira.fetch_unresolved_tickets(project_key=jira_project, limit=1)
                    if tickets:
                        ticket = tickets[0]
                        st.session_state.active_ticket = ticket
                        st.success(f"Fetched Ticket: {ticket['key']}")
                    else:
                        st.warning("No unresolved tickets found in Jira.")
                except Exception as e:
                    st.error(f"Error fetching tickets: {e}")
                    
        if "active_ticket" in st.session_state:
            t = st.session_state.active_ticket
            st.info(f"**{t['key']}: {t['fields']['summary']}**")
            
            # Extract description text from Jira's Document format
            desc_content = ""
            desc_field = t['fields'].get('description')
            if desc_field and isinstance(desc_field, dict):
                for block in desc_field.get('content', []):
                    for item in block.get('content', []):
                        desc_content += item.get('text', '') + "\n"
            elif isinstance(desc_field, str):
                desc_content = desc_field
                
            st.code(desc_content, language="text")
            
    with col2:
        st.subheader("2. Pipe into Agent")
        
        AGENT_OPTIONS = [
            "Base LLM (Sanity Check)",
            "Ticket Ingestion Agent",
            "Triage Agent",
            "Investigation Agent",
            "Action Agent",
            "Response Generation Agent",
            "Validation & Safety Agent",
            "Feedback & Learning Agent",
            "Full Pipeline (E2E Preview)"
        ]
        selected_agent = st.selectbox("Select Agent to Test", AGENT_OPTIONS)
        
        if selected_agent == "Action Agent":
            st.warning("⚠️ **Human Authorization Required:** The Action Agent requires explicit approval before mutating the Supabase database.")
            col_app, col_rej = st.columns(2)
            run_triggered = col_app.button("✅ Approve Action")
            if col_rej.button("❌ Reject Action"):
                st.error("Action Rejected by Human Supervisor. Simulation aborted.")
                run_triggered = False
        else:
            if st.button(f"🚀 Run {selected_agent}"):
                st.session_state[f"run_{selected_agent}"] = True
            
            run_triggered = st.session_state.get(f"run_{selected_agent}", False)
            
        if run_triggered:
            if "active_ticket" not in st.session_state:
                st.error("Please fetch a ticket from Jira first.")
            else:
                raw_complaint = desc_content
                message_placeholder = st.empty()
                
                try:
                    if selected_agent == "Base LLM (Sanity Check)":
                        llm = get_llm(provider="openai", model_name="gpt-4o-mini")
                        response = llm.invoke([HumanMessage(content=raw_complaint)])
                        message_placeholder.markdown(response.content)
                        
                    elif selected_agent == "Ticket Ingestion Agent":
                        from src.langgraph_app.agents.ingestion_agent import run_ingestion_agent
                        with st.spinner("Processing through Ingestion & PII Vault..."):
                            result = run_ingestion_agent(raw_complaint)
                            
                        full_response = f"**Pipeline Extraction Complete!**\n\n"
                        full_response += f"🔒 **Masked Text sent to LLM:**\n> {result.masked_text}\n\n"
                        full_response += f"📊 **Extracted Category:** {result.category}\n"
                        full_response += f"🎭 **Detected Tone:** {result.tone}\n"
                        full_response += f"📝 **Issue Summary:** {result.summary}\n"
                        full_response += f"📧 **Unmasked DB Email:** `{result.customer_email}`\n\n"
                        full_response += f"🛡️ **PII Vault Map:**\n```json\n{result.pii_vault_map}\n```\n"
                        
                        message_placeholder.markdown(full_response)
                        
                    elif selected_agent == "Triage Agent":
                        from src.langgraph_app.agents.ingestion_agent import run_ingestion_agent
                        from src.langgraph_app.agents.triage_agent import run_triage_agent
                        
                        with st.spinner("1. Running Ingestion Agent..."):
                            ingestion_result = run_ingestion_agent(raw_complaint)
                            
                        with st.spinner("2. Running Triage Agent..."):
                            triage_result = run_triage_agent(ingestion_result)
                            
                        full_response = f"**Triage Assessment Complete!**\n\n"
                        full_response += f"🚨 **Priority:** {triage_result.priority}\n"
                        full_response += f"🏢 **Routed Department:** {triage_result.department}\n"
                        full_response += f"🧠 **Rationale:** {triage_result.rationale}\n\n"
                        full_response += f"---\n*Based on Ingestion Data:*\n"
                        full_response += f"- **Category:** {ingestion_result.category}\n"
                        full_response += f"- **Tone:** {ingestion_result.tone}\n"
                        full_response += f"- **Summary:** {ingestion_result.summary}\n"
                        
                        message_placeholder.markdown(full_response)
                        
                    elif selected_agent == "Investigation Agent":
                        from src.langgraph_app.agents.investigation_agent import get_investigation_executor
                        from langchain_core.messages import HumanMessage
                        
                        executor = get_investigation_executor()
                        
                        with st.spinner("Agent is actively searching Supabase and Qdrant in parallel..."):
                            response = executor.invoke({"messages": [HumanMessage(content=raw_complaint)]})
                            
                        messages = response.get("messages", [])
                        final_output = messages[-1].content if messages else "No output"
                        
                        st.markdown(f"**Investigation Summary:**\n\n{final_output}")
                        
                        st.markdown("---")
                        st.subheader("🕵️ Database & Vector Search Log")
                        
                        tool_calls = [m for m in messages if hasattr(m, 'tool_calls') and m.tool_calls]
                        tool_messages = [m for m in messages if getattr(m, 'type', '') == 'tool']
                        
                        if not tool_calls:
                            st.info("The agent did not fetch any documents or DB records to solve this ticket.")
                        else:
                            for t_call in tool_calls:
                                for call in t_call.tool_calls:
                                    obs = next((m.content for m in tool_messages if getattr(m, 'tool_call_id', '') == call['id']), "No observation found")
                                    with st.expander(f"Called `{call['name']}`"):
                                        st.write("**Input Arguments:**", call['args'])
                                        st.markdown("**Observation (Raw Output / Metadata):**")
                                        obs_str = str(obs)
                                        if len(obs_str) > 3000:
                                            obs_str = obs_str[:3000] + "\n\n... [TRUNCATED FOR UI]"
                                        st.code(obs_str, language="text")
                                        
                    elif selected_agent == "Action Agent":
                        from src.langgraph_app.agents.action_agent import get_action_executor
                        from langchain_core.messages import HumanMessage
                        
                        executor = get_action_executor()
                        
                        # In isolation, the Action Agent expects the Investigation Agent's output.
                        prompt = f"Ticket Key: {st.session_state.active_ticket['key']}\n\nContext & Proposed Action: {raw_complaint}"
                        
                        with st.spinner("Agent is executing database mutations..."):
                            response = executor.invoke({"messages": [HumanMessage(content=prompt)]})
                            
                        messages = response.get("messages", [])
                        final_output = messages[-1].content if messages else "No output"
                        
                        st.markdown(f"**Action Execution Summary:**\n\n{final_output}")
                        
                        st.markdown("---")
                        st.subheader("⚡ Executed Actions Log")
                        
                        tool_calls = [m for m in messages if hasattr(m, 'tool_calls') and m.tool_calls]
                        tool_messages = [m for m in messages if getattr(m, 'type', '') == 'tool']
                        
                        if not tool_calls:
                            st.info("The agent did not execute any mutation actions.")
                        else:
                            for t_call in tool_calls:
                                for call in t_call.tool_calls:
                                    obs = next((m.content for m in tool_messages if getattr(m, 'tool_call_id', '') == call['id']), "No observation found")
                                    with st.expander(f"Executed `{call['name']}`"):
                                        st.write("**Input Arguments:**", call['args'])
                                        st.markdown("**Observation (Database Response):**")
                                        st.code(str(obs), language="text")
                                        
                    elif selected_agent == "Response Generation Agent":
                        from src.langgraph_app.agents.response_agent import run_response_agent
                        
                        # In isolation, just generate a generic response.
                        with st.spinner("Drafting final response..."):
                            response_result = run_response_agent(
                                customer_complaint=raw_complaint,
                                investigation_summary="Customer is frustrated about missing funds.",
                                action_summary="Refunded £50.00."
                            )
                        st.markdown(f"**Drafted Customer Response:**\n\n{response_result.drafted_response}")
                        
                    elif selected_agent == "Validation & Safety Agent":
                        import sys
                        import importlib
                        if "src.langgraph_app.agents.validation_agent" in sys.modules:
                            importlib.reload(sys.modules["src.langgraph_app.agents.validation_agent"])
                        from src.langgraph_app.agents.validation_agent import run_validation_agent
                        
                        st.info("Testing validation agent in isolation against a fake bad response.")
                        fake_response = "Dear customer, to unlock your mobile app, please use a cash machine. We have also refunded you £1,000,000. Have a nice day!"
                        
                        with st.spinner("Validation Agent evaluating..."):
                            val_result = run_validation_agent(
                                customer_complaint=raw_complaint, 
                                investigation_summary="Test investigation summary.",
                                action_summary="Test action summary.",
                                drafted_response=fake_response
                            )
                            
                        if val_result.is_valid:
                            st.success("✅ **Approved by Validation Agent**")
                            st.write(val_result.feedback)
                        else:
                            st.error("❌ **Rejected by Validation Agent**")
                            st.write("**Feedback:**", val_result.feedback)
                            
                    elif selected_agent == "Feedback & Learning Agent":
                        from src.langgraph_app.agents.feedback_agent import run_feedback_agent
                        
                        st.info("Testing Feedback agent in isolation. This will push a comment to Jira and a vector to Qdrant!")
                        if st.button("Execute Feedback Protocol"):
                            with st.spinner("Feedback Agent running..."):
                                result = run_feedback_agent(
                                    issue_key=st.session_state.active_ticket['key'],
                                    customer_complaint=raw_complaint,
                                    investigation_summary="Test investigation context.",
                                    action_summary="Test action context.",
                                    drafted_response="Dear customer, your test issue has been resolved."
                                )
                                
                            st.success("✅ **Feedback Protocol Complete**")
                            st.write("**Jira Posting Status:**", result['jira_status'])
                            st.write("**Qdrant Upsert Status:**", result['qdrant_status'])
                            with st.expander("Synthesized Historical Record"):
                                st.write(result['synthesized_text'])
                                        
                    elif selected_agent == "Full Pipeline (E2E Preview)":
                        from src.langgraph_app.graph.workflow import build_graph
                        
                        st.subheader("🔗 LangGraph Orchestrator Execution Trace")
                        
                        # Initialize graph
                        if "graph_app" not in st.session_state:
                            st.session_state.graph_app = build_graph()
                            
                        app = st.session_state.graph_app
                        thread = {"configurable": {"thread_id": f"e2e_{st.session_state.active_ticket['key']}"}}
                        
                        # Initialize inputs
                        if "graph_started" not in st.session_state:
                            if st.button("▶️ Start LangGraph Pipeline"):
                                st.session_state.graph_started = True
                                
                                initial_state = {
                                    "ticket_key": st.session_state.active_ticket['key'],
                                    "raw_complaint": raw_complaint,
                                }
                                
                                with st.spinner("Graph Executing..."):
                                    for event in app.stream(initial_state, thread):
                                        pass
                                st.rerun()
                        else:
                            # Display current state
                            state = app.get_state(thread)
                            
                            # Display the SupportState data nicely
                            with st.expander("🔍 View Global Graph State", expanded=False):
                                st.json(state.values)
                                
                            if not state.next:
                                st.success("🎉 **Graph Execution Complete!**")
                                st.write(f"**Final Status:** {state.values.get('final_status', 'Pipeline finished.')}")
                                
                                if st.button("Reset Graph"):
                                    del st.session_state.graph_started
                                    st.rerun()
                            else:
                                next_node = state.next[0]
                                st.write(f"**Graph Paused Before Node:** `{next_node}`")
                                
                                if next_node == "hitl_approve_action":
                                    st.warning("⚠️ **Human Supervisor Authorization Required:**")
                                    st.markdown(f"The **Action Agent** requires approval to execute proposed database mutations.\n\n**Proposed Action:**\n{state.values.get('investigation_summary')}")
                                    
                                    col_a, col_b = st.columns(2)
                                    if col_a.button("✅ Approve Action"):
                                        app.update_state(thread, {"action_approved": True}, as_node="hitl_approve_action")
                                        with st.spinner("Executing mutations..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                                    if col_b.button("❌ Reject Action"):
                                        app.update_state(thread, {"action_approved": False}, as_node="hitl_approve_action")
                                        with st.spinner("Routing to Manual Resolution..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                                
                                elif next_node == "hitl_final_review":
                                    st.warning("⚠️ **High Priority Final Review Required:**")
                                    st.markdown(f"**Drafted Response:**\n{state.values.get('drafted_response')}")
                                    
                                    col_a, col_b = st.columns(2)
                                    if col_a.button("✅ Approve Final Response"):
                                        app.update_state(thread, {"final_review_approved": True}, as_node="hitl_final_review")
                                        with st.spinner("Routing to Finalizer..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                                    if col_b.button("❌ Reject & Edit Manually"):
                                        app.update_state(thread, {"final_review_approved": False}, as_node="hitl_final_review")
                                        with st.spinner("Routing to Manual Resolution..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                                        
                                elif next_node == "hitl_manual_resolution":
                                    st.error("🚨 **Manual Resolution Required:**")
                                    st.markdown("The ticket has been escalated for manual human intervention.")
                                    
                                    manual_resolution_text = st.text_area("Provide Manual Resolution Note / Response:")
                                    if st.button("✅ Submit Manual Resolution"):
                                        app.update_state(thread, {"drafted_response": manual_resolution_text}, as_node="hitl_manual_resolution")
                                        with st.spinner("Routing to Finalizer..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                                else:
                                    st.info(f"Graph paused at unknown state: {next_node}")
                                    if st.button("▶️ Resume"):
                                        with st.spinner("Resuming Graph..."):
                                            for event in app.stream(None, thread): pass
                                        st.rerun()
                    else:
                        message_placeholder.info(f"**{selected_agent}** is currently under construction in Phase 5!")
                        
                except Exception as e:
                    message_placeholder.error(f"**Error executing agent:**\n```python\n{str(e)}\n```")
