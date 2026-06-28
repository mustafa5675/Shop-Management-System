# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

Project: Retail Shop Management System (Python + MySQL)

Overview
- A CLI-driven backend that records and analyzes retail operations (sales, purchases, returns, customers) with MySQL as the source of truth and CSV as a lightweight redundancy layer. Pandas powers tabular summaries; Matplotlib powers basic charts.
- Active code lives in Shop-Management-System/. The SQL schema for MySQL is Shop-Management-System/Shop_Managemt_System.sql.

Prerequisites
- Python 3 (Windows/PowerShell environment)
- MySQL Server and mysql client

Setup
1) Create a virtual environment (PowerShell):
   - python -m venv .venv
   - .\.venv\Scripts\Activate.ps1

2) Install Python dependencies (no requirements.txt; install directly):
   - pip install pymysql pandas matplotlib

3) Initialize the database schema (prompts for password):
   - mysql -u root -p < ".\Shop-Management-System\Shop_Managemt_System.sql"

Common commands
- Run the full CLI menu:
  - python .\Shop-Management-System\Main.py

- Run a specific viewer function without entering the main menu (keeps repo root as CWD):
  - Sales (tabular/line/bar; weekly/monthly/yearly):
    - python -c "import sys; sys.path.insert(0, r'.\\Shop-Management-System'); import Sales; Sales.run_sales_viewer()"
  - Sales Return viewer:
    - python -c "import sys; sys.path.insert(0, r'.\\Shop-Management-System'); import SalesReturn; SalesReturn.run_sales_return_viewer()"
  - Advanced Purchases viewer (filters + bill grouping + export + stats):
    - python -c "import sys; sys.path.insert(0, r'.\\Shop-Management-System'); from Purchase import advanced_purchases_viewer; advanced_purchases_viewer()"

Notes
- No linter/test tooling is configured in this repo. If that changes (e.g., adding pytest/ruff), update this file with the exact commands and configs.
- Database connection details are defined in Shop-Management-System/Database.py and default to a local MySQL instance.

High-level architecture
- Entry point (Main.py)
  - Presents a text-based menu that routes to feature-specific menus:
    - Sales (Sales.py)
    - Sales Returns (SalesReturn.py)
    - Customers (Customers.py)
    - Purchases (Purchase.py)
    - Purchase Returns (PurchaseReturn.py – currently a stub)

- Persistence (Database.py)
  - get_connection() centralizes access to MySQL using pymysql and returns DictCursor rows to make downstream Pandas DataFrame conversion straightforward.

- Domain modules
  - Sales.py
    - record_sales(): interactive capture → INSERT into Sales; appends to sales_backup.csv for redundancy.
    - view_sales(form_of_data, timeline): SELECT → Pandas DataFrame → resample by week/month/year → return DataFrame or render Matplotlib chart.
    - run_sales_viewer(): interactive wrapper for view_sales.
  - SalesReturn.py
    - record_sales_return(): interactive capture → INSERT into SalesReturn; appends to sales_return_backup.csv.
    - view_sales_return(...), run_sales_return_viewer(): analogous to Sales viewer, grouped by refund amounts over time.
  - Customers.py
    - CRUD operations with simple validation, plus keyword search across name/email/phone. read paths return Pandas tables for operator visibility.
  - Purchase.py
    - record_purchases(): interactive capture including payment method/status and due date (computed from Products.credit_period_days) → INSERT into Purchases; CSV backup.
    - fetch_filtered_purchases(filters): dynamic SQL JOIN across Purchases, Vendors, Products with optional vendor/date/status/amount filters → DataFrame.
    - group_purchases_into_bills[_silent](): groups by (VendorName, PurchaseDate) to produce per-bill item DataFrames and a summary DataFrame.
    - export/display/navigate/statistics helpers: rich, interactive console flows for comparing bills, exporting to CSV, and viewing breakdowns.
    - advanced_purchases_viewer(): orchestrates filters → fetch → grouping → interactive navigator.
  - Products.py
    - Holds configuration-like value credit_period_days used by purchases.
  - PurchaseReturn.py
    - Placeholder menu function; no persistence/flows implemented yet.

- Schema (Shop_Managemt_System.sql)
  - Defines core tables: Customers, Products, Sales, SalesReturn, Purchases, PurchaseReturn, Vendors, Employees, Attendance, Payroll, Inventory, CashRegister, BankRegister.
  - Calculated columns (e.g., Sales.TotalAmount, Purchases.TotalAmount) and enumerations for payment/status values guide application logic.
  - Some tables (e.g., CashRegister/BankRegister/Payroll) are not yet exercised by the current Python modules but indicate intended future scope (cash/bank tracking, payroll linked to attendance, etc.).

Data flow
- Interactive input → validation → DB INSERT via pymysql.
- SELECT queries → list[dict] → Pandas DataFrame for tabular output, grouping/aggregation, and optional charting.
- Best-effort CSV backups for critical INSERT paths (sales, purchases, returns, customers) to support lightweight recovery/auditing outside MySQL.

Repository layout (brief)
- Shop-Management-System/: main Python modules and schema SQL.
- .vscode/: workspace settings.

When to update this file
- Dependency changes (add/remove libraries or introduce requirements.txt/poetry/pipenv).
- New commands for linting/testing or a new entry point.
- Schema changes that materially affect module behavior (e.g., new columns, renamed tables).
