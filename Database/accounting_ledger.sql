-- ============================================================================
-- SHOP MANAGEMENT SYSTEM — COMPLETE ACCOUNTING ENGINE
-- Version 2.0  |  Supersedes ledger_schema.sql
-- ============================================================================
--
-- ARCHITECTURE: DUAL-LAYER SYSTEM
--   Operational Layer  → Sales, Purchases, Payroll, Expenses (shop_management.sql)
--   Accounting Layer   → This file — the authoritative financial truth
--
-- EVERY financial event in the operational layer MUST call the corresponding
-- posting procedure here to generate balanced double-entry journal entries.
--
-- TABLE DEPENDENCY ORDER:
--   1.  chart_of_accounts       (existing — extended here)
--   2.  accounting_periods      (new)
--   3.  transactions            (existing — enhanced)
--   4.  transaction_lines       (existing — unchanged)
--   5.  account_period_balances (new — performance cache)
--   6.  sub_ledger_ar           (new — customer receivables detail)
--   7.  sub_ledger_ap           (new — vendor payables detail)
--   8.  reconciliation_sessions (new)
--   9.  reconciliation_items    (new)
--
-- STORED PROCEDURES:
--   post_sale_to_ledger
--   post_sale_return_to_ledger
--   post_purchase_to_ledger
--   post_purchase_return_to_ledger
--   post_expense_to_ledger
--   post_payroll_to_ledger
--   post_capital_injection_to_ledger
--   void_journal_entry
--   open_accounting_period
--   close_accounting_period
--   rebuild_period_balances
--
-- FUNCTIONS:
--   get_account_balance(account_id, as_of_date)
--   get_account_id_by_code(account_code)
--
-- VIEWS:
--   v_general_ledger
--   v_trial_balance
--   v_profit_and_loss
--   v_balance_sheet
--   v_accounts_receivable_aging
--   v_accounts_payable_aging
--   v_cash_flow_summary
--   v_expense_analysis
--   v_vendor_outstanding
--   v_customer_outstanding
--   v_monthly_pnl_trend
-- ============================================================================

USE Shop_Management;

-- ============================================================================
-- SECTION 1 — CHART OF ACCOUNTS  (extend existing)
-- ============================================================================
-- Uses INSERT IGNORE — safe to re-run; will not duplicate existing codes.
-- Range layout:
--   1000–1999 : ASSETS
--   2000–2999 : LIABILITIES
--   3000–3999 : EQUITY
--   4000–4999 : REVENUE
--   5000–5999 : EXPENSES
-- ============================================================================

INSERT IGNORE INTO `chart_of_accounts`
    (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`)
VALUES
-- ── ASSETS ──────────────────────────────────────────────────────────────────
('1000', 'Cash on Hand',            'ASSET', 'DEBIT', 'Physical cash in the register'),
('1100', 'Bank Account',            'ASSET', 'DEBIT', 'Primary business bank account'),
('1150', 'Petty Cash',              'ASSET', 'DEBIT', 'Small cash fund for minor expenses'),
('1200', 'Accounts Receivable',     'ASSET', 'DEBIT', 'Amounts owed by credit customers'),
('1210', 'GST Input Credit',        'ASSET', 'DEBIT', 'GST paid on purchases (input tax credit)'),
('1300', 'Inventory',               'ASSET', 'DEBIT', 'Products held for sale at cost'),
('1400', 'Prepaid Expenses',        'ASSET', 'DEBIT', 'Expenses paid in advance'),
('1500', 'Other Current Assets',    'ASSET', 'DEBIT', 'Miscellaneous short-term assets'),

-- ── LIABILITIES ─────────────────────────────────────────────────────────────
('2000', 'Accounts Payable',        'LIABILITY', 'CREDIT', 'Amounts owed to vendors/suppliers'),
('2100', 'Accrued Expenses',        'LIABILITY', 'CREDIT', 'Expenses incurred but not yet paid'),
('2200', 'GST Payable',             'LIABILITY', 'CREDIT', 'GST collected on sales, payable to government'),
('2300', 'Salary Payable',          'LIABILITY', 'CREDIT', 'Net salaries due to employees'),
('2400', 'TDS Payable',             'LIABILITY', 'CREDIT', 'Tax deducted at source, payable to government'),
('2500', 'Advance from Customers',  'LIABILITY', 'CREDIT', 'Pre-payments received from customers'),
('2600', 'Other Current Liabilities','LIABILITY','CREDIT', 'Miscellaneous short-term liabilities'),

-- ── EQUITY ──────────────────────────────────────────────────────────────────
('3000', 'Owner Capital',           'EQUITY', 'CREDIT', 'Capital invested by the owner'),
('3100', 'Retained Earnings',       'EQUITY', 'CREDIT', 'Accumulated net profits'),
('3200', 'Owner Drawings',          'EQUITY', 'DEBIT',  'Withdrawals made by the owner (contra-equity)'),

-- ── REVENUE ─────────────────────────────────────────────────────────────────
('4000', 'Sales Revenue',           'REVENUE', 'CREDIT', 'Gross revenue from product sales'),
('4100', 'Sales Returns & Allowances','REVENUE','DEBIT', 'Customer returns/refunds (contra-revenue)'),
('4200', 'Discounts Allowed',       'REVENUE', 'DEBIT',  'Discounts given to customers (contra-revenue)'),
('4300', 'Other Income',            'REVENUE', 'CREDIT', 'Non-operating income, interest earned, etc.'),

-- ── EXPENSES ────────────────────────────────────────────────────────────────
('5000', 'Cost of Goods Sold',      'EXPENSE', 'DEBIT',  'Direct cost of products sold'),
('5100', 'Purchase Returns',        'EXPENSE', 'CREDIT', 'Returns to vendors (contra-expense)'),
('5200', 'Salary & Wages Expense',  'EXPENSE', 'DEBIT',  'Employee gross salaries and wages'),
('5210', 'Bonus & Incentives',      'EXPENSE', 'DEBIT',  'Employee bonuses and performance incentives'),
('5220', 'Overtime Expense',        'EXPENSE', 'DEBIT',  'Overtime pay to employees'),
('5300', 'Rent Expense',            'EXPENSE', 'DEBIT',  'Shop/office/warehouse rent'),
('5400', 'Electricity Expense',     'EXPENSE', 'DEBIT',  'Electricity bills'),
('5410', 'Water Expense',           'EXPENSE', 'DEBIT',  'Water utility bills'),
('5420', 'Internet & Phone Expense','EXPENSE', 'DEBIT',  'Internet, broadband, telephone bills'),
('5500', 'Office Supplies Expense', 'EXPENSE', 'DEBIT',  'Stationery, consumables, packaging'),
('5510', 'Tea & Refreshments',      'EXPENSE', 'DEBIT',  'Staff tea, coffee, refreshments'),
('5600', 'Marketing & Advertising', 'EXPENSE', 'DEBIT',  'Promotions, ads, print materials'),
('5700', 'Transport & Freight',     'EXPENSE', 'DEBIT',  'Delivery, courier, shipping, fuel'),
('5800', 'Maintenance & Repairs',   'EXPENSE', 'DEBIT',  'Equipment and property maintenance'),
('5810', 'Depreciation Expense',    'EXPENSE', 'DEBIT',  'Asset depreciation'),
('5900', 'Bank Charges',            'EXPENSE', 'DEBIT',  'Bank fees, transaction charges, cheque bounce'),
('5910', 'Subscription Expense',    'EXPENSE', 'DEBIT',  'Software, services, annual subscriptions'),
('5920', 'Tax & License Expense',   'EXPENSE', 'DEBIT',  'Business taxes, license renewal fees'),
('5950', 'Miscellaneous Expense',   'EXPENSE', 'DEBIT',  'Any other operational expenses not categorised');


-- ============================================================================
-- SECTION 2 — ACCOUNTING PERIODS
-- Controls which period is open for posting. Closing a period locks history.
-- ============================================================================

CREATE TABLE IF NOT EXISTS `accounting_periods` (
    `period_id`     INT             AUTO_INCREMENT PRIMARY KEY,
    `period_name`   VARCHAR(30)     NOT NULL UNIQUE    COMMENT 'e.g. APR-2025, FY2025-Q1',
    `period_type`   ENUM('MONTHLY','QUARTERLY','YEARLY') NOT NULL DEFAULT 'MONTHLY',
    `start_date`    DATE            NOT NULL,
    `end_date`      DATE            NOT NULL,
    `status`        ENUM('OPEN','CLOSED','LOCKED') NOT NULL DEFAULT 'OPEN'
                        COMMENT 'OPEN=postings allowed; CLOSED=soft lock; LOCKED=hard lock',
    `closed_by`     INT             DEFAULT NULL,
    `closed_at`     TIMESTAMP       NULL DEFAULT NULL,
    `notes`         VARCHAR(255)    DEFAULT NULL,
    `created_at`    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_period_dates UNIQUE (start_date, end_date),
    FOREIGN KEY (closed_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_period_status (status),
    INDEX idx_period_dates  (start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Accounting period management — controls when journals can be posted';


-- ============================================================================
-- SECTION 3 — TRANSACTIONS  (enhanced header)
-- Drop the old version and recreate with period_id and posted_by (INT)
-- ============================================================================

-- Back up and recreate with enhancements.
-- NOTE: If migrating live data, rename instead of dropping.
DROP TABLE IF EXISTS `transactions`;

CREATE TABLE IF NOT EXISTS `transactions` (
    `transaction_id`   INT           AUTO_INCREMENT PRIMARY KEY,
    `period_id`        INT           DEFAULT NULL          COMMENT 'Links to accounting_periods',
    `transaction_date` DATE          NOT NULL              COMMENT 'Accounting date',
    `reference_type`   VARCHAR(50)   NOT NULL
                           COMMENT 'SALE | SALE_RETURN | PURCHASE | PURCHASE_RETURN | EXPENSE | PAYROLL | CAPITAL | ADJUSTMENT | VOID',
    `reference_id`     INT           NOT NULL              COMMENT 'PK from the source operational table',
    `description`      VARCHAR(255)  NOT NULL,
    `posted_by`        INT           DEFAULT NULL          COMMENT 'user_id from Users table',
    `is_voided`        BOOLEAN       NOT NULL DEFAULT FALSE,
    `void_reason`      VARCHAR(255)  DEFAULT NULL,
    `voided_by`        INT           DEFAULT NULL,
    `voided_at`        TIMESTAMP     NULL DEFAULT NULL,
    `created_at`       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (period_id)  REFERENCES accounting_periods(period_id) ON DELETE RESTRICT,
    FOREIGN KEY (posted_by)  REFERENCES Users(user_id)                ON DELETE SET NULL,
    FOREIGN KEY (voided_by)  REFERENCES Users(user_id)                ON DELETE SET NULL,
    INDEX idx_txn_date      (transaction_date),
    INDEX idx_txn_reference (reference_type, reference_id),
    INDEX idx_txn_period    (period_id),
    INDEX idx_txn_voided    (is_voided),
    INDEX idx_txn_created   (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Journal entry headers — one row per accounting event';


-- ============================================================================
-- SECTION 4 — TRANSACTION LINES  (debit / credit entries — unchanged)
-- ============================================================================

DROP TABLE IF EXISTS `transaction_lines`;

CREATE TABLE IF NOT EXISTS `transaction_lines` (
    `line_id`        INT            AUTO_INCREMENT PRIMARY KEY,
    `transaction_id` INT            NOT NULL,
    `account_id`     INT            NOT NULL,
    `entry_type`     ENUM('DEBIT','CREDIT') NOT NULL,
    `amount`         DECIMAL(15,2)  NOT NULL,
    `description`    VARCHAR(255)   DEFAULT NULL,
    `created_at`     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_amount_positive CHECK (amount > 0),
    FOREIGN KEY (transaction_id) REFERENCES `transactions`(transaction_id) ON DELETE RESTRICT,
    FOREIGN KEY (account_id)     REFERENCES `chart_of_accounts`(account_id) ON DELETE RESTRICT,
    INDEX idx_tl_transaction         (transaction_id),
    INDEX idx_tl_account             (account_id),
    INDEX idx_tl_transaction_account (transaction_id, account_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual debit/credit lines — debits MUST equal credits per transaction_id';


-- ============================================================================
-- SECTION 5 — ACCOUNT PERIOD BALANCES CACHE
-- Pre-computed closing balances per account per period for fast reporting.
-- Rebuilt by rebuild_period_balances() after period close.
-- ============================================================================

CREATE TABLE IF NOT EXISTS `account_period_balances` (
    `balance_id`    INT             AUTO_INCREMENT PRIMARY KEY,
    `period_id`     INT             NOT NULL,
    `account_id`    INT             NOT NULL,
    `opening_balance` DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    `total_debits`  DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
    `total_credits` DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
    `closing_balance` DECIMAL(15,2) NOT NULL DEFAULT 0.00
                        COMMENT 'opening + debits - credits for DEBIT-normal accounts; opposite for CREDIT-normal',
    `computed_at`   TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_period_account (period_id, account_id),
    FOREIGN KEY (period_id)  REFERENCES accounting_periods(period_id)    ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES chart_of_accounts(account_id)    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Cached period-end balances for fast Balance Sheet and P&L queries';


-- ============================================================================
-- SECTION 6 — SUB-LEDGERS  (Accounts Receivable & Accounts Payable detail)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 6.1  Sub-Ledger AR  — per-customer receivable tracking
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sub_ledger_ar` (
    `ar_id`          INT             AUTO_INCREMENT PRIMARY KEY,
    `transaction_id` INT             NOT NULL,
    `customer_id`    INT             NOT NULL,
    `reference_type` VARCHAR(50)     NOT NULL   COMMENT 'SALE | SALE_RETURN | RECEIPT | ADJUSTMENT',
    `reference_id`   INT             NOT NULL,
    `txn_date`       DATE            NOT NULL,
    `debit_amount`   DECIMAL(15,2)   NOT NULL DEFAULT 0.00  COMMENT 'Increases receivable (credit sale)',
    `credit_amount`  DECIMAL(15,2)   NOT NULL DEFAULT 0.00  COMMENT 'Decreases receivable (payment received / return)',
    `due_date`       DATE            DEFAULT NULL,
    `is_settled`     BOOLEAN         NOT NULL DEFAULT FALSE,
    `created_at`     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (transaction_id) REFERENCES `transactions`(transaction_id) ON DELETE RESTRICT,
    FOREIGN KEY (customer_id)    REFERENCES Customers(customer_id)         ON DELETE RESTRICT,
    INDEX idx_ar_customer   (customer_id),
    INDEX idx_ar_due_date   (due_date),
    INDEX idx_ar_settled    (is_settled),
    INDEX idx_ar_txn_date   (txn_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Customer-level receivables detail — sub-ledger to account 1200';

-- FIX (Issue 2): Trigger to auto-settle AR entries when balance reaches zero.
-- After every insert into sub_ledger_ar, recalculate the net balance for the
-- same customer+reference and flip is_settled=TRUE on all matching rows.
DELIMITER $$
DROP TRIGGER IF EXISTS trg_settle_ar $$
CREATE TRIGGER trg_settle_ar
AFTER INSERT ON sub_ledger_ar
FOR EACH ROW
BEGIN
    DECLARE v_net_balance DECIMAL(15,2);

    -- Net balance: positive = still owed, zero/negative = fully settled
    SELECT COALESCE(SUM(debit_amount) - SUM(credit_amount), 0)
    INTO   v_net_balance
    FROM   sub_ledger_ar
    WHERE  customer_id    = NEW.customer_id
      AND  reference_id   = NEW.reference_id
      AND  reference_type = NEW.reference_type;

    IF v_net_balance <= 0 THEN
        UPDATE sub_ledger_ar
        SET    is_settled = TRUE
        WHERE  customer_id    = NEW.customer_id
          AND  reference_id   = NEW.reference_id
          AND  reference_type = NEW.reference_type
          AND  is_settled     = FALSE;
    END IF;
END $$
DELIMITER ;

-- ----------------------------------------------------------------------------
-- 6.2  Sub-Ledger AP  — per-vendor payable tracking
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sub_ledger_ap` (
    `ap_id`          INT             AUTO_INCREMENT PRIMARY KEY,
    `transaction_id` INT             NOT NULL,
    `vendor_id`      INT             NOT NULL,
    `reference_type` VARCHAR(50)     NOT NULL   COMMENT 'PURCHASE | PURCHASE_RETURN | PAYMENT | ADJUSTMENT',
    `reference_id`   INT             NOT NULL,
    `txn_date`       DATE            NOT NULL,
    `credit_amount`  DECIMAL(15,2)   NOT NULL DEFAULT 0.00  COMMENT 'Increases payable (credit purchase)',
    `debit_amount`   DECIMAL(15,2)   NOT NULL DEFAULT 0.00  COMMENT 'Decreases payable (payment made / return)',
    `due_date`       DATE            DEFAULT NULL,
    `is_settled`     BOOLEAN         NOT NULL DEFAULT FALSE,
    `created_at`     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (transaction_id) REFERENCES `transactions`(transaction_id) ON DELETE RESTRICT,
    FOREIGN KEY (vendor_id)      REFERENCES Vendors(vendor_id)             ON DELETE RESTRICT,
    INDEX idx_ap_vendor    (vendor_id),
    INDEX idx_ap_due_date  (due_date),
    INDEX idx_ap_settled   (is_settled),
    INDEX idx_ap_txn_date  (txn_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Vendor-level payables detail — sub-ledger to account 2000';

-- FIX (Issue 2): Trigger to auto-settle AP entries when balance reaches zero.
-- After every insert into sub_ledger_ap, recalculate the net balance for the
-- same vendor+reference and flip is_settled=TRUE on all matching rows.
DELIMITER $$
DROP TRIGGER IF EXISTS trg_settle_ap $$
CREATE TRIGGER trg_settle_ap
AFTER INSERT ON sub_ledger_ap
FOR EACH ROW
BEGIN
    DECLARE v_net_balance DECIMAL(15,2);

    -- Net balance: positive = still owed, zero/negative = fully settled
    SELECT COALESCE(SUM(credit_amount) - SUM(debit_amount), 0)
    INTO   v_net_balance
    FROM   sub_ledger_ap
    WHERE  vendor_id      = NEW.vendor_id
      AND  reference_id   = NEW.reference_id
      AND  reference_type = NEW.reference_type;

    IF v_net_balance <= 0 THEN
        UPDATE sub_ledger_ap
        SET    is_settled = TRUE
        WHERE  vendor_id      = NEW.vendor_id
          AND  reference_id   = NEW.reference_id
          AND  reference_type = NEW.reference_type
          AND  is_settled     = FALSE;
    END IF;
END $$
DELIMITER ;


-- ============================================================================
-- SECTION 7 — CASH REGISTER RECONCILIATION
-- ============================================================================

CREATE TABLE IF NOT EXISTS `reconciliation_sessions` (
    `session_id`      INT             AUTO_INCREMENT PRIMARY KEY,
    `session_type`    ENUM('CASH','BANK') NOT NULL,
    `session_date`    DATE            NOT NULL,
    `opened_by`       INT             NOT NULL,
    `opened_at`       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `opening_balance` DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
    `expected_closing` DECIMAL(15,2)  DEFAULT NULL   COMMENT 'System-calculated expected balance',
    `actual_closing`  DECIMAL(15,2)   DEFAULT NULL   COMMENT 'Physical count / bank statement figure',
    `variance`        DECIMAL(15,2)   GENERATED ALWAYS AS
                          (actual_closing - expected_closing) STORED
                          COMMENT 'Positive = surplus, Negative = shortage',
    `status`          ENUM('OPEN','RECONCILED','DISCREPANCY') NOT NULL DEFAULT 'OPEN',
    `closed_by`       INT             DEFAULT NULL,
    `closed_at`       TIMESTAMP       NULL DEFAULT NULL,
    `notes`           VARCHAR(500)    DEFAULT NULL,

    FOREIGN KEY (opened_by) REFERENCES Users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (closed_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_recon_date   (session_date),
    INDEX idx_recon_type   (session_type),
    INDEX idx_recon_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Cash register and bank reconciliation session headers';

CREATE TABLE IF NOT EXISTS `reconciliation_items` (
    `item_id`      INT             AUTO_INCREMENT PRIMARY KEY,
    `session_id`   INT             NOT NULL,
    `item_type`    ENUM('MATCHED','UNMATCHED_LEDGER','UNMATCHED_STATEMENT','ADJUSTMENT') NOT NULL,
    `reference_type` VARCHAR(50)   DEFAULT NULL,
    `reference_id` INT             DEFAULT NULL,
    `description`  VARCHAR(255)    NOT NULL,
    `amount`       DECIMAL(15,2)   NOT NULL,
    `is_cleared`   BOOLEAN         NOT NULL DEFAULT FALSE,
    `created_at`   TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (session_id) REFERENCES reconciliation_sessions(session_id) ON DELETE CASCADE,
    INDEX idx_recon_item_session (session_id),
    INDEX idx_recon_item_cleared (is_cleared)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual line items within a reconciliation session';


-- ============================================================================
-- SECTION 8 — STORED PROCEDURES  &  FUNCTIONS
-- ============================================================================

DELIMITER $$

-- ============================================================================
-- 8.0  HELPER FUNCTION: get_account_id_by_code
-- Returns account_id for a given account_code. Used inside all procedures.
-- ============================================================================
DROP FUNCTION IF EXISTS get_account_id_by_code $$
CREATE FUNCTION get_account_id_by_code(p_code VARCHAR(20))
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_id INT;
    SELECT account_id INTO v_id
    FROM chart_of_accounts
    WHERE account_code = p_code AND is_active = TRUE
    LIMIT 1;
    RETURN v_id;
END $$

-- ============================================================================
-- 8.1  FUNCTION: get_account_balance
-- Returns the net balance of an account as of a given date.
-- For DEBIT-normal accounts: balance = total_debits - total_credits
-- For CREDIT-normal accounts: balance = total_credits - total_debits
-- ============================================================================
DROP FUNCTION IF EXISTS get_account_balance $$
CREATE FUNCTION get_account_balance(
    p_account_id  INT,
    p_as_of_date  DATE
)
RETURNS DECIMAL(15,2)
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE v_normal_balance  ENUM('DEBIT','CREDIT');
    DECLARE v_total_debits    DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_total_credits   DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_balance         DECIMAL(15,2) DEFAULT 0.00;

    SELECT normal_balance INTO v_normal_balance
    FROM chart_of_accounts WHERE account_id = p_account_id;

    SELECT
        COALESCE(SUM(CASE WHEN tl.entry_type = 'DEBIT'  THEN tl.amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN tl.entry_type = 'CREDIT' THEN tl.amount ELSE 0 END), 0)
    INTO v_total_debits, v_total_credits
    FROM transaction_lines tl
    JOIN transactions      t  ON t.transaction_id = tl.transaction_id
    WHERE tl.account_id      = p_account_id
      AND t.transaction_date <= p_as_of_date
      AND t.is_voided         = FALSE;

    IF v_normal_balance = 'DEBIT' THEN
        SET v_balance = v_total_debits - v_total_credits;
    ELSE
        SET v_balance = v_total_credits - v_total_debits;
    END IF;

    RETURN v_balance;
END $$

-- ============================================================================
-- 8.2  PROCEDURE: validate_and_post
-- Internal helper — validates that a transaction is balanced before committing.
-- Raises SQLSTATE '45000' if unbalanced (triggers rollback in callers).
-- ============================================================================
DROP PROCEDURE IF EXISTS validate_and_post $$
CREATE PROCEDURE validate_and_post(IN p_transaction_id INT)
BEGIN
    DECLARE v_debits  DECIMAL(15,2);
    DECLARE v_credits DECIMAL(15,2);

    SELECT
        COALESCE(SUM(CASE WHEN entry_type='DEBIT'  THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN entry_type='CREDIT' THEN amount ELSE 0 END), 0)
    INTO v_debits, v_credits
    FROM transaction_lines
    WHERE transaction_id = p_transaction_id;

    IF ABS(v_debits - v_credits) > 0.01 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Journal entry is unbalanced: total debits ≠ total credits';
    END IF;
END $$

-- ============================================================================
-- 8.3  PROCEDURE: post_sale_to_ledger
--
-- Generates four journal lines for a completed sale:
--
--   CASH / CARD / UPI / NET_BANKING sale:
--     DR  Cash (1000) or Bank (1100)          total_amount
--     CR  Sales Revenue (4000)                net_amount  (total - gst)
--     CR  GST Payable (2200)                  gst_amount
--     DR  Cost of Goods Sold (5000)           cogs_amount
--     CR  Inventory (1300)                    cogs_amount
--
--   CREDIT sale:
--     DR  Accounts Receivable (1200)          total_amount
--     CR  Sales Revenue (4000)                net_amount
--     CR  GST Payable (2200)                  gst_amount
--     DR  Cost of Goods Sold (5000)           cogs_amount
--     CR  Inventory (1300)                    cogs_amount
--
--   DISCOUNT applied (if discount_amount > 0):
--     DR  Discounts Allowed (4200)            discount_amount
--     CR  Accounts Receivable / Cash (1200/1000)  discount_amount
-- ============================================================================
DROP PROCEDURE IF EXISTS post_sale_to_ledger $$
CREATE PROCEDURE post_sale_to_ledger(
    IN p_sale_id        INT,
    IN p_sale_date      DATE,
    IN p_total_amount   DECIMAL(15,2),   -- amount including GST
    IN p_gst_amount     DECIMAL(15,2),   -- GST portion
    IN p_cogs_amount    DECIMAL(15,2),   -- cost of product sold
    IN p_discount_amount DECIMAL(15,2),  -- discount given (0 if none)
    IN p_payment_method VARCHAR(20),     -- cash|card|net_banking|upi|credit
    IN p_customer_id    INT,             -- NULL for walk-in
    IN p_posted_by      INT              -- Users.user_id
)
BEGIN
    DECLARE v_txn_id          INT;
    DECLARE v_net_revenue     DECIMAL(15,2);
    DECLARE v_cash_acct       INT;
    DECLARE v_bank_acct       INT;
    DECLARE v_ar_acct         INT;
    DECLARE v_revenue_acct    INT;
    DECLARE v_gst_acct        INT;
    DECLARE v_cogs_acct       INT;
    DECLARE v_inventory_acct  INT;
    DECLARE v_discount_acct   INT;
    DECLARE v_debit_acct      INT;   -- cash/bank/AR depending on method
    DECLARE v_period_id       INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- Resolve account IDs
    SET v_cash_acct      = get_account_id_by_code('1000');
    SET v_bank_acct      = get_account_id_by_code('1100');
    SET v_ar_acct        = get_account_id_by_code('1200');
    SET v_revenue_acct   = get_account_id_by_code('4000');
    SET v_gst_acct       = get_account_id_by_code('2200');
    SET v_cogs_acct      = get_account_id_by_code('5000');
    SET v_inventory_acct = get_account_id_by_code('1300');
    SET v_discount_acct  = get_account_id_by_code('4200');

    -- FIX (Issue 6): v_net_revenue is the GROSS revenue before discount.
    -- The debit (Cash/AR) is already the net amount the customer actually paid.
    -- Discount is then recorded as a separate DR to Discounts Allowed (4200),
    -- so revenue and discount are both gross — no double-reduction of Cash/AR.
    SET v_net_revenue = p_total_amount - p_gst_amount + p_discount_amount;

    -- Determine debit account based on payment method
    IF p_payment_method = 'credit' THEN
        SET v_debit_acct = v_ar_acct;
    ELSEIF p_payment_method IN ('card', 'net_banking', 'upi') THEN
        SET v_debit_acct = v_bank_acct;
    ELSE
        SET v_debit_acct = v_cash_acct;  -- default cash
    END IF;

    -- FIX (Issue 3): Reject the transaction if no OPEN period covers this date.
    -- Without this guard, v_period_id would be NULL and the entry would bypass
    -- period locking — silently undermining the closed-period audit trail.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status = 'OPEN'
      AND p_sale_date BETWEEN start_date AND end_date
    LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post sale: no OPEN accounting period found for this date. Open a period first.';
    END IF;

    START TRANSACTION;

    -- Create journal header
    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_sale_date, 'SALE', p_sale_id,
         CONCAT('Sale #', p_sale_id, ' — ', p_payment_method), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    -- LINE 1: DR Cash/Bank/AR  (net collected = total after discount)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_debit_acct, 'DEBIT', p_total_amount, 'Amount received/receivable (net of discount)');

    -- LINE 2: CR Sales Revenue  (gross revenue before discount, net of GST)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_revenue_acct, 'CREDIT', v_net_revenue, 'Gross sales revenue net of GST');

    -- LINE 3: CR GST Payable  (only if GST > 0)
    IF p_gst_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_gst_acct, 'CREDIT', p_gst_amount, 'GST collected from customer');
    END IF;

    -- LINE 4: DR Cost of Goods Sold
    IF p_cogs_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_cogs_acct, 'DEBIT', p_cogs_amount, 'Cost of goods sold');

        -- LINE 5: CR Inventory
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_inventory_acct, 'CREDIT', p_cogs_amount, 'Inventory reduction on sale');
    END IF;

    -- FIX (Issue 6): Discount entry is ONLY a debit to Discounts Allowed (4200).
    -- The matching credit is Revenue (4000) being recorded at gross, not Cash again.
    -- Entry: DR Discounts Allowed / CR Sales Revenue (net_revenue already includes discount)
    IF p_discount_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_discount_acct, 'DEBIT', p_discount_amount, 'Discount allowed to customer (contra-revenue)');

        -- The balancing credit is embedded in v_net_revenue above (gross = net + discount).
        -- No additional credit entry needed — removing the old double-credit line here.
    END IF;

    -- Populate AR sub-ledger for credit sales
    IF p_payment_method = 'credit' AND p_customer_id IS NOT NULL THEN
        INSERT INTO sub_ledger_ar
            (transaction_id, customer_id, reference_type, reference_id,
             txn_date, debit_amount, due_date)
        VALUES
            (v_txn_id, p_customer_id, 'SALE', p_sale_id,
             p_sale_date, p_total_amount, NULL);
    END IF;

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.4  PROCEDURE: post_sale_return_to_ledger
--
--   DR  Sales Returns & Allowances (4100)     refund_amount
--   CR  Cash (1000) / Bank (1100) / AR (1200) refund_amount
--   DR  Inventory (1300)                      cogs_amount   (restocked)
--   CR  Cost of Goods Sold (5000)             cogs_amount
-- ============================================================================
DROP PROCEDURE IF EXISTS post_sale_return_to_ledger $$
CREATE PROCEDURE post_sale_return_to_ledger(
    IN p_return_id       INT,
    IN p_return_date     DATE,
    IN p_refund_amount   DECIMAL(15,2),
    IN p_cogs_amount     DECIMAL(15,2),
    IN p_payment_method  VARCHAR(20),
    IN p_customer_id     INT,
    IN p_posted_by       INT
)
BEGIN
    DECLARE v_txn_id         INT;
    DECLARE v_returns_acct   INT;
    DECLARE v_cash_acct      INT;
    DECLARE v_bank_acct      INT;
    DECLARE v_ar_acct        INT;
    DECLARE v_inventory_acct INT;
    DECLARE v_cogs_acct      INT;
    DECLARE v_credit_acct    INT;
    DECLARE v_period_id      INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_returns_acct   = get_account_id_by_code('4100');
    SET v_cash_acct      = get_account_id_by_code('1000');
    SET v_bank_acct      = get_account_id_by_code('1100');
    SET v_ar_acct        = get_account_id_by_code('1200');
    SET v_inventory_acct = get_account_id_by_code('1300');
    SET v_cogs_acct      = get_account_id_by_code('5000');

    IF p_payment_method = 'credit' THEN
        SET v_credit_acct = v_ar_acct;
    ELSEIF p_payment_method IN ('card','net_banking','upi') THEN
        SET v_credit_acct = v_bank_acct;
    ELSE
        SET v_credit_acct = v_cash_acct;
    END IF;

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_return_date BETWEEN start_date AND end_date LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post sale return: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_return_date, 'SALE_RETURN', p_return_id,
         CONCAT('Sale Return #', p_return_id), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    -- DR Sales Returns (contra-revenue)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_returns_acct, 'DEBIT', p_refund_amount, 'Sales return contra-revenue');

    -- CR Cash/Bank/AR (refund paid out or AR reduced)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_credit_acct, 'CREDIT', p_refund_amount, 'Refund paid to customer');

    -- Restock inventory
    IF p_cogs_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_inventory_acct, 'DEBIT', p_cogs_amount, 'Inventory restocked from return');

        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_cogs_acct, 'CREDIT', p_cogs_amount, 'COGS reversal on stock return');
    END IF;

    IF p_payment_method = 'credit' AND p_customer_id IS NOT NULL THEN
        INSERT INTO sub_ledger_ar
            (transaction_id, customer_id, reference_type, reference_id,
             txn_date, credit_amount)
        VALUES
            (v_txn_id, p_customer_id, 'SALE_RETURN', p_return_id,
             p_return_date, p_refund_amount);
    END IF;

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.5  PROCEDURE: post_purchase_to_ledger
--
--   CASH purchase:
--     DR  Inventory (1300)         total_amount
--     DR  GST Input Credit (1210)  gst_amount
--     CR  Cash (1000) / Bank (1100) total_amount + gst_amount
--
--   CREDIT purchase:
--     DR  Inventory (1300)         total_amount
--     DR  GST Input Credit (1210)  gst_amount
--     CR  Accounts Payable (2000)  total_amount + gst_amount
-- ============================================================================
DROP PROCEDURE IF EXISTS post_purchase_to_ledger $$
CREATE PROCEDURE post_purchase_to_ledger(
    IN p_purchase_id     INT,
    IN p_purchase_date   DATE,
    IN p_total_amount    DECIMAL(15,2),
    IN p_gst_amount      DECIMAL(15,2),
    IN p_payment_method  VARCHAR(20),
    IN p_vendor_id       INT,
    IN p_due_date        DATE,
    IN p_posted_by       INT
)
BEGIN
    DECLARE v_txn_id         INT;
    DECLARE v_inventory_acct INT;
    DECLARE v_gst_input_acct INT;
    DECLARE v_cash_acct      INT;
    DECLARE v_bank_acct      INT;
    DECLARE v_ap_acct        INT;
    DECLARE v_credit_acct    INT;
    DECLARE v_total_payable  DECIMAL(15,2);
    DECLARE v_period_id      INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_inventory_acct = get_account_id_by_code('1300');
    SET v_gst_input_acct = get_account_id_by_code('1210');
    SET v_cash_acct      = get_account_id_by_code('1000');
    SET v_bank_acct      = get_account_id_by_code('1100');
    SET v_ap_acct        = get_account_id_by_code('2000');
    SET v_total_payable  = p_total_amount + p_gst_amount;

    IF p_payment_method = 'credit' THEN
        SET v_credit_acct = v_ap_acct;
    ELSEIF p_payment_method IN ('card','net_banking','upi') THEN
        SET v_credit_acct = v_bank_acct;
    ELSE
        SET v_credit_acct = v_cash_acct;
    END IF;

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_purchase_date BETWEEN start_date AND end_date LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post purchase: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_purchase_date, 'PURCHASE', p_purchase_id,
         CONCAT('Purchase #', p_purchase_id), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    -- DR Inventory (net cost, excluding GST)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_inventory_acct, 'DEBIT', p_total_amount, 'Inventory addition from purchase');

    -- DR GST Input Credit (if > 0)
    IF p_gst_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_gst_input_acct, 'DEBIT', p_gst_amount, 'GST input tax credit on purchase');
    END IF;

    -- CR Cash/Bank/AP
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_credit_acct, 'CREDIT', v_total_payable, 'Payment / payable for purchase');

    -- AP sub-ledger for credit purchases
    IF p_payment_method = 'credit' AND p_vendor_id IS NOT NULL THEN
        INSERT INTO sub_ledger_ap
            (transaction_id, vendor_id, reference_type, reference_id,
             txn_date, credit_amount, due_date)
        VALUES
            (v_txn_id, p_vendor_id, 'PURCHASE', p_purchase_id,
             p_purchase_date, v_total_payable, p_due_date);
    END IF;

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.6  PROCEDURE: post_purchase_return_to_ledger
--
--   DR  Accounts Payable (2000) / Cash (1000) / Bank (1100)  refund_amount
--   CR  Inventory (1300)                                      cost_amount
--   CR  Purchase Returns (5100)                               cost_amount  (contra-expense)
-- ============================================================================
DROP PROCEDURE IF EXISTS post_purchase_return_to_ledger $$
CREATE PROCEDURE post_purchase_return_to_ledger(
    IN p_return_id       INT,
    IN p_return_date     DATE,
    IN p_refund_amount   DECIMAL(15,2),
    IN p_cost_amount     DECIMAL(15,2),
    IN p_payment_method  VARCHAR(20),
    IN p_vendor_id       INT,
    IN p_posted_by       INT
)
BEGIN
    DECLARE v_txn_id         INT;
    DECLARE v_ap_acct        INT;
    DECLARE v_cash_acct      INT;
    DECLARE v_bank_acct      INT;
    DECLARE v_inventory_acct INT;
    DECLARE v_pur_ret_acct   INT;
    DECLARE v_debit_acct     INT;
    DECLARE v_period_id      INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_ap_acct        = get_account_id_by_code('2000');
    SET v_cash_acct      = get_account_id_by_code('1000');
    SET v_bank_acct      = get_account_id_by_code('1100');
    SET v_inventory_acct = get_account_id_by_code('1300');
    SET v_pur_ret_acct   = get_account_id_by_code('5100');

    IF p_payment_method = 'credit' THEN
        SET v_debit_acct = v_ap_acct;
    ELSEIF p_payment_method IN ('card','net_banking','upi') THEN
        SET v_debit_acct = v_bank_acct;
    ELSE
        SET v_debit_acct = v_cash_acct;
    END IF;

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_return_date BETWEEN start_date AND end_date LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post purchase return: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_return_date, 'PURCHASE_RETURN', p_return_id,
         CONCAT('Purchase Return #', p_return_id), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_debit_acct, 'DEBIT', p_refund_amount, 'AP reduced / cash received on return');

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_inventory_acct, 'CREDIT', p_cost_amount, 'Inventory returned to vendor');

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_pur_ret_acct, 'CREDIT', p_cost_amount, 'Purchase return contra-expense');

    IF p_payment_method = 'credit' AND p_vendor_id IS NOT NULL THEN
        INSERT INTO sub_ledger_ap
            (transaction_id, vendor_id, reference_type, reference_id,
             txn_date, debit_amount)
        VALUES
            (v_txn_id, p_vendor_id, 'PURCHASE_RETURN', p_return_id,
             p_return_date, p_refund_amount);
    END IF;

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.7  PROCEDURE: post_expense_to_ledger
--
--   DR  [Expense Account based on account_code]  amount
--   CR  Cash (1000) / Bank (1100) / Accrued (2100)   amount
--
-- Pass the account_code for the specific expense type:
--   5300=Rent | 5400=Electricity | 5410=Water | 5420=Internet
--   5500=Office Supplies | 5510=Tea | 5600=Marketing
--   5700=Transport | 5800=Maintenance | 5900=Bank Charges
--   5910=Subscriptions | 5920=Tax/License | 5950=Misc
-- ============================================================================
DROP PROCEDURE IF EXISTS post_expense_to_ledger $$
CREATE PROCEDURE post_expense_to_ledger(
    IN p_expense_id      INT,
    IN p_expense_date    DATE,
    IN p_amount          DECIMAL(15,2),
    IN p_expense_code    VARCHAR(20),     -- account code e.g. '5300'
    IN p_payment_mode    VARCHAR(20),     -- cash|bank|upi|card|accrued
    IN p_description     VARCHAR(255),
    IN p_posted_by       INT
)
BEGIN
    DECLARE v_txn_id       INT;
    DECLARE v_expense_acct INT;
    DECLARE v_cash_acct    INT;
    DECLARE v_bank_acct    INT;
    DECLARE v_accrued_acct INT;
    DECLARE v_credit_acct  INT;
    DECLARE v_period_id    INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_expense_acct = get_account_id_by_code(p_expense_code);
    SET v_cash_acct    = get_account_id_by_code('1000');
    SET v_bank_acct    = get_account_id_by_code('1100');
    SET v_accrued_acct = get_account_id_by_code('2100');

    IF v_expense_acct IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Invalid expense account code provided';
    END IF;

    IF p_payment_mode IN ('bank','card','upi','net_banking') THEN
        SET v_credit_acct = v_bank_acct;
    ELSEIF p_payment_mode = 'accrued' THEN
        SET v_credit_acct = v_accrued_acct;
    ELSE
        SET v_credit_acct = v_cash_acct;
    END IF;

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_expense_date BETWEEN start_date AND end_date LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post expense: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_expense_date, 'EXPENSE', p_expense_id,
         COALESCE(p_description, CONCAT('Expense #', p_expense_id)), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_expense_acct, 'DEBIT', p_amount, p_description);

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_credit_acct, 'CREDIT', p_amount, 'Payment for expense');

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.8  PROCEDURE: post_payroll_to_ledger
--
--   DR  Salary & Wages Expense (5200)   gross_salary
--   DR  Bonus & Incentives (5210)       bonus_amount  (if > 0)
--   DR  Overtime Expense (5220)         overtime_amount (if > 0)
--   CR  Salary Payable (2300)           net_salary
--   CR  TDS Payable (2400)              tds_amount     (if > 0)
-- ============================================================================
DROP PROCEDURE IF EXISTS post_payroll_to_ledger $$
CREATE PROCEDURE post_payroll_to_ledger(
    IN p_salary_id      INT,
    IN p_payment_date   DATE,
    IN p_base_salary    DECIMAL(15,2),
    IN p_bonus          DECIMAL(15,2),
    IN p_overtime_amt   DECIMAL(15,2),
    IN p_tds_amount     DECIMAL(15,2),
    IN p_net_salary     DECIMAL(15,2),
    IN p_posted_by      INT
)
BEGIN
    DECLARE v_txn_id         INT;
    DECLARE v_salary_acct    INT;
    DECLARE v_bonus_acct     INT;
    DECLARE v_overtime_acct  INT;
    DECLARE v_sal_pay_acct   INT;
    DECLARE v_tds_acct       INT;
    DECLARE v_period_id      INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_salary_acct   = get_account_id_by_code('5200');
    SET v_bonus_acct    = get_account_id_by_code('5210');
    SET v_overtime_acct = get_account_id_by_code('5220');
    SET v_sal_pay_acct  = get_account_id_by_code('2300');
    SET v_tds_acct      = get_account_id_by_code('2400');

    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_payment_date BETWEEN start_date AND end_date LIMIT 1;

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post payroll: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_payment_date, 'PAYROLL', p_salary_id,
         CONCAT('Payroll #', p_salary_id), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    -- DR Base Salary Expense
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_salary_acct, 'DEBIT', p_base_salary, 'Base salary expense');

    -- DR Bonus (if any)
    IF p_bonus > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_bonus_acct, 'DEBIT', p_bonus, 'Bonus / incentive expense');
    END IF;

    -- DR Overtime (if any)
    IF p_overtime_amt > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_overtime_acct, 'DEBIT', p_overtime_amt, 'Overtime pay expense');
    END IF;

    -- CR Salary Payable (net after TDS)
    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_sal_pay_acct, 'CREDIT', p_net_salary, 'Net salary payable to employee');

    -- CR TDS Payable
    IF p_tds_amount > 0 THEN
        INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
        VALUES (v_txn_id, v_tds_acct, 'CREDIT', p_tds_amount, 'TDS deducted and payable to government');
    END IF;

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.9  PROCEDURE: post_capital_injection_to_ledger
-- Records owner putting money into the business.
--   DR  Cash (1000) / Bank (1100)   amount
--   CR  Owner Capital (3000)        amount
-- ============================================================================
DROP PROCEDURE IF EXISTS post_capital_injection_to_ledger $$
CREATE PROCEDURE post_capital_injection_to_ledger(
    IN p_reference_id   INT,
    IN p_txn_date       DATE,
    IN p_amount         DECIMAL(15,2),
    IN p_payment_mode   VARCHAR(20),
    IN p_description    VARCHAR(255),
    IN p_posted_by      INT
)
BEGIN
    DECLARE v_txn_id      INT;
    DECLARE v_cash_acct   INT;
    DECLARE v_bank_acct   INT;
    DECLARE v_capital_acct INT;
    DECLARE v_debit_acct  INT;
    DECLARE v_period_id   INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET v_cash_acct    = get_account_id_by_code('1000');
    SET v_bank_acct    = get_account_id_by_code('1100');
    SET v_capital_acct = get_account_id_by_code('3000');

    SET v_debit_acct = IF(p_payment_mode IN ('bank','upi','card'), v_bank_acct, v_cash_acct);

    -- FIX (Issue 3): Guard against missing/closed accounting period.
    SELECT period_id INTO v_period_id
    FROM accounting_periods
    WHERE status='OPEN' AND p_txn_date BETWEEN start_date AND end_date LIMIT 1;

    IF v_period_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot post capital injection: no OPEN accounting period found for this date.';
    END IF;

    START TRANSACTION;

    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, p_txn_date, 'CAPITAL', p_reference_id,
         COALESCE(p_description, 'Capital injection by owner'), p_posted_by);
    SET v_txn_id = LAST_INSERT_ID();

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_debit_acct, 'DEBIT', p_amount, 'Cash/Bank received from owner');

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    VALUES (v_txn_id, v_capital_acct, 'CREDIT', p_amount, 'Owner capital contribution');

    CALL validate_and_post(v_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.10  PROCEDURE: void_journal_entry
-- Reverses a transaction by creating an equal and opposite journal entry.
-- Original entry is NOT deleted — is_voided is set to TRUE.
-- ============================================================================
DROP PROCEDURE IF EXISTS void_journal_entry $$
CREATE PROCEDURE void_journal_entry(
    IN p_transaction_id  INT,
    IN p_void_reason     VARCHAR(255),
    IN p_voided_by       INT
)
BEGIN
    DECLARE v_void_txn_id  INT;
    DECLARE v_txn_date     DATE;
    DECLARE v_ref_type     VARCHAR(50);
    DECLARE v_ref_id       INT;
    DECLARE v_period_id    INT;
    DECLARE v_already_void BOOLEAN;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- Guard: prevent double void
    SELECT is_voided, transaction_date, reference_type, reference_id, period_id
    INTO v_already_void, v_txn_date, v_ref_type, v_ref_id, v_period_id
    FROM transactions WHERE transaction_id = p_transaction_id;

    IF v_already_void THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transaction is already voided';
    END IF;

    START TRANSACTION;

    -- Mark original as voided
    UPDATE transactions
    SET is_voided  = TRUE,
        void_reason = p_void_reason,
        voided_by   = p_voided_by,
        voided_at   = NOW()
    WHERE transaction_id = p_transaction_id;

    -- Create reversal journal (swaps DEBIT ↔ CREDIT)
    INSERT INTO transactions
        (period_id, transaction_date, reference_type, reference_id, description, posted_by)
    VALUES
        (v_period_id, CURDATE(), 'VOID', p_transaction_id,
         CONCAT('VOID of Txn #', p_transaction_id, ': ', p_void_reason), p_voided_by);
    SET v_void_txn_id = LAST_INSERT_ID();

    INSERT INTO transaction_lines (transaction_id, account_id, entry_type, amount, description)
    SELECT
        v_void_txn_id,
        account_id,
        CASE entry_type WHEN 'DEBIT' THEN 'CREDIT' ELSE 'DEBIT' END,
        amount,
        CONCAT('Reversal of Line #', line_id)
    FROM transaction_lines
    WHERE transaction_id = p_transaction_id;

    CALL validate_and_post(v_void_txn_id);
    COMMIT;
END $$

-- ============================================================================
-- 8.11  PROCEDURE: open_accounting_period
-- Creates a new monthly accounting period.
-- ============================================================================
DROP PROCEDURE IF EXISTS open_accounting_period $$
CREATE PROCEDURE open_accounting_period(
    IN p_period_name  VARCHAR(30),
    IN p_start_date   DATE,
    IN p_end_date     DATE,
    IN p_created_by   INT
)
BEGIN
    INSERT INTO accounting_periods (period_name, period_type, start_date, end_date, status)
    VALUES (p_period_name, 'MONTHLY', p_start_date, p_end_date, 'OPEN');
END $$

-- ============================================================================
-- 8.12  PROCEDURE: close_accounting_period
-- Closes a period so no new entries can be posted to it.
-- Triggers rebuild_period_balances for reporting cache.
-- ============================================================================
DROP PROCEDURE IF EXISTS close_accounting_period $$
CREATE PROCEDURE close_accounting_period(
    IN p_period_id  INT,
    IN p_closed_by  INT,
    IN p_notes      VARCHAR(255)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    UPDATE accounting_periods
    SET status    = 'CLOSED',
        closed_by = p_closed_by,
        closed_at = NOW(),
        notes     = p_notes
    WHERE period_id = p_period_id AND status = 'OPEN';

    IF ROW_COUNT() = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Period not found or already closed';
    END IF;

    -- Rebuild balance cache for the closed period
    CALL rebuild_period_balances(p_period_id);

    COMMIT;
END $$

-- ============================================================================
-- 8.13  PROCEDURE: rebuild_period_balances
-- Recomputes account_period_balances for a given period.
-- Called automatically on period close; can be called manually for repairs.
-- ============================================================================
DROP PROCEDURE IF EXISTS rebuild_period_balances $$
CREATE PROCEDURE rebuild_period_balances(IN p_period_id INT)
BEGIN
    DECLARE v_start DATE;
    DECLARE v_end   DATE;

    SELECT start_date, end_date INTO v_start, v_end
    FROM accounting_periods WHERE period_id = p_period_id;

    -- Remove stale cache
    DELETE FROM account_period_balances WHERE period_id = p_period_id;

    -- Reinsert computed balances
    INSERT INTO account_period_balances
        (period_id, account_id, opening_balance, total_debits, total_credits, closing_balance)
    SELECT
        p_period_id,
        coa.account_id,
        -- Opening balance = balance as of one day before period start
        get_account_balance(coa.account_id, DATE_SUB(v_start, INTERVAL 1 DAY)),
        -- Period debits
        COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  THEN tl.amount ELSE 0 END), 0),
        -- Period credits
        COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' THEN tl.amount ELSE 0 END), 0),
        -- Closing balance
        get_account_balance(coa.account_id, v_end)
    FROM chart_of_accounts coa
    LEFT JOIN transaction_lines tl ON tl.account_id = coa.account_id
    LEFT JOIN transactions      t  ON t.transaction_id = tl.transaction_id
                                   AND t.transaction_date BETWEEN v_start AND v_end
                                   AND t.is_voided = FALSE
    GROUP BY coa.account_id;
END $$

DELIMITER ;


-- ============================================================================
-- SECTION 9 — FINANCIAL REPORT VIEWS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 9.1  v_general_ledger
-- All transactions with account details — the complete audit record
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_general_ledger AS
SELECT
    t.transaction_id,
    t.transaction_date,
    ap.period_name,
    t.reference_type,
    t.reference_id,
    t.description                           AS journal_description,
    coa.account_code,
    coa.account_name,
    coa.account_type,
    tl.entry_type,
    tl.amount,
    CASE
        WHEN tl.entry_type = 'DEBIT'  THEN tl.amount
        ELSE 0
    END                                     AS debit_amount,
    CASE
        WHEN tl.entry_type = 'CREDIT' THEN tl.amount
        ELSE 0
    END                                     AS credit_amount,
    tl.description                          AS line_description,
    t.is_voided,
    CONCAT(u.full_name, '')                 AS posted_by,
    t.created_at
FROM transaction_lines tl
JOIN transactions       t   ON t.transaction_id   = tl.transaction_id
JOIN chart_of_accounts  coa ON coa.account_id     = tl.account_id
LEFT JOIN accounting_periods ap ON ap.period_id   = t.period_id
LEFT JOIN Users          u   ON u.user_id          = t.posted_by
ORDER BY t.transaction_date, t.transaction_id, tl.line_id;

-- ----------------------------------------------------------------------------
-- 9.2  v_trial_balance
-- All account balances as of today — debits and credits in separate columns
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_trial_balance AS
SELECT
    coa.account_code,
    coa.account_name,
    coa.account_type,
    coa.normal_balance,
    COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0) AS total_debits,
    COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0) AS total_credits,
    CASE coa.normal_balance
        WHEN 'DEBIT'  THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
        WHEN 'CREDIT' THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
    END                                             AS net_balance,
    coa.is_active
FROM chart_of_accounts coa
LEFT JOIN transaction_lines tl  ON tl.account_id     = coa.account_id
LEFT JOIN transactions       t  ON t.transaction_id  = tl.transaction_id
WHERE coa.is_active = TRUE
GROUP BY coa.account_id, coa.account_code, coa.account_name,
         coa.account_type, coa.normal_balance, coa.is_active
ORDER BY coa.account_code;

-- ----------------------------------------------------------------------------
-- 9.3  v_profit_and_loss
-- Revenue vs Expenses — Gross Profit and Net Profit calculated
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_profit_and_loss AS
SELECT
    coa.account_type,
    coa.account_code,
    coa.account_name,
    coa.normal_balance,
    CASE coa.normal_balance
        WHEN 'CREDIT' THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
        WHEN 'DEBIT' THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END), 0)
    END                                              AS period_amount,
    CASE
        WHEN coa.account_type = 'REVENUE' THEN 'Income'
        WHEN coa.account_code = '5000'    THEN 'Cost of Sales'
        WHEN coa.account_type = 'EXPENSE' THEN 'Operating Expense'
    END                                              AS pnl_section
FROM chart_of_accounts coa
LEFT JOIN transaction_lines tl  ON tl.account_id    = coa.account_id
LEFT JOIN transactions       t  ON t.transaction_id = tl.transaction_id
WHERE coa.account_type IN ('REVENUE','EXPENSE')
  AND coa.is_active = TRUE
GROUP BY coa.account_id, coa.account_code, coa.account_name,
         coa.account_type, coa.normal_balance
ORDER BY coa.account_type DESC, coa.account_code;

-- ----------------------------------------------------------------------------
-- 9.4  v_balance_sheet
-- Assets, Liabilities, and Equity snapshot
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_balance_sheet AS
SELECT
    coa.account_type,
    coa.account_code,
    coa.account_name,
    CASE coa.normal_balance
        WHEN 'DEBIT'  THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END),0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END),0)
        WHEN 'CREDIT' THEN
            COALESCE(SUM(CASE WHEN tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount ELSE 0 END),0)
          - COALESCE(SUM(CASE WHEN tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN tl.amount ELSE 0 END),0)
    END                                              AS balance,
    CASE coa.account_type
        WHEN 'ASSET'     THEN 1
        WHEN 'LIABILITY' THEN 2
        WHEN 'EQUITY'    THEN 3
    END                                              AS display_order
FROM chart_of_accounts coa
LEFT JOIN transaction_lines tl  ON tl.account_id    = coa.account_id
LEFT JOIN transactions       t  ON t.transaction_id = tl.transaction_id
WHERE coa.account_type IN ('ASSET','LIABILITY','EQUITY')
  AND coa.is_active = TRUE
GROUP BY coa.account_id, coa.account_code, coa.account_name,
         coa.account_type, coa.normal_balance
ORDER BY display_order, coa.account_code;

-- ----------------------------------------------------------------------------
-- 9.5  v_accounts_receivable_aging
-- Outstanding customer balances grouped by age bucket
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_accounts_receivable_aging AS
SELECT
    c.customer_id,
    c.customer_name,
    c.phone,
    SUM(ar.debit_amount - ar.credit_amount)             AS total_outstanding,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ar.txn_date) <= 30
             THEN ar.debit_amount - ar.credit_amount ELSE 0 END) AS `0-30_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ar.txn_date) BETWEEN 31 AND 60
             THEN ar.debit_amount - ar.credit_amount ELSE 0 END) AS `31-60_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ar.txn_date) BETWEEN 61 AND 90
             THEN ar.debit_amount - ar.credit_amount ELSE 0 END) AS `61-90_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ar.txn_date) > 90
             THEN ar.debit_amount - ar.credit_amount ELSE 0 END) AS `90plus_days`,
    MAX(ar.txn_date)                                    AS last_transaction_date
FROM sub_ledger_ar ar
JOIN Customers c ON c.customer_id = ar.customer_id
WHERE ar.is_settled = FALSE
GROUP BY c.customer_id, c.customer_name, c.phone
HAVING total_outstanding > 0
ORDER BY total_outstanding DESC;

-- ----------------------------------------------------------------------------
-- 9.6  v_accounts_payable_aging
-- Outstanding vendor payables grouped by age bucket
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_accounts_payable_aging AS
SELECT
    v.vendor_id,
    v.vendor_name,
    v.phone,
    SUM(ap.credit_amount - ap.debit_amount)             AS total_outstanding,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ap.txn_date) <= 30
             THEN ap.credit_amount - ap.debit_amount ELSE 0 END) AS `0-30_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ap.txn_date) BETWEEN 31 AND 60
             THEN ap.credit_amount - ap.debit_amount ELSE 0 END) AS `31-60_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ap.txn_date) BETWEEN 61 AND 90
             THEN ap.credit_amount - ap.debit_amount ELSE 0 END) AS `61-90_days`,
    SUM(CASE WHEN DATEDIFF(CURDATE(), ap.txn_date) > 90
             THEN ap.credit_amount - ap.debit_amount ELSE 0 END) AS `90plus_days`,
    MIN(ap.due_date)                                    AS earliest_due_date
FROM sub_ledger_ap ap
JOIN Vendors v ON v.vendor_id = ap.vendor_id
WHERE ap.is_settled = FALSE
GROUP BY v.vendor_id, v.vendor_name, v.phone
HAVING total_outstanding > 0
ORDER BY earliest_due_date ASC;

-- ----------------------------------------------------------------------------
-- 9.7  v_cash_flow_summary
-- Monthly cash and bank movements grouped by reference type
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cash_flow_summary AS
SELECT
    DATE_FORMAT(t.transaction_date, '%Y-%m')            AS month,
    t.reference_type,
    SUM(CASE WHEN tl.entry_type='DEBIT'  AND coa.account_code IN ('1000','1100','1150')
             THEN tl.amount ELSE 0 END)                 AS cash_inflow,
    SUM(CASE WHEN tl.entry_type='CREDIT' AND coa.account_code IN ('1000','1100','1150')
             THEN tl.amount ELSE 0 END)                 AS cash_outflow,
    SUM(CASE WHEN tl.entry_type='DEBIT'  AND coa.account_code IN ('1000','1100','1150')
             THEN tl.amount ELSE 0 END)
  - SUM(CASE WHEN tl.entry_type='CREDIT' AND coa.account_code IN ('1000','1100','1150')
             THEN tl.amount ELSE 0 END)                 AS net_cash_flow
FROM transaction_lines tl
JOIN transactions      t   ON t.transaction_id  = tl.transaction_id
JOIN chart_of_accounts coa ON coa.account_id    = tl.account_id
WHERE t.is_voided = FALSE
  AND coa.account_code IN ('1000','1100','1150')
GROUP BY DATE_FORMAT(t.transaction_date, '%Y-%m'), t.reference_type
ORDER BY month DESC, t.reference_type;

-- ----------------------------------------------------------------------------
-- 9.8  v_expense_analysis
-- Monthly expense breakdown by account — feeds the Expense Report
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_expense_analysis AS
SELECT
    DATE_FORMAT(t.transaction_date, '%Y-%m')            AS month,
    coa.account_code,
    coa.account_name,
    COUNT(DISTINCT t.transaction_id)                    AS transaction_count,
    SUM(tl.amount)                                      AS total_expense
FROM transaction_lines tl
JOIN transactions      t   ON t.transaction_id  = tl.transaction_id
JOIN chart_of_accounts coa ON coa.account_id    = tl.account_id
WHERE coa.account_type = 'EXPENSE'
  AND tl.entry_type    = 'DEBIT'
  AND t.is_voided      = FALSE
GROUP BY DATE_FORMAT(t.transaction_date, '%Y-%m'), coa.account_id,
         coa.account_code, coa.account_name
ORDER BY month DESC, total_expense DESC;

-- ----------------------------------------------------------------------------
-- 9.9  v_vendor_outstanding
-- Full outstanding payable per vendor including overdue flag
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_vendor_outstanding AS
SELECT
    v.vendor_id,
    v.vendor_name,
    v.phone,
    v.credit_period_days,
    ap.reference_type,
    ap.reference_id,
    ap.txn_date,
    ap.due_date,
    (ap.credit_amount - ap.debit_amount)                AS outstanding_amount,
    DATEDIFF(CURDATE(), ap.due_date)                    AS days_overdue,
    CASE
        WHEN ap.due_date IS NULL             THEN 'NO DUE DATE'
        WHEN CURDATE() > ap.due_date         THEN 'OVERDUE'
        WHEN DATEDIFF(ap.due_date, CURDATE()) <= 7 THEN 'DUE SOON'
        ELSE 'CURRENT'
    END                                                 AS payment_status
FROM sub_ledger_ap ap
JOIN Vendors v ON v.vendor_id = ap.vendor_id
WHERE ap.is_settled = FALSE
  AND (ap.credit_amount - ap.debit_amount) > 0
ORDER BY days_overdue DESC;

-- ----------------------------------------------------------------------------
-- 9.10  v_customer_outstanding
-- Full outstanding receivable per customer including overdue flag
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_customer_outstanding AS
SELECT
    c.customer_id,
    c.customer_name,
    c.phone,
    ar.reference_type,
    ar.reference_id,
    ar.txn_date,
    ar.due_date,
    (ar.debit_amount - ar.credit_amount)                AS outstanding_amount,
    DATEDIFF(CURDATE(), ar.due_date)                    AS days_overdue,
    CASE
        WHEN ar.due_date IS NULL             THEN 'NO DUE DATE'
        WHEN CURDATE() > ar.due_date         THEN 'OVERDUE'
        WHEN DATEDIFF(ar.due_date, CURDATE()) <= 7 THEN 'DUE SOON'
        ELSE 'CURRENT'
    END                                                 AS collection_status
FROM sub_ledger_ar ar
JOIN Customers c ON c.customer_id = ar.customer_id
WHERE ar.is_settled = FALSE
  AND (ar.debit_amount - ar.credit_amount) > 0
ORDER BY days_overdue DESC;

-- ----------------------------------------------------------------------------
-- 9.11  v_monthly_pnl_trend
-- 12-month rolling P&L — Revenue, COGS, Gross Profit, Expenses, Net Profit
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_pnl_trend AS
SELECT
    DATE_FORMAT(t.transaction_date, '%Y-%m')            AS month,
    SUM(CASE
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='CREDIT' AND t.is_voided=FALSE
        THEN tl.amount
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='DEBIT'  AND t.is_voided=FALSE
        THEN -tl.amount
        ELSE 0 END)                                     AS total_revenue,
    SUM(CASE
        WHEN coa.account_code='5000' AND tl.entry_type='DEBIT' AND t.is_voided=FALSE
        THEN tl.amount ELSE 0 END)                      AS cost_of_goods_sold,
    SUM(CASE
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN -tl.amount
        ELSE 0 END)
      - SUM(CASE
        WHEN coa.account_code='5000' AND tl.entry_type='DEBIT' AND t.is_voided=FALSE
        THEN tl.amount ELSE 0 END)                      AS gross_profit,
    SUM(CASE
        WHEN coa.account_type='EXPENSE' AND coa.account_code != '5000'
             AND tl.entry_type='DEBIT' AND t.is_voided=FALSE THEN tl.amount
        WHEN coa.account_type='EXPENSE' AND coa.account_code != '5000'
             AND tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN -tl.amount
        ELSE 0 END)                                     AS operating_expenses,
    -- Net Profit = Gross Profit - Operating Expenses
    (
    SUM(CASE
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='CREDIT' AND t.is_voided=FALSE THEN tl.amount
        WHEN coa.account_type='REVENUE' AND coa.normal_balance='CREDIT'
             AND tl.entry_type='DEBIT'  AND t.is_voided=FALSE THEN -tl.amount
        ELSE 0 END)
    - SUM(CASE
        WHEN coa.account_type='EXPENSE' AND tl.entry_type='DEBIT' AND t.is_voided=FALSE
        THEN tl.amount
        WHEN coa.account_type='EXPENSE' AND tl.entry_type='CREDIT' AND t.is_voided=FALSE
        THEN -tl.amount
        ELSE 0 END)
    )                                                   AS net_profit
FROM transaction_lines tl
JOIN transactions      t   ON t.transaction_id  = tl.transaction_id
JOIN chart_of_accounts coa ON coa.account_id    = tl.account_id
WHERE t.transaction_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
GROUP BY DATE_FORMAT(t.transaction_date, '%Y-%m')
ORDER BY month DESC;


-- ============================================================================
-- END OF ACCOUNTING ENGINE
-- ============================================================================
-- Summary of additions:
--
-- TABLES (8 new):
--   accounting_periods, transactions (rebuilt), transaction_lines (rebuilt),
--   account_period_balances, sub_ledger_ar, sub_ledger_ap,
--   reconciliation_sessions, reconciliation_items
--
-- CHART OF ACCOUNTS (31 accounts total):
--   Assets: 1000, 1100, 1150, 1200, 1210, 1300, 1400, 1500
--   Liabilities: 2000, 2100, 2200, 2300, 2400, 2500, 2600
--   Equity: 3000, 3100, 3200
--   Revenue: 4000, 4100, 4200, 4300
--   Expenses: 5000, 5100, 5200, 5210, 5220, 5300, 5400, 5410, 5420,
--             5500, 5510, 5600, 5700, 5800, 5810, 5900, 5910, 5920, 5950
--
-- FUNCTIONS (2):
--   get_account_id_by_code, get_account_balance
--
-- PROCEDURES (13):
--   validate_and_post, post_sale_to_ledger, post_sale_return_to_ledger,
--   post_purchase_to_ledger, post_purchase_return_to_ledger,
--   post_expense_to_ledger, post_payroll_to_ledger,
--   post_capital_injection_to_ledger, void_journal_entry,
--   open_accounting_period, close_accounting_period,
--   rebuild_period_balances, create_ledger_transaction (legacy kept),
--   validate_transaction_balance (legacy kept)
--
-- VIEWS (11):
--   v_general_ledger, v_trial_balance, v_profit_and_loss,
--   v_balance_sheet, v_accounts_receivable_aging,
--   v_accounts_payable_aging, v_cash_flow_summary,
--   v_expense_analysis, v_vendor_outstanding,
--   v_customer_outstanding, v_monthly_pnl_trend
-- ============================================================================
