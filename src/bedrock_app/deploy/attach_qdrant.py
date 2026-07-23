"""
Step 2.4: Attach Qdrant Search Action Group to Resolution Agent
==============================================================
This script:
  1. Creates / updates the AuraBank-QdrantSearch Lambda function
  2. Attaches QdrantSearchActionGroup to the existing Resolution Agent
  3. Re-prepares the agent and updates its alias to a new version

Run:
  python3 src/bedrock_app/deploy/attach_qdrant.py
"""

import os
import io
import json
import time
import zipfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

import boto3

# ── Config ────────────────────────────────────────────────────────────────────
REGION         = "eu-north-1"
ACCESS_KEY     = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY     = os.getenv("AWS_SECRET_ACCESS_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL     = os.getenv("QDRANT_HISTORY_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_HISTORY_API_KEY", "")

LAMBDA_NAME    = "AuraBank-QdrantSearch"
ACTION_GROUP   = "QdrantSearchActionGroup"
SCHEMA_PATH    = Path(__file__).parent.parent / "schemas" / "qdrant_action_group.json"
HANDLER_PATH   = Path(__file__).parent.parent / "lambdas" / "lambda_qdrant.py"

_boto = dict(aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name=REGION)

lmb    = boto3.client("lambda",       **_boto)
bedrock = boto3.client("bedrock-agent", **_boto)

with open(Path(__file__).parent / "bedrock_config.json") as f:
    config = json.load(f)

RESOLUTION_AGENT_ID = config["resolution_agent_id"]
LAMBDA_ROLE_ARN = "arn:aws:iam::937934926023:role/AuraBankLambdaExecutionRole"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _zip(source_path: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(source_path, source_path.name)
    return buf.getvalue()


def _wait_lambda_active(name: str, timeout: int = 60):
    for _ in range(timeout // 3):
        state = lmb.get_function(FunctionName=name)["Configuration"]["State"]
        if state == "Active":
            return
        time.sleep(3)
    raise TimeoutError(f"Lambda {name} did not become Active within {timeout}s")


def _wait_agent_prepared(agent_id: str, timeout: int = 120):
    for _ in range(timeout // 5):
        status = bedrock.get_agent(agentId=agent_id)["agent"]["agentStatus"]
        print(f"  Agent status: {status}")
        if status == "PREPARED":
            return
        if status == "FAILED":
            raise RuntimeError(f"Agent {agent_id} entered FAILED state")
        time.sleep(5)
    raise TimeoutError(f"Agent did not reach PREPARED within {timeout}s")


# ── Step 1: Deploy Lambda ─────────────────────────────────────────────────────

def deploy_qdrant_lambda() -> str:
    """Creates or updates the AuraBank-QdrantSearch Lambda. Returns its ARN."""
    print("\n  ── Deploying AuraBank-QdrantSearch Lambda ──")
    code_zip = _zip(HANDLER_PATH)

    env_vars = {
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "QDRANT_URL":     QDRANT_URL,
        "QDRANT_API_KEY": QDRANT_API_KEY,
    }

    try:
        resp = lmb.create_function(
            FunctionName=LAMBDA_NAME,
            Runtime="python3.12",
            Role=LAMBDA_ROLE_ARN,
            Handler="lambda_qdrant.lambda_handler",
            Code={"ZipFile": code_zip},
            Timeout=60,
            MemorySize=256,
            Environment={"Variables": env_vars},
        )
        arn = resp["FunctionArn"]
        print(f"  ✅ Lambda created: {arn}")
    except lmb.exceptions.ResourceConflictException:
        # Update existing
        lmb.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=code_zip)
        time.sleep(3)
        lmb.update_function_configuration(
            FunctionName=LAMBDA_NAME,
            Timeout=60,
            MemorySize=256,
            Environment={"Variables": env_vars},
        )
        arn = lmb.get_function(FunctionName=LAMBDA_NAME)["Configuration"]["FunctionArn"]
        print(f"  ♻️  Lambda updated: {arn}")

    _wait_lambda_active(LAMBDA_NAME)

    # Grant Bedrock permission to invoke this Lambda
    try:
        lmb.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId="AllowBedrockInvoke",
            Action="lambda:InvokeFunction",
            Principal="bedrock.amazonaws.com",
        )
        print("  ✅ Bedrock invoke permission granted")
    except lmb.exceptions.ResourceConflictException:
        print("  ♻️  Bedrock invoke permission already exists")

    return arn


# ── Step 2: Attach Action Group ───────────────────────────────────────────────

def attach_qdrant_action_group(lambda_arn: str):
    """Attaches QdrantSearchActionGroup to the Resolution Agent."""
    print(f"\n  ── Attaching {ACTION_GROUP} to Resolution Agent ──")

    with open(SCHEMA_PATH) as f:
        schema_json = f.read()

    # Check if action group already exists
    existing = bedrock.list_agent_action_groups(
        agentId=RESOLUTION_AGENT_ID, agentVersion="DRAFT"
    )["actionGroupSummaries"]
    existing_names = {ag["actionGroupName"]: ag["actionGroupId"] for ag in existing}

    if ACTION_GROUP in existing_names:
        ag_id = existing_names[ACTION_GROUP]
        bedrock.update_agent_action_group(
            agentId=RESOLUTION_AGENT_ID,
            agentVersion="DRAFT",
            actionGroupId=ag_id,
            actionGroupName=ACTION_GROUP,
            actionGroupExecutor={"lambda": lambda_arn},
            apiSchema={"payload": schema_json},
            actionGroupState="ENABLED",
        )
        print(f"  ♻️  Action group updated: {ag_id}")
    else:
        resp = bedrock.create_agent_action_group(
            agentId=RESOLUTION_AGENT_ID,
            agentVersion="DRAFT",
            actionGroupName=ACTION_GROUP,
            actionGroupExecutor={"lambda": lambda_arn},
            apiSchema={"payload": schema_json},
            actionGroupState="ENABLED",
        )
        ag_id = resp["agentActionGroup"]["actionGroupId"]
        print(f"  ✅ Action group created: {ag_id}")


# ── Step 3: Re-prepare and re-alias ──────────────────────────────────────────

def reprepare_and_alias():
    """Prepares the agent and creates a new version alias."""
    print(f"\n  ── Re-preparing Resolution Agent {RESOLUTION_AGENT_ID} ──")
    bedrock.prepare_agent(agentId=RESOLUTION_AGENT_ID)
    _wait_agent_prepared(RESOLUTION_AGENT_ID)
    print("  ✅ Agent prepared")

    # Create new version
    ver_resp = bedrock.create_agent_version(agentId=RESOLUTION_AGENT_ID)
    version  = ver_resp["agentVersion"]["agentVersion"]
    print(f"  ✅ New agent version: {version}")

    # Update the existing alias to point to the new version
    alias_id = config["resolution_alias_id"]
    bedrock.update_agent_alias(
        agentId=RESOLUTION_AGENT_ID,
        agentAliasId=alias_id,
        agentAliasName="production",
        routingConfiguration=[{"agentVersion": version}],
    )
    print(f"  ✅ Alias {alias_id} updated to version {version}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("STEP 2.4: Attaching Qdrant Search to Resolution Agent")
    print("=" * 60)

    lambda_arn = deploy_qdrant_lambda()
    attach_qdrant_action_group(lambda_arn)
    reprepare_and_alias()

    print("\n✅ Done! Resolution Agent now has 3 action groups:")
    for ag in bedrock.list_agent_action_groups(
        agentId=RESOLUTION_AGENT_ID, agentVersion="DRAFT"
    )["actionGroupSummaries"]:
        print(f"   - {ag['actionGroupName']} ({ag['actionGroupState']})")
