# Accounting Ledger Structure - Summary

## Files Created

1. **`ledger_schema.sql`** - Complete MySQL schema with:
   - `chart_of_accounts` table
   - `transactions` table (header)
   - `transaction_lines` table (debit/credit entries)
   - Stored procedures for transaction creation and validation
   - Pre-populated chart of accounts

2. **`LEDGER_USAGE_GUIDE.md`** - Detailed mapping of operational transactions to ledger entries

## Quick Start

1. **Run the SQL schema**:
   ```sql
   SOURCE ledger_schema.sql;
   ```

2. **Create a ledger transaction** (Python example):
   ```python
   # 1. Insert operational record (e.g., Sale)
   cursor.execute("INSERT INTO Sales (...) VALUES (...)")
   sale_id = cursor.lastrowid
   
   # 2. Create transaction header
   cursor.callproc('create_ledger_transaction', [
       '2024-01-15',  # date
       'SALES',       # reference_type
       sale_id,       # reference_id
       'Sale of Product X',  # description
       'user123',     # created_by
       0              # output param (transaction_id)
   ])
   cursor.execute("SELECT @p_transaction_id")
   transaction_id = cursor.fetchone()[0]
   
   # 3. Insert balanced lines
   cursor.execute("""
       INSERT INTO transaction_lines 
       (transaction_id, account_id, entry_type, amount, description)
       VALUES 
       (%s, (SELECT account_id FROM chart_of_accounts WHERE account_code='1000'), 'DEBIT', 500.00, 'Cash received'),
       (%s, (SELECT account_id FROM chart_of_accounts WHERE account_code='4000'), 'CREDIT', 500.00, 'Sales revenue')
   """, (transaction_id, transaction_id))
   
   # 4. Validate balance
   cursor.callproc('validate_transaction_balance', [transaction_id, 0])
   cursor.execute("SELECT @p_is_balanced")
   is_balanced = cursor.fetchone()[0]
   
   if is_balanced:
       conn.commit()
   else:
       conn.rollback()
       raise ValueError("Transaction not balanced!")
   ```

## Key Design Features

✅ **Append-Only**: No updates/deletes on ledger tables  
✅ **Double-Entry**: Every transaction balances (debits = credits)  
✅ **Reference Linking**: Links to Sales, Purchases, Payroll, etc.  
✅ **No Running Balances**: Calculated on-demand from transaction lines  
✅ **Extensible**: Easy to add new account types and transaction types  

## Account Structure

- **1000-1999**: Assets (Cash, Bank, Receivables, Inventory)
- **2000-2999**: Liabilities (Payables, Accrued Expenses)
- **3000-3999**: Equity (Capital, Retained Earnings)
- **4000-4999**: Revenue (Sales, Returns, Discounts)
- **5000-5999**: Expenses (COGS, Salaries, Rent, etc.)

## Next Steps

1. Integrate ledger creation into your existing modules (Sales.py, Purchase.py, etc.)
2. Create reporting queries to calculate account balances
3. Build financial statements (Income Statement, Balance Sheet) from ledger data
4. Add audit logging for transaction creation

## Important Notes

- **Always validate balance** before committing transactions
- **Never update or delete** ledger entries directly
- **Use stored procedures** for transaction creation when possible
- **Wrap in database transactions** to ensure atomicity
- **Reference operational records** via `reference_type` and `reference_id`
