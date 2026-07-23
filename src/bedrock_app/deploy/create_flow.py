"""
Aura Bank — Bedrock Flow Creation (Step 2.3) — Fixed Version
=============================================================
Redesigned to conform to Bedrock Flows validation rules:

1. CriticalParserLambda  — tiny inline Lambda that parses the triage
   JSON and returns exactly "CRITICAL" or "NORMAL" so the condition
   node can do a simple string == comparison.

2. CriticalCheck condition node uses:
     "expression": 'criticalFlag == "CRITICAL"'
   for the CRITICAL branch and the sentinel name "default" (no
   expression field) for the fallback/NORMAL branch.

3. HITLReviewPrompt feeds the triage result to a prompt node that
   formats it for a human reviewer (AWAITING_HUMAN_APPROVAL).

4. ResolutionAgent runs on the NORMAL path.

Architecture:
  FlowInput (ticket text)
      ↓
  TriageAgent
      ↓
  CriticalParserLambda  → "CRITICAL" | "NORMAL"
      ↓
  CriticalCheck (condition)
      ↓ IsCritical                  ↓ default
  HITLReviewPrompt            ResolutionAgent
      ↓                             ↓
  CriticalOutput              ResolvedOutput
"""

import os, sys, json, time, base64, io, zipfile
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
load_dotenv(os.path.join(_ROOT, ".env"), override=True)
import boto3

REGION     = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
_CONFIG    = os.path.join(os.path.dirname(__file__), "bedrock_config.json")

with open(_CONFIG) as f:
    config = json.load(f)

sts          = boto3.client("sts", aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY)
ACCOUNT_ID   = sts.get_caller_identity()["Account"]
ROLE_ARN     = config["iam_role_arn"]
LAMBDA_ROLE  = config.get("lambda_execution_role_arn",
                          f"arn:aws:iam::{ACCOUNT_ID}:role/AuraBankLambdaExecutionRole")

TRIAGE_ARN      = f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{config['triage_agent_id']}/{config['triage_alias_id']}"
RESOLUTION_ARN  = f"arn:aws:bedrock:{REGION}:{ACCOUNT_ID}:agent-alias/{config['resolution_agent_id']}/{config['resolution_alias_id']}"

bedrock  = boto3.client("bedrock-agent",    aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name=REGION)
lmb      = boto3.client("lambda",           aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name=REGION)


# ── Step A: Deploy CriticalParser Lambda ──────────────────────────────────────
PARSER_CODE = '''
import json

def lambda_handler(event, context):
    """
    Bedrock Flows Lambda event format:
      Input:  {"inputs": [{"name": "functionInput", "type": "String", "value": "<triage text>"}]}
      Output: {"outputs": [{"name": "functionResponse", "type": "String", "value": "CRITICAL|NORMAL"}]}
    """
    # Extract value from Flows input format
    text = ""
    for inp in event.get("inputs", []):
        if inp.get("name") == "functionInput":
            text = inp.get("value", "")
            break

    result = "NORMAL"
    try:
        s = text.rfind("{")
        e = text.rfind("}") + 1
        if s != -1 and e > s:
            data = json.loads(text[s:e])
            if data.get("is_critical") is True:
                result = "CRITICAL"
    except Exception:
        pass

    return {
        "outputs": [
            {"name": "functionResponse", "type": "String", "value": result}
        ]
    }
'''

def _zip(code: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("lambda_function.py", code)
    return buf.getvalue()


def deploy_parser_lambda() -> str:
    name = "AuraBank-CriticalParser"
    try:
        resp = lmb.create_function(
            FunctionName=name, Runtime="python3.12",
            Role=LAMBDA_ROLE,
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": _zip(PARSER_CODE)},
            Timeout=10, MemorySize=128,
            Description="Parses Triage Agent output → CRITICAL | NORMAL",
        )
        arn = resp["FunctionArn"]
        print(f"  ✅ CriticalParser Lambda created: {arn}")
    except lmb.exceptions.ResourceConflictException:
        lmb.update_function_code(FunctionName=name, ZipFile=_zip(PARSER_CODE))
        arn = lmb.get_function_configuration(FunctionName=name)["FunctionArn"]
        print(f"  ♻️  CriticalParser Lambda updated: {arn}")

    # Grant Bedrock permission to invoke
    try:
        lmb.add_permission(
            FunctionName=name, StatementId="AllowBedrockFlow",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
            SourceAccount=ACCOUNT_ID,
        )
    except lmb.exceptions.ResourceConflictException:
        pass

    # Wait for Active
    for _ in range(12):
        if lmb.get_function_configuration(FunctionName=name)["State"] == "Active":
            break
        time.sleep(3)

    return arn


# ── Step B: Build Flow Definition ─────────────────────────────────────────────
def build_flow(parser_arn: str) -> dict:
    return {
        "nodes": [
            # ── FlowInput ─────────────────────────────────────────────────────
            {
                "name": "FlowInput",
                "type": "Input",
                "outputs": [{"name": "document", "type": "String"}],
            },

            # ── TriageAgent ───────────────────────────────────────────────────
            {
                "name": "TriageAgent",
                "type": "Agent",
                "configuration": {"agent": {"agentAliasArn": TRIAGE_ARN}},
                "inputs":  [{"name": "agentInputText",  "type": "String", "expression": "$.data"}],
                "outputs": [{"name": "agentResponse",   "type": "String"}],
            },

            # ── CriticalParserLambda ──────────────────────────────────────────
            {
                "name": "CriticalParser",
                "type": "LambdaFunction",
                "configuration": {"lambdaFunction": {"lambdaArn": parser_arn}},
                "inputs":  [{"name": "functionInput",    "type": "String", "expression": "$.data"}],
                "outputs": [{"name": "functionResponse", "type": "String"}],
            },

            # ── Condition: CRITICAL vs default ────────────────────────────────
            {
                "name": "CriticalCheck",
                "type": "Condition",
                "configuration": {
                    "condition": {
                        "conditions": [
                            {
                                "name": "IsCritical",
                                "expression": 'criticalFlag == "CRITICAL"'
                            },
                            {
                                "name": "default"
                                # no expression — Bedrock treats this as the else branch
                            }
                        ]
                    }
                },
                "inputs": [
                    {"name": "criticalFlag", "type": "String", "expression": "$.data"}
                ],
            },

            # ── HITLReviewPrompt (CRITICAL path) ──────────────────────────────
            {
                "name": "HITLReviewPrompt",
                "type": "Prompt",
                "configuration": {
                    "prompt": {
                        "sourceConfiguration": {
                            "inline": {
                                "modelId": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
                                "templateType": "TEXT",
                                "templateConfiguration": {
                                    "text": {
                                        "text": (
                                            "The following customer support ticket has been "
                                            "classified as CRITICAL by the Triage Agent.\n\n"
                                            "Triage result:\n{{triageResult}}\n\n"
                                            "Summarise the issue in 2-3 sentences for a human "
                                            "reviewer, state what action would be taken, and end "
                                            "your response with:\n"
                                            "STATUS: AWAITING_HUMAN_APPROVAL"
                                        ),
                                        "inputVariables": [{"name": "triageResult"}]
                                    }
                                }
                            }
                        }
                    }
                },
                "inputs": [
                    {"name": "triageResult", "type": "String", "expression": "$.data"}
                ],
                "outputs": [{"name": "modelCompletion", "type": "String"}],
            },

            # ── ResolutionAgent (NORMAL path) ─────────────────────────────────
            {
                "name": "ResolutionAgent",
                "type": "Agent",
                "configuration": {"agent": {"agentAliasArn": RESOLUTION_ARN}},
                "inputs":  [{"name": "agentInputText",  "type": "String", "expression": "$.data"}],
                "outputs": [{"name": "agentResponse",   "type": "String"}],
            },

            # ── Outputs ───────────────────────────────────────────────────────
            {
                "name": "CriticalOutput",
                "type": "Output",
                "inputs": [{"name": "document", "type": "String", "expression": "$.data"}],
            },
            {
                "name": "ResolvedOutput",
                "type": "Output",
                "inputs": [{"name": "document", "type": "String", "expression": "$.data"}],
            },
        ],

        "connections": [
            # FlowInput → TriageAgent
            {"name": "c1", "source": "FlowInput",    "target": "TriageAgent",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "document",      "targetInput": "agentInputText"}}},
            # TriageAgent → CriticalParser
            {"name": "c2", "source": "TriageAgent",  "target": "CriticalParser",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "agentResponse", "targetInput": "functionInput"}}},
            # CriticalParser → CriticalCheck
            {"name": "c3", "source": "CriticalParser", "target": "CriticalCheck",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "functionResponse",  "targetInput": "criticalFlag"}}},

            # CriticalCheck → HITLReviewPrompt (IsCritical branch)
            {"name": "c4", "source": "CriticalCheck", "target": "HITLReviewPrompt",
             "type": "Conditional",
             "configuration": {"conditional": {"condition": "IsCritical"}}},
            # TriageAgent → HITLReviewPrompt (data: pass triage response as review text)
            {"name": "c5", "source": "TriageAgent", "target": "HITLReviewPrompt",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "agentResponse", "targetInput": "triageResult"}}},

            # CriticalCheck → ResolutionAgent (default branch)
            {"name": "c6", "source": "CriticalCheck", "target": "ResolutionAgent",
             "type": "Conditional",
             "configuration": {"conditional": {"condition": "default"}}},
            # FlowInput → ResolutionAgent (original ticket)
            {"name": "c7", "source": "FlowInput", "target": "ResolutionAgent",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "document", "targetInput": "agentInputText"}}},

            # HITLReviewPrompt → CriticalOutput
            {"name": "c8", "source": "HITLReviewPrompt", "target": "CriticalOutput",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "modelCompletion", "targetInput": "document"}}},
            # ResolutionAgent → ResolvedOutput
            {"name": "c9", "source": "ResolutionAgent",  "target": "ResolvedOutput",
             "type": "Data",
             "configuration": {"data": {"sourceOutput": "agentResponse",  "targetInput": "document"}}},
        ]
    }


# ── Step C: Create / Prepare / Alias ─────────────────────────────────────────
def create_flow():
    print("=" * 60)
    print("STEP 2.3: Creating Bedrock Flow")
    print("=" * 60)

    # Check if already exists
    for f in bedrock.list_flows().get("flowSummaries", []):
        if f["name"] == "AuraBank-SupportFlow":
            print(f"♻️  Flow already exists: {f['id']}")
            config["flow_id"] = f["id"]
            with open(_CONFIG, "w") as fp:
                json.dump(config, fp, indent=2)
            return f["id"]

    # Deploy parser Lambda first
    print("\n  ── Deploying CriticalParser Lambda ──")
    parser_arn = deploy_parser_lambda()
    config["lambda_parser_arn"] = parser_arn

    # Create flow
    print("\n  ── Creating flow ──")
    resp = bedrock.create_flow(
        name="AuraBank-SupportFlow",
        description=(
            "Aura Bank 2-agent pipeline: Triage → HITL gate (critical tickets) → Resolution."
        ),
        executionRoleArn=ROLE_ARN,
        definition=build_flow(parser_arn),
    )
    flow_id = resp["id"]
    print(f"  ✅ Flow created: {flow_id}")

    # Wait for NotPrepared status
    for _ in range(12):
        status = bedrock.get_flow(flowIdentifier=flow_id)["status"]
        if status in ("NotPrepared", "Prepared"):
            break
        if status == "Failed":
            errs = bedrock.get_flow(flowIdentifier=flow_id).get("validations", [])
            for e in errs:
                print(f"  ❌ {e.get('message')}")
            raise RuntimeError("Flow creation failed validation.")
        print(f"  ⏳ Status: {status}")
        time.sleep(4)

    # Prepare
    print("  ── Preparing flow ──")
    bedrock.prepare_flow(flowIdentifier=flow_id)
    for _ in range(24):
        status = bedrock.get_flow(flowIdentifier=flow_id)["status"]
        print(f"  ⏳ Status: {status}")
        if status == "Prepared":
            break
        if status == "Failed":
            errs = bedrock.get_flow(flowIdentifier=flow_id).get("validations", [])
            for e in errs:
                print(f"  ❌ {e.get('message')}")
            raise RuntimeError("Flow preparation failed.")
        time.sleep(5)

    # Create version + alias
    print("  ── Creating version and alias ──")
    ver_resp = bedrock.create_flow_version(flowIdentifier=flow_id)
    flow_version = ver_resp["version"]
    print(f"  ✅ Flow version: {flow_version}")

    alias_resp = bedrock.create_flow_alias(
        flowIdentifier=flow_id,
        name="PROD",
        description="Production alias",
        routingConfiguration=[{"flowVersion": flow_version}],
    )
    flow_alias_id = alias_resp["id"]
    print(f"  ✅ Flow alias: {flow_alias_id}")

    # Save IDs
    config["flow_id"]       = flow_id
    config["flow_alias_id"] = flow_alias_id
    with open(_CONFIG, "w") as fp:
        json.dump(config, fp, indent=2)
    print(f"  📄 Config saved.")
    return flow_id


if __name__ == "__main__":
    flow_id = create_flow()
    print(f"\n✅ Done! View in AWS Console → Bedrock → Flows → AuraBank-SupportFlow")
