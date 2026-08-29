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

BACKUP_FILE_ORDERS = "backups/sales_orders_backup.csv"
BACKUP_FILE_LINES  = "backups/sales_lines_backup.csv"
TABLE_ORDER        = "Sales_Orders"
TABLE_LINE         = "Sales_Lines"
BACKUP_COLS_ORDER  = [
    "sale_order_id","sale_date","customer_id","payment_method",
    "payment_status","subtotal","total_discount","total_gst",
    "grand_total","processed_by","backed_up_at"
]
BACKUP_COLS_LINE = [
    "sale_line_id","sale_order_id","product_id","lot_id",
    "qty_sold","unit_price","discount_pct","discount_amount",
    "gst_percent","gst_amount","line_total","cogs_amount","backed_up_at"
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
           ORDER BY lot_id ASC
           FOR UPDATE""",
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
# RECORD SALE  (multi-line basket)
# ─────────────────────────────────────────────────────────────────────────────

def record_sale():
    """
    FIX (Issue 1): Records a full sales order with multiple product lines.
    - One Sales_Orders row captures the basket header (customer, date, payment).
    - One Sales_Lines row is inserted per product.
    - Order-level totals are aggregated and written back to Sales_Orders.
    """
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        # ── Order-level inputs ────────────────────────────────────────────
        print("\n  ─── New Sales Order ─────────────────────────────")
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

        # ── Line item collection loop ─────────────────────────────────────
        basket = []   # list of dicts, one per product line
        print("\n  Add products to the basket. Leave Product ID blank to finish.")
        while True:
            print(f"  ─── Line {len(basket)+1} ─────────────────────────────────")
            product_id = safe_int("  Product ID [blank=done]: ", allow_blank=True)
            if not product_id:
                if not basket:
                    print("❌ At least one product is required."); return
                break

            product = _get_product(cursor, product_id)
            if not product:
                print("  ❌ Product not found. Skipping."); continue

            stock = _get_stock_qty(cursor, product_id)
            print(f"  ℹ️  Stock available : {stock} {product['unit']}")
            if stock <= 0:
                print("  ❌ Out of stock. Skipping."); continue

            qty = safe_int("  Quantity          : ")
            if not qty or qty <= 0:
                print("  ❌ Quantity must be positive. Skipping."); continue
            if qty > stock:
                print(f"  ❌ Only {stock} units available. Skipping."); continue

            print(f"  ℹ️  Default price    : ₹{product['selling_price']}")
            unit_price   = safe_float(f"  Unit Price [₹{product['selling_price']}]: ",
                                      allow_blank=True) or float(product["selling_price"])
            discount_pct = safe_float("  Discount % [0]    : ", allow_blank=True) or 0.0

            gross_amount    = unit_price * qty
            discount_amount = round(gross_amount * discount_pct / 100, 2)
            taxable_amount  = gross_amount - discount_amount
            gst_amount      = round(taxable_amount * float(product["gst_percent"]) / 100, 2)
            line_total      = round(taxable_amount + gst_amount, 2)

            basket.append({
                "product": product,
                "product_id": product_id,
                "qty": qty,
                "unit_price": unit_price,
                "discount_pct": discount_pct,
                "discount_amount": discount_amount,
                "gst_percent": float(product["gst_percent"]),
                "gst_amount": gst_amount,
                "line_total": line_total,
                "gross_amount": gross_amount,
            })
            print(f"  ✅ Added: {product['product_name']} × {qty} = ₹{line_total:,.2f}")

        # ── Order summary ─────────────────────────────────────────────────
        subtotal      = round(sum(b["gross_amount"] for b in basket), 2)
        total_discount = round(sum(b["discount_amount"] for b in basket), 2)
        total_gst     = round(sum(b["gst_amount"]  for b in basket), 2)
        grand_total   = round(sum(b["line_total"]  for b in basket), 2)

        print(f"""
  ─── Order Summary ──────────────────────────
  Lines      : {len(basket)}
  Subtotal   : ₹{subtotal:>12,.2f}
  Discounts  : ₹{total_discount:>12,.2f}
  GST        : ₹{total_gst:>12,.2f}
  GRAND TOTAL: ₹{grand_total:>12,.2f}
  Payment    : {payment_method.upper()}
  ─────────────────────────────────────────────""")
        if not confirm("Confirm order? (y/n): "):
            print("Cancelled."); return

        # ── Database transaction ──────────────────────────────────────────
        conn.begin()

        # 1. Insert order header (Sales_Orders)
        cursor.execute(
            """INSERT INTO Sales_Orders
               (sale_date, customer_id, payment_method, payment_status,
                subtotal, total_discount, total_gst, grand_total, processed_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (sale_date, customer_id, payment_method,
             "paid" if payment_method != "credit" else "pending",
             subtotal, total_discount, total_gst, grand_total, user["user_id"])
        )
        sale_order_id = cursor.lastrowid

        # 2. Insert each line item
        all_cogs = 0.0
        line_ids = []
        before_qty_total = _get_stock_qty(cursor, basket[0]["product_id"])

        for line in basket:
            deductions, avg_cost = _deduct_stock_fifo(
                cursor, line["product_id"], line["qty"]
            )
            cogs_amount    = round(avg_cost * line["qty"], 2)
            all_cogs      += cogs_amount
            primary_lot_id = deductions[0]["lot_id"]

            cursor.execute(
                """INSERT INTO Sales_Lines
                   (sale_order_id, product_id, lot_id, qty_sold,
                    unit_price, discount_pct, discount_amount,
                    gst_percent, gst_amount, line_total, cogs_amount)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sale_order_id, line["product_id"], primary_lot_id, line["qty"],
                 line["unit_price"], line["discount_pct"], line["discount_amount"],
                 line["gst_percent"], line["gst_amount"], line["line_total"],
                 cogs_amount)
            )
            sale_line_id = cursor.lastrowid
            line_ids.append(sale_line_id)
            line["_lot_id"]   = primary_lot_id
            line["_cogs"]     = cogs_amount
            line["_line_id"]  = sale_line_id

            # 3. Inventory movement per line
            stock_before = _get_stock_qty(cursor, line["product_id"]) + line["qty"]
            stock_after  = stock_before - line["qty"]
            cursor.execute(
                """INSERT INTO Inventory_Movements
                   (product_id, lot_id, movement_type, reference_type, reference_id,
                    qty_before, qty_change, qty_after, reason, performed_by)
                   VALUES(%s,%s,'sale_out','SALE_LINE',%s,%s,%s,%s,%s,%s)""",
                (line["product_id"], primary_lot_id, sale_line_id,
                 stock_before, -line["qty"], stock_after,
                 f"Order #{sale_order_id} Line #{sale_line_id}", user["user_id"])
            )

        # 4. Revenue stream entry (order-level)
        cursor.execute(
            """CALL record_revenue_stream(
                %s,'product_sale','SALE_ORDER',%s,%s,%s,%s,%s,%s,NULL,%s,%s, @rev_id)""",
            (sale_date, sale_order_id, subtotal, total_discount,
             total_gst, payment_method, customer_id,
             f"Sale Order #{sale_order_id}", user["user_id"])
        )

        # 5. AR sub-ledger for credit orders
        if payment_method == "credit" and customer_id:
            cursor.execute(
                """INSERT INTO sub_ledger_ar
                   (transaction_id, customer_id, reference_type, reference_id,
                    txn_date, debit_amount)
                   VALUES(0, %s, 'SALE_ORDER', %s, %s, %s)""",
                (customer_id, sale_order_id, sale_date, grand_total)
            )

        conn.commit()

        # 6. Batch ledger: enqueue one post per line so COGS is accurate per lot
        for line in basket:
            BatchLedger.enqueue("post_sale_to_ledger", (
                sale_order_id, str(sale_date),
                line["line_total"], line["gst_amount"],
                line["_cogs"], line["discount_amount"],
                payment_method, customer_id, user["user_id"]
            ))

        # 7. Audit + backup
        log_audit(TABLE_ORDER, sale_order_id, "INSERT", new_value={
            "sale_date": str(sale_date), "lines": len(basket),
            "grand_total": grand_total, "payment_method": payment_method,
            "processed_by": user["username"]
        })
        backup_to_csv(BACKUP_FILE_ORDERS, {
            "sale_order_id": sale_order_id, "sale_date": sale_date,
            "customer_id": customer_id, "payment_method": payment_method,
            "payment_status": "paid" if payment_method != "credit" else "pending",
            "subtotal": subtotal, "total_discount": total_discount,
            "total_gst": total_gst, "grand_total": grand_total,
            "processed_by": user["username"], "backed_up_at": datetime.now()
        }, BACKUP_COLS_ORDER)
        for line in basket:
            backup_to_csv(BACKUP_FILE_LINES, {
                "sale_line_id": line["_line_id"], "sale_order_id": sale_order_id,
                "product_id": line["product_id"], "lot_id": line["_lot_id"],
                "qty_sold": line["qty"], "unit_price": line["unit_price"],
                "discount_pct": line["discount_pct"], "discount_amount": line["discount_amount"],
                "gst_percent": line["gst_percent"], "gst_amount": line["gst_amount"],
                "line_total": line["line_total"], "cogs_amount": line["_cogs"],
                "backed_up_at": datetime.now()
            }, BACKUP_COLS_LINE)

        print(f"\n✅ Sale Order #{sale_order_id} recorded. {len(basket)} line(s). Total: ₹{grand_total:,.2f}")
        # Low-stock warnings
        for line in basket:
            remaining = _get_stock_qty(cursor, line["product_id"])
            if remaining <= line["product"]["reorder_level"]:
                print(f"  ⚠️  LOW STOCK: {line['product']['product_name']} — "
                      f"{remaining} left (reorder at {line['product']['reorder_level']})")

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
# VIEW SALES  (paginated — joins Sales_Orders + Sales_Lines)
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

        conds = ["so.is_deleted=FALSE"]
        vals  = []
        if date_from:
            conds.append("so.sale_date >= %s"); vals.append(date_from)
        if date_to:
            conds.append("so.sale_date <= %s"); vals.append(date_to)
        if customer_id:
            conds.append("so.customer_id=%s"); vals.append(customer_id)
        if product_id:
            conds.append("sl.product_id=%s"); vals.append(product_id)
        if payment_method:
            conds.append("so.payment_method=%s"); vals.append(payment_method)

        where = " AND ".join(conds)
        cursor.execute(
            f"SELECT COUNT(DISTINCT so.sale_order_id) AS n "
            f"FROM Sales_Orders so "
            f"LEFT JOIN Sales_Lines sl ON sl.sale_order_id=so.sale_order_id "
            f"WHERE {where}", vals
        )
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            f"""SELECT so.sale_order_id, so.sale_date, c.customer_name,
                       COUNT(sl.sale_line_id) AS line_count,
                       so.grand_total, so.payment_method, so.payment_status,
                       u.username AS cashier
                FROM Sales_Orders so
                LEFT JOIN Sales_Lines sl ON sl.sale_order_id = so.sale_order_id
                LEFT JOIN Customers  c  ON c.customer_id    = so.customer_id
                LEFT JOIN Users      u  ON u.user_id        = so.processed_by
                WHERE {where}
                GROUP BY so.sale_order_id
                ORDER BY so.sale_order_id DESC
                LIMIT %s OFFSET %s""",
            vals + [page_size, offset]
        )
        display_table(cursor.fetchall(),
                      f"Sales Orders — page {page}/{pages}, total {total}")
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

        conds = ["so.is_deleted=FALSE"]
        vals  = []
        if date_from:       conds.append("so.sale_date >= %s");        vals.append(date_from)
        if date_to:         conds.append("so.sale_date <= %s");         vals.append(date_to)
        if customer_id:     conds.append("so.customer_id=%s");          vals.append(customer_id)
        if product_id:      conds.append("sl.product_id=%s");           vals.append(product_id)
        if payment_method:  conds.append("so.payment_method=%s");       vals.append(payment_method)
        if min_amount:      conds.append("so.grand_total >= %s");       vals.append(min_amount)
        if max_amount:      conds.append("so.grand_total <= %s");       vals.append(max_amount)
        if cashier_id:      conds.append("so.processed_by=%s");         vals.append(cashier_id)

        cursor.execute(
            f"""SELECT so.sale_order_id, so.sale_date, c.customer_name,
                       COUNT(sl.sale_line_id) AS lines, so.grand_total,
                       so.payment_method, so.payment_status, u.username AS cashier
                FROM Sales_Orders so
                LEFT JOIN Sales_Lines sl ON sl.sale_order_id = so.sale_order_id
                LEFT JOIN Customers  c  ON c.customer_id    = so.customer_id
                LEFT JOIN Users      u  ON u.user_id        = so.processed_by
                WHERE {' AND '.join(conds)}
                GROUP BY so.sale_order_id
                ORDER BY so.sale_date DESC, so.sale_order_id DESC""",
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
    updated on the Sales_Orders header after posting. Line items require
    void_journal_entry() + a fresh record_sale().
    """
    user = Session.require_role("admin", "manager", "accountant")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Sales_Orders WHERE sale_order_id=%s AND is_deleted=FALSE", (sale_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Sale order not found."); return

        print(f"\nSale Order #{sale_id}  |  Grand Total: ₹{old['grand_total']}")
        print("⚠️  Only payment_method and payment_status can be updated here.")
        print("   Line-level changes require soft-delete + new sale entry.")

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
            f"UPDATE Sales_Orders SET {', '.join(updates)} WHERE sale_order_id=%s", values
        )
        conn.commit()
        log_audit(TABLE_ORDER, sale_id, "UPDATE",
                  old_value={k: old[k] for k in changed},
                  new_value={k: v["new"] for k, v in changed.items()},
                  changed_fields=", ".join(changed.keys()), reason=reason)
        print(f"✅ Sale Order #{sale_id} updated.")

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
            "SELECT * FROM Sales_Orders WHERE sale_order_id=%s AND is_deleted=FALSE", (sale_id,)
        )
        sale = cursor.fetchone()
        if not sale:
            print("❌ Sale order not found or already deleted."); return

        reason = input("Reason for deletion  : ").strip()
        if not reason:
            print("❌ Reason required."); return
        if not confirm(f"Soft-delete Sale Order #{sale_id} (₹{sale['grand_total']})? (y/n): "):
            print("Cancelled."); return

        # Fetch all lines to restore stock
        cursor.execute(
            "SELECT * FROM Sales_Lines WHERE sale_order_id=%s", (sale_id,)
        )
        lines = cursor.fetchall()

        conn.begin()
        cursor.execute(
            "UPDATE Sales_Orders SET is_deleted=TRUE WHERE sale_order_id=%s", (sale_id,)
        )

        for line in lines:
            if line["lot_id"]:
                cursor.execute(
                    "UPDATE Inventory_Lots SET quantity=quantity+%s WHERE lot_id=%s",
                    (line["qty_sold"], line["lot_id"])
                )
                cursor.execute(
                    """INSERT INTO Inventory_Movements
                       (product_id, lot_id, movement_type, reference_type, reference_id,
                        qty_before, qty_change, qty_after, reason, performed_by)
                       SELECT product_id, lot_id, 'return_in_sale', 'SALE_DELETE', %s,
                              quantity-%s, %s, quantity,
                              %s, %s
                       FROM Inventory_Lots WHERE lot_id=%s""",
                    (sale_id, line["qty_sold"], line["qty_sold"],
                     f"Sale Order #{sale_id} soft-deleted: {reason}", user["user_id"],
                     line["lot_id"])
                )

        # Mark revenue stream deleted
        cursor.execute(
            """UPDATE Revenue_Streams SET is_deleted=TRUE
               WHERE reference_type='SALE_ORDER' AND reference_id=%s""",
            (sale_id,)
        )
        conn.commit()

        # FIX (Issue 4): Enqueue accounting void so the financial ledger is reversed.
        # The batch ledger will call void_journal_entry for the original sale's journal.
        BatchLedger.enqueue("void_journal_entry", (
            sale_id,  # transaction_id (sale order used as reference)
            f"Sale Order #{sale_id} soft-deleted: {reason}",
            user["user_id"]
        ))

        log_audit(TABLE_ORDER, sale_id, "SOFT_DELETE",
                  old_value=dict(sale), reason=reason)
        print(f"✅ Sale Order #{sale_id} soft-deleted. Stock restored for {len(lines)} line(s).")
        print(f"   ⚠️  Ledger void queued — flush to finalize the accounting reversal.")

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
                  COUNT(DISTINCT so.sale_order_id)  AS transactions,
                  SUM(sl.qty_sold)                  AS units_sold,
                  SUM(so.grand_total)               AS gross_revenue,
                  SUM(so.total_gst)                 AS gst_collected,
                  SUM(so.grand_total - so.total_gst) AS net_revenue
               FROM Sales_Orders so
               JOIN Sales_Lines sl ON sl.sale_order_id = so.sale_order_id
               WHERE so.sale_date=%s AND so.is_deleted=FALSE""",
            (report_date,)
        )
        s = cursor.fetchone()

        cursor.execute(
            """SELECT so.payment_method, COUNT(DISTINCT so.sale_order_id) AS cnt,
                      SUM(so.grand_total) AS amount
               FROM Sales_Orders so WHERE so.sale_date=%s AND so.is_deleted=FALSE
               GROUP BY so.payment_method""",
            (report_date,)
        )
        pm = cursor.fetchall()

        cursor.execute(
            """SELECT p.product_name, SUM(sl.qty_sold) AS qty,
                      SUM(sl.line_total) AS revenue
               FROM Sales_Lines sl
               JOIN Sales_Orders so ON so.sale_order_id = sl.sale_order_id
               JOIN Products p      ON p.product_id     = sl.product_id
               WHERE so.sale_date=%s AND so.is_deleted=FALSE
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
            """SELECT so.sale_date,
                      COUNT(DISTINCT so.sale_order_id) AS txns,
                      SUM(sl.qty_sold) AS units,
                      SUM(so.grand_total) AS revenue,
                      SUM(so.total_gst) AS gst
               FROM Sales_Orders so
               JOIN Sales_Lines sl ON sl.sale_order_id = so.sale_order_id
               WHERE YEAR(so.sale_date)=%s AND MONTH(so.sale_date)=%s AND so.is_deleted=FALSE
               GROUP BY so.sale_date ORDER BY so.sale_date""",
            (year, month)
        )
        rows = cursor.fetchall()
        display_table(rows, f"Monthly Sales — {month:02d}/{year}")

        cursor.execute(
            """SELECT so.payment_method,
                      COUNT(DISTINCT so.sale_order_id) AS cnt,
                      SUM(so.grand_total) AS amount
               FROM Sales_Orders so
               WHERE YEAR(so.sale_date)=%s AND MONTH(so.sale_date)=%s AND so.is_deleted=FALSE
               GROUP BY so.payment_method""",
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
                      SUM(sl.qty_sold)  AS total_units,
                      SUM(sl.line_total) AS total_revenue,
                      COUNT(DISTINCT so.sale_order_id) AS transactions
               FROM Sales_Lines sl
               JOIN Sales_Orders so ON so.sale_order_id = sl.sale_order_id
               JOIN Products     p  ON p.product_id     = sl.product_id
               WHERE so.is_deleted=FALSE
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
