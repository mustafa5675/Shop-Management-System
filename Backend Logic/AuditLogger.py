"""
AuditLogger.py
==============
Two responsibilities:

1. log_audit()  — writes one immutable row to Audit_Log after every
   INSERT / UPDATE / SOFT_DELETE / RESTORE.  Errors are swallowed so a
   logging failure never crashes the main application.

2. BatchLedger  — accumulates financial events from operational modules.
   When the queue reaches BATCH_SIZE (5), all pending entries are posted
   atomically to the accounting layer via the stored procedures defined
   in accounting_ledger.sql.
   Call BatchLedger.flush() on application exit to drain leftovers.

Design decision:
   Ledger tables (transactions, transaction_lines) are NOT touched during
   normal day-to-day work.  They receive data in batches, and are only
   queried for formal audits or period-end reporting.
"""

import json
from datetime import datetime
from Database import get_connection
from Session  import Session


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Audit Log writer
# ─────────────────────────────────────────────────────────────────────────────

def log_audit(
    table_name     : str,
    record_id      : int,
    operation      : str,               # INSERT | UPDATE | SOFT_DELETE | RESTORE
    old_value      : dict | None = None,
    new_value      : dict | None = None,
    changed_fields : str  | None = None,  # comma-separated column names
    reason         : str  | None = None,
):
    """
    Insert one immutable row into Audit_Log.
    The acting user is read from the current Session automatically.
    """
    user_id = Session.user_id()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Audit_Log
                (table_name, record_id, operation,
                 old_value, new_value, changed_fields,
                 performed_by, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                table_name, record_id, operation,
                json.dumps(old_value,  default=str) if old_value  else None,
                json.dumps(new_value,  default=str) if new_value  else None,
                changed_fields,
                user_id,
                reason,
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"⚠️  Audit log warning (non-fatal): {e}")
    finally:
        try:
            if cursor: cursor.close()
            if conn:   conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 2.  Batch Ledger
# ─────────────────────────────────────────────────────────────────────────────

class BatchLedger:
    """
    Accumulates financial events and posts them to the accounting ledger
    every BATCH_SIZE (5) transactions via MySQL stored procedures.

    Each item in the queue is a dict:
        { "procedure": str, "params": tuple, "queued_at": str }

    Stored procedures (defined in accounting_ledger.sql):
        post_sale_to_ledger             (9 params)
        post_sale_return_to_ledger      (7 params)
        post_purchase_to_ledger         (8 params)
        post_purchase_return_to_ledger  (7 params)
        post_expense_to_ledger          (7 params)
        post_payroll_to_ledger          (8 params)
        post_capital_injection_to_ledger(6 params)
    """

    BATCH_SIZE: int = 5
    _queue: list    = []

    # Expected param counts for runtime validation
    _SIGNATURE: dict[str, int] = {
        "post_sale_to_ledger":              9,
        "post_sale_return_to_ledger":       7,
        "post_purchase_to_ledger":          8,
        "post_purchase_return_to_ledger":   7,
        "post_expense_to_ledger":           7,
        "post_payroll_to_ledger":           8,
        "post_capital_injection_to_ledger": 6,
    }

    @classmethod
    def enqueue(cls, procedure: str, params: tuple):
        """
        Add one financial event.  Auto-flushes when queue hits BATCH_SIZE.
        """
        expected = cls._SIGNATURE.get(procedure)
        if expected is not None and len(params) != expected:
            raise ValueError(
                f"Procedure '{procedure}' expects {expected} params, "
                f"got {len(params)}."
            )

        cls._queue.append({
            "procedure" : procedure,
            "params"    : params,
            "queued_at" : datetime.now().isoformat(),
        })

        n = len(cls._queue)
        print(f"📋 Ledger queue: {n}/{cls.BATCH_SIZE} pending.")

        if n >= cls.BATCH_SIZE:
            cls.flush()

    @classmethod
    def flush(cls):
        """
        Post all queued entries atomically to the accounting ledger.
        If the batch fails the queue is preserved for retry.
        Call this explicitly at application exit.
        """
        if not cls._queue:
            return

        snapshot = list(cls._queue)
        conn = cursor = None
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            conn.begin()

            for item in snapshot:
                proc   = item["procedure"]
                params = item["params"]
                ph     = ", ".join(["%s"] * len(params))
                cursor.execute(f"CALL {proc}({ph})", params)

            conn.commit()
            cls._queue.clear()
            print(f"✅ Batch ledger: {len(snapshot)} transaction(s) posted to accounting.")

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"❌ Batch ledger flush failed — queue preserved for retry: {e}")

        finally:
            try:
                if cursor: cursor.close()
                if conn:   conn.close()
            except Exception:
                pass

    @classmethod
    def pending(cls) -> int:
        return len(cls._queue)

    @classmethod
    def status(cls):
        print(f"📊 Batch ledger: {cls.pending()}/{cls.BATCH_SIZE} pending.")
