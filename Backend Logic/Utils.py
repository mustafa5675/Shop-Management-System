"""
Utils.py
========
Shared helpers used across all modules:
  - backup_to_csv()        — append one row to a CSV backup file
  - display_table()        — pretty-print list-of-dicts via pandas
  - confirm()              — y/n prompt
  - safe_int()             — validated int input
  - safe_float()           — validated float input
  - EXPENSE_ACCOUNT_MAP    — expense category → chart-of-accounts code
"""

import csv
import os
import pandas as pd
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# CSV backup
# ─────────────────────────────────────────────────────────────────────────────

def backup_to_csv(filepath: str, data: dict, fieldnames: list[str]):
    """
    Append one dict row to a CSV file.
    Creates the file (with header row) if it does not exist yet.
    Errors are non-fatal — a backup failure should never block the user.
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    exists = os.path.isfile(filepath) and os.path.getsize(filepath) > 0
    try:
        with open(filepath, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(data)
        print(f"💾 Backup → {filepath}")
    except Exception as e:
        print(f"⚠️  CSV backup failed (non-fatal): {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

def display_table(rows: list[dict], title: str = ""):
    """Pretty-print a list-of-dicts as a pandas table."""
    if not rows:
        print("⚠️  No records found.")
        return
    if title:
        border = "─" * max(len(title) + 4, 60)
        print(f"\n{border}")
        print(f"  {title}")
        print(f"{border}")
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  {len(rows)} row(s)")


# ─────────────────────────────────────────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────────────────────────────────────────

def confirm(prompt: str = "Confirm? (y/n): ") -> bool:
    return input(prompt).strip().lower() == "y"


def safe_int(prompt: str, allow_blank: bool = False) -> int | None:
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("  ❌ Please enter a whole number.")


def safe_float(prompt: str, allow_blank: bool = False) -> float | None:
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            print("  ❌ Please enter a valid number.")


def safe_date(prompt: str, allow_blank: bool = False):
    """Accept YYYY-MM-DD or blank (if allow_blank). Returns datetime.date or None."""
    from datetime import date
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  ❌ Use format YYYY-MM-DD (e.g. 2025-04-01).")


# ─────────────────────────────────────────────────────────────────────────────
# Expense category → chart-of-accounts code mapping
# ─────────────────────────────────────────────────────────────────────────────

EXPENSE_ACCOUNT_MAP: dict[str, str] = {
    "rent"             : "5300",
    "electricity"      : "5400",
    "water"            : "5410",
    "internet"         : "5420",
    "internet & phone" : "5420",
    "office_supplies"  : "5500",
    "tea"              : "5510",
    "tea & refreshments": "5510",
    "marketing"        : "5600",
    "advertising"      : "5600",
    "transport"        : "5700",
    "maintenance"      : "5800",
    "bank_charges"     : "5900",
    "subscriptions"    : "5910",
    "tax"              : "5920",
    "tax & license"    : "5920",
    "miscellaneous"    : "5950",
}


def get_expense_account_code(category_name: str) -> str:
    """
    Map an Expense_Categories.category_name to a chart-of-accounts code.
    Falls back to '5950' (Miscellaneous) if the name is unrecognised.
    """
    return EXPENSE_ACCOUNT_MAP.get(category_name.lower().strip(), "5950")
