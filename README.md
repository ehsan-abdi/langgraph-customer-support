# Aura Bank AI Support — Multi-Agent Autonomous Banking & Ticket Orchestration Platform

<div align="center">

![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1c1c1c.svg?style=for-the-badge&logo=langchain&logoColor=white)
![AWS Bedrock](https://img.shields.io/badge/AWS-Bedrock%20Agents%20%26%20Flows-FF9900.svg?style=for-the-badge&logo=amazonaws&logoColor=white)
![React](https://img.shields.io/badge/React-19.2-61DAFB.svg?style=for-the-badge&logo=react&logoColor=black)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC.svg?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)

*An enterprise-grade, dual-engine (LangGraph vs. AWS Bedrock) multi-agent customer support & banking operations system featuring real-time WebSocket reasoning streaming, interactive Human-in-the-Loop (HITL) approval gates, and zero-retention PII tokenization.*

</div>

---

## 📖 Executive Summary

**Aura Bank AI Support** is a state-of-the-art multi-agent AI system built to resolve complex customer support inquiries (e.g., unauthorized credit card charges, dispute investigations, and billing adjustments) autonomously while enforcing strict financial compliance, zero-retention data privacy, and mandatory human oversight for state-mutating actions.

To evaluate enterprise cloud scalability vs. self-hosted flexibility, this project implements a **Monorepo Multi-Backend Split**. It allows engineering teams to benchmark **self-hosted LangGraph (`src/langgraph_app`)** side-by-side against **managed Amazon Bedrock Agents (`src/bedrock_app`)** using the **exact same React 19 Frontend Dashboard (`web`)** and shared business tooling (`src/tools`).

---

## 🏗️ Architectural Highlights & Key Features

### 1. Dual-Engine Benchmarking Strategy
* **🟢 LangGraph Engine (`src/langgraph_app/`)**: Self-hosted execution graph powered by LangChain (`ChatOpenAI`, `ChatGroq`) and `MemorySaver` checkpointer. Runs locally or inside containerized clusters with full state inspection.
* **🟠 Amazon Bedrock Engine (`src/bedrock_app/`)**: AWS-native serverless orchestration utilizing Amazon Bedrock Agents, Lambda Action Groups (OpenAPI 3.0 schemas), Knowledge Bases, and Bedrock Flows provisioned cleanly via the AWS Python SDK (`Boto3`).

Both backends expose identical WebSocket (`/api/ticket/stream`) and REST API endpoints on port `8000`, making the orchestration engine completely transparent to the frontend user interface.

### 2. The 6-Agent Autonomous Workflow Hierarchy
Our execution pipeline divides complex financial customer service requests among six specialized, single-responsibility AI agents:

```text
 ┌──────────────────┐
 │ 1. INGESTION     │  ➔ Anonymizes PII via PIIVault & extracts complaint metadata (Category, Tone).
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │ 2. TRIAGE        │  ➔ Evaluates urgency (Urgent/High/Normal/Low) & routes to specialized departments.
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │ 3. INVESTIGATION │  ➔ Queries SQLite core banking records & retrieves institutional RAG policies.
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │ 4. ACTION        │  ➔ Prepares & executes database mutations (charge reversals, card freezes).
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │ 5. RESPONSE      │  ➔ Synthesizes factual investigation findings into professional customer letters.
 └────────┬─────────┘
          ▼
 ┌──────────────────┐
 │ 6. VALIDATION    │  ➔ Audits response against strict compliance & tone guidelines (Max 3 iterations).
 └──────────────────┘
```

### 3. Interactive Human-In-The-Loop (HITL) Governance
State-mutating financial operations cannot run completely unattended. The system enforces dynamic execution breakpoints (`interrupt_before`) at critical nodes (`hitl_manual_resolution`, `hitl_approve_action`, `hitl_final_review`). When an interruption triggers, the backend emits an `interrupted` WebSocket event, prompting the support manager to review, approve, or override actions directly on the interactive **React Flow Canvas (`@xyflow/react`)**.

### 4. Zero-Retention PII Tokenization (`PIIVault`)
Before any customer complaint text is passed to an LLM provider (OpenAI, Groq, or Anthropic Bedrock), the `PIIVault` (`src/security/pii_vault.py`) strips and tokenizes sensitive PII (Credit Card numbers, Emails, Phone numbers, Names) into secure placeholders (e.g., `[CARD_1]`, `[EMAIL_1]`). The unmasked mapping resides exclusively in transient server memory and is re-injected only when strictly required for local database lookups.

---

## 📂 Repository Structure

```text
ai_customer_support/
├── data/                       # [Excluded from Git] Local SQLite banking database (`tickets.db`)
├── db/                         # Shared SQL schema (`schema.sql`) & vector embeddings documentation
├── scripts/                    # Utilities for synthetic customer generation & CFPB data ingestion
├── tests/                      # [Excluded from Git] Unit & integration test suites
│
├── src/
│   ├── core/                   # Shared Pydantic schemas, LLM factory (`llm.py`), and `SupportState`
│   ├── security/               # Tokenization engine (`pii_vault.py`)
│   ├── tools/                  # Shared core business logic (`JiraClient`, `db_tools.py`, `vector_tools.py`)
│   ├── ui/                     # Interactive Streamlit/Gradio local testing playground (`playground.py`)
│   │
│   ├── langgraph_app/          # 🟢 [ENGINE 1: LangGraph StateGraph]
│   │   ├── agents/             # Agent node wrappers (`ingestion_agent.py`, `triage_agent.py`, etc.)
│   │   ├── graph/              # StateGraph compilation & conditional routing (`workflow.py`)
│   │   └── api/                # FastAPI server & WebSocket streaming router (`server.py`)
│   │
│   └── bedrock_app/            # 🟠 [ENGINE 2: AWS Bedrock Native Implementation]
│       ├── schemas/            # OpenAPI 3.0 JSON schemas (`jira_action_group.json`, etc.)
│       ├── lambdas/            # AWS Lambda handlers (`lambda_jira.py`, `lambda_customer_db.py`)
│       ├── deploy/             # Boto3 provisioning scripts (`create_agents.py`, `create_flow.py`)
│       └── api/                # FastAPI Bedrock Runtime Proxy (`server.py`)
│
├── web/                        # 🎨 React 19 + Vite + TailwindCSS SPA Dashboard
│   ├── src/components/         # Dashboard UI (`AgentDashboard.jsx`, `GraphCanvas.jsx`, `HitlOverlay.jsx`)
│   └── package.json            # Frontend dependencies & scripts
│
├── Dockerfile                  # Multi-stage production container build (Serves SPA & Backend)
├── docker-compose.yml          # Container orchestration with volume persistence for SQLite & Qdrant
└── requirements.txt            # Python dependencies (FastAPI, LangGraph, LangChain, Boto3, Pydantic)
```

---

## 🚀 Getting Started & Quickstart

### Prerequisites
* **Python**: 3.10 or higher
* **Node.js**: 18.x or higher (for local React development)
* **Docker & Docker Compose**: (Optional, for containerized deployment)

### 1. Environment Setup
Create your local environment configuration by copying the template:

```bash
cp .env.example .env
```

Populate your `.env` with your preferred LLM provider credentials:
```ini
# LLM Provider Configuration ('openai' or 'groq')
OPENAI_API_KEY="sk-..."
GROQ_API_KEY="gsk_..."

# AWS Credentials (Optional: Required only when running or deploying `src/bedrock_app/`)
AWS_ACCESS_KEY_ID="AKIA..."
AWS_SECRET_ACCESS_KEY="..."
AWS_DEFAULT_REGION="us-east-1"
```

### 2. Option A: Run via Docker Compose (Recommended)
Our multi-stage `Dockerfile` packages both the React dashboard and the FastAPI backend into a single container:

```bash
docker-compose up --build
```
* **Dashboard & Backend API**: Open [http://localhost:8000](http://localhost:8000)

### 3. Option B: Local Manual Development
If you wish to run the backend and frontend separately for hot-reloading:

#### Step 1: Start the Backend Server (`src/langgraph_app/api/server.py`)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run the LangGraph FastAPI Server on port 8000
python src/langgraph_app/api/server.py
```

#### Step 2: Start the React Frontend (`web/`)
```bash
cd web
npm install
npm run dev
```
* **Live UI**: Open [http://localhost:5173](http://localhost:5173) (Automatically proxies API requests to `http://localhost:8000`).

---

## 📡 API Contracts & WebSocket Streaming

### WebSocket Streaming (`ws://localhost:8000/api/ticket/stream/{ticket_id}`)
When a ticket resolution initiates, the backend streams structured JSON events down the WebSocket:

1. **Node Progress Update (`node_update`)**
   ```json
   {
     "type": "node_update",
     "node": "investigation_node",
     "state": {
       "ticket_key": "AURA-29",
       "priority": "High",
       "investigation_summary": "Customer balance verified: $4,250.00. Transaction #8921 flagged as unauthorized."
     }
   }
   ```

2. **HITL Interruption (`interrupted`)**
   ```json
   {
     "type": "interrupted",
     "node": "hitl_approve_action",
     "state": {
       "ticket_key": "AURA-29",
       "action_required": true,
       "action_summary": "Proposed: Reverse $340.00 charge on Card ending in 4492."
     }
   }
   ```

### Resume Execution (`POST /api/ticket/resume/{ticket_id}`)
When the human manager clicks **"Approve"** on the dashboard:
```bash
curl -X POST http://localhost:8000/api/ticket/resume/AURA-29 \
  -H "Content-Type: application/json" \
  -d '{"action_approved": true}'
```

---

## 🛠️ Benchmarking Protocol (LangGraph vs. Bedrock)

To run a side-by-side performance evaluation on ticket `AURA-29`:

1. **Test LangGraph**:
   ```bash
   python src/langgraph_app/api/server.py
   ```
   Execute ticket `AURA-29` on the UI dashboard and record step latency, token consumption, and audit trace clarity.

2. **Test Amazon Bedrock**:
   Deploy your Bedrock infrastructure using our programmatic Python Boto3 setup:
   ```bash
   python src/bedrock_app/deploy/create_agents.py
   python src/bedrock_app/deploy/create_flow.py
   ```
   Launch the Bedrock proxy server:
   ```bash
   python src/bedrock_app/api/server.py
   ```
   Execute ticket `AURA-29` on the exact same UI dashboard and compare execution traces!

---

## 🔒 Security & Git Policies

* **Data Exclusion**: All internal database instances (`data/*.db`), temporary storage, and local unit tests (`tests/`, `test_*.py`) are strictly excluded via `.gitignore` to prevent leaking proprietary datasets.
* **Secrets Management**: Never commit `.env` or `.pem` keys to version control.

---

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.
