"""
AuditLogger.py  (v2 — thread-safe + durable)
=============================================

Problems with v1:

1.  In-memory queue (_queue = []).
    If the process crashed after 3 sales but before the 5th triggered a
    flush, those 3 accounting entries were silently lost. The operational
    tables had the sales; the accounting layer did not.

2.  Class-level list shared across threads.
    Concurrent enqueue() and flush() calls could corrupt the list or cause
    the same item to be posted twice.

3.  All-or-nothing batch failure.
    If one stored procedure call inside flush() raised an exception, the
    entire batch rolled back. The 4 valid entries were discarded along with
    the 1 broken one.

4.  No retry logic.
    A transient DB hiccup would permanently lose the batch.

Fixes in v2:

1.  DURABLE QUEUE: every enqueue() writes to `pending_ledger_queue` in the
    database immediately. The in-memory list is gone. Crash recovery runs
    automatically on the first flush() after restart — any rows still marked
    'pending' are reprocessed.

2.  THREAD LOCK: threading.Lock() serialises all enqueue() and flush()
    calls. Only one thread can touch the queue at a time.

3.  PER-ITEM PROCESSING: flush() processes each queue row in its own
    transaction. A failure on item 3 marks that item 'failed' and moves on
    to items 4 and 5. The other 4 items are still posted.

4.  RETRY LOGIC: items with attempt_count < MAX_ATTEMPTS are retried on the
    next flush(). After MAX_ATTEMPTS they are marked 'failed' permanently and
    require manual intervention.

5.  DEADLOCK DETECTION: OperationalError 1213 (deadlock) is caught
    separately and triggers an immediate retry with exponential backoff
    rather than marking the item as failed.
"""

import json
import time
import threading
import pymysql

from Database import get_connection
from Session  import Session

MAX_ATTEMPTS = 3      # max retries per queue item before marking 'failed'
BATCH_SIZE   = 5      # flush when this many 'pending' rows exist


# ─────────────────────────────────────────────────────────────────────────────
# Audit Log writer  (unchanged interface, same as v1)
# ─────────────────────────────────────────────────────────────────────────────

def log_audit(
    table_name     : str,
    record_id      : int,
    operation      : str,
    old_value      : dict | None = None,
    new_value      : dict | None = None,
    changed_fields : str  | None = None,
    reason         : str  | None = None,
):
    """
    Write one immutable row to Audit_Log.
    Acting user is read from the current thread's Session automatically.
    Errors are swallowed — a logging failure must never crash the caller.
    """
    user_id = Session.user_id()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO Audit_Log
                   (table_name, record_id, operation,
                    old_value, new_value, changed_fields,
                    performed_by, reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
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
# Batch Ledger  (v2)
# ─────────────────────────────────────────────────────────────────────────────

class BatchLedger:
    """
    Durable, thread-safe queue for accounting ledger postings.

    Flow:
      enqueue()
        → writes one row to pending_ledger_queue (status='pending')
        → if pending count >= BATCH_SIZE: calls _flush_under_lock()

      flush()  [public, also called at app exit and after logout]
        → acquires _lock
        → calls _flush_under_lock()

      _flush_under_lock()
        → selects all 'pending' and 'retrying' rows (FOR UPDATE)
        → for each row: calls the stored procedure in its own transaction
          → success: UPDATE status='posted', posted_at=NOW()
          → deadlock: sleep + retry up to MAX_ATTEMPTS
          → other error: UPDATE status='failed' or 'retrying', last_error=msg
    """

    _lock      : threading.Lock = threading.Lock()
    BATCH_SIZE : int            = BATCH_SIZE

    # ── Signature validation (same as v1) ────────────────────────────────

    _SIGNATURE: dict[str, int] = {
        "post_sale_to_ledger"              : 9,
        "post_sale_return_to_ledger"       : 7,
        "post_purchase_to_ledger"          : 8,
        "post_purchase_return_to_ledger"   : 7,
        "post_expense_to_ledger"           : 7,
        "post_payroll_to_ledger"           : 8,
        "post_capital_injection_to_ledger" : 6,
    }

    # ── Public API ────────────────────────────────────────────────────────

    @classmethod
    def enqueue(cls, procedure: str, params: tuple,
                reference_type: str | None = None,
                reference_id:   int | None = None):
        """
        Persist one accounting event to pending_ledger_queue.
        Automatically flushes when BATCH_SIZE pending rows exist.
        Thread-safe.
        """
        expected = cls._SIGNATURE.get(procedure)
        if expected is not None and len(params) != expected:
            raise ValueError(
                f"Procedure '{procedure}' expects {expected} params, got {len(params)}."
            )

        with cls._lock:
            conn = cursor = None
            try:
                conn   = get_connection()
                cursor = conn.cursor()

                cursor.execute(
                    """INSERT INTO pending_ledger_queue
                           (procedure_name, params_json,
                            reference_type, reference_id, enqueued_by)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        procedure,
                        json.dumps(list(params), default=str),
                        reference_type,
                        reference_id,
                        Session.user_id(),
                    ),
                )
                conn.commit()

                cursor.execute(
                    "SELECT COUNT(*) AS n FROM pending_ledger_queue WHERE status='pending'"
                )
                pending_count = cursor.fetchone()["n"]
                print(f"📋 Ledger queue: {pending_count}/{cls.BATCH_SIZE} pending.")

                if pending_count >= cls.BATCH_SIZE:
                    cls._flush_under_lock(conn, cursor)

            except Exception as e:
                print(f"❌ BatchLedger.enqueue failed: {e}")
                if conn:
                    try: conn.rollback()
                    except Exception: pass
            finally:
                try:
                    if cursor: cursor.close()
                    if conn:   conn.close()
                except Exception:
                    pass

    @classmethod
    def flush(cls):
        """
        Post all pending queue items to the accounting layer.
        Call this: at app exit, after logout, or manually by accountant.
        Thread-safe.
        """
        with cls._lock:
            conn = cursor = None
            try:
                conn   = get_connection()
                cursor = conn.cursor()
                cls._flush_under_lock(conn, cursor)
            except Exception as e:
                print(f"❌ BatchLedger.flush error: {e}")
            finally:
                try:
                    if cursor: cursor.close()
                    if conn:   conn.close()
                except Exception:
                    pass

    @classmethod
    def recover(cls):
        """
        Call once at application startup.
        Re-queues any items left 'pending' or 'retrying' from a prior crash.
        """
        with cls._lock:
            conn = cursor = None
            try:
                conn   = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) AS n FROM pending_ledger_queue "
                    "WHERE status IN ('pending','retrying')"
                )
                n = cursor.fetchone()["n"]
                if n > 0:
                    print(f"⚠️  Crash recovery: {n} unposted ledger item(s) found. Flushing...")
                    cls._flush_under_lock(conn, cursor)
            except Exception as e:
                print(f"❌ BatchLedger.recover error: {e}")
            finally:
                try:
                    if cursor: cursor.close()
                    if conn:   conn.close()
                except Exception:
                    pass

    @classmethod
    def pending(cls) -> int:
        """Return count of items currently waiting in the queue."""
        conn = cursor = None
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) AS n FROM pending_ledger_queue "
                "WHERE status IN ('pending','retrying')"
            )
            return cursor.fetchone()["n"]
        except Exception:
            return -1
        finally:
            try:
                if cursor: cursor.close()
                if conn:   conn.close()
            except Exception:
                pass

    @classmethod
    def failed_items(cls) -> list[dict]:
        """Return all items that exhausted MAX_ATTEMPTS. Requires manual review."""
        conn = cursor = None
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pending_ledger_queue WHERE status='failed' ORDER BY enqueued_at"
            )
            return cursor.fetchall()
        except Exception:
            return []
        finally:
            try:
                if cursor: cursor.close()
                if conn:   conn.close()
            except Exception:
                pass

    # ── Private ───────────────────────────────────────────────────────────

    @classmethod
    def _flush_under_lock(cls, shared_conn, shared_cursor):
        """
        Must be called while _lock is held.
        Uses shared_conn to SELECT the pending rows (no separate connection),
        then processes each in its own independent connection so one failure
        cannot roll back another.
        """
        shared_cursor.execute(
            """SELECT queue_id, procedure_name, params_json, attempt_count
               FROM pending_ledger_queue
               WHERE status IN ('pending','retrying')
               ORDER BY queue_id ASC
               FOR UPDATE"""           # row-level lock: prevents duplicate processing
        )
        rows = shared_cursor.fetchall()

        if not rows:
            return

        posted = failed = 0

        for row in rows:
            success = cls._post_one(
                queue_id      = row["queue_id"],
                procedure     = row["procedure_name"],
                params        = json.loads(row["params_json"]),
                attempt_count = row["attempt_count"],
            )
            if success:
                posted += 1
            else:
                failed += 1

        parts = []
        if posted: parts.append(f"{posted} posted")
        if failed: parts.append(f"{failed} failed")
        print(f"✅ Batch ledger flush: {', '.join(parts)}.")

    @classmethod
    def _post_one(cls, queue_id: int, procedure: str,
                  params: list, attempt_count: int) -> bool:
        """
        Execute one stored procedure call in its own transaction.
        Returns True on success, False on permanent failure.
        Retries up to MAX_ATTEMPTS on deadlock.
        """
        for attempt in range(MAX_ATTEMPTS):
            conn = cursor = None
            try:
                conn   = get_connection()
                cursor = conn.cursor()
                conn.begin()

                ph = ", ".join(["%s"] * len(params))
                cursor.execute(f"CALL {procedure}({ph})", params)

                # Mark as posted
                cursor.execute(
                    """UPDATE pending_ledger_queue
                       SET status='posted', posted_at=NOW(),
                           attempt_count=attempt_count+1
                       WHERE queue_id=%s""",
                    (queue_id,)
                )
                conn.commit()
                return True

            except pymysql.err.OperationalError as e:
                if conn:
                    try: conn.rollback()
                    except Exception: pass
                if e.args[0] == 1213:                   # ER_LOCK_DEADLOCK
                    sleep_s = 0.1 * (2 ** attempt)      # 0.1s, 0.2s, 0.4s
                    print(f"  ⚠️  Deadlock on queue_id={queue_id}, "
                          f"retry {attempt+1}/{MAX_ATTEMPTS} in {sleep_s}s")
                    time.sleep(sleep_s)
                    continue                             # retry the loop
                # Non-deadlock operational error — fall through to error handler
                cls._mark_error(queue_id, str(e), attempt_count + 1)
                return False

            except Exception as e:
                if conn:
                    try: conn.rollback()
                    except Exception: pass
                cls._mark_error(queue_id, str(e), attempt_count + 1)
                return False

            finally:
                try:
                    if cursor: cursor.close()
                    if conn:   conn.close()
                except Exception:
                    pass

        # Exhausted all retry attempts (only reached on repeated deadlocks)
        cls._mark_error(queue_id, "Deadlock: exhausted all retry attempts", MAX_ATTEMPTS)
        return False

    @classmethod
    def _mark_error(cls, queue_id: int, error_msg: str, attempt_count: int):
        """Update queue item as failed or retrying depending on attempt count."""
        conn = cursor = None
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            new_status = "failed" if attempt_count >= MAX_ATTEMPTS else "retrying"
            cursor.execute(
                """UPDATE pending_ledger_queue
                   SET status=%s, last_error=%s, attempt_count=%s
                   WHERE queue_id=%s""",
                (new_status, error_msg[:2000], attempt_count, queue_id)
            )
            conn.commit()
            if new_status == "failed":
                print(f"  ❌ queue_id={queue_id} permanently failed after "
                      f"{attempt_count} attempt(s): {error_msg[:120]}")
            else:
                print(f"  ↩️  queue_id={queue_id} will retry (attempt {attempt_count}/{MAX_ATTEMPTS})")
        except Exception:
            pass
        finally:
            try:
                if cursor: cursor.close()
                if conn:   conn.close()
            except Exception:
                pass