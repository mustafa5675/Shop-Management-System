"""
SalesReturn.py  /  Purchase.py  /  PurchaseReturn.py
=====================================================
Three modules in one file for conciseness.
Import individually:  from SalesReturn import sales_return_menu  (etc.)
Or just run this file directly to access all three menus.
"""

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — SalesReturn.py
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Purchase.py
# ══════════════════════════════════════════════════════════════════════════════
"""
Operations
----------
record_purchase()        New lot creation · AP sub-ledger (credit) ·
                         Expense_Ledger insert · BatchLedger enqueue · audit
view_purchases()         Paginated + date/vendor/product/status filters
search_purchases()       Multi-filter including invoice number and amount range
update_purchase()        Soft-update (invoice_no, payment_status only post-commit)
soft_delete_purchase()   Deducts added lot, marks deleted
purchase_insights()      Vendor-wise spend, COGS ratio, overdue AP
"""

def record_purchase():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        vendor_id = safe_int("Vendor ID            : ")
        if not vendor_id: return
        cursor.execute(
            "SELECT * FROM Vendors WHERE vendor_id=%s AND is_deleted=FALSE", (vendor_id,)
        )
        vendor = cursor.fetchone()
        if not vendor:
            print("❌ Vendor not found."); return

        product_id = safe_int("Product ID           : ")
        if not product_id: return
        cursor.execute(
            "SELECT * FROM Products WHERE product_id=%s AND is_deleted=FALSE", (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            print("❌ Product not found."); return

        qty        = safe_int("Qty Purchased        : ")
        unit_cost  = safe_float("Unit Cost (₹)        : ")
        freight    = safe_float("Freight / Shipping   : ") or 0.0
        gst_pct    = safe_float(f"GST % [{product['gst_percent']}]: ",
                                allow_blank=True) or float(product["gst_percent"])
        payment_m  = input("Payment (cash/card/upi/net_banking/credit): ").strip().lower()
        invoice_no = input("Vendor Invoice No.   : ").strip() or None
        exp_date   = safe_date("Expiry Date [blank]  : ", allow_blank=True)
        batch_no   = input("Batch No. [blank]    : ").strip() or None

        if not qty or qty <= 0 or not unit_cost or unit_cost <= 0:
            print("❌ Quantity and unit cost must be positive."); return

        total_before_gst = (unit_cost * qty) + freight
        gst_amount       = round(total_before_gst * gst_pct / 100, 2)
        total            = round(total_before_gst + gst_amount, 2)
        purchase_date    = date.today()

        from datetime import timedelta
        due_date = purchase_date + timedelta(days=vendor["credit_period_days"])

        print(f"""
  ─── Purchase Summary ───────────────────
  Vendor   : {vendor['vendor_name']}
  Product  : {product['product_name']}
  Qty      : {qty}  @ ₹{unit_cost:,.2f}
  Freight  : ₹{freight:,.2f}
  GST      : ₹{gst_amount:,.2f}  ({gst_pct}%)
  TOTAL    : ₹{total:,.2f}
  Due Date : {due_date}
  Payment  : {payment_m.upper()}
  ─────────────────────────────────────────""")
        if not confirm("Confirm purchase? (y/n): "):
            print("Cancelled."); return

        conn.begin()

        # 1. Insert purchase record
        cursor.execute(
            """INSERT INTO Purchases
               (vendor_id, product_id, purchase_date, qty_purchased,
                unit_cost, freight_cost, total, due_date,
                payment_method, payment_status, invoice_no, created_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (vendor_id, product_id, purchase_date, qty,
             unit_cost, freight, total, due_date,
             payment_m,
             "paid" if payment_m != "credit" else "pending",
             invoice_no, user["user_id"])
        )
        purchase_id = cursor.lastrowid

        # 2. Create inventory lot
        landed_cost_per_unit = round((total_before_gst) / qty, 4)
        cursor.execute(
            """INSERT INTO Inventory_Lots
               (product_id, purchase_id, quantity, cost_price,
                exp_date, batch_no)
               VALUES(%s,%s,%s,%s,%s,%s)""",
            (product_id, purchase_id, qty,
             landed_cost_per_unit, exp_date, batch_no)
        )
        lot_id = cursor.lastrowid

        # 3. Movement log
        cursor.execute(
            """SELECT COALESCE(SUM(quantity),0) AS qty
               FROM Inventory_Lots WHERE product_id=%s AND is_deleted=FALSE AND lot_id!=%s""",
            (product_id, lot_id)
        )
        before_qty = cursor.fetchone()["qty"]
        cursor.execute(
            """INSERT INTO Inventory_Movements
               (product_id, lot_id, movement_type, reference_type, reference_id,
                qty_before, qty_change, qty_after, reason, performed_by)
               VALUES(%s,%s,'purchase_in','PURCHASE',%s,%s,%s,%s,%s,%s)""",
            (product_id, lot_id, purchase_id,
             before_qty, qty, before_qty + qty,
             f"Purchase #{purchase_id} from {vendor['vendor_name']}", user["user_id"])
        )

        # 4. Expense Ledger
        cursor.execute(
            "SELECT category_id FROM Expense_Categories WHERE category_name='miscellaneous' LIMIT 1"
        )
        cat_row = cursor.fetchone()
        cat_id  = cat_row["category_id"] if cat_row else None
        cursor.execute(
            """CALL record_expense_ledger(%s,'cost_of_goods',%s,'PURCHASE',%s,
               %s,%s,%s,%s,NULL,%s,%s, @el_id)""",
            (purchase_date, cat_id, purchase_id,
             total_before_gst, gst_amount, payment_m,
             vendor_id,
             f"Purchase #{purchase_id} — {product['product_name']}",
             user["user_id"])
        )

        # 5. AP sub-ledger for credit purchases
        if payment_m == "credit":
            cursor.execute(
                """INSERT INTO sub_ledger_ap
                   (transaction_id, vendor_id, reference_type, reference_id,
                    txn_date, credit_amount, due_date)
                   VALUES(0,%s,'PURCHASE',%s,%s,%s,%s)""",
                (vendor_id, purchase_id, purchase_date, total, due_date)
            )

        conn.commit()

        # 6. Batch ledger
        BatchLedger.enqueue("post_purchase_to_ledger", (
            purchase_id, str(purchase_date), total_before_gst,
            gst_amount, payment_m, vendor_id, str(due_date), user["user_id"]
        ))

        log_audit("Purchases", purchase_id, "INSERT", new_value={
            "vendor_id": vendor_id, "product_id": product_id,
            "qty_purchased": qty, "total": total,
            "payment_method": payment_m, "created_by": user["username"]
        })
        backup_to_csv("backups/purchases_backup.csv", {
            "purchase_id": purchase_id, "vendor_id": vendor_id,
            "product_id": product_id, "qty_purchased": qty,
            "unit_cost": unit_cost, "freight": freight,
            "gst_amount": gst_amount, "total": total,
            "payment_method": payment_m, "due_date": due_date,
            "created_by": user["username"], "backed_up_at": datetime.now()
        }, ["purchase_id","vendor_id","product_id","qty_purchased",
            "unit_cost","freight","gst_amount","total",
            "payment_method","due_date","created_by","backed_up_at"])
        print(f"\n✅ Purchase #{purchase_id} recorded. Lot #{lot_id} created with {qty} units.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def view_purchases(page=1, page_size=20, date_from=None, date_to=None,
                   vendor_id=None, product_id=None, payment_status=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds = ["pu.is_deleted=FALSE"]
        vals  = []
        if date_from:       conds.append("pu.purchase_date>=%s"); vals.append(date_from)
        if date_to:         conds.append("pu.purchase_date<=%s"); vals.append(date_to)
        if vendor_id:       conds.append("pu.vendor_id=%s");      vals.append(vendor_id)
        if product_id:      conds.append("pu.product_id=%s");     vals.append(product_id)
        if payment_status:  conds.append("pu.payment_status=%s"); vals.append(payment_status)

        where = " AND ".join(conds)
        cursor.execute(f"SELECT COUNT(*) AS n FROM Purchases pu WHERE {where}", vals)
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            f"""SELECT pu.purchase_id, pu.purchase_date, v.vendor_name,
                       p.product_name, pu.qty_purchased, pu.unit_cost,
                       pu.freight_cost, pu.total, pu.payment_method,
                       pu.payment_status, pu.due_date, pu.invoice_no
                FROM Purchases pu
                LEFT JOIN Vendors  v ON v.vendor_id =pu.vendor_id
                LEFT JOIN Products p ON p.product_id=pu.product_id
                WHERE {where}
                ORDER BY pu.purchase_id DESC LIMIT %s OFFSET %s""",
            vals + [page_size, offset]
        )
        display_table(cursor.fetchall(),
                      f"Purchases — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def search_purchases(date_from=None, date_to=None, vendor_id=None,
                     product_id=None, invoice_no=None, payment_status=None,
                     min_amount=None, max_amount=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds, vals = ["pu.is_deleted=FALSE"], []
        if date_from:      conds.append("pu.purchase_date>=%s"); vals.append(date_from)
        if date_to:        conds.append("pu.purchase_date<=%s"); vals.append(date_to)
        if vendor_id:      conds.append("pu.vendor_id=%s");      vals.append(vendor_id)
        if product_id:     conds.append("pu.product_id=%s");     vals.append(product_id)
        if invoice_no:     conds.append("pu.invoice_no LIKE %s");vals.append(f"%{invoice_no}%")
        if payment_status: conds.append("pu.payment_status=%s"); vals.append(payment_status)
        if min_amount:     conds.append("pu.total>=%s");         vals.append(min_amount)
        if max_amount:     conds.append("pu.total<=%s");         vals.append(max_amount)

        cursor.execute(
            f"""SELECT pu.purchase_id, pu.purchase_date, v.vendor_name,
                       p.product_name, pu.qty_purchased, pu.total,
                       pu.payment_method, pu.payment_status, pu.due_date
                FROM Purchases pu
                LEFT JOIN Vendors  v ON v.vendor_id =pu.vendor_id
                LEFT JOIN Products p ON p.product_id=pu.product_id
                WHERE {' AND '.join(conds)}
                ORDER BY pu.purchase_date DESC""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, f"Purchase Search — {len(rows)} result(s)")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def update_purchase(purchase_id: int):
    user = Session.require_role("admin", "manager", "accountant")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Purchases WHERE purchase_id=%s AND is_deleted=FALSE",
            (purchase_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Purchase not found."); return

        print(f"\nPurchase #{purchase_id}  |  Total: ₹{old['total']}")
        print("  Only invoice_no and payment_status can be soft-updated here.")

        updates, values, changed = [], [], {}

        inv = input(f"  Invoice No [{old['invoice_no']}]: ").strip()
        if inv and inv != str(old["invoice_no"] or ""):
            updates.append("invoice_no=%s"); values.append(inv)
            changed["invoice_no"] = {"old": old["invoice_no"], "new": inv}

        ps = input(f"  Payment Status [{old['payment_status']}] (paid/pending/partial): ").strip().lower()
        if ps and ps != old["payment_status"]:
            updates.append("payment_status=%s"); values.append(ps)
            changed["payment_status"] = {"old": old["payment_status"], "new": ps}

        if not updates:
            print("⚠️  No changes."); return

        reason = input("Reason               : ").strip()
        if not reason:
            print("❌ Reason required."); return

        values.append(purchase_id)
        conn.begin()
        cursor.execute(
            f"UPDATE Purchases SET {', '.join(updates)} WHERE purchase_id=%s", values
        )
        conn.commit()
        log_audit("Purchases", purchase_id, "UPDATE",
                  old_value={k: old[k] for k in changed},
                  new_value={k: v["new"] for k, v in changed.items()},
                  changed_fields=", ".join(changed.keys()), reason=reason)
        print(f"✅ Purchase #{purchase_id} updated.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def soft_delete_purchase(purchase_id: int):
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM Purchases WHERE purchase_id=%s AND is_deleted=FALSE",
            (purchase_id,)
        )
        pur = cursor.fetchone()
        if not pur:
            print("❌ Purchase not found."); return

        reason = input("Reason               : ").strip()
        if not reason: print("❌ Reason required."); return
        if not confirm(f"Soft-delete Purchase #{purchase_id}? (y/n): "):
            print("Cancelled."); return

        conn.begin()
        cursor.execute(
            "UPDATE Purchases SET is_deleted=TRUE WHERE purchase_id=%s", (purchase_id,)
        )
        # Deduct the lot that was created for this purchase
        cursor.execute(
            "UPDATE Inventory_Lots SET is_deleted=TRUE WHERE purchase_id=%s",
            (purchase_id,)
        )
        conn.commit()
        log_audit("Purchases", purchase_id, "SOFT_DELETE",
                  old_value=dict(pur), reason=reason)
        print(f"✅ Purchase #{purchase_id} soft-deleted. Associated lot hidden.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def purchase_insights(vendor_id: int = None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        where = "pu.is_deleted=FALSE"
        vals  = []
        if vendor_id:
            where += " AND pu.vendor_id=%s"; vals.append(vendor_id)

        cursor.execute(
            f"""SELECT COUNT(*) AS orders,
                       SUM(pu.total) AS total_spend,
                       AVG(pu.total) AS avg_order,
                       MAX(pu.purchase_date) AS last_order,
                       SUM(CASE WHEN pu.payment_status='pending'
                                THEN pu.total ELSE 0 END) AS outstanding_ap
                FROM Purchases pu WHERE {where}""",
            vals
        )
        s = cursor.fetchone()

        cursor.execute(
            f"""SELECT p.product_name, SUM(pu.qty_purchased) AS qty_bought,
                       SUM(pu.total) AS spend
                FROM Purchases pu JOIN Products p ON p.product_id=pu.product_id
                WHERE {where}
                GROUP BY p.product_id ORDER BY spend DESC LIMIT 5""",
            vals
        )
        top = cursor.fetchall()

        label = f"Vendor #{vendor_id}" if vendor_id else "All Vendors"
        W = 60
        print(f"\n{'═'*W}")
        print(f"  Purchase Insights — {label}")
        print(f"{'═'*W}")
        print(f"  Orders          : {s['orders'] or 0}")
        print(f"  Total Spent     : ₹{(s['total_spend'] or 0):>12,.2f}")
        print(f"  Avg Order       : ₹{(s['avg_order'] or 0):>12,.2f}")
        print(f"  Last Order      : {s['last_order'] or '—'}")
        print(f"  Outstanding AP  : ₹{(s['outstanding_ap'] or 0):>12,.2f}")
        if top:
            print(f"{'─'*W}")
            print("  Top Products:")
            for p in top:
                print(f"    {p['product_name']:<32} ₹{p['spend']:>10,.2f}")
        print(f"{'═'*W}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def purchase_menu():
    while True:
        print("""
╔════════════════════════════════╗
║      PURCHASE MANAGEMENT       ║
╠════════════════════════════════╣
║  1. Record Purchase            ║
║  2. View Purchases             ║
║  3. Search Purchases           ║
║  4. Update Purchase            ║
║  5. Delete Purchase (Soft)     ║
║  6. Purchase Insights          ║
║  0. Back                       ║
╚════════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": record_purchase()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                view_purchases(page=pg)
            elif choice == "3":
                df  = safe_date("From    : ", allow_blank=True)
                dt  = safe_date("To      : ", allow_blank=True)
                vid = safe_int("Vendor  : ", allow_blank=True)
                pid = safe_int("Product : ", allow_blank=True)
                inv = input("Invoice : ").strip() or None
                ps  = input("Status  : ").strip() or None
                search_purchases(date_from=df, date_to=dt, vendor_id=vid,
                                 product_id=pid, invoice_no=inv, payment_status=ps)
            elif choice == "4":
                pid = safe_int("Purchase ID to update : ")
                if pid: update_purchase(pid)
            elif choice == "5":
                pid = safe_int("Purchase ID to delete : ")
                if pid: soft_delete_purchase(pid)
            elif choice == "6":
                vid = safe_int("Vendor ID [blank=all] : ", allow_blank=True)
                purchase_insights(vid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PurchaseReturn.py
# ══════════════════════════════════════════════════════════════════════════════

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
