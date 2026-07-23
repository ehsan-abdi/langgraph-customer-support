"""
Aura Bank — AI Customer Support Demo
=====================================
Streamlit frontend for the 2-agent Bedrock pipeline:

  [Ticket] → Triage Agent → HITL gate (critical only) → Resolution Agent → [Response]

Run locally:
  streamlit run bedrock_demo.py

Deploy to Streamlit Community Cloud:
  1. Push to GitHub
  2. connect repo at share.streamlit.io
  3. Add AWS credentials in Secrets tab
"""

import streamlit as st
import boto3
import json
import uuid
import os
import re
import time
from dotenv import load_dotenv

# ── Env setup ─────────────────────────────────────────────────────────────────
load_dotenv()

# ── Page config (must be first Streamlit call) ────────────────────────────────
st.set_page_config(
    page_title="Aura Bank | AI Support Demo",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Page background */
.stApp { background: #0a0e1a; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1526 0%, #111a2e 100%);
    border-right: 1px solid #1e2d4a;
}

/* Header */
.aura-header {
    background: linear-gradient(135deg, #0d1f3c 0%, #1a3a6b 50%, #0d2845 100%);
    border: 1px solid #1e3d6b;
    border-radius: 16px;
    padding: 28px 36px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.aura-header::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 180px; height: 180px;
    background: radial-gradient(circle, rgba(212,175,55,0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.aura-header h1 { color: #e8c84a; font-size: 2rem; font-weight: 700; margin: 0; letter-spacing: -0.5px; }
.aura-header p  { color: #7a9cc4; margin: 4px 0 0 0; font-size: 0.95rem; }

/* Priority badges */
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.badge-urgent  { background: rgba(239,68,68,0.18);  color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
.badge-high    { background: rgba(249,115,22,0.18); color: #fb923c; border: 1px solid rgba(249,115,22,0.3); }
.badge-normal  { background: rgba(234,179,8,0.18);  color: #fbbf24; border: 1px solid rgba(234,179,8,0.3); }
.badge-low     { background: rgba(34,197,94,0.18);  color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }

/* Cards */
.card {
    background: linear-gradient(135deg, #0f1e35 0%, #111827 100%);
    border: 1px solid #1e2d4a;
    border-radius: 12px;
    padding: 20px 24px;
    margin: 12px 0;
}
.card-critical {
    background: linear-gradient(135deg, #1a0f0f 0%, #1f1111 100%);
    border: 1px solid #7f1d1d;
    border-left: 4px solid #ef4444;
}
.card-success {
    background: linear-gradient(135deg, #0f1a0f 0%, #111a11 100%);
    border: 1px solid #14532d;
    border-left: 4px solid #22c55e;
}
.card-escalated {
    background: linear-gradient(135deg, #1a150f 0%, #1f1a11 100%);
    border: 1px solid #7c4f17;
    border-left: 4px solid #f59e0b;
}

/* Step indicator */
.step-row { display: flex; gap: 8px; align-items: center; margin-bottom: 24px; }
.step-dot {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700;
}
.step-active   { background: #1e4b8f; color: #60a5fa; border: 2px solid #3b82f6; }
.step-done     { background: #14532d; color: #4ade80; border: 2px solid #22c55e; }
.step-pending  { background: #111827; color: #4b5563; border: 2px solid #1f2937; }
.step-line     { flex: 1; height: 2px; background: #1f2937; }
.step-line-done{ flex: 1; height: 2px; background: #22c55e; }

/* Label */
.field-label { color: #6b7a99; font-size: 0.78rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
.field-value { color: #c8d6ea; font-size: 0.92rem; }

/* Ticket display */
.ticket-box {
    background: #0a0e1a;
    border: 1px solid #1e2d4a;
    border-radius: 8px;
    padding: 14px 16px;
    color: #94a3b8;
    font-size: 0.9rem;
    line-height: 1.6;
    font-style: italic;
}

/* Response display */
.response-box {
    background: #0a0e1a;
    border: 1px solid #1e3d2a;
    border-radius: 8px;
    padding: 16px 18px;
    color: #d1fae5;
    font-size: 0.92rem;
    line-height: 1.7;
}

/* Sidebar labels */
.sidebar-section { color: #e8c84a; font-weight: 600; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.8px; margin: 16px 0 8px 0; }
.sidebar-text { color: #7a9cc4; font-size: 0.85rem; line-height: 1.5; }
</style>
""", unsafe_allow_html=True)


# ── AWS + Bedrock Config ───────────────────────────────────────────────────────
def get_aws_creds() -> dict:
    """Returns AWS credentials from Streamlit secrets or environment."""
    # Try Streamlit secrets first (Streamlit Cloud)
    key_id  = st.secrets.get("AWS_ACCESS_KEY_ID")     if hasattr(st, "secrets") else None
    secret  = st.secrets.get("AWS_SECRET_ACCESS_KEY") if hasattr(st, "secrets") else None
    region  = st.secrets.get("AWS_DEFAULT_REGION", "") if hasattr(st, "secrets") else ""
    # Fall back to environment variables (local dev)
    if not key_id:  key_id = os.getenv("AWS_ACCESS_KEY_ID", "")
    if not secret:  secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    if not region:  region = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
    return {"aws_access_key_id": key_id, "aws_secret_access_key": secret, "region_name": region}


def check_credentials() -> tuple[bool, str]:
    """
    Verifies AWS credentials are present and valid by calling STS GetCallerIdentity.
    Returns (ok: bool, message: str).
    """
    creds = get_aws_creds()
    if not creds["aws_access_key_id"] or not creds["aws_secret_access_key"]:
        return False, (
            "AWS credentials are missing.\n\n"
            "On Streamlit Cloud: go to **Settings → Secrets** and add:\n"
            "```toml\n"
            "AWS_ACCESS_KEY_ID = \"AKIA...\"\n"
            "AWS_SECRET_ACCESS_KEY = \"your_secret_key\"\n"
            "AWS_DEFAULT_REGION = \"eu-north-1\"\n"
            "```"
        )
    try:
        sts = boto3.client("sts", **creds)
        identity = sts.get_caller_identity()
        acct = identity["Account"]
        return True, f"✅ Connected — AWS account `{acct}`, region `{creds['region_name']}`"
    except Exception as e:
        code = getattr(e, 'response', {}).get('Error', {}).get('Code', type(e).__name__)
        return False, (
            f"AWS authentication failed (`{code}`).\n\n"
            "Please check your **AWS_ACCESS_KEY_ID** and **AWS_SECRET_ACCESS_KEY** "
            "in Streamlit Secrets are correct and not expired."
        )


def get_bedrock_runtime():
    """Creates a fresh Bedrock runtime client from current credentials."""
    return boto3.client("bedrock-agent-runtime", **get_aws_creds())


@st.cache_data
def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__),
                               "src/bedrock_app/deploy/bedrock_config.json")
    with open(config_path) as f:
        return json.load(f)


def invoke_agent(agent_id: str, alias_id: str, text: str) -> str:
    """Invokes a Bedrock Agent and returns the full text response."""
    from botocore.exceptions import ClientError
    runtime = get_bedrock_runtime()
    try:
        resp = runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId=str(uuid.uuid4()),
            inputText=text,
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg  = e.response["Error"].get("Message", "")
        raise RuntimeError(
            f"Bedrock API error ({code}): {msg}\n\n"
            "Check that your IAM user has **AmazonBedrockFullAccess** "
            f"and that agent `{agent_id}` exists in region `{get_aws_creds()['region_name']}`."
        ) from e
    chunks = []
    for event in resp["completion"]:
        if "chunk" in event:
            chunks.append(event["chunk"]["bytes"].decode("utf-8"))
    return "".join(chunks)


def parse_json(text: str) -> dict | None:
    """Extracts JSON from agent response (handles markdown code fences)."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    s, e = cleaned.rfind("{"), cleaned.rfind("}") + 1
    if s == -1 or e <= s:
        return None
    try:
        return json.loads(cleaned[s:e])
    except json.JSONDecodeError:
        return None


def priority_badge(priority: str) -> str:
    css = {
        "urgent": "badge-urgent",
        "high":   "badge-high",
        "normal": "badge-normal",
        "low":    "badge-low",
    }.get(priority.lower(), "badge-normal")
    return f'<span class="badge {css}">{priority}</span>'


def critical_pill(is_critical: bool) -> str:
    if is_critical:
        return '<span class="badge badge-urgent">⚠ Critical</span>'
    return '<span class="badge badge-low">✓ Routine</span>'


# ── Sample Tickets ─────────────────────────────────────────────────────────────
SAMPLES = {
    "🔴 Fraud — Unauthorized charge (CRITICAL)": (
        "URGENT: I am Mark Watts. My account number is 31241890, sort code 20-45-14. "
        "I have just noticed a fraudulent charge of £320.26 from Smith Group that I "
        "absolutely did not authorise. Please investigate and refund this immediately."
    ),
    "🟠 Disputed payment — Account access issue (HIGH)": (
        "I cannot access my online banking account. I've been locked out for 3 days "
        "and I have an urgent payment to make. Account: 31241890, Name: Mark Watts. "
        "This is causing me serious financial problems."
    ),
    "🟡 Statement request (NORMAL)": (
        "Hi, could you please send me a copy of my last 3 months' bank statements? "
        "My account number is 31241890, sort code 20-45-14. Name: Mark Watts. "
        "I need these for a mortgage application."
    ),
    "🟢 General enquiry (LOW)": (
        "Hello, I'd like to know what the current interest rates are on your "
        "easy-access savings accounts. I'm thinking of opening a new savings account."
    ),
}


# ── Session State Init ─────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "stage":        "input",   # input | triage_running | hitl_pending | resolving | done_auto | done_hitl | escalated
        "ticket":       "",
        "triage":       None,
        "resolution":   "",
        "hitl_draft":   "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Step Progress Indicator ────────────────────────────────────────────────────
def step_indicator():
    stage = st.session_state.stage

    def dot(n, label):
        if stage in ("done_auto", "done_hitl", "escalated"):
            cls = "step-done"
        elif stage in ("triage_running",) and n == 1:
            cls = "step-active"
        elif stage in ("hitl_pending", "resolving") and n <= 2:
            cls = "step-done" if n == 1 else "step-active"
        elif stage in ("done_auto", "done_hitl") and n <= 3:
            cls = "step-done"
        else:
            cls = "step-pending"
        return f'<div class="step-dot {cls}">{n}</div><div style="font-size:0.72rem;color:#6b7a99;text-align:center;margin-top:2px">{label}</div>'

    line_done = stage not in ("input", "triage_running")
    line2_done = stage in ("done_auto", "done_hitl", "escalated")

    st.markdown(f"""
    <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:24px;">
        <div style="text-align:center">{dot(1,'Triage')}</div>
        <div class="{'step-line-done' if line_done else 'step-line'}" style="margin-top:15px"></div>
        <div style="text-align:center">{dot(2,'HITL / Auto')}</div>
        <div class="{'step-line-done' if line2_done else 'step-line'}" style="margin-top:15px"></div>
        <div style="text-align:center">{dot(3,'Resolution')}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 0 8px 0">
        <div style="color:#e8c84a;font-size:1.2rem;font-weight:700">🏦 Aura Bank</div>
        <div style="color:#4b6a8f;font-size:0.8rem">AI Support Demo</div>
    </div>
    <hr style="border-color:#1e2d4a;margin:8px 0 16px 0">
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">About</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="sidebar-text">
    Two-agent pipeline powered by <strong style="color:#60a5fa">AWS Bedrock</strong>:
    <br><br>
    🔍 <strong>Triage Agent</strong> — classifies ticket and sets priority<br>
    ⚠️ <strong>HITL gate</strong> — critical tickets routed to human<br>
    🔧 <strong>Resolution Agent</strong> — auto-resolves routine tickets
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">Pipeline</div>', unsafe_allow_html=True)
    st.code("Ticket\n  → Triage Agent\n  → is_critical?\n    YES → HITL (you)\n    NO  → Resolution Agent\n  → Response", language=None)

    st.markdown('<div class="sidebar-section">AWS Connection</div>', unsafe_allow_html=True)
    cred_ok, cred_msg = check_credentials()
    if cred_ok:
        st.success(cred_msg)
    else:
        st.error(cred_msg)

    st.markdown('<div class="sidebar-section">AWS Resources</div>', unsafe_allow_html=True)
    try:
        config = load_config()
        st.markdown(f"""
        <div class="sidebar-text">
        🤖 Triage: <code>{config.get('triage_agent_id','—')}</code><br>
        🤖 Resolution: <code>{config.get('resolution_agent_id','—')}</code><br>
        🌊 Flow: <code>{config.get('flow_id','—')}</code><br>
        🌍 Region: <code>eu-north-1</code>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.warning("bedrock_config.json not found")

    st.markdown('<div class="sidebar-section">Sample Tickets</div>', unsafe_allow_html=True)
    for label, text in SAMPLES.items():
        if st.button(label, use_container_width=True, key=f"sample_{label[:8]}"):
            st.session_state.ticket = text
            st.session_state.stage  = "input"
            st.session_state.triage = None
            st.session_state.resolution = ""
            st.rerun()


# ── Main Content ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="aura-header">
    <h1>🏦 Aura Bank — AI Support Demo</h1>
    <p>Powered by Amazon Bedrock · Claude Sonnet 4.5 · Human-in-the-Loop</p>
</div>
""", unsafe_allow_html=True)

config = load_config()
step_indicator()

# ══════════════════════════════════════════════════════════════════════════════
# STAGE: input
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.stage == "input":
    st.markdown("### 📝 Submit a Customer Ticket")
    st.markdown('<p style="color:#6b7a99;font-size:0.9rem">Enter a support ticket below, or choose a sample from the sidebar.</p>', unsafe_allow_html=True)

    ticket = st.text_area(
        label="Ticket text",
        value=st.session_state.ticket,
        height=150,
        placeholder="e.g. Hi, I noticed an unauthorized charge on my account...",
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        submit = st.button("🚀 Submit Ticket", type="primary", use_container_width=True)

    if submit:
        if not ticket.strip():
            st.error("Please enter a ticket before submitting.")
        else:
            st.session_state.ticket = ticket.strip()
            st.session_state.stage  = "triage_running"
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: triage_running
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "triage_running":
    st.markdown("### 🔍 Step 1 — Triage Agent")

    with st.spinner("Classifying ticket with Triage Agent..."):
        triage_prompt = (
            "[TICKET RECEIVED FOR CLASSIFICATION — DO NOT RESPOND TO CUSTOMER]\n\n"
            + st.session_state.ticket
        )
        raw = invoke_agent(config["triage_agent_id"], config["triage_alias_id"], triage_prompt)
        triage = parse_json(raw)

    if not triage:
        st.error(f"Triage Agent returned an unexpected response. Raw output:\n\n{raw}")
        if st.button("↩ Try Again"):
            st.session_state.stage = "input"
            st.rerun()
    else:
        st.session_state.triage = triage
        if triage.get("is_critical"):
            st.session_state.stage = "hitl_pending"
        else:
            st.session_state.stage = "resolving"
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: hitl_pending — CRITICAL ticket, human must respond
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "hitl_pending":
    triage = st.session_state.triage
    priority = triage.get("priority", "Unknown")

    # Triage summary card
    st.markdown("### 🔍 Step 1 — Triage Result")
    st.markdown(f"""
    <div class="card card-critical">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            {priority_badge(priority)}
            {critical_pill(True)}
            <span style="color:#6b7a99;font-size:0.82rem">Department: <strong style="color:#94a3b8">{triage.get('department','—')}</strong></span>
        </div>
        <div class="field-label">Summary</div>
        <div class="field-value" style="margin-bottom:10px">{triage.get('summary','—')}</div>
        <div class="field-label">Reasoning</div>
        <div class="field-value">{triage.get('reasoning','—')}</div>
    </div>
    """, unsafe_allow_html=True)

    # HITL panel
    st.markdown("### ⚠️ Step 2 — Human Review Required")
    st.markdown(f"""
    <div class="card card-critical" style="margin-bottom:16px">
        <div style="color:#f87171;font-weight:600;margin-bottom:12px">
            🚨 This ticket is classified as <strong>{priority.upper()}</strong> and requires your response.
        </div>
        <div class="field-label">Original Ticket</div>
        <div class="ticket-box">{st.session_state.ticket}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**Write your resolution response below:**")
    hitl_text = st.text_area(
        label="HITL response",
        value=st.session_state.hitl_draft,
        height=200,
        placeholder="Address the customer's issue directly. Be clear, professional, and empathetic.\n\nExample: 'Dear [Name], I have reviewed your account and can confirm that...'",
        label_visibility="collapsed",
        key="hitl_textarea",
    )
    st.session_state.hitl_draft = hitl_text

    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        submit_hitl = st.button("✅ Submit Resolution", type="primary", use_container_width=True)
    with col2:
        escalate = st.button("🚨 Escalate to Senior Team", use_container_width=True)

    if submit_hitl:
        if not hitl_text.strip():
            st.error("Please write a resolution response before submitting.")
        else:
            st.session_state.resolution = hitl_text.strip()
            st.session_state.stage      = "done_hitl"
            st.rerun()

    if escalate:
        st.session_state.stage = "escalated"
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: resolving — non-critical, run Resolution Agent
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "resolving":
    triage = st.session_state.triage
    priority = triage.get("priority", "Unknown")

    # Show triage result
    st.markdown("### 🔍 Step 1 — Triage Result")
    st.markdown(f"""
    <div class="card">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            {priority_badge(priority)}
            {critical_pill(False)}
            <span style="color:#6b7a99;font-size:0.82rem">Department: <strong style="color:#94a3b8">{triage.get('department','—')}</strong></span>
        </div>
        <div class="field-label">Summary</div>
        <div class="field-value" style="margin-bottom:10px">{triage.get('summary','—')}</div>
        <div class="field-label">Reasoning</div>
        <div class="field-value">{triage.get('reasoning','—')}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🔧 Step 2 — Resolution Agent")
    with st.spinner("Resolution Agent investigating and resolving..."):
        resolution_raw = invoke_agent(
            config["resolution_agent_id"],
            config["resolution_alias_id"],
            st.session_state.ticket,
        )

    st.session_state.resolution = resolution_raw
    st.session_state.stage      = "done_auto"
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: done_auto — auto-resolved by Resolution Agent
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "done_auto":
    triage   = st.session_state.triage
    priority = triage.get("priority", "Unknown")

    st.markdown("### 🔍 Triage Result")
    st.markdown(f"""
    <div class="card">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            {priority_badge(priority)}
            {critical_pill(False)}
            <span style="color:#6b7a99;font-size:0.82rem">Department: <strong style="color:#94a3b8">{triage.get('department','—')}</strong></span>
        </div>
        <div class="field-label">Summary</div>
        <div class="field-value" style="margin-bottom:10px">{triage.get('summary','—')}</div>
        <div class="field-label">Reasoning</div>
        <div class="field-value">{triage.get('reasoning','—')}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### ✅ Resolution — Auto-resolved")
    st.markdown(f"""
    <div class="card card-success">
        <div style="color:#4ade80;font-weight:600;margin-bottom:12px">
            🤖 Resolution Agent responded automatically (no human review required)
        </div>
        <div class="response-box">{st.session_state.resolution}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Submit New Ticket", type="primary"):
        for k in ("stage","ticket","triage","resolution","hitl_draft"):
            del st.session_state[k]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: done_hitl — human submitted resolution
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "done_hitl":
    triage   = st.session_state.triage
    priority = triage.get("priority", "Unknown")

    st.markdown("### 🔍 Triage Result")
    st.markdown(f"""
    <div class="card card-critical">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
            {priority_badge(priority)}
            {critical_pill(True)}
            <span style="color:#6b7a99;font-size:0.82rem">Department: <strong style="color:#94a3b8">{triage.get('department','—')}</strong></span>
        </div>
        <div class="field-label">Summary</div>
        <div class="field-value" style="margin-bottom:10px">{triage.get('summary','—')}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### ✅ Resolution — Submitted by Human Reviewer")
    st.markdown(f"""
    <div class="card card-success">
        <div style="color:#4ade80;font-weight:600;margin-bottom:12px">
            👤 Reviewed and resolved by human operator
        </div>
        <div class="response-box">{st.session_state.resolution}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Submit New Ticket", type="primary"):
        for k in ("stage","ticket","triage","resolution","hitl_draft"):
            del st.session_state[k]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STAGE: escalated
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "escalated":
    triage   = st.session_state.triage
    priority = triage.get("priority", "Unknown")

    st.markdown("### 🔍 Triage Result")
    st.markdown(f"""
    <div class="card card-critical">
        <div style="display:flex;align-items:center;gap:10px;">
            {priority_badge(priority)}
            {critical_pill(True)}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 🚨 Escalated to Senior Team")
    st.markdown(f"""
    <div class="card card-escalated">
        <div style="color:#f59e0b;font-weight:600;margin-bottom:10px">
            🚨 This ticket has been escalated and will be reviewed by the senior support team.
        </div>
        <div class="field-label">Original Ticket</div>
        <div class="ticket-box">{st.session_state.ticket}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔄 Submit New Ticket", type="primary"):
        for k in ("stage","ticket","triage","resolution","hitl_draft"):
            del st.session_state[k]
        st.rerun()
