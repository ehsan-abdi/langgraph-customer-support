"""
Lambda Handler: Financial Action Group
=======================================
Handles all state-mutating financial operations on behalf of the Bedrock Resolution Agent.
Responds to two API paths defined in financial_action_group.json:
  - POST /issue_refund
  - POST /suspend_account_or_card

These operations are IRREVERSIBLE. In production this Lambda should only be invoked
after a Human-in-the-Loop approval has been confirmed by the Bedrock Flow.

Amazon Bedrock sends a structured event to this Lambda. This handler:
  1. Parses the Bedrock Action Group event format
  2. Extracts parameters from the requestBody
  3. Calls the corresponding shared database function in src/tools/db_tools.py
  4. Returns the result in Bedrock's expected response envelope format
"""

import os
import sys
import json
from decimal import Decimal
from dotenv import load_dotenv

# ── Path Setup ──────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, _ROOT)
load_dotenv(os.path.join(_ROOT, ".env"), override=True)

# ── Import shared tool functions (via .func to call the raw Python function) ─
from src.tools.db_tools import issue_refund, suspend_account_or_card


def _parse_properties(event: dict) -> dict:
    """
    Converts Bedrock's list-of-dicts parameter format into a flat dict.
    Input:  [{"name": "account_id", "type": "string", "value": "abc-123"}, ...]
    Output: {"account_id": "abc-123"}
    """
    try:
        props = (
            event["requestBody"]["content"]["application/json"]["properties"]
        )
        return {p["name"]: p["value"] for p in props}
    except (KeyError, TypeError):
        return {}


def _decimal_safe(obj):
    """Custom JSON serializer for Decimal types returned by psycopg2/Supabase."""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _build_response(event: dict, http_status: int, body: any) -> dict:
    """Wraps a result in the Bedrock Action Group response envelope."""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", "FinancialActionGroup"),
            "apiPath":     event.get("apiPath", "/unknown"),
            "httpMethod":  event.get("httpMethod", "POST"),
            "httpStatusCode": http_status,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body, default=_decimal_safe)
                }
            }
        }
    }


def lambda_handler(event: dict, context=None) -> dict:
    """
    Main Lambda entry point.
    Routes the Bedrock event to the appropriate financial function based on apiPath.
    """
    api_path = event.get("apiPath", "")
    params   = _parse_properties(event)

    print(f"[Financial Lambda] apiPath={api_path} | params={params}")

    try:
        # ── Route: /issue_refund ─────────────────────────────────────────
        if api_path == "/issue_refund":
            account_id = params.get("account_id", "")
            amount_raw = params.get("amount", "0")
            try:
                amount = float(amount_raw)
            except (ValueError, TypeError):
                return _build_response(event, 400, {"error": f"Invalid amount: '{amount_raw}'"})

            if amount <= 0:
                return _build_response(event, 400, {"error": "Refund amount must be greater than zero."})

            result = issue_refund.func(account_id=account_id, amount=amount)
            return _build_response(event, 200, result)

        # ── Route: /suspend_account_or_card ──────────────────────────────
        elif api_path == "/suspend_account_or_card":
            account_id = params.get("account_id", "")
            result = suspend_account_or_card.func(account_id=account_id)
            return _build_response(event, 200, result)

        # ── Unknown path ─────────────────────────────────────────────────
        else:
            return _build_response(event, 404, {"error": f"Unknown apiPath: '{api_path}'"})

    except Exception as exc:
        print(f"[Financial Lambda] ERROR: {exc}")
        return _build_response(event, 500, {"error": str(exc)})
