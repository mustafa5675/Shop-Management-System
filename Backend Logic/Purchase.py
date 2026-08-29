from datetime   import datetime, date
from Database   import get_connection
from Session    import Session
from AuditLogger import log_audit, BatchLedger
from Utils      import backup_to_csv, display_table, confirm, safe_int, safe_float, safe_date

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
