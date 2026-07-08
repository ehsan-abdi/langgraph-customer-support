import os
import psycopg2
import uuid
from datetime import datetime
from psycopg2.extras import RealDictCursor
from langchain_core.tools import tool
from dotenv import load_dotenv

# Ensure environment variables are loaded (overriding stale shell variables)
load_dotenv(override=True)

def _get_db_connection():
    """Helper method to securely connect to the remote Supabase Postgres instance."""
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL missing in environment")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

@tool
def get_customer_profile(full_name: str, account_number: str, sort_code: str) -> dict:
    """
    Looks up a customer profile using their full name, account number, and sort code.
    Returns their unique customer ID and profile if matched, or throws a strict warning if they do not match.
    """
    try:
        import re
        # Clean account number to guarantee matching regardless of LLM formatting
        clean_account_number = re.sub(r'\D', '', str(account_number))
        
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT c.*, a.* FROM customers c JOIN accounts a ON c.id = a.customer_id "
                    "WHERE a.account_number = %s", (clean_account_number,)
                )
                result = cur.fetchone()
                
                if not result:
                    return {"error": f"Account number {clean_account_number} not found in our systems."}
                
                # Strict Name Checking Warning
                db_name = f"{result['first_name']} {result['last_name']}".lower().strip()
                input_name = str(full_name).lower().strip()
                db_sort = str(result['sort_code']).strip()
                input_sort = str(sort_code).strip()
                
                if db_name != input_name or db_sort != input_sort:
                    return {"error": f"IDENTITY MISMATCH WARNING: The account number provided belongs to '{result['first_name']} {result['last_name']}' with sort code '{result['sort_code']}', which does not match the provided details. Do not proceed with sensitive actions."}
                
                # Convert date/datetime objects to strings so they are cleanly JSON serializable for the LLM
                if result.get('created_at'):
                    result['created_at'] = result['created_at'].isoformat()
                if result.get('dob'):
                    result['dob'] = str(result['dob'])
                    
                return dict(result)
    except Exception as e:
        return {"error": f"Database Connection Error: {str(e)}"}

@tool
def get_account_balances(customer_id: str) -> list:
    """
    Fetches all bank accounts (Current, Savings, Credit Cards, Mortgages) 
    and their current balances for a given Aura Bank customer ID.
    Always pass the customer_id fetched from get_customer_profile.
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                # We do not SELECT * to prevent leaking the customer_id back redundantly
                cur.execute(
                    "SELECT id, account_type, balance, status, sort_code, account_number "
                    "FROM accounts WHERE customer_id = %s", 
                    (customer_id,)
                )
                results = cur.fetchall()
                
                if not results:
                    return []
                
                # Serialize any dates if we ever add them
                for r in results:
                    if r.get('created_at'):
                        r['created_at'] = r['created_at'].isoformat()
                        
                return [dict(r) for r in results]
    except Exception as e:
        return [{"error": f"Database Connection Error: {str(e)}"}]

@tool
def suspend_account_or_card(account_id: str) -> dict:
    """
    Suspends an Aura Bank account or credit card.
    Use this when a customer reports a lost/stolen card or active fraud.
    Requires the specific account_id (uuid) from get_account_balances.
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE accounts SET status = 'Suspended' WHERE id = %s RETURNING id, account_type, status", (account_id,))
                result = cur.fetchone()
                conn.commit()
                if not result:
                    return {"error": "Account not found."}
                return {"success": f"{result['account_type']} successfully suspended.", "data": dict(result)}
    except Exception as e:
        return {"error": f"Database Error: {str(e)}"}

@tool
def issue_refund(account_id: str, amount: float) -> dict:
    """
    Issues a refund or goodwill gesture to an Aura Bank account.
    Requires the specific account_id and the positive refund amount (e.g. 50.0).
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s RETURNING id, balance", (amount, account_id))
                result = cur.fetchone()
                if not result:
                    return {"error": "Account not found."}
                
                cur.execute(
                    "INSERT INTO transactions (id, account_id, amount, merchant, category, transaction_date) VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(uuid.uuid4()), account_id, amount, "Aura Bank Refund", "Refund", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'))
                )
                conn.commit()
                return {"success": f"£{amount} refunded successfully and transaction logged.", "new_balance": result['balance']}
    except Exception as e:
        return {"error": f"Database Error: {str(e)}"}

@tool
def get_recent_transactions(account_id: str, limit: int = 10) -> list:
    """
    Fetches the most recent transactions for a specific Aura Bank account ID.
    Use this to verify if a customer was charged a specific amount by a specific merchant.
    Requires the account_id from get_account_balances.
    """
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, amount, merchant, category, transaction_date "
                    "FROM transactions WHERE account_id = %s ORDER BY transaction_date DESC LIMIT %s",
                    (account_id, limit)
                )
                results = cur.fetchall()
                if not results:
                    return []
                for r in results:
                    if r.get('transaction_date'):
                        r['transaction_date'] = r['transaction_date'].isoformat()
                return [dict(r) for r in results]
    except Exception as e:
        return [{"error": f"Database Error: {str(e)}"}]
