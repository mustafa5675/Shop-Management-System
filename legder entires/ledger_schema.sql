-- ============================================================================
-- CORE ACCOUNTING LEDGER STRUCTURE
-- Double-Entry Accounting System for Shop Management
-- ============================================================================
-- 
-- DESIGN PRINCIPLES:
-- 1. Append-only ledger (no updates/deletes on ledger tables)
-- 2. Every transaction must balance (total debits = total credits)
-- 3. Ledger is the ultimate source of truth for accounting
-- 4. Operational tables (Sales, Purchases, etc.) reference ledger transactions
-- 5. No running balances stored - calculated on-demand from transaction lines
--
-- USAGE:
-- When a Sale, Purchase, Expense, Payroll, or Return occurs:
-- 1. Insert operational record (Sales, Purchases, etc.)
-- 2. Create a transaction header in 'transactions' table
-- 3. Insert balanced debit/credit lines in 'transaction_lines' table
-- 4. Reference the operational record via reference_type and reference_id
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CHART OF ACCOUNTS
-- ----------------------------------------------------------------------------
-- Defines all accounts used in the accounting system
-- Account codes follow a hierarchical structure (e.g., 1000s = Assets)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `chart_of_accounts` (
    `account_id` INT AUTO_INCREMENT NOT NULL,
    `account_code` VARCHAR(20) NOT NULL UNIQUE COMMENT 'Hierarchical account code (e.g., 1000, 1100, 2000)',
    `account_name` VARCHAR(100) NOT NULL COMMENT 'Display name of the account',
    `account_type` ENUM('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE') NOT NULL COMMENT 'Accounting category',
    `normal_balance` ENUM('DEBIT', 'CREDIT') NOT NULL COMMENT 'Normal balance side for this account type',
    `parent_account_id` INT NULL COMMENT 'For hierarchical account structure (optional)',
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Active accounts can be used in transactions',
    `description` VARCHAR(255) NULL COMMENT 'Account description/notes',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`account_id`),
    INDEX `idx_account_code` (`account_code`),
    INDEX `idx_account_type` (`account_type`),
    INDEX `idx_parent` (`parent_account_id`),
    FOREIGN KEY (`parent_account_id`) REFERENCES `chart_of_accounts`(`account_id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Master list of all accounts in the accounting system';

-- ----------------------------------------------------------------------------
-- TRANSACTIONS (Transaction Header)
-- ----------------------------------------------------------------------------
-- Represents a single accounting event (e.g., a sale, purchase, expense)
-- Each transaction must have balanced debit/credit lines
-- Links to operational tables via reference_type and reference_id
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `transactions` (
    `transaction_id` INT AUTO_INCREMENT NOT NULL,
    `transaction_date` DATE NOT NULL COMMENT 'Accounting date of the transaction',
    `reference_type` VARCHAR(50) NOT NULL COMMENT 'Type of source document: SALES, PURCHASE, EXPENSE, PAYROLL, SALES_RETURN, PURCHASE_RETURN, ADJUSTMENT, etc.',
    `reference_id` INT NOT NULL COMMENT 'ID from the source table (e.g., Sales_ID, Purchase_ID, Salary_ID)',
    `description` VARCHAR(255) NOT NULL COMMENT 'Human-readable description of the transaction',
    `created_by` VARCHAR(100) NULL COMMENT 'User/system that created this transaction',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'System timestamp - immutable',
    `updated_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'For corrections only - original record preserved',
    `is_voided` BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'If true, transaction is reversed (via offsetting entry)',
    `void_reason` VARCHAR(255) NULL COMMENT 'Reason for voiding (if applicable)',
    PRIMARY KEY (`transaction_id`),
    INDEX `idx_transaction_date` (`transaction_date`),
    INDEX `idx_reference` (`reference_type`, `reference_id`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Header table for accounting transactions. Each transaction represents one accounting event.';

-- ----------------------------------------------------------------------------
-- TRANSACTION LINES (Debit/Credit Entries)
-- ----------------------------------------------------------------------------
-- Individual debit/credit entries that make up a transaction
-- Each transaction must have at least 2 lines (one debit, one credit)
-- Total debits must equal total credits per transaction
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `transaction_lines` (
    `line_id` INT AUTO_INCREMENT NOT NULL,
    `transaction_id` INT NOT NULL COMMENT 'Links to transactions table',
    `account_id` INT NOT NULL COMMENT 'Links to chart_of_accounts table',
    `entry_type` ENUM('DEBIT', 'CREDIT') NOT NULL COMMENT 'Whether this is a debit or credit entry',
    `amount` DECIMAL(15,2) NOT NULL COMMENT 'Amount (always positive, entry_type determines debit/credit)',
    `description` VARCHAR(255) NULL COMMENT 'Line item description (optional)',
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'System timestamp - immutable',
    PRIMARY KEY (`line_id`),
    INDEX `idx_transaction` (`transaction_id`),
    INDEX `idx_account` (`account_id`),
    INDEX `idx_transaction_account` (`transaction_id`, `account_id`),
    FOREIGN KEY (`transaction_id`) REFERENCES `transactions`(`transaction_id`) ON DELETE RESTRICT,
    FOREIGN KEY (`account_id`) REFERENCES `chart_of_accounts`(`account_id`) ON DELETE RESTRICT,
    CONSTRAINT `chk_amount_positive` CHECK (`amount` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual debit/credit entries. Each transaction must have balanced debits and credits.';

-- ----------------------------------------------------------------------------
-- STORED PROCEDURE: Create Balanced Transaction
-- ----------------------------------------------------------------------------
-- Inserts a transaction header and all lines atomically, ensuring balance
-- This is the recommended way to create ledger entries
-- 
-- Usage:
--   CALL create_ledger_transaction(
--       '2024-01-15',           -- transaction_date
--       'SALES',                 -- reference_type
--       100,                     -- reference_id
--       'Sale of Product X',     -- description
--       'user123',               -- created_by
--       @transaction_id          -- output parameter
--   );
--   Then insert lines using the returned transaction_id
-- ----------------------------------------------------------------------------
DELIMITER $$

CREATE PROCEDURE `create_ledger_transaction`(
    IN p_transaction_date DATE,
    IN p_reference_type VARCHAR(50),
    IN p_reference_id INT,
    IN p_description VARCHAR(255),
    IN p_created_by VARCHAR(100),
    OUT p_transaction_id INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;
    
    START TRANSACTION;
    
    -- Insert transaction header
    INSERT INTO `transactions` (
        `transaction_date`,
        `reference_type`,
        `reference_id`,
        `description`,
        `created_by`
    ) VALUES (
        p_transaction_date,
        p_reference_type,
        p_reference_id,
        p_description,
        p_created_by
    );
    
    SET p_transaction_id = LAST_INSERT_ID();
    
    COMMIT;
END$$

-- ----------------------------------------------------------------------------
-- STORED PROCEDURE: Validate Transaction Balance
-- ----------------------------------------------------------------------------
-- Validates that a transaction has balanced debits and credits
-- Returns 1 if balanced, 0 if not balanced
-- ----------------------------------------------------------------------------
CREATE PROCEDURE `validate_transaction_balance`(
    IN p_transaction_id INT,
    OUT p_is_balanced TINYINT
)
BEGIN
    DECLARE total_debits DECIMAL(15,2);
    DECLARE total_credits DECIMAL(15,2);
    
    SELECT 
        COALESCE(SUM(CASE WHEN `entry_type` = 'DEBIT' THEN `amount` ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN `entry_type` = 'CREDIT' THEN `amount` ELSE 0 END), 0)
    INTO total_debits, total_credits
    FROM `transaction_lines`
    WHERE `transaction_id` = p_transaction_id;
    
    -- Check if balanced (allow small rounding differences of 0.01)
    IF ABS(total_debits - total_credits) <= 0.01 THEN
        SET p_is_balanced = 1;
    ELSE
        SET p_is_balanced = 0;
    END IF;
END$$

DELIMITER ;

-- ----------------------------------------------------------------------------
-- IMPORTANT: Transaction Balance Validation
-- ----------------------------------------------------------------------------
-- The ledger enforces double-entry accounting through application logic:
-- 
-- 1. Always insert all transaction lines within a single database transaction
-- 2. After inserting all lines, call validate_transaction_balance() procedure
-- 3. If not balanced, rollback the entire transaction
-- 
-- Example Python pattern:
--   BEGIN TRANSACTION
--   INSERT INTO transactions (...) VALUES (...)
--   transaction_id = last_insert_id()
--   INSERT INTO transaction_lines (...) VALUES (...)
--   INSERT INTO transaction_lines (...) VALUES (...)
--   CALL validate_transaction_balance(transaction_id, @balanced)
--   IF @balanced = 0 THEN ROLLBACK ELSE COMMIT
-- 
-- Note: Direct INSERTs into transaction_lines are allowed, but you MUST
-- ensure balance validation happens before committing.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- INITIAL CHART OF ACCOUNTS DATA
-- ----------------------------------------------------------------------------
-- Pre-populated accounts for a small retail + wholesale business
-- Account codes follow standard numbering:
--   1000-1999: Assets
--   2000-2999: Liabilities
--   3000-3999: Equity
--   4000-4999: Revenue
--   5000-5999: Expenses
-- ----------------------------------------------------------------------------

-- ASSETS (1000-1999)
INSERT INTO `chart_of_accounts` (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`) VALUES
('1000', 'Cash', 'ASSET', 'DEBIT', 'Physical cash on hand'),
('1100', 'Bank Account', 'ASSET', 'DEBIT', 'Primary business bank account'),
('1200', 'Accounts Receivable', 'ASSET', 'DEBIT', 'Amounts owed by customers'),
('1300', 'Inventory', 'ASSET', 'DEBIT', 'Products held for sale'),
('1400', 'Prepaid Expenses', 'ASSET', 'DEBIT', 'Expenses paid in advance');

-- LIABILITIES (2000-2999)
INSERT INTO `chart_of_accounts` (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`) VALUES
('2000', 'Accounts Payable', 'LIABILITY', 'CREDIT', 'Amounts owed to vendors/suppliers'),
('2100', 'Accrued Expenses', 'LIABILITY', 'CREDIT', 'Expenses incurred but not yet paid'),
('2200', 'Sales Tax Payable', 'LIABILITY', 'CREDIT', 'Sales tax collected from customers');

-- EQUITY (3000-3999)
INSERT INTO `chart_of_accounts` (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`) VALUES
('3000', 'Owner Capital', 'EQUITY', 'CREDIT', 'Owner investment in the business'),
('3100', 'Retained Earnings', 'EQUITY', 'CREDIT', 'Accumulated profits');

-- REVENUE (4000-4999)
INSERT INTO `chart_of_accounts` (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`) VALUES
('4000', 'Sales Revenue', 'REVENUE', 'CREDIT', 'Revenue from product sales'),
('4100', 'Sales Returns', 'REVENUE', 'DEBIT', 'Returns and refunds (contra-revenue account)'),
('4200', 'Discounts Allowed', 'REVENUE', 'DEBIT', 'Discounts given to customers (contra-revenue)');

-- EXPENSES (5000-5999)
INSERT INTO `chart_of_accounts` (`account_code`, `account_name`, `account_type`, `normal_balance`, `description`) VALUES
('5000', 'Cost of Goods Sold', 'EXPENSE', 'DEBIT', 'Direct cost of products sold'),
('5100', 'Purchase Returns', 'EXPENSE', 'CREDIT', 'Returns to suppliers (contra-expense account)'),
('5200', 'Salary Expense', 'EXPENSE', 'DEBIT', 'Employee salaries and wages'),
('5300', 'Rent Expense', 'EXPENSE', 'DEBIT', 'Rental expenses'),
('5400', 'Utilities Expense', 'EXPENSE', 'DEBIT', 'Electricity, water, internet, etc.'),
('5500', 'Office Supplies Expense', 'EXPENSE', 'DEBIT', 'Office supplies and materials'),
('5600', 'Marketing Expense', 'EXPENSE', 'DEBIT', 'Advertising and marketing costs'),
('5700', 'Other Expenses', 'EXPENSE', 'DEBIT', 'Miscellaneous expenses');
