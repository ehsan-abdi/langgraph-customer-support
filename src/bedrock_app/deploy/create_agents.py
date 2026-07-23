"""
Aura Bank Bedrock Agent Provisioning Script
============================================
Uses boto3 to programmatically create, prepare, and alias the Aura Bank
Bedrock Agents inside your AWS account.

Run per step:
  python create_agents.py --step triage       # Step 2.1: Triage Agent
  python create_agents.py --step resolution   # Step 2.2: Resolution Agent + Action Groups
  python create_agents.py --step all          # Run both

Results (agent IDs and aliases) are saved to:
  src/bedrock_app/deploy/bedrock_config.json
"""

import os
import sys
import json
import time
import argparse
from dotenv import load_dotenv

# ── Path Setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, _ROOT)
load_dotenv(os.path.join(_ROOT, ".env"), override=True)

import boto3

# ── Constants ─────────────────────────────────────────────────────────────────
REGION          = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
ACCESS_KEY      = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY      = os.getenv("AWS_SECRET_ACCESS_KEY")
ACCOUNT_ID      = None   # Populated at runtime via STS
CONFIG_PATH     = os.path.join(os.path.dirname(__file__), "bedrock_config.json")

# Cross-region inference profile — Claude Sonnet 4.5, EU, ACTIVE
FOUNDATION_MODEL = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"

IAM_ROLE_NAME   = "AuraBankBedrockAgentRole"

# ── Boto3 Clients ─────────────────────────────────────────────────────────────
def get_clients():
    kwargs = dict(
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
    )
    return (
        boto3.client("sts",           **kwargs),
        boto3.client("iam",           aws_access_key_id=ACCESS_KEY,
                                      aws_secret_access_key=SECRET_KEY),
        boto3.client("bedrock-agent", **kwargs),
    )


# ── Config Helpers ────────────────────────────────────────────────────────────
def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  📄 Config saved to {CONFIG_PATH}")


# ── IAM Role ──────────────────────────────────────────────────────────────────
def ensure_iam_role(iam, account_id: str) -> str:
    """
    Creates (or retrieves) the IAM execution role that all Bedrock agents will
    assume when invoking Action Group Lambdas and reading Knowledge Bases.
    Returns the Role ARN.
    """
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account_id},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{account_id}:agent/*"}
            }
        }]
    }

    try:
        resp = iam.create_role(
            RoleName=IAM_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for Aura Bank Bedrock Agents",
        )
        role_arn = resp["Role"]["Arn"]
        print(f"  ✅ IAM role created: {role_arn}")

        # Attach managed Bedrock policy
        iam.attach_role_policy(
            RoleName=IAM_ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/AmazonBedrockFullAccess",
        )
        print(f"  ✅ AmazonBedrockFullAccess policy attached")

        # Brief pause to allow IAM to propagate globally
        print("  ⏳ Waiting 10s for IAM role to propagate...")
        time.sleep(10)

    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=IAM_ROLE_NAME)["Role"]["Arn"]
        print(f"  ♻️  IAM role already exists: {role_arn}")

    return role_arn


# ── Agent Helpers ─────────────────────────────────────────────────────────────
def wait_for_agent_status(bedrock_agent, agent_id: str, target_statuses: list, timeout: int = 60):
    """Polls until the agent reaches one of the target statuses or times out."""
    print(f"  ⏳ Waiting for agent status to reach {target_statuses}...")
    for _ in range(timeout // 5):
        status = bedrock_agent.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"     Current status: {status}")
        if status in target_statuses:
            return status
        if status == "FAILED":
            raise RuntimeError(f"Agent {agent_id} entered FAILED state.")
        time.sleep(5)
    raise TimeoutError(f"Agent {agent_id} did not reach {target_statuses} within {timeout}s.")


def prepare_and_alias(bedrock_agent, agent_id: str, alias_name: str) -> str:
    """Prepares an agent and creates a versioned alias. Returns alias ID."""
    print(f"\n  🔧 Preparing agent {agent_id}...")
    bedrock_agent.prepare_agent(agentId=agent_id)
    wait_for_agent_status(bedrock_agent, agent_id, ["PREPARED"])

    print(f"  🏷️  Creating alias '{alias_name}'...")
    alias_resp = bedrock_agent.create_agent_alias(
        agentId=agent_id,
        agentAliasName=alias_name,
        description=f"Production alias for {alias_name}",
    )
    alias_id = alias_resp["agentAlias"]["agentAliasId"]
    print(f"  ✅ Alias created: {alias_id}")
    return alias_id


# ── Step 2.1: Triage Agent ────────────────────────────────────────────────────
TRIAGE_INSTRUCTION = """You are a TICKET CLASSIFIER for Aura Bank's customer support system.

YOU ARE NOT A CUSTOMER SERVICE AGENT. DO NOT HELP THE CUSTOMER DIRECTLY. DO NOT ASK QUESTIONS.

Your ONE and ONLY task: read the ticket text → output a JSON classification → STOP.

ABSOLUTE RULES (violating any rule is a critical system failure):
1. Your ENTIRE response must be a single valid JSON object — nothing before it, nothing after it.
2. NEVER greet the customer, ask questions, or request additional information.
3. NEVER attempt to resolve, help with, or respond to the customer's issue.
4. NEVER ask for identity verification, dates of birth, addresses, or any personal details.
5. Classify using ONLY the information already present in the ticket text.

Output EXACTLY this JSON structure:
{
  "priority": "<Urgent|High|Normal|Low>",
  "department": "<Fraud|Billing|Technical Support|General>",
  "is_critical": <true|false>,
  "summary": "<One sentence summary of the issue>",
  "reasoning": "<One sentence explaining your priority decision>"
}

Priority definitions:
- Urgent: Active fraud, unauthorized transactions in progress, compromised/stolen account, lost/stolen card needing immediate cancellation.
- High: Disputed charges under investigation, failed payments, account access issues, potential (not confirmed) fraud.
- Normal: Statement requests, balance inquiries, transaction history queries, product questions.
- Low: Feedback, service quality complaints, general information requests, greetings.

is_critical MUST be true ONLY for Urgent priority (requires immediate human review).
is_critical MUST be false for High, Normal, and Low (can be handled automatically).

EXAMPLES — study these carefully:

Input: "Someone has made three unauthorized charges on my card totalling £650. I need it frozen immediately."
Output:
{
  "priority": "Urgent",
  "department": "Fraud",
  "is_critical": true,
  "summary": "Customer reports three unauthorized card charges totalling £650 and requests immediate card freeze.",
  "reasoning": "Active fraud with multiple unauthorized transactions requires immediate human review and security action."
}

Input: "Hi, could you send me my last 3 months of bank statements? I need them for a mortgage application."
Output:
{
  "priority": "Normal",
  "department": "General",
  "is_critical": false,
  "summary": "Customer requests last 3 months of bank statements for a mortgage application.",
  "reasoning": "Routine document request with no financial risk or urgency — can be auto-resolved."
}

Input: "I lost my wallet and need my debit card cancelled right away."
Output:
{
  "priority": "Urgent",
  "department": "Fraud",
  "is_critical": true,
  "summary": "Customer has lost their wallet and requests immediate card cancellation.",
  "reasoning": "Lost card poses immediate fraud risk and requires urgent human-approved cancellation."
}

Input: "What is the current interest rate on your savings accounts?"
Output:
{
  "priority": "Low",
  "department": "General",
  "is_critical": false,
  "summary": "Customer enquiring about current savings account interest rates.",
  "reasoning": "General product information request with no financial urgency or risk."
}

Input: "A direct debit of £150 to Utility Corp failed yesterday. Can you check my account and what happened?"
Output:
{
  "priority": "High",
  "department": "Billing",
  "is_critical": false,
  "summary": "Customer reports a failed £150 direct debit to Utility Corp and requests account investigation.",
  "reasoning": "Failed payment is high priority but not an active security emergency — can be auto-resolved."
}

Now classify the ticket below. Output ONLY the JSON object — nothing else."""


def create_triage_agent(bedrock_agent, iam_role_arn: str, config: dict) -> dict:
    """
    Step 2.1: Creates the Triage Agent.
    The Triage Agent is a pure-reasoning agent with no Action Groups.
    It classifies incoming tickets and determines if human oversight is needed.
    """
    print("\n" + "="*60)
    print("STEP 2.1: Creating Triage Agent")
    print("="*60)

    # Skip if already created
    if config.get("triage_agent_id"):
        print(f"  ♻️  Triage Agent already exists: {config['triage_agent_id']}")
        return config

    resp = bedrock_agent.create_agent(
        agentName="AuraBank-TriageAgent",
        description="Classifies Aura Bank customer support tickets by priority and determines if human-in-the-loop oversight is required.",
        foundationModel=FOUNDATION_MODEL,
        agentResourceRoleArn=iam_role_arn,
        instruction=TRIAGE_INSTRUCTION,
        idleSessionTTLInSeconds=600,
    )

    agent     = resp["agent"]
    agent_id  = agent["agentId"]
    print(f"  ✅ Triage Agent created! agentId = {agent_id}")
    print(f"     Status: {agent['agentStatus']}")

    # Wait for agent to move out of CREATING state
    wait_for_agent_status(bedrock_agent, agent_id, ["NOT_PREPARED", "PREPARED"])

    # Prepare and alias
    alias_id = prepare_and_alias(bedrock_agent, agent_id, "PROD")

    config["triage_agent_id"]    = agent_id
    config["triage_alias_id"]    = alias_id
    config["triage_agent_model"] = FOUNDATION_MODEL
    save_config(config)

    return config


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2.2 — Lambda Deployment + Resolution Agent
# ══════════════════════════════════════════════════════════════════════════════

# ── Self-contained Lambda Handler: Customer DB ─────────────────────────────────
# Uses Supabase REST API over HTTPS — no binary dependencies, works from Lambda.
CUSTOMER_DB_HANDLER = '''
import json, os, re, uuid
from urllib import request as urlreq, parse, error as urlerr

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def _get(table, qs):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{qs}"
    req = urlreq.Request(url, headers=HEADERS)
    with urlreq.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def _parse(event):
    try:
        return {p["name"]: p["value"]
                for p in event["requestBody"]["content"]["application/json"]["properties"]}
    except (KeyError, TypeError):
        return {}

def _resp(event, status, body):
    return {"messageVersion": "1.0", "response": {
        "actionGroup": event.get("actionGroup"),
        "apiPath": event.get("apiPath"),
        "httpMethod": event.get("httpMethod"),
        "httpStatusCode": status,
        "responseBody": {"application/json": {"body": json.dumps(body, default=str)}}
    }}

def lambda_handler(event, context):
    path   = event.get("apiPath", "")
    params = _parse(event)
    print(f"[CustomerDB] {path} | {params}")
    try:
        if path == "/get_customer_profile":
            acct = re.sub(r"\\D", "", params.get("account_number", ""))
            # Join customers + accounts via a select that filters on account_number
            rows = _get("accounts",
                f"account_number=eq.{parse.quote(acct)}"
                "&select=account_number,sort_code,customer_id,customers(id,first_name,last_name,email)")
            if not rows:
                return _resp(event, 200, {"error": f"Account {acct} not found."})
            r   = rows[0]
            cust = r["customers"]
            db_name = f"{cust[\"first_name\"]} {cust[\"last_name\"]}".lower().strip()
            in_name = params.get("full_name", "").lower().strip()
            db_sort = str(r["sort_code"]).strip()
            in_sort = params.get("sort_code", "").strip()
            if db_name != in_name or db_sort != in_sort:
                return _resp(event, 200, {"error":
                    f"IDENTITY MISMATCH: Account belongs to \'\'{cust[\"first_name\"]} {cust[\"last_name\"]}\'\' "
                    f"(sort: {r[\'sort_code\']}). Do not proceed."})
            return _resp(event, 200, {
                "id": cust["id"], "first_name": cust["first_name"],
                "last_name": cust["last_name"], "email": cust["email"],
                "account_number": r["account_number"], "sort_code": r["sort_code"]
            })

        elif path == "/get_account_balances":
            cid  = params.get("customer_id", "")
            rows = _get("accounts",
                f"customer_id=eq.{parse.quote(cid)}"
                "&select=id,account_type,balance,status,sort_code,account_number")
            return _resp(event, 200, rows)

        elif path == "/get_recent_transactions":
            aid   = params.get("account_id", "")
            limit = int(params.get("limit", 10))
            rows  = _get("transactions",
                f"account_id=eq.{parse.quote(aid)}"
                f"&select=id,amount,merchant,category,transaction_date"
                f"&order=transaction_date.desc&limit={limit}")
            return _resp(event, 200, rows)

        else:
            return _resp(event, 404, {"error": f"Unknown path: {path}"})
    except Exception as e:
        print(f"ERROR: {e}")
        return _resp(event, 500, {"error": str(e)})
'''

# ── Self-contained Lambda Handler: Financial Actions ───────────────────────────
FINANCIAL_HANDLER = '''
import json, os, uuid
from urllib import request as urlreq, error as urlerr
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def _rpc(table, method, qs, body=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{qs}"
    data = json.dumps(body).encode() if body else None
    req  = urlreq.Request(url, data=data, headers=HEADERS, method=method)
    with urlreq.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def _parse(event):
    try:
        return {p["name"]: p["value"]
                for p in event["requestBody"]["content"]["application/json"]["properties"]}
    except (KeyError, TypeError):
        return {}

def _resp(event, status, body):
    return {"messageVersion": "1.0", "response": {
        "actionGroup": event.get("actionGroup"),
        "apiPath": event.get("apiPath"),
        "httpMethod": event.get("httpMethod"),
        "httpStatusCode": status,
        "responseBody": {"application/json": {"body": json.dumps(body, default=str)}}
    }}

def lambda_handler(event, context):
    path   = event.get("apiPath", "")
    params = _parse(event)
    print(f"[Financial] {path} | {params}")
    try:
        if path == "/issue_refund":
            account_id = params.get("account_id", "")
            try:
                amount = float(params.get("amount", "0"))
            except ValueError:
                return _resp(event, 400, {"error": "Invalid amount."})
            if amount <= 0:
                return _resp(event, 400, {"error": "Amount must be positive."})
            # Get current balance first
            accts = _rpc("accounts", "GET", f"id=eq.{account_id}&select=id,balance", None)
            if not accts:
                return _resp(event, 200, {"error": "Account not found."})
            new_bal = round(float(accts[0]["balance"]) + amount, 2)
            # Update balance
            _rpc("accounts", "PATCH", f"id=eq.{account_id}", {"balance": new_bal})
            # Insert refund transaction
            _rpc("transactions", "POST", "", {
                "id": str(uuid.uuid4()), "account_id": account_id,
                "amount": amount, "merchant": "Aura Bank Refund",
                "category": "Refund",
                "transaction_date": datetime.now(timezone.utc).isoformat()
            })
            return _resp(event, 200, {"success": f"Refund of GBP{amount:.2f} applied.", "new_balance": new_bal})

        elif path == "/suspend_account_or_card":
            account_id = params.get("account_id", "")
            rows = _rpc("accounts", "PATCH",
                f"id=eq.{account_id}&select=id,account_type,status",
                {"status": "Suspended"})
            if not rows:
                return _resp(event, 200, {"error": "Account not found."})
            r = rows[0]
            return _resp(event, 200, {"success": f"{r[\'account_type\']} suspended.",
                "data": {"id": r["id"], "account_type": r["account_type"], "status": r["status"]}})

        else:
            return _resp(event, 404, {"error": f"Unknown path: {path}"})
    except Exception as e:
        print(f"ERROR: {e}")
        return _resp(event, 500, {"error": str(e)})
'''

# ── Resolution Agent Instruction ───────────────────────────────────────────────
RESOLUTION_INSTRUCTION = """You are the Resolution Agent for Aura Bank's AI-powered customer support system.

Your job is to investigate customer banking issues using your tools and resolve them completely.

INVESTIGATION WORKFLOW — always follow this exact sequence:
1. Extract customer details (full_name, account_number, sort_code) from the ticket text provided.
2. Call get_customer_profile to verify identity and obtain the customer_id.
3. If identity verification FAILS (error in response) — stop immediately, report the mismatch, and do NOT take any financial action.
4. Call get_account_balances with the customer_id to see all accounts and their IDs.
5. Call get_recent_transactions on the most relevant account (e.g. Current account for card disputes) to verify the disputed transaction exists.
6. Execute the appropriate resolution:
   - Unauthorized charges / fraud refund → call issue_refund with the exact disputed amount and the relevant account_id.
   - Lost or stolen card → call suspend_account_or_card with the relevant account_id.
7. End your response with a JSON resolution summary (see format below).

CRITICAL RULES:
- Always call get_customer_profile FIRST. Never skip identity verification.
- Only issue refunds for amounts confirmed in the transaction history.
- Only suspend accounts when loss or theft is explicitly stated.
- Never take financial action if identity verification fails.
- Always complete the full workflow before outputting the summary.

OUTPUT FORMAT — end your response with ONLY this JSON object:
{
  "status": "resolved",
  "action_taken": "<concise description of what was done>",
  "customer_name": "<verified full name>",
  "amount_refunded": <positive float, or 0.0 if no refund>,
  "account_suspended": <true or false>,
  "summary": "<1-2 sentence plain-English summary to pass to the response drafting stage>"
}"""


# ── Lambda IAM Execution Role ──────────────────────────────────────────────────
LAMBDA_ROLE_NAME = "AuraBankLambdaExecutionRole"

def ensure_lambda_role(iam) -> str:
    """Creates (or retrieves) the IAM execution role for the Lambda functions."""
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"},
                       "Action": "sts:AssumeRole"}]
    }
    try:
        role = iam.create_role(
            RoleName=LAMBDA_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Execution role for Aura Bank Lambda Action Group handlers",
        )
        role_arn = role["Role"]["Arn"]
        iam.attach_role_policy(RoleName=LAMBDA_ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole")
        print(f"  ✅ Lambda IAM role created: {role_arn}")
        print("  ⏳ Waiting 10s for Lambda role to propagate...")
        time.sleep(10)
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName=LAMBDA_ROLE_NAME)["Role"]["Arn"]
        print(f"  ♻️  Lambda IAM role already exists: {role_arn}")
    return role_arn


# ── Lambda Packaging ───────────────────────────────────────────────────────────
def package_lambda(handler_code: str, function_name: str) -> bytes:
    """
    Zips the handler into an in-memory bytes object.
    No pip install needed — handlers use only Python built-ins.
    """
    import tempfile, zipfile, io

    print(f"  📦 Packaging {function_name}...")
    with tempfile.TemporaryDirectory() as tmpdir:
        handler_path = os.path.join(tmpdir, "lambda_function.py")
        with open(handler_path, "w") as f:
            f.write(handler_code)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(handler_path, "lambda_function.py")
        print(f"    ✅ Package size: {len(buf.getvalue()) / 1024:.1f} KB")
        return buf.getvalue()


# ── Lambda Deployment ──────────────────────────────────────────────────────────
def deploy_lambda(lambda_client, function_name: str, zip_bytes: bytes,
                  env_vars: dict, role_arn: str) -> str:
    """Deploys (or updates) a Lambda function. Returns the function ARN."""
    try:
        resp = lambda_client.create_function(
            FunctionName=function_name,
            Runtime="python3.12",
            Role=role_arn,
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Environment={"Variables": env_vars},
            Timeout=30,
            MemorySize=256,
            Description=f"Aura Bank Bedrock Action Group handler: {function_name}",
        )
        arn = resp["FunctionArn"]
        print(f"  ✅ Lambda created: {arn}")
    except lambda_client.exceptions.ResourceConflictException:
        lambda_client.update_function_code(FunctionName=function_name, ZipFile=zip_bytes)
        # Wait for code update to finish before updating config
        for _ in range(24):
            upd = lambda_client.get_function_configuration(FunctionName=function_name)
            if upd.get("LastUpdateStatus") == "Successful":
                break
            time.sleep(3)
        lambda_client.update_function_configuration(
            FunctionName=function_name, Environment={"Variables": env_vars})
        resp = lambda_client.get_function_configuration(FunctionName=function_name)
        arn = resp["FunctionArn"]
        print(f"  ♻️  Lambda updated: {arn}")

    # Wait for the update to be active
    print("  ⏳ Waiting for Lambda to become Active...")
    for _ in range(24):
        state = lambda_client.get_function_configuration(
            FunctionName=function_name)["State"]
        if state == "Active":
            break
        time.sleep(5)
    return arn


def add_bedrock_permission(lambda_client, function_name: str, account_id: str):
    """Grants Bedrock the ability to invoke this Lambda function."""
    stmt_id = "AllowBedrockAgentInvoke"
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=stmt_id,
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
            SourceAccount=account_id,
        )
        print(f"  ✅ Bedrock invoke permission granted on {function_name}")
    except lambda_client.exceptions.ResourceConflictException:
        print(f"  ♻️  Bedrock permission already exists on {function_name}")


# ── Step 2.2: Resolution Agent ────────────────────────────────────────────────
def create_resolution_agent(bedrock_agent, lambda_client, iam, config: dict,
                             account_id: str) -> dict:
    """
    Step 2.2: Deploys the Lambda Action Group handlers to AWS Lambda,
    then creates the Resolution Agent and attaches both Action Groups.
    """
    from urllib.parse import urlparse, unquote

    print("\n" + "="*60)
    print("STEP 2.2: Deploying Lambdas + Creating Resolution Agent")
    print("="*60)

    # ── Parse Supabase credentials ─────────────────────────────────────────
    db_url = os.getenv("SUPABASE_DB_URL", "")
    parsed = urlparse(db_url)
    db_env = {
        "SUPABASE_URL": "https://htatmlshxlpegcubqfwr.supabase.co",
        "SUPABASE_KEY": os.getenv("SUPABASE_KEY", "sb_publishable_o_Vw6vD-FaCB-nX0R-Lhbw_kYfvAAK6"),
    }
    print(f"  🔌 Supabase URL: {db_env['SUPABASE_URL']}")

    # ── Lambda execution role ──────────────────────────────────────────────
    lambda_role_arn = ensure_lambda_role(iam)

    # ── Package + Deploy CustomerDB Lambda ────────────────────────────────
    print("\n  ── CustomerDB Lambda ──")
    customer_db_zip = package_lambda(CUSTOMER_DB_HANDLER, "AuraBank-CustomerDB")
    customer_db_arn = deploy_lambda(
        lambda_client, "AuraBank-CustomerDB", customer_db_zip, db_env, lambda_role_arn)
    add_bedrock_permission(lambda_client, "AuraBank-CustomerDB", account_id)
    config["lambda_customer_db_arn"] = customer_db_arn

    # ── Package + Deploy Financial Lambda ─────────────────────────────────
    print("\n  ── Financial Lambda ──")
    financial_zip = package_lambda(FINANCIAL_HANDLER, "AuraBank-Financial")
    financial_arn  = deploy_lambda(
        lambda_client, "AuraBank-Financial", financial_zip, db_env, lambda_role_arn)
    add_bedrock_permission(lambda_client, "AuraBank-Financial", account_id)
    config["lambda_financial_arn"] = financial_arn

    # ── Read OpenAPI schemas ───────────────────────────────────────────────
    schema_dir = os.path.join(_ROOT, "src/bedrock_app/schemas")
    with open(os.path.join(schema_dir, "customer_db_action_group.json")) as f:
        customer_db_schema = f.read()
    with open(os.path.join(schema_dir, "financial_action_group.json")) as f:
        financial_schema = f.read()

    # ── Create Resolution Agent ────────────────────────────────────────────
    if config.get("resolution_agent_id"):
        print(f"\n  ♻️  Resolution Agent already exists: {config['resolution_agent_id']}")
    else:
        print("\n  ── Creating Resolution Agent ──")
        resp = bedrock_agent.create_agent(
            agentName="AuraBank-ResolutionAgent",
            description="Investigates and resolves Aura Bank customer issues using database lookup and financial action tools.",
            foundationModel=FOUNDATION_MODEL,
            agentResourceRoleArn=config["iam_role_arn"],
            instruction=RESOLUTION_INSTRUCTION,
            idleSessionTTLInSeconds=600,
        )
        agent_id = resp["agent"]["agentId"]
        print(f"  ✅ Resolution Agent created! agentId = {agent_id}")
        wait_for_agent_status(bedrock_agent, agent_id, ["NOT_PREPARED", "PREPARED"])
        config["resolution_agent_id"] = agent_id

    agent_id = config["resolution_agent_id"]

    # ── Attach Action Groups ───────────────────────────────────────────────
    print("\n  ── Attaching Action Groups ──")
    existing_groups = {
        ag["actionGroupName"]
        for ag in bedrock_agent.list_agent_action_groups(
            agentId=agent_id, agentVersion="DRAFT")["actionGroupSummaries"]
    }

    if "CustomerDBActionGroup" not in existing_groups:
        bedrock_agent.create_agent_action_group(
            agentId=agent_id, agentVersion="DRAFT",
            actionGroupName="CustomerDBActionGroup",
            description="Read-only access to Aura Bank customer profiles, balances, and transactions.",
            actionGroupExecutor={"lambda": customer_db_arn},
            apiSchema={"payload": customer_db_schema},
        )
        print("  ✅ CustomerDBActionGroup attached")
    else:
        print("  ♻️  CustomerDBActionGroup already attached")

    if "FinancialActionGroup" not in existing_groups:
        bedrock_agent.create_agent_action_group(
            agentId=agent_id, agentVersion="DRAFT",
            actionGroupName="FinancialActionGroup",
            description="State-mutating financial operations: refunds and card suspensions.",
            actionGroupExecutor={"lambda": financial_arn},
            apiSchema={"payload": financial_schema},
        )
        print("  ✅ FinancialActionGroup attached")
    else:
        print("  ♻️  FinancialActionGroup already attached")

    # ── Prepare + Alias ────────────────────────────────────────────────────
    if not config.get("resolution_alias_id"):
        alias_id = prepare_and_alias(bedrock_agent, agent_id, "PROD")
        config["resolution_alias_id"]    = alias_id
        config["resolution_agent_model"] = FOUNDATION_MODEL
    else:
        # Re-prepare to pick up action group changes
        print(f"\n  🔧 Re-preparing agent with action groups...")
        bedrock_agent.prepare_agent(agentId=agent_id)
        wait_for_agent_status(bedrock_agent, agent_id, ["PREPARED"])
        print(f"  ✅ Agent re-prepared")

    save_config(config)
    return config


# ── Main Entry Point ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Aura Bank Bedrock Agent Provisioning")
    parser.add_argument("--step", choices=["triage", "resolution", "all"],
                        default="triage", help="Which agent step to run")
    args = parser.parse_args()

    sts, iam, bedrock_agent = get_clients()
    global ACCOUNT_ID
    ACCOUNT_ID = sts.get_caller_identity()["Account"]
    print(f"🔑 AWS Account: {ACCOUNT_ID} | Region: {REGION}")

    config = load_config()

    # Lambda client (same region)
    lambda_client = boto3.client(
        "lambda",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
    )

    # ── Step 2.1: Triage Agent
    if args.step in ("triage", "all"):
        role_arn = ensure_iam_role(iam, ACCOUNT_ID)
        config["iam_role_arn"] = role_arn
        config = create_triage_agent(bedrock_agent, role_arn, config)

    # ── Step 2.2: Resolution Agent + Lambdas
    if args.step in ("resolution", "all"):
        config = create_resolution_agent(
            bedrock_agent, lambda_client, iam, config, ACCOUNT_ID)


if __name__ == "__main__":
    main()
