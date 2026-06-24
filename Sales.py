"""
Sales.py
========
Core sales processing module.

Operations
----------
record_sale()            FIFO stock deduction · GST calc · AR sub-ledger ·
                         Revenue_Streams insert · BatchLedger enqueue · audit · CSV
view_sales()             Paginated listing with date/product/customer filters
search_sales()           Multi-filter: date range / customer / product /
                         payment method / amount range / status
update_sale()            Soft-update (non-financial fields only; financial
                         fields require void + re-entry to preserve integrity)
soft_delete_sale()       Reverses stock, marks deleted, notifies batch ledger
sale_insights()          Per-sale cost/margin breakdown
daily_report()           Date-level summary: revenue, COGS, margin, units
monthly_report()         Month-level trend with payment method breakdown
top_products()           Best-selling products by revenue and units
"""

import csv
from datetime import datetime, date
from Database    import get_connection
from Session     import Session
from AuditLogger import log_audit, BatchLedger
from Utils       import (
    backup_to_csv, display_table, confirm,
    safe_int, safe_float, safe_date
)

BACKUP_FILE = "backups/sales_backup.csv"
TABLE       = "Sales"
BACKUP_COLS = [
    "sale_id","sale_date","customer_id","product_id","lot_id",
    "qty_sold","unit_price","discount_pct","gst_amount",
    "total","payment_method","processed_by","backed_up_at"
]


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_product(cursor, product_id: int) -> dict | None:
    cursor.execute(
        "SELECT * FROM Products WHERE product_id=%s AND is_deleted=FALSE",
        (product_id,)
    )
    return cursor.fetchone()


def _deduct_stock_fifo(cursor, product_id: int, qty_needed: int) -> tuple[list, float]:
    """
    Deducts qty_needed from Inventory_Lots (oldest lot first — FIFO).
    Returns: (deductions list, weighted_avg_cost per unit).
    Raises ValueError if stock is insufficient.
    """
    cursor.execute(
        """SELECT lot_id, quantity, cost_price
           FROM Inventory_Lots
           WHERE product_id=%s AND is_deleted=FALSE AND quantity>0
           ORDER BY lot_id ASC""",
        (product_id,)
    )
    lots = cursor.fetchall()
    total_avail = sum(l["quantity"] for l in lots)
    if total_avail < qty_needed:
        raise ValueError(
            f"Insufficient stock. Available: {total_avail}, Required: {qty_needed}"
        )

    deductions    = []
    remaining     = qty_needed
    weighted_cost = 0.0

    for lot in lots:
        if remaining <= 0:
            break
        deduct = min(lot["quantity"], remaining)
        cursor.execute(
            "UPDATE Inventory_Lots SET quantity=quantity-%s WHERE lot_id=%s",
            (deduct, lot["lot_id"])
        )
        weighted_cost += deduct * float(lot["cost_price"])
        deductions.append({"lot_id": lot["lot_id"], "qty": deduct,
                            "cost": float(lot["cost_price"])})
        remaining -= deduct

    avg_cost = weighted_cost / qty_needed
    return deductions, avg_cost


def _get_stock_qty(cursor, product_id: int) -> int:
    cursor.execute(
        """SELECT COALESCE(SUM(quantity),0) AS qty
           FROM Inventory_Lots WHERE product_id=%s AND is_deleted=FALSE""",
        (product_id,)
    )
    return cursor.fetchone()["qty"]


# ─────────────────────────────────────────────────────────────────────────────
# RECORD SALE
# ─────────────────────────────────────────────────────────────────────────────

def record_sale():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        # ── Inputs ───────────────────────────────────────────────────────
        product_id = safe_int("Product ID           : ")
        if not product_id: return

        product = _get_product(cursor, product_id)
        if not product:
            print("❌ Product not found."); return

        stock = _get_stock_qty(cursor, product_id)
        print(f"   ℹ️  Stock available : {stock} {product['unit']}")
        if stock <= 0:
            print("❌ Out of stock."); return

        qty = safe_int("Quantity to sell     : ")
        if not qty or qty <= 0:
            print("❌ Quantity must be positive."); return

        # Default to product's selling price but allow override
        print(f"   ℹ️  Default price    : ₹{product['selling_price']}")
        unit_price  = safe_float(f"Unit Price [₹{product['selling_price']}]: ",
                                 allow_blank=True) or float(product["selling_price"])
        discount_pct = safe_float("Discount % [0]       : ", allow_blank=True) or 0.0
        payment_method = input("Payment (cash/card/upi/net_banking/credit): ").strip().lower()
        valid_pm = ("cash","card","upi","net_banking","credit")
        if payment_method not in valid_pm:
            print(f"❌ Payment must be one of: {valid_pm}"); return

        customer_id = None
        if payment_method == "credit":
            customer_id = safe_int("Customer ID (required for credit): ")
            if not customer_id:
                print("❌ Customer ID required for credit sales."); return
            cursor.execute(
                "SELECT customer_id FROM Customers WHERE customer_id=%s AND is_deleted=FALSE",
                (customer_id,)
            )
            if not cursor.fetchone():
                print("❌ Customer not found."); return
        else:
            cid_raw = safe_int("Customer ID [blank=walk-in]: ", allow_blank=True)
            customer_id = cid_raw

        sale_date = date.today()

        # ── Calculations ──────────────────────────────────────────────────
        gross_amount    = unit_price * qty
        discount_amount = round(gross_amount * discount_pct / 100, 2)
        taxable_amount  = gross_amount - discount_amount
        gst_amount      = round(taxable_amount * float(product["gst_percent"]) / 100, 2)
        total           = round(taxable_amount + gst_amount, 2)
        cogs_amount     = 0.0   # computed after FIFO

        # ── Confirmation ──────────────────────────────────────────────────
        print(f"""
  ─── Sale Summary ──────────────────────
  Product    : {product['product_name']}
  Qty        : {qty} {product['unit']}
  Unit Price : ₹{unit_price:,.2f}
  Discount   : {discount_pct}%  (₹{discount_amount:,.2f})
  GST        : ₹{gst_amount:,.2f}  ({product['gst_percent']}%)
  TOTAL      : ₹{total:,.2f}
  Payment    : {payment_method.upper()}
  ────────────────────────────────────────""")
        if not confirm("Confirm sale? (y/n): "):
            print("Cancelled."); return

        # ── Database transaction ──────────────────────────────────────────
        conn.begin()

        # 1. Deduct stock FIFO
        deductions, avg_cost = _deduct_stock_fifo(cursor, product_id, qty)
        cogs_amount = round(avg_cost * qty, 2)
        primary_lot_id = deductions[0]["lot_id"]

        # 2. Insert sale
        cursor.execute(
            """INSERT INTO Sales
               (sale_date, customer_id, product_id, lot_id, qty_sold,
                unit_price, discount_pct, gst_amount, total,
                payment_method, payment_status, processed_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sale_date, customer_id, product_id, primary_lot_id,
             qty, unit_price, discount_pct, gst_amount, total,
             payment_method,
             "paid" if payment_method != "credit" else "pending",
             user["user_id"])
        )
        sale_id = cursor.lastrowid

        # 3. Inventory movement log
        before_qty = stock
        after_qty  = stock - qty
        cursor.execute(
            """INSERT INTO Inventory_Movements
               (product_id, lot_id, movement_type, reference_type, reference_id,
                qty_before, qty_change, qty_after, reason, performed_by)
               VALUES(%s,%s,'sale_out','SALE',%s,%s,%s,%s,%s,%s)""",
            (product_id, primary_lot_id, sale_id,
             before_qty, -qty, after_qty,
             f"Sale #{sale_id}", user["user_id"])
        )

        # 4. Revenue stream
        cursor.execute(
            """CALL record_revenue_stream(
                %s,'product_sale','SALE',%s,%s,%s,%s,%s,%s,%s,%s,%s, @rev_id)""",
            (sale_date, sale_id, gross_amount, discount_amount,
             gst_amount, payment_method, customer_id, product_id,
             f"Sale #{sale_id} — {product['product_name']}", user["user_id"])
        )

        # 5. AR sub-ledger for credit sales
        if payment_method == "credit" and customer_id:
            cursor.execute(
                """INSERT INTO sub_ledger_ar
                   (transaction_id, customer_id, reference_type, reference_id,
                    txn_date, debit_amount)
                   VALUES(0, %s, 'SALE', %s, %s, %s)""",
                (customer_id, sale_id, sale_date, total)
            )

        conn.commit()

        # 6. Batch ledger enqueue (every 5 → auto-flushes to accounting layer)
        BatchLedger.enqueue("post_sale_to_ledger", (
            sale_id, str(sale_date), total, gst_amount,
            cogs_amount, discount_amount, payment_method,
            customer_id, user["user_id"]
        ))

        # 7. Audit + backup
        log_audit(TABLE, sale_id, "INSERT", new_value={
            "sale_date": str(sale_date), "product_id": product_id,
            "qty_sold": qty, "total": total, "payment_method": payment_method,
            "processed_by": user["username"]
        })
        backup_to_csv(BACKUP_FILE, {
            "sale_id": sale_id, "sale_date": sale_date,
            "customer_id": customer_id, "product_id": product_id,
            "lot_id": primary_lot_id, "qty_sold": qty,
            "unit_price": unit_price, "discount_pct": discount_pct,
            "gst_amount": gst_amount, "total": total,
            "payment_method": payment_method,
            "processed_by": user["username"], "backed_up_at": datetime.now()
        }, BACKUP_COLS)

        print(f"\n✅ Sale #{sale_id} recorded. Total: ₹{total:,.2f}")
        if after_qty <= product["reorder_level"]:
            print(f"⚠️  LOW STOCK ALERT: {after_qty} units remaining (reorder at {product['reorder_level']})")

    except ValueError as e:
        if conn: conn.rollback()
        print(f"❌ {e}")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error recording sale: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# VIEW SALES  (paginated)
# ─────────────────────────────────────────────────────────────────────────────

def view_sales(page: int = 1, page_size: int = 20,
               date_from=None, date_to=None,
               customer_id=None, product_id=None,
               payment_method=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds = ["s.is_deleted=FALSE"]
        vals  = []
        if date_from:
            conds.append("s.sale_date >= %s"); vals.append(date_from)
        if date_to:
            conds.append("s.sale_date <= %s"); vals.append(date_to)
        if customer_id:
            conds.append("s.customer_id=%s"); vals.append(customer_id)
        if product_id:
            conds.append("s.product_id=%s"); vals.append(product_id)
        if payment_method:
            conds.append("s.payment_method=%s"); vals.append(payment_method)

        where = " AND ".join(conds)
        cursor.execute(
            f"SELECT COUNT(*) AS n FROM Sales s WHERE {where}", vals
        )
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            f"""SELECT s.sale_id, s.sale_date, c.customer_name,
                       p.product_name, s.qty_sold, s.unit_price,
                       s.discount_pct, s.gst_amount, s.total,
                       s.payment_method, s.payment_status,
                       u.username AS cashier
                FROM Sales s
                LEFT JOIN Customers c ON c.customer_id = s.customer_id
                LEFT JOIN Products  p ON p.product_id  = s.product_id
                LEFT JOIN Users     u ON u.user_id      = s.processed_by
                WHERE {where}
                ORDER BY s.sale_id DESC
                LIMIT %s OFFSET %s""",
            vals + [page_size, offset]
        )
        display_table(cursor.fetchall(),
                      f"Sales — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH SALES
# ─────────────────────────────────────────────────────────────────────────────

def search_sales(date_from=None, date_to=None, customer_id=None,
                 product_id=None, payment_method=None,
                 min_amount=None, max_amount=None, cashier_id=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds = ["s.is_deleted=FALSE"]
        vals  = []
        if date_from:       conds.append("s.sale_date >= %s");       vals.append(date_from)
        if date_to:         conds.append("s.sale_date <= %s");        vals.append(date_to)
        if customer_id:     conds.append("s.customer_id=%s");         vals.append(customer_id)
        if product_id:      conds.append("s.product_id=%s");          vals.append(product_id)
        if payment_method:  conds.append("s.payment_method=%s");      vals.append(payment_method)
        if min_amount:      conds.append("s.total >= %s");            vals.append(min_amount)
        if max_amount:      conds.append("s.total <= %s");            vals.append(max_amount)
        if cashier_id:      conds.append("s.processed_by=%s");        vals.append(cashier_id)

        cursor.execute(
            f"""SELECT s.sale_id, s.sale_date, c.customer_name,
                       p.product_name, s.qty_sold, s.total,
                       s.payment_method, s.payment_status, u.username AS cashier
                FROM Sales s
                LEFT JOIN Customers c ON c.customer_id=s.customer_id
                LEFT JOIN Products  p ON p.product_id =s.product_id
                LEFT JOIN Users     u ON u.user_id     =s.processed_by
                WHERE {' AND '.join(conds)}
                ORDER BY s.sale_date DESC, s.sale_id DESC""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, f"Sale Search — {len(rows)} result(s)")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT UPDATE  (non-financial fields only)
# ─────────────────────────────────────────────────────────────────────────────

def update_sale(sale_id: int):
    """
    Only non-financial fields (payment_method, payment_status) may be
    updated after posting. Changing qty / price / product requires
    void_journal_entry() + a fresh record_sale().
    """
    user = Session.require_role("admin", "manager", "accountant")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Sales WHERE sale_id=%s AND is_deleted=FALSE", (sale_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Sale not found."); return

        print(f"\nSale #{sale_id}  |  Product: {old['product_id']}  |  Total: ₹{old['total']}")
        print("⚠️  Only payment_method and payment_status can be updated here.")
        print("   Quantity / price changes require soft-delete + new sale entry.")

        updates, values, changed = [], [], {}

        pm = input(f"  Payment Method [{old['payment_method']}]: ").strip().lower()
        if pm and pm != old["payment_method"]:
            updates.append("payment_method=%s"); values.append(pm)
            changed["payment_method"] = {"old": old["payment_method"], "new": pm}

        ps = input(f"  Payment Status [{old['payment_status']}] (paid/pending/partial): ").strip().lower()
        if ps and ps != old["payment_status"]:
            updates.append("payment_status=%s"); values.append(ps)
            changed["payment_status"] = {"old": old["payment_status"], "new": ps}

        if not updates:
            print("⚠️  No changes."); return

        reason = input("Reason for update    : ").strip()
        if not reason:
            print("❌ Reason required."); return

        values.append(sale_id)
        conn.begin()
        cursor.execute(
            f"UPDATE Sales SET {', '.join(updates)} WHERE sale_id=%s", values
        )
        conn.commit()
        log_audit(TABLE, sale_id, "UPDATE",
                  old_value={k: old[k] for k in changed},
                  new_value={k: v["new"] for k, v in changed.items()},
                  changed_fields=", ".join(changed.keys()), reason=reason)
        print(f"✅ Sale #{sale_id} updated.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT DELETE  (reverses stock)
# ─────────────────────────────────────────────────────────────────────────────

def soft_delete_sale(sale_id: int):
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Sales WHERE sale_id=%s AND is_deleted=FALSE", (sale_id,)
        )
        sale = cursor.fetchone()
        if not sale:
            print("❌ Sale not found or already deleted."); return

        reason = input("Reason for deletion  : ").strip()
        if not reason:
            print("❌ Reason required."); return
        if not confirm(f"Soft-delete Sale #{sale_id} (₹{sale['total']})? (y/n): "):
            print("Cancelled."); return

        conn.begin()
        cursor.execute(
            "UPDATE Sales SET is_deleted=TRUE WHERE sale_id=%s", (sale_id,)
        )

        # Restore stock to the original lot
        if sale["lot_id"]:
            cursor.execute(
                "UPDATE Inventory_Lots SET quantity=quantity+%s WHERE lot_id=%s",
                (sale["qty_sold"], sale["lot_id"])
            )

        # Movement log for restoration
        cursor.execute(
            """INSERT INTO Inventory_Movements
               (product_id, lot_id, movement_type, reference_type, reference_id,
                qty_before, qty_change, qty_after, reason, performed_by)
               SELECT product_id, lot_id, 'return_in_sale', 'SALE_DELETE', %s,
                      quantity-%s, %s, quantity,
                      %s, %s
               FROM Inventory_Lots WHERE lot_id=%s""",
            (sale_id, sale["qty_sold"], sale["qty_sold"],
             f"Sale #{sale_id} soft-deleted: {reason}", user["user_id"],
             sale["lot_id"])
        )

        # Mark revenue stream deleted
        cursor.execute(
            """UPDATE Revenue_Streams SET is_deleted=TRUE
               WHERE reference_type='SALE' AND reference_id=%s""",
            (sale_id,)
        )
        conn.commit()

        log_audit(TABLE, sale_id, "SOFT_DELETE",
                  old_value=dict(sale), reason=reason)
        print(f"✅ Sale #{sale_id} soft-deleted. Stock restored to lot #{sale['lot_id']}.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────────────────────────────────────

def daily_report(report_date: date = None):
    Session.require()
    report_date = report_date or date.today()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT
                  COUNT(*)               AS transactions,
                  SUM(qty_sold)          AS units_sold,
                  SUM(total)             AS gross_revenue,
                  SUM(gst_amount)        AS gst_collected,
                  SUM(total-gst_amount)  AS net_revenue
               FROM Sales
               WHERE sale_date=%s AND is_deleted=FALSE""",
            (report_date,)
        )
        s = cursor.fetchone()

        cursor.execute(
            """SELECT payment_method, COUNT(*) AS cnt, SUM(total) AS amount
               FROM Sales WHERE sale_date=%s AND is_deleted=FALSE
               GROUP BY payment_method""",
            (report_date,)
        )
        pm = cursor.fetchall()

        cursor.execute(
            """SELECT p.product_name, SUM(s.qty_sold) AS qty,
                      SUM(s.total) AS revenue
               FROM Sales s JOIN Products p ON p.product_id=s.product_id
               WHERE s.sale_date=%s AND s.is_deleted=FALSE
               GROUP BY p.product_id ORDER BY revenue DESC LIMIT 5""",
            (report_date,)
        )
        top = cursor.fetchall()

        W = 62
        print(f"\n{'═'*W}")
        print(f"  Daily Sales Report — {report_date}")
        print(f"{'═'*W}")
        print(f"  Transactions    : {s['transactions'] or 0}")
        print(f"  Units Sold      : {s['units_sold'] or 0}")
        print(f"  Gross Revenue   : ₹{(s['gross_revenue'] or 0):>12,.2f}")
        print(f"  GST Collected   : ₹{(s['gst_collected'] or 0):>12,.2f}")
        print(f"  Net Revenue     : ₹{(s['net_revenue'] or 0):>12,.2f}")
        if pm:
            print(f"{'─'*W}")
            print("  By Payment Method:")
            for p in pm:
                print(f"    {p['payment_method']:<16} {p['cnt']:>3} txns  ₹{p['amount']:>10,.2f}")
        if top:
            print(f"{'─'*W}")
            print("  Top Products:")
            for p in top:
                print(f"    {p['product_name']:<32} qty:{p['qty']:>5}  ₹{p['revenue']:>10,.2f}")
        print(f"{'═'*W}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def monthly_report(year: int, month: int):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT sale_date, COUNT(*) AS txns,
                      SUM(qty_sold) AS units, SUM(total) AS revenue,
                      SUM(gst_amount) AS gst
               FROM Sales
               WHERE YEAR(sale_date)=%s AND MONTH(sale_date)=%s AND is_deleted=FALSE
               GROUP BY sale_date ORDER BY sale_date""",
            (year, month)
        )
        rows = cursor.fetchall()
        display_table(rows, f"Monthly Sales — {month:02d}/{year}")

        cursor.execute(
            """SELECT payment_method, COUNT(*) AS cnt, SUM(total) AS amount
               FROM Sales
               WHERE YEAR(sale_date)=%s AND MONTH(sale_date)=%s AND is_deleted=FALSE
               GROUP BY payment_method""",
            (year, month)
        )
        display_table(cursor.fetchall(), "Payment Method Breakdown")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def top_products(limit: int = 10):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT p.product_id, p.product_name, p.sku,
                      SUM(s.qty_sold)  AS total_units,
                      SUM(s.total)     AS total_revenue,
                      COUNT(s.sale_id) AS transactions
               FROM Sales s JOIN Products p ON p.product_id=s.product_id
               WHERE s.is_deleted=FALSE
               GROUP BY p.product_id
               ORDER BY total_revenue DESC
               LIMIT %s""",
            (limit,)
        )
        display_table(cursor.fetchall(), f"Top {limit} Products by Revenue")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────────────────────────────────────

def sales_menu():
    while True:
        print("""
╔══════════════════════════════════╗
║         SALES MANAGEMENT         ║
╠══════════════════════════════════╣
║  1. Record Sale                  ║
║  2. View Sales                   ║
║  3. Search Sales                 ║
║  4. Update Sale                  ║
║  5. Delete Sale (Soft)           ║
║  6. Daily Report                 ║
║  7. Monthly Report               ║
║  8. Top Products                 ║
║  0. Back                         ║
╚══════════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": record_sale()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                df = safe_date("Date From [blank]: ", allow_blank=True)
                dt = safe_date("Date To   [blank]: ", allow_blank=True)
                view_sales(page=pg, date_from=df, date_to=dt)
            elif choice == "3":
                df  = safe_date("Date From  : ", allow_blank=True)
                dt  = safe_date("Date To    : ", allow_blank=True)
                cid = safe_int("Customer ID: ", allow_blank=True)
                pid = safe_int("Product ID : ", allow_blank=True)
                pm  = input("Payment Method [blank=all]: ").strip().lower() or None
                mn  = safe_float("Min Amount : ", allow_blank=True)
                mx  = safe_float("Max Amount : ", allow_blank=True)
                search_sales(date_from=df, date_to=dt,
                             customer_id=cid, product_id=pid,
                             payment_method=pm, min_amount=mn, max_amount=mx)
            elif choice == "4":
                sid = safe_int("Sale ID to update : ")
                if sid: update_sale(sid)
            elif choice == "5":
                sid = safe_int("Sale ID to delete : ")
                if sid: soft_delete_sale(sid)
            elif choice == "6":
                d = safe_date("Date [today]: ", allow_blank=True) or date.today()
                daily_report(d)
            elif choice == "7":
                yr = safe_int("Year  : ") or date.today().year
                mo = safe_int("Month : ") or date.today().month
                monthly_report(yr, mo)
            elif choice == "8":
                n = safe_int("Top N products [10]: ", allow_blank=True) or 10
                top_products(n)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")

if __name__ == "__main__":
    sales_menu()