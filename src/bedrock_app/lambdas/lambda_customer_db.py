"""
Lambda Handler: Customer DB Action Group
========================================
Handles all read-only customer database lookups on behalf of the Bedrock Resolution Agent.
Responds to three API paths defined in customer_db_action_group.json:
  - POST /get_customer_profile
  - POST /get_account_balances
  - POST /get_recent_transactions

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
# Ensures src/ is on the path whether running locally or packaged in Lambda.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, _ROOT)
load_dotenv(os.path.join(_ROOT, ".env"), override=True)

# ── Import shared tool functions (via .func to call the raw Python function) ─
from src.tools.db_tools import (
    get_customer_profile,
    get_account_balances,
    get_recent_transactions,
)


def _parse_properties(event: dict) -> dict:
    """
    Extracts the request parameters from a Bedrock Action Group Lambda event.

    Bedrock passes parameters as a list of dicts:
        [{"name": "account_id", "type": "string", "value": "abc-123"}, ...]

    This helper converts that list into a flat dict:
        {"account_id": "abc-123"}
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
    """
    Wraps a result in the Bedrock Action Group response envelope.
    The 'body' field must be a JSON string, not a dict.
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", "CustomerDBActionGroup"),
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
    Routes the Bedrock event to the appropriate database function based on apiPath.
    """
    api_path = event.get("apiPath", "")
    params   = _parse_properties(event)

    print(f"[CustomerDB Lambda] apiPath={api_path} | params={params}")

    try:
        # ── Route: /get_customer_profile ─────────────────────────────────
        if api_path == "/get_customer_profile":
            result = get_customer_profile.func(
                full_name      = params.get("full_name", ""),
                account_number = params.get("account_number", ""),
                sort_code      = params.get("sort_code", ""),
            )
            return _build_response(event, 200, result)

        # ── Route: /get_account_balances ─────────────────────────────────
        elif api_path == "/get_account_balances":
            result = get_account_balances.func(
                customer_id = params.get("customer_id", "")
            )
            return _build_response(event, 200, result)

        # ── Route: /get_recent_transactions ──────────────────────────────
        elif api_path == "/get_recent_transactions":
            limit  = int(params.get("limit", 10))
            result = get_recent_transactions.func(
                account_id = params.get("account_id", ""),
                limit      = limit,
            )
            return _build_response(event, 200, result)

        # ── Unknown path ─────────────────────────────────────────────────
        else:
            return _build_response(event, 404, {"error": f"Unknown apiPath: '{api_path}'"})

    except Exception as exc:
        print(f"[CustomerDB Lambda] ERROR: {exc}")
        return _build_response(event, 500, {"error": str(exc)})
