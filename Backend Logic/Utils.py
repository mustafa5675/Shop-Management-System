"""
Utils.py  (v2 — adds race condition guards)
============================================
New additions over v1:

  with_deadlock_retry()    — decorator that retries a function on MySQL
                             deadlock (ER 1213) with exponential backoff.

  optimistic_update()      — helper that builds the WHERE clause for
                             optimistic-lock UPDATE statements and checks
                             whether the update actually affected a row.
                             Raises ConcurrentModificationError if the row
                             was modified by another transaction between the
                             read and the write.

  ConcurrentModificationError — raised when an optimistic lock conflict
                             is detected. The caller should re-read the row
                             and retry the operation.
"""

import csv
import os
import time
import functools
import pymysql
import pandas as pd
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# Custom exception for optimistic lock conflicts
# ─────────────────────────────────────────────────────────────────────────────

class ConcurrentModificationError(Exception):
    """
    Raised when an optimistic-lock UPDATE finds that the row was modified
    by another transaction between the initial SELECT and this UPDATE.
    Callers should catch this and retry the full read-modify-write cycle.
    """
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Deadlock retry decorator
# ─────────────────────────────────────────────────────────────────────────────

def with_deadlock_retry(max_retries: int = 10, base_delay: float = 0.1, max_delay: float = 5.0):
    """
    Decorator. Retries the wrapped function when MySQL raises a deadlock
    error (OperationalError 1213). Uses exponential backoff.

    Usage:
        @with_deadlock_retry(max_retries=3)
        def record_sale():
            ...

    On each deadlock the function re-executes from the start, so it must be
    idempotent up to the final conn.commit() — which is always the case
    when the function opens its own connection and rolls back on exception.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except pymysql.err.OperationalError as e:
                    if e.args[0] == 1213 and attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"  ⚠️  Deadlock detected, retry {attempt + 1}/"
                              f"{max_retries} in {delay:.2f}s…")
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Optimistic lock helper
# ─────────────────────────────────────────────────────────────────────────────

def optimistic_update(
    cursor,
    table:      str,
    pk_col:     str,
    pk_val:     int,
    known_ver:  int,
    set_clause: str,
    set_values: list,
) -> int:
    """
    Execute an UPDATE that includes a row_version check.

    Builds:
        UPDATE <table>
        SET <set_clause>, row_version = row_version + 1
        WHERE <pk_col> = %s AND row_version = %s

    Returns the new row_version (known_ver + 1) on success.
    Raises ConcurrentModificationError if 0 rows were affected
    (meaning another transaction incremented the version first).

    The caller must be inside an open transaction (conn.begin()) and
    must call conn.commit() after this returns successfully.
    """
    sql = (
        f"UPDATE {table} "
        f"SET {set_clause}, row_version = row_version + 1 "
        f"WHERE {pk_col} = %s AND row_version = %s"
    )
    cursor.execute(sql, set_values + [pk_val, known_ver])
    if cursor.rowcount == 0:
        raise ConcurrentModificationError(
            f"{table}.{pk_col}={pk_val} was modified by another user. "
            "Please refresh and try again."
        )
    return known_ver + 1


# ─────────────────────────────────────────────────────────────────────────────
# CSV backup (unchanged from v1)
# ─────────────────────────────────────────────────────────────────────────────

def backup_to_csv(filepath: str, data: dict, fieldnames: list[str]):
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
# Display helpers (unchanged from v1)
# ─────────────────────────────────────────────────────────────────────────────

def display_table(rows: list[dict], title: str = ""):
    if not rows:
        print("⚠️  No records found.")
        return
    if title:
        border = "─" * max(len(title) + 4, 60)
        print(f"\n{border}\n  {title}\n{border}")
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n  {len(rows)} row(s)")


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
    from datetime import date
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  ❌ Use format YYYY-MM-DD.")


# ─────────────────────────────────────────────────────────────────────────────
# Expense category → chart-of-accounts code (unchanged from v1)
# ─────────────────────────────────────────────────────────────────────────────

EXPENSE_ACCOUNT_MAP: dict[str, str] = {
    "rent"              : "5300",
    "electricity"       : "5400",
    "water"             : "5410",
    "internet"          : "5420",
    "internet & phone"  : "5420",
    "office_supplies"   : "5500",
    "tea"               : "5510",
    "tea & refreshments": "5510",
    "marketing"         : "5600",
    "advertising"       : "5600",
    "transport"         : "5700",
    "maintenance"       : "5800",
    "bank_charges"      : "5900",
    "subscriptions"     : "5910",
    "tax"               : "5920",
    "tax & license"     : "5920",
    "miscellaneous"     : "5950",
}


def get_expense_account_code(category_name: str) -> str:
    return EXPENSE_ACCOUNT_MAP.get(category_name.lower().strip(), "5950")