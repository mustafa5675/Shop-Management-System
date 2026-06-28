-- ============================================================================
-- FINANCIAL STREAMS — REVENUE TRACKING, EXPENSE LEDGER & CASH FLOW
-- Run AFTER shop_management.sql and accounting_ledger.sql
-- ============================================================================
--
-- PURPOSE:
--   The operational tables (Sales, Purchases, Expenses, Payroll) capture
--   individual transactions from the business perspective.
--   These new tables aggregate every monetary inflow and outflow into two
--   unified financial registers:
--
--     Revenue_Streams  → every rupee the business earns (from any source)
--     Expense_Ledger   → every rupee the business spends (to any party)
--
--   Both tables carry payment_mode (cash/bank/upi/card/credit) so that the
--   Cash Flow Statement can separate ACTUAL cash movements from credit events.
--
--   Cash_Flow_Periods + Cash_Flow_Lines build the formal cash flow statement
--   (Operating / Investing / Financing) for any date range on demand.
--
-- TABLE LIST:
--   1. Revenue_Streams
--   2. Expense_Ledger
--   3. Cash_Flow_Periods
--   4. Cash_Flow_Lines
--
-- STORED PROCEDURES:
--   record_revenue_stream        — called by Sales, SalesReturn reversal, etc.
--   record_expense_ledger        — called by Purchase, Payroll, Expenses, etc.
--   generate_cash_flow_statement — builds CFS for any date window
--
-- VIEWS:
--   v_revenue_by_stream          — revenue breakdown by type and payment mode
--   v_expense_by_category        — expense breakdown by category and payment mode
--   v_daily_cash_position        — daily cash + bank running balance
--   v_cash_flow_statement        — full CFS from Cash_Flow_Lines
--   v_monthly_revenue_vs_expense — monthly P&L trend from stream tables
-- ============================================================================

USE Shop_Management;

-- ============================================================================
-- TABLE 1 — Revenue_Streams
-- Every inflow the business generates, regardless of source.
-- Linked back to the originating operational table via reference_type/id.
-- ============================================================================
CREATE TABLE IF NOT EXISTS `Revenue_Streams` (
    `revenue_id`      INT             AUTO_INCREMENT PRIMARY KEY,
    `revenue_date`    DATE            NOT NULL,

    -- Source classification
    `revenue_type`    ENUM(
                          'product_sale',     -- from Sales table
                          'sale_reversal',    -- correction / void reversal
                          'service_charge',   -- service fees
                          'interest_earned',  -- bank interest
                          'discount_received',-- supplier rebates
                          'loyalty_redemption_reversal',
                          'other'
                      ) NOT NULL DEFAULT 'product_sale',

    -- Back-link to operational record
    `reference_type`  VARCHAR(50)     DEFAULT NULL  COMMENT 'SALE | SERVICE | INTEREST | OTHER',
    `reference_id`    INT             DEFAULT NULL  COMMENT 'PK in the source table',

    -- Amounts
    `gross_amount`    DECIMAL(15,2)   NOT NULL      COMMENT 'Pre-discount, pre-GST amount',
    `discount_amount` DECIMAL(15,2)   NOT NULL DEFAULT 0.00,
    `gst_amount`      DECIMAL(15,2)   NOT NULL DEFAULT 0.00  COMMENT 'GST collected from buyer',
    `net_revenue`     DECIMAL(15,2)   NOT NULL      COMMENT 'gross - discount (excl. GST collected)',
    `total_collected` DECIMAL(15,2)   NOT NULL      COMMENT 'Actual amount received = net + gst',

    -- HOW it was received — critical for cash flow classification
    `payment_mode`    ENUM('cash','bank','upi','card','credit')
                                      NOT NULL DEFAULT 'cash',

    -- WHO paid
    `customer_id`     INT             DEFAULT NULL,
    `product_id`      INT             DEFAULT NULL,

    -- Soft delete + tracking
    `description`     VARCHAR(255)    DEFAULT NULL,
    `is_deleted`      BOOLEAN         NOT NULL DEFAULT FALSE,
    `created_by`      INT             DEFAULT NULL,
    `created_at`      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`      TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE SET NULL,
    FOREIGN KEY (product_id)  REFERENCES Products(product_id)   ON DELETE SET NULL,
    FOREIGN KEY (created_by)  REFERENCES Users(user_id)         ON DELETE SET NULL,

    INDEX idx_rs_date        (revenue_date),
    INDEX idx_rs_type        (revenue_type),
    INDEX idx_rs_payment     (payment_mode),
    INDEX idx_rs_customer    (customer_id),
    INDEX idx_rs_product     (product_id),
    INDEX idx_rs_reference   (reference_type, reference_id),
    INDEX idx_rs_deleted     (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Unified revenue stream register — all business inflows with payment mode';


-- ============================================================================
-- TABLE 2 — Expense_Ledger
-- Every outflow the business makes, regardless of department.
-- Covers: purchase costs, payroll, rent, utilities, freight, misc — everything.
-- ============================================================================
CREATE TABLE IF NOT EXISTS `Expense_Ledger` (
    `expense_ledger_id` INT           AUTO_INCREMENT PRIMARY KEY,
    `expense_date`      DATE          NOT NULL,

    -- Expense classification
    `expense_type`      ENUM(
                            'cost_of_goods',     -- purchase cost from Purchases
                            'payroll',           -- salary / wages from Payroll
                            'rent',
                            'utilities',         -- electricity, water, internet
                            'transport',         -- freight, fuel, courier
                            'marketing',
                            'maintenance',
                            'bank_charges',
                            'office_supplies',
                            'tax_payment',
                            'subscription',
                            'purchase_return_reversal',
                            'other'
                        ) NOT NULL,

    -- Expense sub-category (links to Expense_Categories)
    `category_id`       INT           DEFAULT NULL,

    -- Back-link to operational record
    `reference_type`    VARCHAR(50)   DEFAULT NULL  COMMENT 'PURCHASE | PAYROLL | EXPENSE | ADJUSTMENT',
    `reference_id`      INT           DEFAULT NULL,

    -- Amounts
    `gross_amount`      DECIMAL(15,2) NOT NULL      COMMENT 'Total expense before GST input',
    `gst_input_amount`  DECIMAL(15,2) NOT NULL DEFAULT 0.00  COMMENT 'GST paid (input credit)',
    `net_expense`       DECIMAL(15,2) NOT NULL      COMMENT 'Actual cost net of GST input',
    `total_paid`        DECIMAL(15,2) NOT NULL      COMMENT 'Actual amount outgoing = gross + gst',

    -- HOW it was paid — critical for cash flow
    `payment_mode`      ENUM('cash','bank','upi','card','credit')
                                      NOT NULL DEFAULT 'cash',

    -- WHO was paid
    `vendor_id`         INT           DEFAULT NULL,
    `employee_id`       INT           DEFAULT NULL,

    -- Soft delete + tracking
    `description`       VARCHAR(255)  NOT NULL,
    `is_deleted`        BOOLEAN       NOT NULL DEFAULT FALSE,
    `created_by`        INT           DEFAULT NULL,
    `created_at`        TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id)  REFERENCES Expense_Categories(category_id) ON DELETE SET NULL,
    FOREIGN KEY (vendor_id)    REFERENCES Vendors(vendor_id)               ON DELETE SET NULL,
    FOREIGN KEY (employee_id)  REFERENCES Employees(employee_id)           ON DELETE SET NULL,
    FOREIGN KEY (created_by)   REFERENCES Users(user_id)                   ON DELETE SET NULL,

    INDEX idx_el_date        (expense_date),
    INDEX idx_el_type        (expense_type),
    INDEX idx_el_payment     (payment_mode),
    INDEX idx_el_vendor      (vendor_id),
    INDEX idx_el_employee    (employee_id),
    INDEX idx_el_category    (category_id),
    INDEX idx_el_reference   (reference_type, reference_id),
    INDEX idx_el_deleted     (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Unified expense ledger — all business outflows with payment mode and source';


-- ============================================================================
-- TABLE 3 — Cash_Flow_Periods
-- Header record for each generated cash flow statement.
-- Stores the summary totals for three CFS sections.
-- ============================================================================
CREATE TABLE IF NOT EXISTS `Cash_Flow_Periods` (
    `cfs_id`              INT           AUTO_INCREMENT PRIMARY KEY,
    `period_name`         VARCHAR(60)   NOT NULL              COMMENT 'e.g. APR-2025 CFS',
    `period_type`         ENUM('MONTHLY','QUARTERLY','YEARLY') NOT NULL DEFAULT 'MONTHLY',
    `start_date`          DATE          NOT NULL,
    `end_date`            DATE          NOT NULL,

    -- Opening position (from prior period closing or manual entry)
    `opening_cash`        DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    `opening_bank`        DECIMAL(15,2) NOT NULL DEFAULT 0.00,
    `opening_total`       DECIMAL(15,2) GENERATED ALWAYS AS
                              (opening_cash + opening_bank) STORED,

    -- Operating Activities (cash from/for core business)
    `operating_inflow`    DECIMAL(15,2) DEFAULT 0.00,
    `operating_outflow`   DECIMAL(15,2) DEFAULT 0.00,
    `net_operating`       DECIMAL(15,2) DEFAULT 0.00,

    -- Investing Activities (asset purchase/sale, equipment)
    `investing_inflow`    DECIMAL(15,2) DEFAULT 0.00,
    `investing_outflow`   DECIMAL(15,2) DEFAULT 0.00,
    `net_investing`       DECIMAL(15,2) DEFAULT 0.00,

    -- Financing Activities (capital, loans, drawings)
    `financing_inflow`    DECIMAL(15,2) DEFAULT 0.00,
    `financing_outflow`   DECIMAL(15,2) DEFAULT 0.00,
    `net_financing`       DECIMAL(15,2) DEFAULT 0.00,

    -- Net change and closing position
    `net_cash_change`     DECIMAL(15,2) DEFAULT 0.00,
    `closing_cash`        DECIMAL(15,2) DEFAULT 0.00,
    `closing_bank`        DECIMAL(15,2) DEFAULT 0.00,
    `closing_total`       DECIMAL(15,2) GENERATED ALWAYS AS
                              (closing_cash + closing_bank) STORED,

    `status`              ENUM('DRAFT','FINAL','APPROVED') NOT NULL DEFAULT 'DRAFT',
    `notes`               TEXT          DEFAULT NULL,
    `generated_by`        INT           DEFAULT NULL,
    `generated_at`        TIMESTAMP     NULL DEFAULT NULL,
    `approved_by`         INT           DEFAULT NULL,
    `approved_at`         TIMESTAMP     NULL DEFAULT NULL,
    `created_at`          TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_cfs_period (start_date, end_date),
    FOREIGN KEY (generated_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by)  REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_cfs_period   (start_date, end_date),
    INDEX idx_cfs_status   (status),
    INDEX idx_cfs_type     (period_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Cash flow statement headers — one row per period (monthly/quarterly/yearly)';


-- ============================================================================
-- TABLE 4 — Cash_Flow_Lines
-- Individual line items within a cash flow statement.
-- Each line belongs to one of three activities and one of two directions.
-- ============================================================================
CREATE TABLE IF NOT EXISTS `Cash_Flow_Lines` (
    `line_id`           INT             AUTO_INCREMENT PRIMARY KEY,
    `cfs_id`            INT             NOT NULL,

    -- Standard CFS classification
    `activity_type`     ENUM('OPERATING','INVESTING','FINANCING') NOT NULL,
    `flow_direction`    ENUM('INFLOW','OUTFLOW')                  NOT NULL,

    -- What is this line about
    `line_category`     VARCHAR(150)    NOT NULL
                            COMMENT 'e.g. Cash received from customers, Payments to vendors',
    `payment_mode`      ENUM('cash','bank','upi','card')          NOT NULL DEFAULT 'cash',

    -- Source tracking
    `reference_type`    VARCHAR(50)     DEFAULT NULL,
    `reference_id`      INT             DEFAULT NULL,

    `amount`            DECIMAL(15,2)   NOT NULL,
    `transaction_count` INT             NOT NULL DEFAULT 1
                            COMMENT 'How many transactions are aggregated in this line',
    `description`       VARCHAR(255)    DEFAULT NULL,
    `created_at`        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (cfs_id) REFERENCES Cash_Flow_Periods(cfs_id) ON DELETE CASCADE,
    INDEX idx_cfl_cfs       (cfs_id),
    INDEX idx_cfl_activity  (activity_type),
    INDEX idx_cfl_direction (flow_direction),
    INDEX idx_cfl_payment   (payment_mode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Individual CFS line items grouped by activity and flow direction';


-- ============================================================================
-- STORED PROCEDURES
-- ============================================================================

DELIMITER $$

-- ----------------------------------------------------------------------------
-- record_revenue_stream
-- Called by Sales.py, SalesReturn.py reversal, etc.
-- Inserts into Revenue_Streams.
-- ----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS record_revenue_stream $$
CREATE PROCEDURE record_revenue_stream(
    IN p_revenue_date    DATE,
    IN p_revenue_type    VARCHAR(30),
    IN p_reference_type  VARCHAR(50),
    IN p_reference_id    INT,
    IN p_gross_amount    DECIMAL(15,2),
    IN p_discount_amount DECIMAL(15,2),
    IN p_gst_amount      DECIMAL(15,2),
    IN p_payment_mode    VARCHAR(20),
    IN p_customer_id     INT,
    IN p_product_id      INT,
    IN p_description     VARCHAR(255),
    IN p_created_by      INT,
    OUT p_revenue_id     INT
)
BEGIN
    DECLARE v_net_revenue     DECIMAL(15,2);
    DECLARE v_total_collected DECIMAL(15,2);

    SET v_net_revenue     = p_gross_amount - p_discount_amount;
    SET v_total_collected = v_net_revenue + p_gst_amount;

    INSERT INTO Revenue_Streams (
        revenue_date, revenue_type, reference_type, reference_id,
        gross_amount, discount_amount, gst_amount, net_revenue, total_collected,
        payment_mode, customer_id, product_id, description, created_by
    ) VALUES (
        p_revenue_date, p_revenue_type, p_reference_type, p_reference_id,
        p_gross_amount, p_discount_amount, p_gst_amount, v_net_revenue, v_total_collected,
        p_payment_mode, p_customer_id, p_product_id, p_description, p_created_by
    );

    SET p_revenue_id = LAST_INSERT_ID();
END$$

-- ----------------------------------------------------------------------------
-- record_expense_ledger
-- Called by Purchase.py, Payroll.py, Expenses recording, etc.
-- Inserts into Expense_Ledger.
-- ----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS record_expense_ledger $$
CREATE PROCEDURE record_expense_ledger(
    IN p_expense_date      DATE,
    IN p_expense_type      VARCHAR(50),
    IN p_category_id       INT,
    IN p_reference_type    VARCHAR(50),
    IN p_reference_id      INT,
    IN p_gross_amount      DECIMAL(15,2),
    IN p_gst_input_amount  DECIMAL(15,2),
    IN p_payment_mode      VARCHAR(20),
    IN p_vendor_id         INT,
    IN p_employee_id       INT,
    IN p_description       VARCHAR(255),
    IN p_created_by        INT,
    OUT p_expense_ledger_id INT
)
BEGIN
    DECLARE v_net_expense  DECIMAL(15,2);
    DECLARE v_total_paid   DECIMAL(15,2);

    SET v_net_expense = p_gross_amount - p_gst_input_amount;
    SET v_total_paid  = p_gross_amount + p_gst_input_amount;

    INSERT INTO Expense_Ledger (
        expense_date, expense_type, category_id, reference_type, reference_id,
        gross_amount, gst_input_amount, net_expense, total_paid,
        payment_mode, vendor_id, employee_id, description, created_by
    ) VALUES (
        p_expense_date, p_expense_type, p_category_id, p_reference_type, p_reference_id,
        p_gross_amount, p_gst_input_amount, v_net_expense, v_total_paid,
        p_payment_mode, p_vendor_id, p_employee_id, p_description, p_created_by
    );

    SET p_expense_ledger_id = LAST_INSERT_ID();
END$$

-- ----------------------------------------------------------------------------
-- generate_cash_flow_statement
-- Builds a complete Cash Flow Statement for a given date range.
-- Reads from Revenue_Streams, Expense_Ledger, Cash_Transactions, Bank_Transactions.
-- Excludes CREDIT mode transactions (not actual cash movement).
-- ----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS generate_cash_flow_statement $$
CREATE PROCEDURE generate_cash_flow_statement(
    IN  p_start_date    DATE,
    IN  p_end_date      DATE,
    IN  p_period_name   VARCHAR(60),
    IN  p_period_type   VARCHAR(20),
    IN  p_opening_cash  DECIMAL(15,2),
    IN  p_opening_bank  DECIMAL(15,2),
    IN  p_generated_by  INT,
    OUT p_cfs_id        INT
)
BEGIN
    -- Operating
    DECLARE v_op_inflow      DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_op_outflow     DECIMAL(15,2) DEFAULT 0.00;
    -- Investing
    DECLARE v_inv_inflow     DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_inv_outflow    DECIMAL(15,2) DEFAULT 0.00;
    -- Financing
    DECLARE v_fin_inflow     DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_fin_outflow    DECIMAL(15,2) DEFAULT 0.00;
    -- Closing
    DECLARE v_net_change     DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_closing_cash   DECIMAL(15,2) DEFAULT 0.00;
    DECLARE v_closing_bank   DECIMAL(15,2) DEFAULT 0.00;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;

    -- ── Create period header ──────────────────────────────────────────────
    INSERT INTO Cash_Flow_Periods (
        period_name, period_type, start_date, end_date,
        opening_cash, opening_bank, status, generated_by, generated_at
    ) VALUES (
        p_period_name, p_period_type, p_start_date, p_end_date,
        p_opening_cash, p_opening_bank, 'DRAFT', p_generated_by, NOW()
    );
    SET p_cfs_id = LAST_INSERT_ID();

    -- ── Delete existing lines if regenerating ────────────────────────────
    DELETE FROM Cash_Flow_Lines WHERE cfs_id = p_cfs_id;

    -- ════════════════════════════════════════════════════════════════════════
    -- SECTION A — OPERATING ACTIVITIES
    -- Cash inflows: cash/card/upi/bank sales
    -- ════════════════════════════════════════════════════════════════════════

    -- A1: Cash received from customers (Sales — non-credit)
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'OPERATING', 'INFLOW',
        CONCAT('Cash from customers (', payment_mode, ')'),
        payment_mode, 'SALE',
        COALESCE(SUM(total_collected), 0),
        COUNT(*),
        'Revenue collected from product sales'
    FROM Revenue_Streams
    WHERE revenue_date BETWEEN p_start_date AND p_end_date
      AND payment_mode != 'credit'
      AND revenue_type  = 'product_sale'
      AND is_deleted    = FALSE
    GROUP BY payment_mode
    HAVING SUM(total_collected) > 0;

    -- A2: Payments to vendors for purchases (non-credit)
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'OPERATING', 'OUTFLOW',
        CONCAT('Payments to vendors (', payment_mode, ')'),
        payment_mode, 'PURCHASE',
        COALESCE(SUM(total_paid), 0),
        COUNT(*),
        'Cash paid to vendors for stock purchases'
    FROM Expense_Ledger
    WHERE expense_date  BETWEEN p_start_date AND p_end_date
      AND payment_mode != 'credit'
      AND expense_type  = 'cost_of_goods'
      AND is_deleted    = FALSE
    GROUP BY payment_mode
    HAVING SUM(total_paid) > 0;

    -- A3: Operational expenses paid (rent, electricity, etc.)
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'OPERATING', 'OUTFLOW',
        CONCAT('Operating expenses — ', expense_type, ' (', payment_mode, ')'),
        payment_mode, 'EXPENSE',
        COALESCE(SUM(total_paid), 0),
        COUNT(*),
        'Cash paid for operational expenses'
    FROM Expense_Ledger
    WHERE expense_date  BETWEEN p_start_date AND p_end_date
      AND payment_mode != 'credit'
      AND expense_type NOT IN ('cost_of_goods','payroll')
      AND is_deleted    = FALSE
    GROUP BY expense_type, payment_mode
    HAVING SUM(total_paid) > 0;

    -- A4: Payroll paid
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'OPERATING', 'OUTFLOW',
        CONCAT('Salary & wages paid (', payment_mode, ')'),
        payment_mode, 'PAYROLL',
        COALESCE(SUM(total_paid), 0),
        COUNT(*),
        'Net salaries paid to employees'
    FROM Expense_Ledger
    WHERE expense_date  BETWEEN p_start_date AND p_end_date
      AND payment_mode != 'credit'
      AND expense_type  = 'payroll'
      AND is_deleted    = FALSE
    GROUP BY payment_mode
    HAVING SUM(total_paid) > 0;

    -- A5: GST paid out (net: GST collected - GST input)
    -- This is captured via Cash_Transactions (tax payments)
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'OPERATING', 'OUTFLOW',
        'GST / Tax payments (bank)', 'bank', 'TAX',
        COALESCE(SUM(total_paid), 0), COUNT(*),
        'GST and statutory tax payments'
    FROM Expense_Ledger
    WHERE expense_date BETWEEN p_start_date AND p_end_date
      AND payment_mode != 'credit'
      AND expense_type  = 'tax_payment'
      AND is_deleted    = FALSE
    HAVING SUM(total_paid) > 0;

    -- ════════════════════════════════════════════════════════════════════════
    -- SECTION B — INVESTING ACTIVITIES
    -- Capital equipment, asset purchases, asset sales (currently tracked
    -- via Cash_Transactions with reference_type = 'ASSET')
    -- ════════════════════════════════════════════════════════════════════════

    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'INVESTING',
        CASE txn_type WHEN 'in' THEN 'INFLOW' ELSE 'OUTFLOW' END,
        CASE txn_type WHEN 'in'  THEN 'Proceeds from asset sale'
                      ELSE 'Purchase of fixed assets / equipment' END,
        'cash', 'ASSET',
        COALESCE(SUM(amount), 0), COUNT(*),
        'Capital asset transactions'
    FROM Cash_Transactions
    WHERE txn_date       BETWEEN p_start_date AND p_end_date
      AND reference_type = 'ASSET'
    GROUP BY txn_type
    HAVING SUM(amount) > 0;

    -- ════════════════════════════════════════════════════════════════════════
    -- SECTION C — FINANCING ACTIVITIES
    -- Owner capital injections, drawings, loan receipts/repayments
    -- ════════════════════════════════════════════════════════════════════════

    -- C1: Capital injections (from Revenue_Streams revenue_type = 'other' + ref CAPITAL)
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'FINANCING', 'INFLOW',
        CONCAT('Owner capital injection (', payment_mode, ')'),
        payment_mode, 'CAPITAL',
        COALESCE(SUM(total_collected), 0), COUNT(*),
        'Capital introduced by owner'
    FROM Revenue_Streams
    WHERE revenue_date   BETWEEN p_start_date AND p_end_date
      AND reference_type = 'CAPITAL'
      AND payment_mode  != 'credit'
      AND is_deleted     = FALSE
    GROUP BY payment_mode
    HAVING SUM(total_collected) > 0;

    -- C2: Owner drawings
    INSERT INTO Cash_Flow_Lines
        (cfs_id, activity_type, flow_direction, line_category,
         payment_mode, reference_type, amount, transaction_count, description)
    SELECT
        p_cfs_id, 'FINANCING', 'OUTFLOW',
        CONCAT('Owner drawings (', payment_mode, ')'),
        payment_mode, 'DRAWING',
        COALESCE(SUM(total_paid), 0), COUNT(*),
        'Cash withdrawn by owner'
    FROM Expense_Ledger
    WHERE expense_date   BETWEEN p_start_date AND p_end_date
      AND reference_type = 'DRAWING'
      AND payment_mode  != 'credit'
      AND is_deleted     = FALSE
    GROUP BY payment_mode
    HAVING SUM(total_paid) > 0;

    -- ════════════════════════════════════════════════════════════════════════
    -- Compute totals and update period header
    -- ════════════════════════════════════════════════════════════════════════

    SELECT
        COALESCE(SUM(CASE WHEN activity_type='OPERATING' AND flow_direction='INFLOW'  THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN activity_type='OPERATING' AND flow_direction='OUTFLOW' THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN activity_type='INVESTING' AND flow_direction='INFLOW'  THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN activity_type='INVESTING' AND flow_direction='OUTFLOW' THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN activity_type='FINANCING' AND flow_direction='INFLOW'  THEN amount ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN activity_type='FINANCING' AND flow_direction='OUTFLOW' THEN amount ELSE 0 END), 0)
    INTO v_op_inflow, v_op_outflow,
         v_inv_inflow, v_inv_outflow,
         v_fin_inflow, v_fin_outflow
    FROM Cash_Flow_Lines WHERE cfs_id = p_cfs_id;

    SET v_net_change   = (v_op_inflow - v_op_outflow)
                       + (v_inv_inflow - v_inv_outflow)
                       + (v_fin_inflow - v_fin_outflow);

    -- Split net change proportionally between cash and bank
    -- (Simple heuristic: sum from actual Cash_Transactions and Bank_Transactions)
    SELECT
        COALESCE(SUM(CASE WHEN txn_type='in' THEN amount ELSE -amount END), 0)
    INTO v_closing_cash
    FROM Cash_Transactions
    WHERE txn_date BETWEEN p_start_date AND p_end_date;

    SELECT
        COALESCE(SUM(CASE WHEN txn_type IN ('deposit','upi_in','cheque_in','transfer_in')
                          THEN amount ELSE -amount END), 0)
    INTO v_closing_bank
    FROM Bank_Transactions
    WHERE txn_date BETWEEN p_start_date AND p_end_date;

    SET v_closing_cash = p_opening_cash + v_closing_cash;
    SET v_closing_bank = p_opening_bank + v_closing_bank;

    UPDATE Cash_Flow_Periods SET
        operating_inflow  = v_op_inflow,
        operating_outflow = v_op_outflow,
        net_operating     = v_op_inflow  - v_op_outflow,
        investing_inflow  = v_inv_inflow,
        investing_outflow = v_inv_outflow,
        net_investing     = v_inv_inflow - v_inv_outflow,
        financing_inflow  = v_fin_inflow,
        financing_outflow = v_fin_outflow,
        net_financing     = v_fin_inflow - v_fin_outflow,
        net_cash_change   = v_net_change,
        closing_cash      = v_closing_cash,
        closing_bank      = v_closing_bank,
        generated_at      = NOW()
    WHERE cfs_id = p_cfs_id;

    COMMIT;
END$$

DELIMITER ;


-- ============================================================================
-- VIEWS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- v_revenue_by_stream
-- Monthly revenue broken down by type and payment mode.
-- Shows exactly how much came from cash vs card vs credit etc.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_revenue_by_stream AS
SELECT
    DATE_FORMAT(revenue_date, '%Y-%m')          AS month,
    revenue_type,
    payment_mode,
    COUNT(*)                                    AS transaction_count,
    COALESCE(SUM(gross_amount),    0)           AS gross_revenue,
    COALESCE(SUM(discount_amount), 0)           AS total_discounts,
    COALESCE(SUM(gst_amount),      0)           AS gst_collected,
    COALESCE(SUM(net_revenue),     0)           AS net_revenue,
    COALESCE(SUM(total_collected), 0)           AS total_collected
FROM Revenue_Streams
WHERE is_deleted = FALSE
GROUP BY DATE_FORMAT(revenue_date, '%Y-%m'), revenue_type, payment_mode
ORDER BY month DESC, total_collected DESC;

-- ----------------------------------------------------------------------------
-- v_expense_by_category
-- Monthly expenses by type, category, and payment mode.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_expense_by_category AS
SELECT
    DATE_FORMAT(el.expense_date, '%Y-%m')       AS month,
    el.expense_type,
    ec.category_name,
    el.payment_mode,
    COUNT(*)                                    AS transaction_count,
    COALESCE(SUM(el.gross_amount),       0)     AS gross_expense,
    COALESCE(SUM(el.gst_input_amount),   0)     AS gst_input_credit,
    COALESCE(SUM(el.net_expense),        0)     AS net_expense,
    COALESCE(SUM(el.total_paid),         0)     AS total_paid
FROM Expense_Ledger el
LEFT JOIN Expense_Categories ec ON ec.category_id = el.category_id
WHERE el.is_deleted = FALSE
GROUP BY DATE_FORMAT(el.expense_date, '%Y-%m'),
         el.expense_type, ec.category_name, el.payment_mode
ORDER BY month DESC, total_paid DESC;

-- ----------------------------------------------------------------------------
-- v_daily_cash_position
-- Running daily cash + bank balance computed from all transactions.
-- Shows exactly how much cash and bank the business holds on each day.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_cash_position AS
SELECT
    txn_date                                    AS `date`,
    'cash'                                      AS account_type,
    COALESCE(SUM(CASE WHEN txn_type='in'  THEN amount ELSE 0 END), 0) AS inflow,
    COALESCE(SUM(CASE WHEN txn_type='out' THEN amount ELSE 0 END), 0) AS outflow,
    COALESCE(SUM(CASE WHEN txn_type='in'  THEN amount ELSE -amount END), 0) AS daily_net
FROM Cash_Transactions
GROUP BY txn_date
UNION ALL
SELECT
    txn_date,
    'bank',
    COALESCE(SUM(CASE WHEN txn_type IN ('deposit','upi_in','cheque_in','transfer_in')
                      THEN amount ELSE 0 END), 0),
    COALESCE(SUM(CASE WHEN txn_type IN ('withdrawal','upi_out','cheque_out','transfer_out','bank_charge')
                      THEN amount ELSE 0 END), 0),
    COALESCE(SUM(CASE WHEN txn_type IN ('deposit','upi_in','cheque_in','transfer_in')
                      THEN amount ELSE -amount END), 0)
FROM Bank_Transactions
GROUP BY txn_date
ORDER BY `date` DESC, account_type;

-- ----------------------------------------------------------------------------
-- v_cash_flow_statement
-- Presents the latest approved/draft CFS with all line items.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cash_flow_statement AS
SELECT
    cfp.cfs_id,
    cfp.period_name,
    cfp.start_date,
    cfp.end_date,
    cfp.status,
    cfp.opening_cash,
    cfp.opening_bank,
    cfp.opening_total,
    cfl.activity_type,
    cfl.flow_direction,
    cfl.line_category,
    cfl.payment_mode,
    cfl.amount,
    cfl.transaction_count,
    cfl.description,
    cfp.operating_inflow,
    cfp.operating_outflow,
    cfp.net_operating,
    cfp.investing_inflow,
    cfp.investing_outflow,
    cfp.net_investing,
    cfp.financing_inflow,
    cfp.financing_outflow,
    cfp.net_financing,
    cfp.net_cash_change,
    cfp.closing_cash,
    cfp.closing_bank,
    cfp.closing_total
FROM Cash_Flow_Periods cfp
JOIN Cash_Flow_Lines cfl ON cfl.cfs_id = cfp.cfs_id
ORDER BY cfp.start_date DESC, cfl.activity_type, cfl.flow_direction;

-- ----------------------------------------------------------------------------
-- v_monthly_revenue_vs_expense
-- Side-by-side monthly revenue vs expense with net surplus/deficit.
-- Cash vs credit breakdown included.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_monthly_revenue_vs_expense AS
SELECT
    m.month,
    COALESCE(r.total_revenue,         0)        AS total_revenue,
    COALESCE(r.cash_revenue,          0)        AS cash_revenue,
    COALESCE(r.credit_revenue,        0)        AS credit_revenue,
    COALESCE(e.total_expense,         0)        AS total_expense,
    COALESCE(e.cash_expense,          0)        AS cash_expense,
    COALESCE(e.credit_expense,        0)        AS credit_expense,
    COALESCE(r.total_revenue, 0) -
    COALESCE(e.total_expense, 0)                AS net_surplus_deficit,
    COALESCE(r.cash_revenue,  0) -
    COALESCE(e.cash_expense,  0)                AS net_cash_flow
FROM (
    SELECT DATE_FORMAT(revenue_date, '%Y-%m') AS month FROM Revenue_Streams WHERE is_deleted=FALSE
    UNION
    SELECT DATE_FORMAT(expense_date, '%Y-%m') AS month FROM Expense_Ledger  WHERE is_deleted=FALSE
) m
LEFT JOIN (
    SELECT
        DATE_FORMAT(revenue_date, '%Y-%m')                       AS month,
        SUM(total_collected)                                     AS total_revenue,
        SUM(CASE WHEN payment_mode != 'credit' THEN total_collected ELSE 0 END) AS cash_revenue,
        SUM(CASE WHEN payment_mode  = 'credit' THEN total_collected ELSE 0 END) AS credit_revenue
    FROM Revenue_Streams WHERE is_deleted=FALSE
    GROUP BY DATE_FORMAT(revenue_date, '%Y-%m')
) r ON r.month = m.month
LEFT JOIN (
    SELECT
        DATE_FORMAT(expense_date, '%Y-%m')                       AS month,
        SUM(total_paid)                                          AS total_expense,
        SUM(CASE WHEN payment_mode != 'credit' THEN total_paid ELSE 0 END) AS cash_expense,
        SUM(CASE WHEN payment_mode  = 'credit' THEN total_paid ELSE 0 END) AS credit_expense
    FROM Expense_Ledger WHERE is_deleted=FALSE
    GROUP BY DATE_FORMAT(expense_date, '%Y-%m')
) e ON e.month = m.month
GROUP BY m.month
ORDER BY m.month DESC;

-- ============================================================================
-- END: financial_streams.sql
-- ============================================================================
-- New tables  : Revenue_Streams, Expense_Ledger, Cash_Flow_Periods, Cash_Flow_Lines
-- Procedures  : record_revenue_stream, record_expense_ledger,
--               generate_cash_flow_statement
-- Views       : v_revenue_by_stream, v_expense_by_category,
--               v_daily_cash_position, v_cash_flow_statement,
--               v_monthly_revenue_vs_expense
-- ============================================================================
