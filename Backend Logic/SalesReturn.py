"""
Operations
----------
record_sales_return()    Validates original sale · restores stock · refund ·
                         Revenue_Streams reversal · BatchLedger enqueue · audit
view_sales_returns()     Paginated listing with status filter
search_returns()         Filter by sale_id / customer / product / status / date
approve_return()         Admin/manager approve pending return
decline_return()         Admin/manager decline pending return
sales_return_insights()  Monthly return rate, top return reasons
"""

from datetime   import datetime, date
from Database   import get_connection
from Session    import Session
from AuditLogger import log_audit, BatchLedger
from Utils      import backup_to_csv, display_table, confirm, safe_int, safe_float, safe_date

# ── SalesReturn helpers ───────────────────────────────────────────────────────

def record_sales_return():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        sale_id = safe_int("Original Sale ID     : ")
        if not sale_id: return

        cursor.execute(
            """SELECT s.*, p.product_name, p.buying_price, p.gst_percent
               FROM Sales s JOIN Products p ON p.product_id=s.product_id
               WHERE s.sale_id=%s AND s.is_deleted=FALSE""",
            (sale_id,)
        )
        sale = cursor.fetchone()
        if not sale:
            print("❌ Sale not found."); return

        print(f"\n  Sale #{sale_id}: {sale['product_name']}")
        print(f"  Qty Sold: {sale['qty_sold']}  |  Total: ₹{sale['total']}")

        qty_returned   = safe_int("Qty to return        : ")
        if not qty_returned or qty_returned <= 0:
            print("❌ Quantity must be positive."); return
        if qty_returned > sale["qty_sold"]:
            print(f"❌ Cannot return more than sold qty ({sale['qty_sold']})."); return

        refund_amount  = safe_float(f"Refund Amount [₹{sale['total']}]: ", allow_blank=True)
        refund_amount  = refund_amount if refund_amount is not None else float(sale["total"])
        reason         = input("Reason               : ").strip()
        if not reason:
            print("❌ Reason required."); return
        refund_mode    = input("Refund via (cash/bank/upi/credit): ").strip().lower() or "cash"
        return_date    = date.today()

        # COGS reversal: proportional cost of returned qty
        unit_cogs = float(sale["buying_price"])
        cogs_reversal = round(unit_cogs * qty_returned, 2)
        proportion = qty_returned / sale["qty_sold"]
        gst_reversal = round(float(sale["gst_amount"]) * proportion, 2)

        print(f"\n  Refund: ₹{refund_amount:,.2f}  |  Mode: {refund_mode.upper()}")
        if not confirm("Confirm return? (y/n): "):
            print("Cancelled."); return

        conn.begin()

        # 1. Insert return record
        cursor.execute(
            """INSERT INTO Sales_Return
               (sale_id, customer_id, product_id, return_date,
                qty_returned, refund_amount, reason, status, processed_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,'pending',%s)""",
            (sale_id, sale["customer_id"], sale["product_id"],
             return_date, qty_returned, refund_amount, reason, user["user_id"])
        )
        return_id = cursor.lastrowid

        # 2. Restore stock to original lot
        if sale["lot_id"]:
            cursor.execute(
                "UPDATE Inventory_Lots SET quantity=quantity+%s WHERE lot_id=%s",
                (qty_returned, sale["lot_id"])
            )

        # 3. Movement log
        cursor.execute(
            """INSERT INTO Inventory_Movements
               (product_id, lot_id, movement_type, reference_type, reference_id,
                qty_before, qty_change, qty_after, reason, performed_by)
               SELECT product_id, %s, 'return_in_sale', 'SALE_RETURN', %s,
                      quantity-%s, %s, quantity, %s, %s
               FROM Inventory_Lots WHERE lot_id=%s""",
            (sale["lot_id"], return_id, qty_returned, qty_returned,
             f"Return #{return_id}: {reason}", user["user_id"], sale["lot_id"])
        )

        # 4. Revenue reversal in Revenue_Streams
        cursor.execute(
            """CALL record_revenue_stream(%s,'sale_reversal','SALE_RETURN',%s,
               %s,0,%s,%s,%s,%s,%s,%s, @rev_id)""",
            (return_date, return_id,
             -refund_amount, -gst_reversal,
             refund_mode, sale["customer_id"], sale["product_id"],
             f"Return #{return_id} — {sale['product_name']}", user["user_id"])
        )

        conn.commit()

        # 5. Batch ledger
        BatchLedger.enqueue("post_sale_return_to_ledger", (
            return_id, str(return_date), refund_amount, cogs_reversal,
            refund_mode, sale["customer_id"], user["user_id"]
        ))

        log_audit("Sales_Return", return_id, "INSERT", new_value={
            "sale_id": sale_id, "qty_returned": qty_returned,
            "refund_amount": refund_amount, "reason": reason,
            "processed_by": user["username"]
        })
        backup_to_csv("backups/sales_return_backup.csv", {
            "return_id": return_id, "sale_id": sale_id,
            "product_id": sale["product_id"], "qty_returned": qty_returned,
            "refund_amount": refund_amount, "reason": reason,
            "return_date": return_date, "backed_up_at": datetime.now()
        }, ["return_id","sale_id","product_id","qty_returned",
            "refund_amount","reason","return_date","backed_up_at"])
        print(f"✅ Return #{return_id} recorded. Status: PENDING (awaiting approval).")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def view_sales_returns(page=1, page_size=20, status=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds, vals = ["sr.is_deleted=FALSE"], []
        if status:
            conds.append("sr.status=%s"); vals.append(status)

        cursor.execute(
            f"SELECT COUNT(*) AS n FROM Sales_Return sr WHERE {' AND '.join(conds)}", vals
        )
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            f"""SELECT sr.sales_return_id, sr.return_date, sr.sale_id,
                       c.customer_name, p.product_name,
                       sr.qty_returned, sr.refund_amount, sr.reason, sr.status,
                       u.username AS processed_by
                FROM Sales_Return sr
                LEFT JOIN Customers c ON c.customer_id=sr.customer_id
                LEFT JOIN Products  p ON p.product_id =sr.product_id
                LEFT JOIN Users     u ON u.user_id    =sr.processed_by
                WHERE {' AND '.join(conds)}
                ORDER BY sr.sales_return_id DESC LIMIT %s OFFSET %s""",
            vals + [page_size, offset]
        )
        display_table(cursor.fetchall(),
                      f"Sales Returns — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def approve_return(return_id: int):
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Sales_Return WHERE sales_return_id=%s AND status='pending'",
            (return_id,)
        )
        r = cursor.fetchone()
        if not r:
            print("❌ Return not found or not pending."); return
        conn.begin()
        cursor.execute(
            "UPDATE Sales_Return SET status='approved' WHERE sales_return_id=%s",
            (return_id,)
        )
        conn.commit()
        log_audit("Sales_Return", return_id, "UPDATE",
                  old_value={"status": "pending"}, new_value={"status": "approved"},
                  changed_fields="status")
        print(f"✅ Return #{return_id} approved.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def decline_return(return_id: int):
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Sales_Return WHERE sales_return_id=%s AND status='pending'",
            (return_id,)
        )
        r = cursor.fetchone()
        if not r:
            print("❌ Return not found or not pending."); return
        reason = input("Decline reason       : ").strip()
        conn.begin()
        cursor.execute(
            "UPDATE Sales_Return SET status='declined' WHERE sales_return_id=%s",
            (return_id,)
        )
        # Re-deduct the stock that was restored on recording
        if r["product_id"]:
            cursor.execute(
                """UPDATE Inventory_Lots SET quantity=quantity-%s
                   WHERE product_id=%s AND is_deleted=FALSE
                   ORDER BY lot_id DESC LIMIT 1""",
                (r["qty_returned"], r["product_id"])
            )
        conn.commit()
        log_audit("Sales_Return", return_id, "UPDATE",
                  old_value={"status": "pending"}, new_value={"status": "declined"},
                  changed_fields="status", reason=reason)
        print(f"✅ Return #{return_id} declined. Stock adjustment reversed.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def search_returns(sale_id=None, customer_id=None, product_id=None,
                   status=None, date_from=None, date_to=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        conds, vals = ["is_deleted=FALSE"], []
        if sale_id:     conds.append("sale_id=%s");        vals.append(sale_id)
        if customer_id: conds.append("customer_id=%s");    vals.append(customer_id)
        if product_id:  conds.append("product_id=%s");     vals.append(product_id)
        if status:      conds.append("status=%s");         vals.append(status)
        if date_from:   conds.append("return_date>=%s");   vals.append(date_from)
        if date_to:     conds.append("return_date<=%s");   vals.append(date_to)
        cursor.execute(
            f"""SELECT sales_return_id, return_date, sale_id, customer_id,
                       product_id, qty_returned, refund_amount, reason, status
                FROM Sales_Return WHERE {' AND '.join(conds)}
                ORDER BY return_date DESC""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, f"Return Search — {len(rows)} result(s)")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def sales_return_menu():
    while True:
        print("""
╔════════════════════════════════╗
║     SALES RETURN MANAGEMENT    ║
╠════════════════════════════════╣
║  1. Record Sales Return        ║
║  2. View Sales Returns         ║
║  3. Search Returns             ║
║  4. Approve Return             ║
║  5. Decline Return             ║
║  0. Back                       ║
╚════════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": record_sales_return()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                st = input("Status filter (pending/approved/declined/blank): ").strip() or None
                view_sales_returns(page=pg, status=st)
            elif choice == "3":
                sid = safe_int("Sale ID    : ", allow_blank=True)
                cid = safe_int("Customer ID: ", allow_blank=True)
                pid = safe_int("Product ID : ", allow_blank=True)
                st  = input("Status     : ").strip() or None
                df  = safe_date("From date  : ", allow_blank=True)
                dt  = safe_date("To date    : ", allow_blank=True)
                search_returns(sale_id=sid, customer_id=cid, product_id=pid,
                               status=st, date_from=df, date_to=dt)
            elif choice == "4":
                rid = safe_int("Return ID to approve : ")
                if rid: approve_return(rid)
            elif choice == "5":
                rid = safe_int("Return ID to decline : ")
                if rid: decline_return(rid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")