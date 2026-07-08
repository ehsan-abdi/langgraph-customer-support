import os
import asyncio
import csv
import zipfile
import time
from io import TextIOWrapper
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "historical_tickets")
os.makedirs(OUTPUT_DIR, exist_ok=True)
ZIP_FILE = os.path.join(DATA_DIR, "complaints.csv.zip")

PRODUCTS = [
    "Checking or savings account", 
    "Credit card", 
    "Money transfer, virtual currency, or money service", 
    "Bank account or service", 
    "Money transfers"
]

def load_complaints_from_zip(limit=500):
    if not os.path.exists(ZIP_FILE):
        print(f"Error: {ZIP_FILE} not found. Please ensure it is downloaded.")
        return []
        
    complaints = []
    print("Extracting and parsing CSV from ZIP archive...")
    with zipfile.ZipFile(ZIP_FILE, 'r') as zf:
        # Assuming the first file in the zip is the CSV
        csv_filename = zf.namelist()[0]
        with zf.open(csv_filename, 'r') as f:
            # Wrap the bytes object to decode as text
            reader = csv.DictReader(TextIOWrapper(f, encoding='utf-8'))
            
            for row in reader:
                narrative = row.get("Consumer complaint narrative", "").strip()
                product = row.get("Product", "")
                
                # Filter criteria: Must have narrative and match products
                if narrative and product in PRODUCTS:
                    complaints.append({
                        "complaint_id": row.get("Complaint ID"),
                        "date_received": row.get("Date received"),
                        "product": product,
                        "issue": row.get("Issue"),
                        "complaint_what_happened": narrative
                    })
                    
                    if len(complaints) >= limit * 2: # load a bit more in case some exist
                        break
                        
    return complaints

async def generate_resolution(client, complaint_text):
    prompt = f"""
    You are an expert customer service agent at Aura Bank. 
    A customer has submitted the following complaint.
    
    Customer Complaint:
    {complaint_text}
    
    Draft a professional, detailed, and empathetic resolution to this ticket as it would be resolved in a real retail bank. 
    Explain what went wrong, how Aura Bank has fixed it, and any next steps. 
    
    CRITICAL INSTRUCTION: Do NOT offer any financial compensation or a "gesture of goodwill" UNLESS the customer has been clearly damaged financially by a direct bank error OR the tone of the complaint is extremely angry. For normal complaints, standard delays, or simple misunderstandings, resolve the issue professionally without offering any free money or credits.
    
    Limit your response to 200-300 words.
    """
    
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful and professional customer service AI for Aura Bank."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return None

async def process_ticket(client, source, semaphore):
    complaint_id = source.get("complaint_id")
    if not complaint_id:
        return False
        
    filename = f"ticket_{complaint_id}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Checkpoint to avoid reprocessing
    if os.path.exists(filepath):
        return False
        
    narrative = source.get("complaint_what_happened", "")
    if not narrative:
        return False
        
    async with semaphore:
        resolution = await generate_resolution(client, narrative)
        if not resolution:
            return False
            
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Ticket ID: {complaint_id}\n")
            f.write(f"Date Received: {source.get('date_received', '')}\n")
            f.write(f"Product Category: {source.get('product', 'Unknown')}\n")
            f.write(f"Issue: {source.get('issue', 'Unknown')}\n")
            f.write("="*50 + "\n")
            f.write("CUSTOMER COMPLAINT:\n")
            f.write(f"{narrative}\n")
            f.write("="*50 + "\n")
            f.write("AURA Bank RESOLUTION:\n")
            f.write(f"{resolution}\n")
            
        return True

async def main():
    if not OPENAI_API_KEY:
        print("Missing OPENAI_API_KEY in .env")
        return
        
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    # Set to a high number to process all remaining valid tickets from the CSV
    TARGET_COUNT = 10000
    
    complaints = load_complaints_from_zip(limit=TARGET_COUNT + 1000)
    print(f"Parsed {len(complaints)} valid complaints from the CSV dump.")
    
    if not complaints:
        return
        
    print(f"Starting generation using OpenAI gpt-4o-mini for {TARGET_COUNT} new tickets...")
    
    processed_count = 0
    
    # Using a semaphore of 20 for extremely fast concurrent processing
    semaphore = asyncio.Semaphore(20)
    tasks = []
    
    start_time = time.time()
    
    for source in complaints:
        if processed_count >= TARGET_COUNT:
            break
            
        complaint_id = source.get("complaint_id")
        filepath = os.path.join(OUTPUT_DIR, f"ticket_{complaint_id}.txt")
        if os.path.exists(filepath):
            continue
            
        task = asyncio.create_task(process_ticket(client, source, semaphore))
        tasks.append(task)
        processed_count += 1
        
    if not tasks:
        print("No new tickets to process.")
        return
        
    print(f"Executing {len(tasks)} tasks concurrently...")
    results = await asyncio.gather(*tasks)
    
    successes = sum(results)
    elapsed = time.time() - start_time
    print(f"\nDone! Successfully processed and saved {successes} new tickets in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    asyncio.run(main())
