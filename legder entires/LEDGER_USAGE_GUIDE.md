# Accounting Ledger Usage Guide

## Overview

This document explains how operational transactions (Sales, Purchases, Expenses, Payroll, Returns) map to double-entry accounting ledger entries.

## Core Principles

1. **Append-Only**: Ledger tables (`transactions` and `transaction_lines`) are never updated or deleted. Corrections are made via reversing entries.
2. **Double-Entry**: Every transaction must have balanced debits and credits (total debits = total credits).
3. **Reference Linking**: Each ledger transaction references the source operational record via `reference_type` and `reference_id`.

## Transaction Mapping Examples

### 1. SALE (Cash Sale)

**Operational Record**: `Sales` table (Sales_ID = 100)

**Ledger Entry**:
- **Transaction Header**: 
  - `reference_type` = 'SALES'
  - `reference_id` = 100
  - `description` = 'Cash sale of Product X'
  
- **Transaction Lines**:
  1. **DEBIT** `Cash` (1000) - $500.00
  2. **CREDIT** `Sales Revenue` (4000) - $500.00

**For Credit Sales** (customer pays later):
  1. **DEBIT** `Accounts Receivable` (1200) - $500.00
  2. **CREDIT** `Sales Revenue` (4000) - $500.00

**When Customer Pays** (settling receivable):
  1. **DEBIT** `Cash` (1000) - $500.00
  2. **CREDIT** `Accounts Receivable` (1200) - $500.00

---

### 2. PURCHASE (Inventory Purchase)

**Operational Record**: `Purchases` table (Purchase_ID = 50)

**For Cash Purchase**:
- **Transaction Lines**:
  1. **DEBIT** `Inventory` (1300) - $300.00
  2. **CREDIT** `Cash` (1000) - $300.00

**For Credit Purchase** (pay vendor later):
- **Transaction Lines**:
  1. **DEBIT** `Inventory` (1300) - $300.00
  2. **CREDIT** `Accounts Payable` (2000) - $300.00

**When Paying Vendor** (settling payable):
- **Transaction Lines**:
  1. **DEBIT** `Accounts Payable` (2000) - $300.00
  2. **CREDIT** `Cash` (1000) or `Bank Account` (1100) - $300.00

---

### 3. SALE WITH COST OF GOODS SOLD

**When a sale occurs, you also need to record the cost of inventory sold**:

**Sale Transaction** (Sales_ID = 100):
- **Transaction Lines**:
  1. **DEBIT** `Cash` (1000) - $500.00
  2. **CREDIT** `Sales Revenue` (4000) - $500.00

**COGS Transaction** (same reference, or separate):
- **Transaction Lines**:
  1. **DEBIT** `Cost of Goods Sold` (5000) - $300.00 (cost of inventory)
  2. **CREDIT** `Inventory` (1300) - $300.00 (reduce inventory)

---

### 4. EXPENSE (e.g., Rent, Utilities)

**Operational Record**: Could be an `Expenses` table (Expense_ID = 25)

**For Cash Payment**:
- **Transaction Lines**:
  1. **DEBIT** `Rent Expense` (5300) - $1,000.00
  2. **CREDIT** `Cash` (1000) or `Bank Account` (1100) - $1,000.00

**For Accrued Expense** (expense incurred but not yet paid):
- **Transaction Lines**:
  1. **DEBIT** `Rent Expense` (5300) - $1,000.00
  2. **CREDIT** `Accrued Expenses` (2100) - $1,000.00

**When Paying Accrued Expense**:
- **Transaction Lines**:
  1. **DEBIT** `Accrued Expenses` (2100) - $1,000.00
  2. **CREDIT** `Cash` (1000) or `Bank Account` (1100) - $1,000.00

---

### 5. PAYROLL

**Operational Record**: `Payroll` table (Salary_ID = 10)

**When Paying Employee Salary**:
- **Transaction Lines**:
  1. **DEBIT** `Salary Expense` (5200) - $2,000.00
  2. **CREDIT** `Cash` (1000) or `Bank Account` (1100) - $2,000.00

**For Accrued Payroll** (salary earned but not yet paid):
- **Transaction Lines**:
  1. **DEBIT** `Salary Expense` (5200) - $2,000.00
  2. **CREDIT** `Accrued Expenses` (2100) - $2,000.00

---

### 6. SALES RETURN

**Operational Record**: `Sales_Return` table (SalesR_ID = 5)

**When Customer Returns Product**:
- **Transaction Lines**:
  1. **DEBIT** `Sales Returns` (4100) - $100.00 (contra-revenue, reduces revenue)
  2. **CREDIT** `Cash` (1000) or `Accounts Receivable` (1200) - $100.00

**If Inventory is Returned to Stock**:
- **Transaction Lines**:
  1. **DEBIT** `Inventory` (1300) - $60.00 (cost of returned item)
  2. **CREDIT** `Cost of Goods Sold` (5000) - $60.00 (reverse COGS)

---

### 7. PURCHASE RETURN

**Operational Record**: `Purchase_Return` table (PurchaseR_ID = 3)

**When Returning Product to Vendor**:
- **Transaction Lines**:
  1. **DEBIT** `Accounts Payable` (2000) or `Cash` (1000) - $150.00
  2. **CREDIT** `Purchase Returns` (5100) - $150.00 (contra-expense, reduces COGS)

**If Inventory is Removed**:
- **Transaction Lines**:
  1. **DEBIT** `Purchase Returns` (5100) - $150.00
  2. **CREDIT** `Inventory` (1300) - $150.00

---

## Implementation Notes

### Transaction Creation Workflow

1. **Insert Operational Record**: Create record in Sales, Purchases, Payroll, etc.
2. **Create Transaction Header**: Insert into `transactions` table with reference to operational record.
3. **Create Balanced Lines**: Insert into `transaction_lines` table ensuring debits = credits.
4. **Database Validation**: Triggers automatically validate balance.

### Error Handling

- If debits ≠ credits, the database trigger will reject the transaction.
- Always wrap transaction creation in a database transaction (BEGIN/COMMIT) to ensure atomicity.

### Corrections and Reversals

- **Never delete or update** ledger entries.
- To correct an error:
  1. Create a new transaction with `reference_type` = 'ADJUSTMENT'
  2. Reverse the incorrect entry (swap debits/credits)
  3. Create the correct entry
  4. Optionally mark original transaction as `is_voided` = TRUE

### Querying Balances

To get account balances, sum debits and credits:
```sql
SELECT 
    account_id,
    account_code,
    account_name,
    SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE 0 END) as total_debits,
    SUM(CASE WHEN entry_type = 'CREDIT' THEN amount ELSE 0 END) as total_credits,
    SUM(CASE WHEN entry_type = 'DEBIT' THEN amount ELSE -amount END) as balance
FROM transaction_lines tl
JOIN chart_of_accounts coa ON tl.account_id = coa.account_id
WHERE coa.account_code = '1000'  -- Cash account
GROUP BY account_id;
```

### Account Type Normal Balances

- **Assets**: Normal balance is DEBIT (increase with debits)
- **Liabilities**: Normal balance is CREDIT (increase with credits)
- **Equity**: Normal balance is CREDIT (increase with credits)
- **Revenue**: Normal balance is CREDIT (increase with credits)
- **Expenses**: Normal balance is DEBIT (increase with debits)

---

## Summary

The ledger system provides a complete audit trail of all accounting events. Each operational transaction (Sale, Purchase, etc.) creates one or more balanced accounting entries that follow double-entry principles. The ledger is append-only, ensuring data integrity and compliance with accounting standards.
