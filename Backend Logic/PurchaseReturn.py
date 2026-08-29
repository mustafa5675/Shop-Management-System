from datetime   import datetime, date
from Database   import get_connection
from Session    import Session
from AuditLogger import log_audit, BatchLedger
from Utils      import backup_to_csv, display_table, confirm, safe_int, safe_float, safe_date

def record_purchase_return():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        purchase_id = safe_int("Original Purchase ID : ")
        if not purchase_id: return

        cursor.execute(
            """SELECT pu.*, p.product_name, v.vendor_name
               FROM Purchases pu
               JOIN Products p ON p.product_id=pu.product_id
               JOIN Vendors  v ON v.vendor_id =pu.vendor_id
               WHERE pu.purchase_id=%s AND pu.is_deleted=FALSE""",
            (purchase_id,)
        )
        purchase = cursor.fetchone()
        if not purchase:
            print("❌ Purchase not found."); return

        print(f"\n  Purchase #{purchase_id}: {purchase['product_name']}")
        print(f"  Qty: {purchase['qty_purchased']}  |  Total: ₹{purchase['total']}")
        print(f"  Vendor: {purchase['vendor_name']}")

        qty_returned  = safe_int("Qty to return        : ")
        if not qty_returned or qty_returned <= 0:
            print("❌ Quantity must be positive."); return
        if qty_returned > purchase["qty_purchased"]:
            print(f"❌ Cannot return more than purchased ({purchase['qty_purchased']})."); return

        refund_amount = safe_float(f"Expected refund [₹{purchase['total']}]: ",
                                   allow_blank=True) or float(purchase["total"])
        reason        = input("Reason               : ").strip()
        if not reason:
            print("❌ Reason required."); return
        refund_mode   = input("Refund via (cash/bank/upi/credit): ").strip().lower() or "credit"
        return_date   = date.today()

        proportion    = qty_returned / purchase["qty_purchased"]
        cost_amount   = round(float(purchase["unit_cost"]) * qty_returned, 2)
        gst_reversal  = round(float(purchase.get("gst_amount", 0) or 0) * proportion, 2)

        print(f"\n  Return Qty: {qty_returned}  |  Refund: ₹{refund_amount:,.2f}")
        if not confirm("Confirm return? (y/n): "):
            print("Cancelled."); return

        conn.begin()

        cursor.execute(
            """INSERT INTO Purchase_Return
               (purchase_id, vendor_id, product_id, return_date,
                qty_returned, refund_amount, reason, status, processed_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,'pending',%s)""",
            (purchase_id, purchase["vendor_id"], purchase["product_id"],
             return_date, qty_returned, refund_amount, reason, user["user_id"])
        )
        return_id = cursor.lastrowid

        # Deduct from oldest lot (FIFO) for this product
        cursor.execute(
            """SELECT lot_id, quantity FROM Inventory_Lots
               WHERE product_id=%s AND purchase_id=%s AND is_deleted=FALSE AND quantity>0
               ORDER BY lot_id ASC LIMIT 1""",
            (purchase["product_id"], purchase_id)
        )
        lot = cursor.fetchone()
        lot_id = None
        if lot:
            deduct = min(lot["quantity"], qty_returned)
            cursor.execute(
                "UPDATE Inventory_Lots SET quantity=quantity-%s WHERE lot_id=%s",
                (deduct, lot["lot_id"])
            )
            lot_id = lot["lot_id"]

            cursor.execute(
                """INSERT INTO Inventory_Movements
                   (product_id, lot_id, movement_type, reference_type, reference_id,
                    qty_before, qty_change, qty_after, reason, performed_by)
                   VALUES(%s,%s,'return_out_purchase','PURCHASE_RETURN',%s,
                          %s,%s,%s,%s,%s)""",
                (purchase["product_id"], lot_id, return_id,
                 lot["quantity"], -deduct, lot["quantity"] - deduct,
                 f"Purchase Return #{return_id}", user["user_id"])
            )

        # Expense Ledger reversal
        cursor.execute(
            """CALL record_expense_ledger(%s,'purchase_return_reversal',NULL,
               'PURCHASE_RETURN',%s,%s,%s,%s,%s,NULL,%s,%s, @el_id)""",
            (return_date, return_id,
             -cost_amount, -gst_reversal,
             refund_mode, purchase["vendor_id"],
             f"Purchase Return #{return_id} — {purchase['product_name']}",
             user["user_id"])
        )

        # AP sub-ledger
        if purchase["payment_method"] == "credit":
            cursor.execute(
                """INSERT INTO sub_ledger_ap
                   (transaction_id, vendor_id, reference_type, reference_id,
                    txn_date, debit_amount)
                   VALUES(0,%s,'PURCHASE_RETURN',%s,%s,%s)""",
                (purchase["vendor_id"], return_id, return_date, refund_amount)
            )

        conn.commit()

        BatchLedger.enqueue("post_purchase_return_to_ledger", (
            return_id, str(return_date), refund_amount, cost_amount,
            purchase["payment_method"], purchase["vendor_id"], user["user_id"]
        ))

        log_audit("Purchase_Return", return_id, "INSERT", new_value={
            "purchase_id": purchase_id, "qty_returned": qty_returned,
            "refund_amount": refund_amount, "reason": reason,
            "processed_by": user["username"]
        })
        print(f"✅ Purchase Return #{return_id} recorded. Status: PENDING.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def view_purchase_returns(page=1, page_size=20, status=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds, vals = ["pr.is_deleted=FALSE"], []
        if status:
            conds.append("pr.status=%s"); vals.append(status)

        cursor.execute(
            f"SELECT COUNT(*) AS n FROM Purchase_Return pr WHERE {' AND '.join(conds)}", vals
        )
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            f"""SELECT pr.purchase_return_id, pr.return_date, pr.purchase_id,
                       v.vendor_name, p.product_name,
                       pr.qty_returned, pr.refund_amount, pr.reason, pr.status
                FROM Purchase_Return pr
                LEFT JOIN Vendors  v ON v.vendor_id =pr.vendor_id
                LEFT JOIN Products p ON p.product_id=pr.product_id
                WHERE {' AND '.join(conds)}
                ORDER BY pr.purchase_return_id DESC LIMIT %s OFFSET %s""",
            vals + [page_size, offset]
        )
        display_table(cursor.fetchall(),
                      f"Purchase Returns — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def approve_purchase_return(return_id: int):
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Purchase_Return WHERE purchase_return_id=%s AND status='pending'",
            (return_id,)
        )
        r = cursor.fetchone()
        if not r:
            print("❌ Return not found or not pending."); return
        conn.begin()
        cursor.execute(
            "UPDATE Purchase_Return SET status='approved' WHERE purchase_return_id=%s",
            (return_id,)
        )
        conn.commit()
        log_audit("Purchase_Return", return_id, "UPDATE",
                  old_value={"status": "pending"}, new_value={"status": "approved"},
                  changed_fields="status")
        print(f"✅ Purchase Return #{return_id} approved.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def purchase_return_menu():
    while True:
        print("""
╔══════════════════════════════════╗
║   PURCHASE RETURN MANAGEMENT     ║
╠══════════════════════════════════╣
║  1. Record Purchase Return       ║
║  2. View Purchase Returns        ║
║  3. Approve Purchase Return      ║
║  0. Back                         ║
╚══════════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": record_purchase_return()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                st = input("Status (pending/approved/declined/blank): ").strip() or None
                view_purchase_returns(page=pg, status=st)
            elif choice == "3":
                rid = safe_int("Return ID to approve: ")
                if rid: approve_purchase_return(rid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")
