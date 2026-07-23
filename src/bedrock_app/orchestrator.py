"""
Aura Bank Multi-Agent Orchestrator
====================================
Orchestrates the full 2-agent customer support pipeline:

  [Ticket]
     ↓
  [Triage Agent]  — classifies ticket, sets priority + is_critical
     ↓
  [HITL Gate]     — for URGENT/HIGH tickets, pauses for human approval
     ↓ (if approved, or not critical)
  [Resolution Agent] — verifies identity, fetches data, executes action
     ↓
  [Result]

The HITL gate is pluggable:
  - ConsoleHITL (default): prompts a human operator in the terminal
  - AutoApproveHITL:       always approves (for integration tests)
  - RejectHITL:            always rejects (for negative tests)
"""

import os
import sys
import json
import uuid
import time
from typing import Callable, Optional
from dotenv import load_dotenv

# ── Path Setup ─────────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
load_dotenv(os.path.join(_ROOT, ".env"), override=True)

import boto3

# ── Config ─────────────────────────────────────────────────────────────────────
_CONFIG_PATH = os.path.join(_ROOT, "src/bedrock_app/deploy/bedrock_config.json")

def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)

def _make_runtime():
    config = _load_config()
    return boto3.client(
        "bedrock-agent-runtime",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "eu-north-1"),
    ), config


# ── HITL Gate Implementations ──────────────────────────────────────────────────

def console_hitl(triage: dict, ticket: str) -> bool:
    """
    Displays triage details to a human operator and waits for their
    approval or rejection via the terminal. Used for demos and testing.
    """
    print("\n" + "╔" + "═"*58 + "╗")
    print("║  ⚠️   HUMAN REVIEW REQUIRED — CRITICAL TICKET           ║")
    print("╚" + "═"*58 + "╝")
    print(f"  Priority   : {triage.get('priority', 'Unknown')}")
    print(f"  Department : {triage.get('department', 'Unknown')}")
    print(f"  Summary    : {triage.get('summary', 'N/A')}")
    print(f"  Reasoning  : {triage.get('reasoning', 'N/A')}")
    print()
    print("  Ticket text:")
    print(f"  {ticket[:200]}{'...' if len(ticket) > 200 else ''}")
    print()

    while True:
        answer = input("  ► Approve resolution? [yes / no]: ").strip().lower()
        if answer in ("yes", "y"):
            print("  ✅ Approved — proceeding to Resolution Agent.\n")
            return True
        elif answer in ("no", "n"):
            print("  ❌ Rejected — ticket escalated to senior team.\n")
            return False
        else:
            print("  Please enter 'yes' or 'no'.")


def auto_approve_hitl(triage: dict, ticket: str) -> bool:
    """Always approves — for integration tests only."""
    print(f"  [AutoApprove] Critical ticket auto-approved for testing.")
    return True


def auto_reject_hitl(triage: dict, ticket: str) -> bool:
    """Always rejects — for negative test cases."""
    print(f"  [AutoReject] Critical ticket auto-rejected for testing.")
    return False


# ── Agent Invocation Helpers ───────────────────────────────────────────────────

def _invoke_agent(runtime, agent_id: str, alias_id: str, text: str) -> str:
    """Invokes a Bedrock Agent and returns the full text response."""
    resp = runtime.invoke_agent(
        agentId=agent_id,
        agentAliasId=alias_id,
        sessionId=str(uuid.uuid4()),
        inputText=text,
    )
    return "".join(
        event["chunk"]["bytes"].decode("utf-8")
        for event in resp["completion"]
        if "chunk" in event
    )


def _parse_json_from_response(text: str) -> Optional[dict]:
    """
    Extracts and parses the last JSON object from an agent response.
    Handles plain JSON and markdown code-block fenced JSON (```json ... ```).
    """
    import re
    # Strip markdown fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    # Find the outermost { ... } block
    s = cleaned.rfind("{")
    e = cleaned.rfind("}") + 1
    if s == -1 or e <= s:
        return None
    try:
        return json.loads(cleaned[s:e])
    except json.JSONDecodeError:
        return None


# ── Main Orchestrator ──────────────────────────────────────────────────────────

def process_ticket(
    ticket_text: str,
    hitl_gate: Callable = console_hitl,
    verbose: bool = True,
) -> dict:
    """
    Full pipeline: Triage → HITL (if critical) → Resolution.

    Args:
        ticket_text:  The raw customer support ticket.
        hitl_gate:    Callable(triage_dict, ticket_text) → bool.
                      Called for critical tickets to obtain human approval.
                      Defaults to console_hitl (terminal prompt).
        verbose:      Print step-by-step progress.

    Returns:
        dict with keys: status, triage, resolution (if resolved), reason (if rejected).
    """
    runtime, config = _make_runtime()

    # ── Step 1: Triage ────────────────────────────────────────────────────────
    if verbose:
        print("\n🔍 STEP 1 — Triage Agent classifying ticket...")

    # Wrap in classifier context so the model knows it is processing a ticket,
    # NOT conversing directly with the customer.
    triage_prompt = (
        "[TICKET RECEIVED FOR CLASSIFICATION — DO NOT RESPOND TO CUSTOMER]"
        f"\n\n{ticket_text}"
    )
    triage_raw = _invoke_agent(
        runtime,
        config["triage_agent_id"],
        config["triage_alias_id"],
        triage_prompt,
    )

    triage = _parse_json_from_response(triage_raw)
    if not triage:
        if verbose:
            print(f"  ⚠️  Raw triage output (repr): {repr(triage_raw[:400])}")
        return {"status": "error", "reason": "Triage Agent returned non-JSON output.", "raw": triage_raw}

    if verbose:
        print(f"  Priority   : {triage.get('priority')}")
        print(f"  Department : {triage.get('department')}")
        print(f"  is_critical: {triage.get('is_critical')}")
        print(f"  Summary    : {triage.get('summary')}")

    # ── Step 2: HITL Gate ────────────────────────────────────────────────────
    if triage.get("is_critical"):
        if verbose:
            print("\n⚠️  STEP 2 — Critical ticket: invoking HITL gate...")

        approved = hitl_gate(triage, ticket_text)

        if not approved:
            return {
                "status": "rejected",
                "reason": "Human reviewer rejected the action.",
                "triage": triage,
            }
    else:
        if verbose:
            print(f"\n✅ STEP 2 — Non-critical ({triage.get('priority')}) — HITL skipped, auto-resolving.")

    # ── Step 3: Resolution ───────────────────────────────────────────────────
    if verbose:
        print("\n🔧 STEP 3 — Resolution Agent investigating and resolving...")

    resolution_raw = _invoke_agent(
        runtime,
        config["resolution_agent_id"],
        config["resolution_alias_id"],
        ticket_text,
    )

    resolution = _parse_json_from_response(resolution_raw)

    if verbose:
        print()
        print("📋 Resolution Agent response:")
        print("-" * 50)
        print(resolution_raw)
        print("-" * 50)

    return {
        "status": "resolved",
        "triage": triage,
        "resolution": resolution,
        "resolution_raw": resolution_raw,
    }


# ── CLI Entry Point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Aura Bank Support Orchestrator")
    parser.add_argument("--ticket", type=str, help="Ticket text to process")
    parser.add_argument("--auto-approve", action="store_true",
                        help="Auto-approve HITL (for testing)")
    parser.add_argument("--auto-reject", action="store_true",
                        help="Auto-reject HITL (for testing)")
    args = parser.parse_args()

    ticket = args.ticket or input("Enter ticket text: ")
    hitl = (auto_approve_hitl if args.auto_approve
            else auto_reject_hitl if args.auto_reject
            else console_hitl)

    result = process_ticket(ticket, hitl_gate=hitl, verbose=True)

    print("\n" + "="*60)
    print("FINAL RESULT")
    print("="*60)
    print(json.dumps({k: v for k, v in result.items() if k != "resolution_raw"},
                     indent=2, default=str))
