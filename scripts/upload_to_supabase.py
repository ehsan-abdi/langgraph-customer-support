import os
import csv
import psycopg2
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from dotenv import load_dotenv

load_dotenv(override=True)
DB_URL = os.environ.get("SUPABASE_DB_URL")
if not DB_URL:
    raise ValueError("SUPABASE_DB_URL missing in environment")
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SCHEMA_FILE = os.path.join(BASE_DIR, "db", "schema.sql")
CUSTOMERS_CSV = os.path.join(BASE_DIR, "data", "synthetic_db", "customers.csv")
ACCOUNTS_CSV = os.path.join(BASE_DIR, "data", "synthetic_db", "accounts.csv")

def setup_schema(conn):
    logging.info("Applying schema.sql to the database...")
    with open(SCHEMA_FILE, 'r') as f:
        schema_sql = f.read()
    
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    logging.info("Schema applied successfully.")

def upload_csv(conn, table_name, csv_filepath):
    logging.info(f"Uploading {csv_filepath} to table '{table_name}'...")
    
    with open(csv_filepath, 'r', encoding='utf-8') as f:
        # We use PostgreSQL's COPY_EXPERT for blazing fast bulk inserts
        with conn.cursor() as cur:
            copy_sql = f"COPY {table_name} FROM STDIN WITH CSV HEADER"
            cur.copy_expert(sql=copy_sql, file=f)
    conn.commit()
    logging.info(f"Successfully uploaded data to '{table_name}'.")

def main():
    logging.info("Connecting to Supabase...")
    try:
        conn = psycopg2.connect(DB_URL)
        logging.info("Connected!")
        
        setup_schema(conn)
        
        upload_csv(conn, "customers", CUSTOMERS_CSV)
        upload_csv(conn, "accounts", ACCOUNTS_CSV)
        
        TRANSACTIONS_CSV = os.path.join(BASE_DIR, "data", "synthetic_db", "transactions.csv")
        if os.path.exists(TRANSACTIONS_CSV):
            upload_csv(conn, "transactions", TRANSACTIONS_CSV)
        
        logging.info("All data uploaded successfully!")
        
    except Exception as e:
        logging.error(f"Failed to upload data: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    main()
