-- ============================================================================
-- SHOP MANAGEMENT SYSTEM — COMPLETE DATABASE SCHEMA
-- Version 2.0
-- ============================================================================
--
-- TABLE CREATION ORDER (respects all foreign key dependencies):
--   1.  Roles
--   2.  Users
--   3.  User_Sessions
--   4.  Vendors
--   5.  Customers
--   6.  Expense_Categories
--   7.  Categories
--   8.  Products
--   9.  Inventory_Lots
--   10. Inventory_Movements
--   11. Sales
--   12. Sales_Return
--   13. Purchases
--   14. Purchase_Return
--   15. Employees
--   16. Attendance
--   17. Payroll
--   18. Cash_Transactions
--   19. Bank_Transactions
--   20. Expenses
--   21. Notifications
--   22. Audit_Log
--   23. Backups
--
-- DESIGN PRINCIPLES:
--   - Soft deletes on all operational tables (is_deleted flag)
--   - created_at / updated_at on every table
--   - Single universal Audit_Log for all operations
--   - All ENUMs use lowercase snake_case values
--   - FKs enforce referential integrity; ON DELETE RESTRICT by default
--   - Pincode is NOT unique (many customers can share a pin code)
--   - Phone numbers stored as VARCHAR to allow leading zeros / formatting
-- ============================================================================

CREATE DATABASE IF NOT EXISTS Shop_Management
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE Shop_Management;

-- ============================================================================
-- SECTION 1 — USER MANAGEMENT & AUTHENTICATION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1.1 Roles
-- Defines permission groups: Admin, Manager, Cashier, Accountant, Inventory
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Roles (
    role_id     INT             AUTO_INCREMENT PRIMARY KEY,
    role_name   VARCHAR(50)     NOT NULL UNIQUE COMMENT 'e.g. admin, manager, cashier, accountant, inventory_staff',
    description VARCHAR(255)    DEFAULT NULL,
    created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='User permission roles';

-- Seed default roles
INSERT IGNORE INTO Roles (role_name, description) VALUES
    ('admin',            'Full system access'),
    ('manager',          'Operational management access'),
    ('cashier',          'Sales and billing access'),
    ('accountant',       'Financial and ledger access'),
    ('inventory_staff',  'Inventory and purchase access');

-- ----------------------------------------------------------------------------
-- 1.2 Users
-- System login accounts linked to roles
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Users (
    user_id       INT           AUTO_INCREMENT PRIMARY KEY,
    role_id       INT           NOT NULL,
    username      VARCHAR(50)   NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL                 COMMENT 'bcrypt hash — never store plain text',
    full_name     VARCHAR(100)  NOT NULL,
    email         VARCHAR(100)  NOT NULL UNIQUE,
    phone         VARCHAR(20)   DEFAULT NULL,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    is_deleted    BOOLEAN       NOT NULL DEFAULT FALSE,
    last_login_at TIMESTAMP     NULL     DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (role_id) REFERENCES Roles(role_id) ON DELETE RESTRICT,
    INDEX idx_users_role      (role_id),
    INDEX idx_users_username  (username),
    INDEX idx_users_email     (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='System user accounts with role-based access';

-- ----------------------------------------------------------------------------
-- 1.3 User_Sessions
-- Tracks active and historical login sessions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS User_Sessions (
    session_id    INT           AUTO_INCREMENT PRIMARY KEY,
    user_id       INT           NOT NULL,
    login_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    logout_at     TIMESTAMP     NULL     DEFAULT NULL,
    ip_address    VARCHAR(45)   DEFAULT NULL               COMMENT 'IPv4 or IPv6',
    device_info   VARCHAR(255)  DEFAULT NULL,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,

    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    INDEX idx_sessions_user   (user_id),
    INDEX idx_sessions_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Login session tracking for audit and security';


-- ============================================================================
-- SECTION 2 — VENDOR MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1 Vendors
-- Supplier master records
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Vendors (
    vendor_id           INT             AUTO_INCREMENT PRIMARY KEY,
    vendor_name         VARCHAR(100)    NOT NULL,
    email               VARCHAR(100)    NOT NULL UNIQUE,
    phone               VARCHAR(20)     NOT NULL UNIQUE,
    address             VARCHAR(200)    NOT NULL,
    city                VARCHAR(50)     NOT NULL,
    state               VARCHAR(50)     NOT NULL,
    postal_code         VARCHAR(20)     NOT NULL,
    country             VARCHAR(50)     NOT NULL DEFAULT 'India',
    credit_period_days  INT             NOT NULL DEFAULT 0  COMMENT 'Payment due window in days',
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    is_deleted          BOOLEAN         NOT NULL DEFAULT FALSE,
    created_by          INT             DEFAULT NULL       COMMENT 'user_id of creator',
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (created_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_vendors_name    (vendor_name),
    INDEX idx_vendors_city    (city),
    INDEX idx_vendors_deleted (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Vendor/supplier master records';


-- ============================================================================
-- SECTION 3 — CUSTOMER MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1 Customers
-- Retail and wholesale customer master records
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Customers (
    customer_id   INT           AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100)  NOT NULL,
    phone         VARCHAR(20)   NOT NULL UNIQUE,
    email         VARCHAR(100)  NOT NULL UNIQUE,
    address       VARCHAR(200)  NOT NULL,
    city          VARCHAR(50)   NOT NULL,
    state         VARCHAR(50)   NOT NULL,
    postal_code   VARCHAR(20)   NOT NULL               COMMENT 'NOT unique — many customers share a pincode',
    country       VARCHAR(50)   NOT NULL DEFAULT 'India',
    loyalty_points INT          NOT NULL DEFAULT 0,
    is_deleted    BOOLEAN       NOT NULL DEFAULT FALSE,
    created_by    INT           DEFAULT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (created_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_customers_name    (customer_name),
    INDEX idx_customers_phone   (phone),
    INDEX idx_customers_email   (email),
    INDEX idx_customers_deleted (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Customer profiles for retail and wholesale';


-- ============================================================================
-- SECTION 4 — PRODUCT & INVENTORY MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1 Expense_Categories  (declared here — also used in Section 7)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Expense_Categories (
    category_id   INT           AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100)  NOT NULL UNIQUE          COMMENT 'e.g. rent, electricity, salary, transport',
    description   VARCHAR(255)  DEFAULT NULL,
    is_deleted    BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Expense type categories for financial tracking';

INSERT IGNORE INTO Expense_Categories (category_name, description) VALUES
    ('rent',            'Monthly/yearly rent payments'),
    ('electricity',     'Electricity bills'),
    ('internet',        'Internet and broadband bills'),
    ('water',           'Water utility bills'),
    ('transport',       'Fuel, freight, courier charges'),
    ('maintenance',     'Equipment and property maintenance'),
    ('office_supplies', 'Stationery, packaging, consumables'),
    ('marketing',       'Advertising and promotions'),
    ('bank_charges',    'Bank fees, transaction charges'),
    ('miscellaneous',   'Any other operational expenses');

-- ----------------------------------------------------------------------------
-- 4.2 Categories
-- Product classification hierarchy
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Categories (
    category_id   INT           AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100)  NOT NULL UNIQUE,
    parent_id     INT           DEFAULT NULL              COMMENT 'Self-reference for sub-categories',
    description   VARCHAR(255)  DEFAULT NULL,
    is_deleted    BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (parent_id) REFERENCES Categories(category_id) ON DELETE SET NULL,
    INDEX idx_categories_parent (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Hierarchical product categories';

-- ----------------------------------------------------------------------------
-- 4.3 Products
-- Master product catalogue
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Products (
    product_id      INT             AUTO_INCREMENT PRIMARY KEY,
    category_id     INT             DEFAULT NULL,
    vendor_id       INT             DEFAULT NULL          COMMENT 'Primary/default supplier',
    product_name    VARCHAR(150)    NOT NULL,
    sku             VARCHAR(50)     DEFAULT NULL UNIQUE   COMMENT 'Stock Keeping Unit / barcode',
    brand           VARCHAR(100)    DEFAULT NULL,
    unit            VARCHAR(30)     DEFAULT 'pcs'         COMMENT 'e.g. pcs, kg, litre, box',
    buying_price    DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    selling_price   DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    gst_percent     DECIMAL(5,2)    NOT NULL DEFAULT 0.00 COMMENT 'GST rate applicable',
    reorder_level   INT             NOT NULL DEFAULT 10   COMMENT 'Trigger low-stock alert below this qty',
    is_expirable    BOOLEAN         NOT NULL DEFAULT FALSE,
    is_deleted      BOOLEAN         NOT NULL DEFAULT FALSE,
    created_by      INT             DEFAULT NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id) REFERENCES Categories(category_id) ON DELETE SET NULL,
    FOREIGN KEY (vendor_id)   REFERENCES Vendors(vendor_id)      ON DELETE SET NULL,
    FOREIGN KEY (created_by)  REFERENCES Users(user_id)          ON DELETE SET NULL,
    INDEX idx_products_name     (product_name),
    INDEX idx_products_sku      (sku),
    INDEX idx_products_category (category_id),
    INDEX idx_products_vendor   (vendor_id),
    INDEX idx_products_deleted  (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Master product catalogue with pricing and GST';

-- ----------------------------------------------------------------------------
-- 4.4 Inventory_Lots
-- Batch/lot level stock tracking with expiry support
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Inventory_Lots (
    lot_id       INT           AUTO_INCREMENT PRIMARY KEY,
    product_id   INT           NOT NULL,
    purchase_id  INT           DEFAULT NULL              COMMENT 'Links to purchase that created this lot',
    quantity     INT           NOT NULL                  COMMENT 'Current available quantity in this lot',
    cost_price   DECIMAL(12,2) NOT NULL DEFAULT 0.00     COMMENT 'Per-unit landed cost for this lot',
    exp_date     DATE          DEFAULT NULL,
    mfg_date     DATE          DEFAULT NULL,
    batch_no     VARCHAR(50)   DEFAULT NULL,
    is_deleted   BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP     NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id) REFERENCES Products(product_id) ON DELETE RESTRICT,
    INDEX idx_lots_product   (product_id),
    INDEX idx_lots_exp_date  (exp_date),
    INDEX idx_lots_deleted   (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Batch/lot level inventory tracking with expiry dates';

-- ----------------------------------------------------------------------------
-- 4.5 Inventory_Movements
-- Immutable log of every stock movement (event sourcing for inventory)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Inventory_Movements (
    movement_id     INT             AUTO_INCREMENT PRIMARY KEY,
    product_id      INT             NOT NULL,
    lot_id          INT             DEFAULT NULL,
    movement_type   ENUM(
                        'purchase_in',
                        'sale_out',
                        'return_in_sale',
                        'return_out_purchase',
                        'adjustment_in',
                        'adjustment_out',
                        'damaged',
                        'expired',
                        'transfer_in',
                        'transfer_out'
                    ) NOT NULL,
    reference_type  VARCHAR(50)     DEFAULT NULL          COMMENT 'SALE, PURCHASE, ADJUSTMENT, etc.',
    reference_id    INT             DEFAULT NULL          COMMENT 'ID from reference table',
    qty_before      INT             NOT NULL,
    qty_change      INT             NOT NULL              COMMENT 'Positive = in, Negative = out',
    qty_after       INT             NOT NULL,
    reason          VARCHAR(255)    DEFAULT NULL,
    performed_by    INT             DEFAULT NULL,
    movement_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (product_id)   REFERENCES Products(product_id) ON DELETE RESTRICT,
    FOREIGN KEY (lot_id)       REFERENCES Inventory_Lots(lot_id) ON DELETE SET NULL,
    FOREIGN KEY (performed_by) REFERENCES Users(user_id)        ON DELETE SET NULL,
    INDEX idx_inv_mov_product   (product_id),
    INDEX idx_inv_mov_type      (movement_type),
    INDEX idx_inv_mov_ref       (reference_type, reference_id),
    INDEX idx_inv_mov_at        (movement_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Immutable stock movement log — every inventory event recorded here';


-- ============================================================================
-- SECTION 5 — SALES MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 5.1 Sales
-- Sales transaction header
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Sales (
    sale_id        INT              AUTO_INCREMENT PRIMARY KEY,
    sale_date      DATE             NOT NULL,
    customer_id    INT              DEFAULT NULL           COMMENT 'NULL = walk-in customer',
    product_id     INT              NOT NULL,
    lot_id         INT              DEFAULT NULL,
    qty_sold       INT              NOT NULL DEFAULT 1,
    unit_price     DECIMAL(12,2)    NOT NULL,
    discount_pct   DECIMAL(5,2)     NOT NULL DEFAULT 0.00  COMMENT 'Discount percentage applied',
    gst_amount     DECIMAL(12,2)    NOT NULL DEFAULT 0.00,
    total          DECIMAL(12,2)    NOT NULL,
    payment_method ENUM(
                       'cash',
                       'card',
                       'net_banking',
                       'upi',
                       'credit'
                   ) NOT NULL DEFAULT 'cash',
    payment_status ENUM('paid', 'pending', 'partial') NOT NULL DEFAULT 'paid',
    processed_by   INT              DEFAULT NULL           COMMENT 'Cashier user_id',
    is_deleted     BOOLEAN          NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP        NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)  REFERENCES Customers(customer_id) ON DELETE RESTRICT,
    FOREIGN KEY (product_id)   REFERENCES Products(product_id)   ON DELETE RESTRICT,
    FOREIGN KEY (lot_id)       REFERENCES Inventory_Lots(lot_id) ON DELETE SET NULL,
    FOREIGN KEY (processed_by) REFERENCES Users(user_id)         ON DELETE SET NULL,
    INDEX idx_sales_date         (sale_date),
    INDEX idx_sales_customer     (customer_id),
    INDEX idx_sales_product      (product_id),
    INDEX idx_sales_payment      (payment_method),
    INDEX idx_sales_status       (payment_status),
    INDEX idx_sales_processed_by (processed_by),
    INDEX idx_sales_deleted      (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Sales transaction records';

-- ----------------------------------------------------------------------------
-- 5.2 Sales_Return
-- Customer returns against a sale
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Sales_Return (
    sales_return_id  INT             AUTO_INCREMENT PRIMARY KEY,
    sale_id          INT             NOT NULL,
    customer_id      INT             DEFAULT NULL,
    product_id       INT             NOT NULL,
    return_date      DATE            NOT NULL,
    qty_returned     INT             NOT NULL DEFAULT 1,
    refund_amount    DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    reason           VARCHAR(255)    DEFAULT NULL,
    status           ENUM('pending','approved','declined') NOT NULL DEFAULT 'pending',
    processed_by     INT             DEFAULT NULL,
    is_deleted       BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (sale_id)      REFERENCES Sales(sale_id)           ON DELETE RESTRICT,
    FOREIGN KEY (customer_id)  REFERENCES Customers(customer_id)   ON DELETE SET NULL,
    FOREIGN KEY (product_id)   REFERENCES Products(product_id)     ON DELETE RESTRICT,
    FOREIGN KEY (processed_by) REFERENCES Users(user_id)           ON DELETE SET NULL,
    INDEX idx_sales_ret_sale      (sale_id),
    INDEX idx_sales_ret_customer  (customer_id),
    INDEX idx_sales_ret_date      (return_date),
    INDEX idx_sales_ret_status    (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Customer return transactions linked to original sales';


-- ============================================================================
-- SECTION 6 — PURCHASE MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 6.1 Purchases
-- Vendor purchase transaction header
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Purchases (
    purchase_id      INT             AUTO_INCREMENT PRIMARY KEY,
    vendor_id        INT             NOT NULL,
    product_id       INT             NOT NULL,
    purchase_date    DATE            NOT NULL,
    qty_purchased    INT             NOT NULL,
    unit_cost        DECIMAL(12,2)   NOT NULL,
    freight_cost     DECIMAL(12,2)   NOT NULL DEFAULT 0.00 COMMENT 'Shipping/freight added to landed cost',
    total            DECIMAL(12,2)   NOT NULL,
    due_date         DATE            NOT NULL               COMMENT 'Payment due date based on credit period',
    payment_method   ENUM(
                         'cash',
                         'card',
                         'net_banking',
                         'upi',
                         'credit'
                     ) NOT NULL DEFAULT 'credit',
    payment_status   ENUM('paid', 'pending', 'partial')    NOT NULL DEFAULT 'pending',
    invoice_no       VARCHAR(100)    DEFAULT NULL           COMMENT 'Vendor invoice number',
    is_deleted       BOOLEAN         NOT NULL DEFAULT FALSE,
    created_by       INT             DEFAULT NULL,
    created_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (vendor_id)   REFERENCES Vendors(vendor_id)   ON DELETE RESTRICT,
    FOREIGN KEY (product_id)  REFERENCES Products(product_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by)  REFERENCES Users(user_id)       ON DELETE SET NULL,
    INDEX idx_purchases_vendor   (vendor_id),
    INDEX idx_purchases_product  (product_id),
    INDEX idx_purchases_date     (purchase_date),
    INDEX idx_purchases_due_date (due_date),
    INDEX idx_purchases_status   (payment_status),
    INDEX idx_purchases_deleted  (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Vendor purchase records with landed cost tracking';

-- ----------------------------------------------------------------------------
-- 6.2 Purchase_Return
-- Returns to vendor against a purchase
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Purchase_Return (
    purchase_return_id  INT             AUTO_INCREMENT PRIMARY KEY,
    purchase_id         INT             NOT NULL,
    vendor_id           INT             NOT NULL,
    product_id          INT             NOT NULL,
    return_date         DATE            NOT NULL,
    qty_returned        INT             NOT NULL DEFAULT 1,
    refund_amount       DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    reason              VARCHAR(255)    NOT NULL,
    status              ENUM('pending','approved','declined') NOT NULL DEFAULT 'pending',
    processed_by        INT             DEFAULT NULL,
    is_deleted          BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (purchase_id)  REFERENCES Purchases(purchase_id) ON DELETE RESTRICT,
    FOREIGN KEY (vendor_id)    REFERENCES Vendors(vendor_id)     ON DELETE RESTRICT,
    FOREIGN KEY (product_id)   REFERENCES Products(product_id)   ON DELETE RESTRICT,
    FOREIGN KEY (processed_by) REFERENCES Users(user_id)         ON DELETE SET NULL,
    INDEX idx_pur_ret_purchase (purchase_id),
    INDEX idx_pur_ret_vendor   (vendor_id),
    INDEX idx_pur_ret_date     (return_date),
    INDEX idx_pur_ret_status   (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Return transactions sent back to vendors';


-- ============================================================================
-- SECTION 7 — EMPLOYEE MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 7.1 Employees
-- Employee HR records
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Employees (
    employee_id   INT             AUTO_INCREMENT PRIMARY KEY,
    user_id       INT             DEFAULT NULL             COMMENT 'Links to login account if employee has system access',
    full_name     VARCHAR(100)    NOT NULL,
    phone         VARCHAR(20)     NOT NULL UNIQUE,
    email         VARCHAR(150)    NOT NULL UNIQUE,
    address       VARCHAR(255)    NOT NULL,
    city          VARCHAR(50)     NOT NULL,
    state         VARCHAR(50)     NOT NULL,
    country       VARCHAR(50)     NOT NULL DEFAULT 'India',
    designation   VARCHAR(100)    NOT NULL,
    department    VARCHAR(100)    DEFAULT NULL,
    hire_date     DATE            NOT NULL,
    base_salary   DECIMAL(12,2)   NOT NULL,
    shift_start   TIME            DEFAULT '09:00:00',
    shift_end     TIME            DEFAULT '18:00:00',
    is_active     BOOLEAN         NOT NULL DEFAULT TRUE,
    is_deleted    BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_employees_name    (full_name),
    INDEX idx_employees_dept    (department),
    INDEX idx_employees_active  (is_active),
    INDEX idx_employees_deleted (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Employee HR master records';

-- ----------------------------------------------------------------------------
-- 7.2 Attendance
-- Daily attendance tracking per employee
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Attendance (
    attendance_id   INT     AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT     NOT NULL,
    work_date       DATE    NOT NULL,
    check_in_time   TIME    DEFAULT NULL,
    check_out_time  TIME    DEFAULT NULL,
    status          ENUM(
                        'present',
                        'absent',
                        'half_day',
                        'late',
                        'paid_leave',
                        'unpaid_leave',
                        'holiday'
                    ) NOT NULL DEFAULT 'absent',
    overtime_hours  DECIMAL(4,2) NOT NULL DEFAULT 0.00,
    remarks         VARCHAR(255) DEFAULT NULL,
    marked_by       INT     DEFAULT NULL                   COMMENT 'user_id who recorded this entry',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_attendance_emp_date (employee_id, work_date),
    FOREIGN KEY (employee_id) REFERENCES Employees(employee_id) ON DELETE RESTRICT,
    FOREIGN KEY (marked_by)   REFERENCES Users(user_id)         ON DELETE SET NULL,
    INDEX idx_attendance_date   (work_date),
    INDEX idx_attendance_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Daily employee attendance with check-in/out tracking';

-- ----------------------------------------------------------------------------
-- 7.3 Payroll
-- Monthly salary calculation per employee
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Payroll (
    salary_id           INT             AUTO_INCREMENT PRIMARY KEY,
    employee_id         INT             NOT NULL,
    payroll_month       DATE            NOT NULL               COMMENT 'Use first day of month: YYYY-MM-01',
    total_working_days  INT             NOT NULL,
    present_days        INT             NOT NULL DEFAULT 0,
    paid_leave_days     INT             NOT NULL DEFAULT 0,
    unpaid_leave_days   INT             NOT NULL DEFAULT 0,
    half_days           INT             NOT NULL DEFAULT 0,
    overtime_hours      DECIMAL(6,2)    NOT NULL DEFAULT 0.00,
    base_salary         DECIMAL(12,2)   NOT NULL,
    overtime_amount     DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    bonus               DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    deductions          DECIMAL(12,2)   NOT NULL DEFAULT 0.00,
    net_salary          DECIMAL(12,2)   NOT NULL,
    payment_date        DATE            DEFAULT NULL,
    payment_status      ENUM('pending','paid','hold') NOT NULL DEFAULT 'pending',
    remarks             VARCHAR(255)    DEFAULT NULL,
    processed_by        INT             DEFAULT NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_payroll_emp_month (employee_id, payroll_month),
    FOREIGN KEY (employee_id)   REFERENCES Employees(employee_id) ON DELETE RESTRICT,
    FOREIGN KEY (processed_by)  REFERENCES Users(user_id)         ON DELETE SET NULL,
    INDEX idx_payroll_month  (payroll_month),
    INDEX idx_payroll_status (payment_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Monthly payroll computation and payment records';


-- ============================================================================
-- SECTION 8 — FINANCIAL MANAGEMENT
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 8.1 Cash_Transactions
-- Every cash movement in or out of the register
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Cash_Transactions (
    cash_txn_id    INT             AUTO_INCREMENT PRIMARY KEY,
    txn_date       DATE            NOT NULL,
    txn_type       ENUM('in', 'out') NOT NULL,
    amount         DECIMAL(12,2)   NOT NULL,
    reference_type VARCHAR(50)     DEFAULT NULL             COMMENT 'SALE, PURCHASE, EXPENSE, PAYROLL, etc.',
    reference_id   INT             DEFAULT NULL,
    description    VARCHAR(255)    NOT NULL,
    balance_after  DECIMAL(12,2)   DEFAULT NULL             COMMENT 'Running balance (calculated at insert)',
    recorded_by    INT             DEFAULT NULL,
    shift_date     DATE            DEFAULT NULL             COMMENT 'For cashier shift reconciliation',
    created_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (recorded_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_cash_date      (txn_date),
    INDEX idx_cash_type      (txn_type),
    INDEX idx_cash_reference (reference_type, reference_id),
    INDEX idx_cash_shift     (shift_date, recorded_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Immutable cash register transaction log';

-- ----------------------------------------------------------------------------
-- 8.2 Bank_Transactions
-- Bank account deposits, withdrawals, UPI, cheque tracking
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Bank_Transactions (
    bank_txn_id    INT             AUTO_INCREMENT PRIMARY KEY,
    txn_date       DATE            NOT NULL,
    txn_type       ENUM(
                       'deposit',
                       'withdrawal',
                       'upi_in',
                       'upi_out',
                       'cheque_in',
                       'cheque_out',
                       'transfer_in',
                       'transfer_out',
                       'bank_charge'
                   ) NOT NULL,
    amount         DECIMAL(12,2)   NOT NULL,
    reference_type VARCHAR(50)     DEFAULT NULL,
    reference_id   INT             DEFAULT NULL,
    cheque_no      VARCHAR(50)     DEFAULT NULL,
    upi_ref        VARCHAR(100)    DEFAULT NULL,
    description    VARCHAR(255)    NOT NULL,
    balance_after  DECIMAL(12,2)   DEFAULT NULL,
    is_reconciled  BOOLEAN         NOT NULL DEFAULT FALSE,
    recorded_by    INT             DEFAULT NULL,
    created_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (recorded_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_bank_date        (txn_date),
    INDEX idx_bank_type        (txn_type),
    INDEX idx_bank_reconciled  (is_reconciled),
    INDEX idx_bank_reference   (reference_type, reference_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Bank account transaction log with reconciliation support';

-- ----------------------------------------------------------------------------
-- 8.3 Expenses
-- All operational expenses beyond purchase costs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Expenses (
    expense_id    INT             AUTO_INCREMENT PRIMARY KEY,
    category_id   INT             NOT NULL,
    expense_date  DATE            NOT NULL,
    amount        DECIMAL(12,2)   NOT NULL,
    payment_mode  ENUM('cash', 'bank', 'upi', 'card') NOT NULL DEFAULT 'cash',
    vendor_id     INT             DEFAULT NULL               COMMENT 'Vendor linked if applicable',
    employee_id   INT             DEFAULT NULL               COMMENT 'For reimbursement tracking',
    description   VARCHAR(255)    NOT NULL,
    receipt_ref   VARCHAR(100)    DEFAULT NULL               COMMENT 'Receipt or bill number',
    is_recurring  BOOLEAN         NOT NULL DEFAULT FALSE,
    approved_by   INT             DEFAULT NULL,
    is_approved   BOOLEAN         NOT NULL DEFAULT FALSE,
    is_deleted    BOOLEAN         NOT NULL DEFAULT FALSE,
    recorded_by   INT             DEFAULT NULL,
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP       NULL     DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (category_id)  REFERENCES Expense_Categories(category_id) ON DELETE RESTRICT,
    FOREIGN KEY (vendor_id)    REFERENCES Vendors(vendor_id)               ON DELETE SET NULL,
    FOREIGN KEY (employee_id)  REFERENCES Employees(employee_id)           ON DELETE SET NULL,
    FOREIGN KEY (approved_by)  REFERENCES Users(user_id)                   ON DELETE SET NULL,
    FOREIGN KEY (recorded_by)  REFERENCES Users(user_id)                   ON DELETE SET NULL,
    INDEX idx_expenses_date     (expense_date),
    INDEX idx_expenses_category (category_id),
    INDEX idx_expenses_vendor   (vendor_id),
    INDEX idx_expenses_approved (is_approved),
    INDEX idx_expenses_deleted  (is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='All operational expenses — rent, bills, transport, misc, etc.';


-- ============================================================================
-- SECTION 9 — SYSTEM SUPPORT TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 9.1 Notifications
-- In-app alert and reminder system
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Notifications (
    notification_id  INT           AUTO_INCREMENT PRIMARY KEY,
    user_id          INT           DEFAULT NULL             COMMENT 'NULL = broadcast to all relevant roles',
    notification_type ENUM(
                         'low_stock',
                         'out_of_stock',
                         'expiry_alert',
                         'payment_due',
                         'salary_due',
                         'vendor_payment',
                         'daily_summary',
                         'system_alert'
                     ) NOT NULL,
    title            VARCHAR(150)  NOT NULL,
    message          TEXT          NOT NULL,
    reference_type   VARCHAR(50)   DEFAULT NULL,
    reference_id     INT           DEFAULT NULL,
    is_read          BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    INDEX idx_notif_user    (user_id),
    INDEX idx_notif_type    (notification_type),
    INDEX idx_notif_read    (is_read),
    INDEX idx_notif_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='In-app notifications and alerts for all modules';

-- ----------------------------------------------------------------------------
-- 9.2 Audit_Log
-- Universal immutable audit trail for every write operation in the system
-- Covers: INSERT, UPDATE, DELETE (soft) on all tables
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Audit_Log (
    audit_id        BIGINT          AUTO_INCREMENT PRIMARY KEY,
    table_name      VARCHAR(100)    NOT NULL,
    record_id       INT             NOT NULL               COMMENT 'PK of the affected row',
    operation       ENUM(
                        'INSERT',
                        'UPDATE',
                        'SOFT_DELETE',
                        'RESTORE',
                        'LOGIN',
                        'LOGOUT',
                        'LOGIN_FAILED'
                    ) NOT NULL,
    old_value       JSON            DEFAULT NULL           COMMENT 'Previous state (NULL for INSERT)',
    new_value       JSON            DEFAULT NULL           COMMENT 'New state (NULL for DELETE)',
    changed_fields  VARCHAR(500)    DEFAULT NULL           COMMENT 'Comma-separated list of changed columns',
    performed_by    INT             DEFAULT NULL           COMMENT 'user_id — NULL if system action',
    ip_address      VARCHAR(45)     DEFAULT NULL,
    device_info     VARCHAR(255)    DEFAULT NULL,
    reason          VARCHAR(255)    DEFAULT NULL           COMMENT 'Optional reason provided by user',
    logged_at       TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (performed_by) REFERENCES Users(user_id) ON DELETE SET NULL,
    INDEX idx_audit_table     (table_name),
    INDEX idx_audit_record    (table_name, record_id),
    INDEX idx_audit_operation (operation),
    INDEX idx_audit_user      (performed_by),
    INDEX idx_audit_logged_at (logged_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Universal immutable audit trail — all write operations logged here';

-- ----------------------------------------------------------------------------
-- 9.3 Backups
-- Metadata registry of all CSV/DB backup jobs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS Backups (
    backup_id      INT             AUTO_INCREMENT PRIMARY KEY,
    backup_type    ENUM('csv', 'sql', 'full') NOT NULL DEFAULT 'csv',
    table_name     VARCHAR(100)    DEFAULT NULL           COMMENT 'NULL = full database backup',
    file_path      VARCHAR(500)    NOT NULL,
    file_size_kb   DECIMAL(12,2)   DEFAULT NULL,
    status         ENUM('success', 'failed', 'in_progress') NOT NULL DEFAULT 'in_progress',
    error_message  TEXT            DEFAULT NULL,
    triggered_by   VARCHAR(50)     NOT NULL DEFAULT 'scheduler' COMMENT 'scheduler or user_id',
    created_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_backups_type      (backup_type),
    INDEX idx_backups_table     (table_name),
    INDEX idx_backups_status    (status),
    INDEX idx_backups_created   (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Backup job registry — tracks all CSV and SQL backup runs';


-- ============================================================================
-- FOREIGN KEYS DEFERRED (added after all tables exist)
-- Inventory_Lots.purchase_id → Purchases.purchase_id
-- ============================================================================
ALTER TABLE Inventory_Lots
    ADD CONSTRAINT fk_lots_purchase
    FOREIGN KEY (purchase_id) REFERENCES Purchases(purchase_id) ON DELETE SET NULL;


-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
-- Tables created:
--   Roles, Users, User_Sessions,
--   Vendors, Customers,
--   Expense_Categories, Categories, Products,
--   Inventory_Lots, Inventory_Movements,
--   Sales, Sales_Return,
--   Purchases, Purchase_Return,
--   Employees, Attendance, Payroll,
--   Cash_Transactions, Bank_Transactions, Expenses,
--   Notifications, Audit_Log, Backups
--
-- Total: 23 tables
-- =========================================