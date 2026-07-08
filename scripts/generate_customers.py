import os
import csv
import uuid
import random
from datetime import datetime, timedelta
from faker import Faker

# Set up Faker for UK locale
fake = Faker('en_GB')

# Configuration
NUM_CUSTOMERS = 1000
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "synthetic_db")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Generate stable Barclays-like sort codes
SORT_CODES = ['20-00-00', '20-11-88', '20-20-20', '20-45-14', '20-33-51', '20-77-99']

def generate_customers():
    customers = []
    for _ in range(NUM_CUSTOMERS):
        tier_roll = random.random()
        if tier_roll > 0.90:
            tier = 'Wealth'
        elif tier_roll > 0.70:
            tier = 'Premier'
        else:
            tier = 'Standard'

        customers.append({
            'first_name': fake.first_name(),
            'last_name': fake.last_name()
        })
        customers[-1]['email'] = f"{customers[-1]['first_name'].lower()}.{customers[-1]['last_name'].lower()}{random.randint(1,99)}@example.com"
        
        customers[-1].update({
            'id': str(uuid.uuid4()),
            'phone': fake.phone_number(),
            'address': fake.street_address() + ", " + fake.city(),
            'postcode': fake.postcode(),
            'dob': fake.date_of_birth(minimum_age=18, maximum_age=90).strftime('%Y-%m-%d'),
            'account_tier': tier,
            'created_at': fake.date_time_between(start_date='-5y', end_date='now').strftime('%Y-%m-%d %H:%M:%S')
        })
    return customers

def generate_accounts(customers):
    accounts = []
    
    for customer in customers:
        # Every customer has a current account
        accounts.append({
            'id': str(uuid.uuid4()),
            'customer_id': customer['id'],
            'account_type': 'Current',
            'balance': round(random.uniform(50.0, 15000.0), 2),
            'sort_code': random.choice(SORT_CODES),
            'account_number': str(fake.random_number(digits=8, fix_len=True)),
            'status': 'Active',
            'created_at': customer['created_at']
        })
        
        # 70% have savings
        if random.random() > 0.3:
            accounts.append({
                'id': str(uuid.uuid4()),
                'customer_id': customer['id'],
                'account_type': 'Savings',
                'balance': round(random.uniform(100.0, 50000.0), 2),
                'sort_code': random.choice(SORT_CODES),
                'account_number': str(fake.random_number(digits=8, fix_len=True)),
                'status': 'Active',
                'created_at': fake.date_time_between(start_date='-3y', end_date='now').strftime('%Y-%m-%d %H:%M:%S')
            })
            
        # 40% have credit card
        if random.random() > 0.6:
            accounts.append({
                'id': str(uuid.uuid4()),
                'customer_id': customer['id'],
                'account_type': 'Credit Card',
                'balance': round(random.uniform(-5000.0, 0.0), 2), # Negative balance for credit card
                'sort_code': random.choice(SORT_CODES),
                'account_number': str(fake.random_number(digits=8, fix_len=True)),
                'status': 'Active',
                'created_at': fake.date_time_between(start_date='-2y', end_date='now').strftime('%Y-%m-%d %H:%M:%S')
            })
            
        # 15% have a mortgage
        if random.random() > 0.85:
            accounts.append({
                'id': str(uuid.uuid4()),
                'customer_id': customer['id'],
                'account_type': 'Mortgage',
                'balance': round(random.uniform(-500000.0, -50000.0), 2),
                'sort_code': random.choice(SORT_CODES),
                'account_number': str(fake.random_number(digits=8, fix_len=True)),
                'status': 'Active',
                'created_at': fake.date_time_between(start_date='-10y', end_date='now').strftime('%Y-%m-%d %H:%M:%S')
            })
            
    return accounts

def generate_transactions(accounts):
    transactions = []
    for account in accounts:
        for _ in range(10):
            amount = round(random.uniform(-500.0, 500.0), 2)
            if account['account_type'] == 'Credit Card':
                amount = round(random.uniform(-500.0, -10.0), 2)
            transactions.append({
                'id': str(uuid.uuid4()),
                'account_id': account['id'],
                'amount': amount,
                'merchant': fake.company(),
                'status': 'Completed',
                'created_at': fake.date_time_between(start_date='-1y', end_date='now').strftime('%Y-%m-%d %H:%M:%S')
            })
    return transactions

def export_to_csv(data, filename, fieldnames):
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"Exported {len(data)} records to {filepath}")

if __name__ == "__main__":
    print(f"Generating {NUM_CUSTOMERS} synthetic UK customers...")
    customers = generate_customers()
    accounts = generate_accounts(customers)
    
    export_to_csv(
        customers, 
        "customers.csv", 
        ['id', 'first_name', 'last_name', 'email', 'phone', 'address', 'postcode', 'dob', 'account_tier', 'created_at']
    )
    
    export_to_csv(
        accounts, 
        "accounts.csv", 
        ['id', 'customer_id', 'account_type', 'balance', 'sort_code', 'account_number', 'status', 'created_at']
    )
    
    transactions = generate_transactions(accounts)
    export_to_csv(
        transactions, 
        "transactions.csv", 
        ['id', 'account_id', 'amount', 'merchant', 'status', 'created_at']
    )
    
    print("Synthetic database generation complete!")
