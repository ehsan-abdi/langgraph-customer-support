-- Drop tables if they exist to allow clean re-runs
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS customers;

-- Customers Table
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    address TEXT,
    postcode VARCHAR(20),
    dob DATE,
    account_tier VARCHAR(50) CHECK (account_tier IN ('Standard', 'Premier', 'Wealth')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Accounts Table
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    account_type VARCHAR(50) CHECK (account_type IN ('Current', 'Savings', 'Mortgage', 'Credit Card', 'Loan')),
    balance DECIMAL(15, 2) DEFAULT 0.00,
    sort_code VARCHAR(8) NOT NULL, -- Format: XX-XX-XX
    account_number VARCHAR(8) NOT NULL,
    status VARCHAR(50) DEFAULT 'Active' CHECK (status IN ('Active', 'Suspended', 'Closed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Transactions Table
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    amount DECIMAL(15, 2) NOT NULL, -- Negative for debit, positive for credit
    merchant VARCHAR(255),
    category VARCHAR(100),
    transaction_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_accounts_customer_id ON accounts(customer_id);
CREATE INDEX idx_accounts_sort_account ON accounts(sort_code, account_number);
CREATE INDEX idx_transactions_account_id ON transactions(account_id);
