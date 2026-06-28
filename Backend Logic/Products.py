"""
Products.py
===========
Product catalogue and inventory management.

Operations
----------
add_product()            Insert product with category/vendor link | audit | CSV
view_products()          Paginated listing with stock summary
search_products()        Filter: name / category / brand / SKU / low-stock flag
update_product()         Soft-update: full diff logged in Audit_Log
soft_delete_product()    Blocks if stock > 0
restore_product()        Reverses soft-delete
product_insights()       Margin, stock value, movement velocity, slow/fast flag
low_stock_report()       All products below reorder_level
adjust_inventory()       Manual stock adjustment → Inventory_Movements log
"""

from datetime import datetime
from Database    import get_connection
from Session     import Session
from AuditLogger import log_audit
from Utils       import backup_to_csv, display_table, confirm, safe_int, safe_float

BACKUP_FILE = "backups/products_backup.csv"
TABLE       = "Products"
BACKUP_COLS = [
    "product_id","product_name","sku","brand","category_id","vendor_id",
    "buying_price","selling_price","gst_percent","reorder_level",
    "is_expirable","created_by","backed_up_at"
]


# ─────────────────────────────────────────────────────────────────────────────
# ADD PRODUCT
# ─────────────────────────────────────────────────────────────────────────────

def add_product():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        name        = input("Product Name         : ").strip()
        sku         = input("SKU / Barcode        : ").strip() or None
        brand       = input("Brand                : ").strip() or None
        unit        = input("Unit [pcs]           : ").strip() or "pcs"
        category_id = safe_int("Category ID          : ", allow_blank=True)
        vendor_id   = safe_int("Default Vendor ID    : ", allow_blank=True)
        buying_p    = safe_float("Buying Price (₹)     : ")
        selling_p   = safe_float("Selling Price (₹)    : ")
        gst_pct     = safe_float("GST % [0]            : ") or 0.0
        reorder_lvl = safe_int("Reorder Level [10]   : ") or 10
        is_exp      = input("Is Expirable? (y/n)  : ").strip().lower() == "y"

        if not name:
            print("❌ Product name is required."); return
        if buying_p is None or selling_p is None:
            print("❌ Buying and Selling prices are required."); return
        if selling_p < buying_p:
            print("⚠️  Warning: Selling price is below buying price (negative margin).")

        if sku:
            cursor.execute(
                "SELECT product_id FROM Products WHERE sku=%s AND is_deleted=FALSE",
                (sku,)
            )
            if cursor.fetchone():
                print("❌ SKU already exists."); return

        conn.begin()
        cursor.execute(
            """INSERT INTO Products
               (product_name,sku,brand,unit,category_id,vendor_id,
                buying_price,selling_price,gst_percent,reorder_level,
                is_expirable,created_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name,sku,brand,unit,category_id,vendor_id,
             buying_p,selling_p,gst_pct,reorder_lvl,is_exp,user["user_id"])
        )
        new_id = cursor.lastrowid
        conn.commit()

        log_audit(TABLE, new_id, "INSERT", new_value={
            "product_name": name, "sku": sku, "buying_price": buying_p,
            "selling_price": selling_p, "created_by": user["username"]
        })
        backup_to_csv(BACKUP_FILE, {
            "product_id": new_id, "product_name": name, "sku": sku,
            "brand": brand, "category_id": category_id, "vendor_id": vendor_id,
            "buying_price": buying_p, "selling_price": selling_p,
            "gst_percent": gst_pct, "reorder_level": reorder_lvl,
            "is_expirable": is_exp, "created_by": user["username"],
            "backed_up_at": datetime.now()
        }, BACKUP_COLS)
        print(f"✅ Product added. ID: {new_id}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# VIEW  (with live stock summary)
# ─────────────────────────────────────────────────────────────────────────────

def view_products(page: int = 1, page_size: int = 20):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS n FROM Products WHERE is_deleted=FALSE")
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            """SELECT p.product_id, p.product_name, p.sku, p.brand,
                      c.category_name,
                      p.buying_price, p.selling_price, p.gst_percent,
                      COALESCE(SUM(il.quantity),0)  AS stock_qty,
                      p.reorder_level,
                      CASE WHEN COALESCE(SUM(il.quantity),0) <= p.reorder_level
                           THEN '⚠️ LOW' ELSE '✅ OK' END AS stock_status
               FROM Products p
               LEFT JOIN Categories c   ON c.category_id = p.category_id
               LEFT JOIN Inventory_Lots il ON il.product_id=p.product_id
                                          AND il.is_deleted=FALSE
               WHERE p.is_deleted=FALSE
               GROUP BY p.product_id
               ORDER BY p.product_id DESC
               LIMIT %s OFFSET %s""",
            (page_size, offset)
        )
        display_table(cursor.fetchall(),
                      f"Products — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def search_products(keyword=None, category_id=None, vendor_id=None,
                    low_stock_only=False):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds = ["p.is_deleted=FALSE"]
        vals  = []
        if keyword:
            conds.append("(p.product_name LIKE %s OR p.sku LIKE %s OR p.brand LIKE %s)")
            kw = f"%{keyword}%"; vals += [kw, kw, kw]
        if category_id:
            conds.append("p.category_id=%s"); vals.append(category_id)
        if vendor_id:
            conds.append("p.vendor_id=%s"); vals.append(vendor_id)

        having = "HAVING COALESCE(SUM(il.quantity),0) <= p.reorder_level" \
                 if low_stock_only else ""

        cursor.execute(
            f"""SELECT p.product_id, p.product_name, p.sku, p.brand,
                       p.buying_price, p.selling_price,
                       COALESCE(SUM(il.quantity),0) AS stock_qty, p.reorder_level
                FROM Products p
                LEFT JOIN Inventory_Lots il ON il.product_id=p.product_id
                                            AND il.is_deleted=FALSE
                WHERE {' AND '.join(conds)}
                GROUP BY p.product_id {having}
                ORDER BY p.product_name""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, "Product Search Results")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT UPDATE
# ─────────────────────────────────────────────────────────────────────────────

def update_product(product_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Products WHERE product_id=%s AND is_deleted=FALSE",
            (product_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Product not found."); return

        print(f"\nEditing: {old['product_name']}  (Enter to keep current)")
        fields = {
            "product_name"  : ("Name         ", lambda v: v),
            "sku"           : ("SKU          ", lambda v: v or None),
            "brand"         : ("Brand        ", lambda v: v or None),
            "unit"          : ("Unit         ", lambda v: v),
            "buying_price"  : ("Buying Price ", lambda v: float(v)),
            "selling_price" : ("Selling Price", lambda v: float(v)),
            "gst_percent"   : ("GST %        ", lambda v: float(v)),
            "reorder_level" : ("Reorder Level", lambda v: int(v)),
        }
        updates, values, changed = [], [], {}

        for col, (label, transform) in fields.items():
            raw = input(f"  {label} [{old[col]}]: ").strip()
            if raw:
                try:
                    new_val = transform(raw)
                    if str(new_val) != str(old[col]):
                        updates.append(f"{col}=%s")
                        values.append(new_val)
                        changed[col] = {"old": old[col], "new": new_val}
                except (ValueError, TypeError):
                    print(f"  ⚠️  Invalid value for {label.strip()}, skipped.")

        if not updates:
            print("⚠️  No changes."); return

        reason = input("Reason for update    : ").strip() or None
        values.append(product_id)

        conn.begin()
        cursor.execute(
            f"UPDATE Products SET {', '.join(updates)} WHERE product_id=%s", values
        )
        conn.commit()

        log_audit(TABLE, product_id, "UPDATE",
                  old_value={k: old[k] for k in changed},
                  new_value={k: v["new"] for k, v in changed.items()},
                  changed_fields=", ".join(changed.keys()), reason=reason)
        print(f"✅ Product updated. Changed: {', '.join(changed.keys())}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT DELETE
# ─────────────────────────────────────────────────────────────────────────────

def soft_delete_product(product_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Products WHERE product_id=%s AND is_deleted=FALSE",
            (product_id,)
        )
        record = cursor.fetchone()
        if not record:
            print("❌ Product not found."); return

        cursor.execute(
            """SELECT COALESCE(SUM(quantity),0) AS qty
               FROM Inventory_Lots WHERE product_id=%s AND is_deleted=FALSE""",
            (product_id,)
        )
        qty = cursor.fetchone()["qty"]
        if qty > 0:
            print(f"⚠️  Product has {qty} units in stock. Clear stock before deleting."); return

        reason = input("Reason for deletion  : ").strip()
        if not reason:
            print("❌ Reason required."); return
        if not confirm(f"Soft-delete '{record['product_name']}'? (y/n): "):
            print("Cancelled."); return

        conn.begin()
        cursor.execute(
            "UPDATE Products SET is_deleted=TRUE WHERE product_id=%s", (product_id,)
        )
        conn.commit()

        log_audit(TABLE, product_id, "SOFT_DELETE",
                  old_value=dict(record), reason=reason)
        print(f"✅ Product soft-deleted. Original record preserved in Audit_Log.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────────────────────

def restore_product(product_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT product_name FROM Products WHERE product_id=%s AND is_deleted=TRUE",
            (product_id,)
        )
        r = cursor.fetchone()
        if not r:
            print("❌ No soft-deleted product with that ID."); return
        conn.begin()
        cursor.execute(
            "UPDATE Products SET is_deleted=FALSE WHERE product_id=%s", (product_id,)
        )
        conn.commit()
        log_audit(TABLE, product_id, "RESTORE",
                  new_value={"restored_by": user["username"]})
        print(f"✅ Product '{r['product_name']}' restored.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

def product_insights(product_id: int):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT p.*, c.category_name, v.vendor_name
               FROM Products p
               LEFT JOIN Categories c ON c.category_id=p.category_id
               LEFT JOIN Vendors v    ON v.vendor_id=p.vendor_id
               WHERE p.product_id=%s AND p.is_deleted=FALSE""",
            (product_id,)
        )
        p = cursor.fetchone()
        if not p:
            print("❌ Product not found."); return

        # Stock
        cursor.execute(
            """SELECT COALESCE(SUM(quantity),0) AS total_stock,
                      COUNT(*)                  AS lots,
                      MIN(exp_date)             AS nearest_expiry
               FROM Inventory_Lots WHERE product_id=%s AND is_deleted=FALSE""",
            (product_id,)
        )
        stock = cursor.fetchone()

        # Sales performance
        cursor.execute(
            """SELECT COUNT(*) AS txns,
                      COALESCE(SUM(qty_sold),0) AS total_sold,
                      COALESCE(SUM(total),0)    AS revenue
               FROM Sales WHERE product_id=%s AND is_deleted=FALSE""",
            (product_id,)
        )
        sales = cursor.fetchone()

        # Purchase history
        cursor.execute(
            """SELECT COUNT(*) AS orders,
                      COALESCE(SUM(qty_purchased),0) AS total_bought,
                      COALESCE(AVG(unit_cost),0)     AS avg_cost
               FROM Purchases WHERE product_id=%s AND is_deleted=FALSE""",
            (product_id,)
        )
        pur = cursor.fetchone()

        margin_pct = 0
        if p["buying_price"] and p["buying_price"] > 0:
            margin_pct = ((p["selling_price"] - p["buying_price"])
                          / p["buying_price"]) * 100

        stock_value = (stock["total_stock"] or 0) * float(p["buying_price"])

        # Velocity: avg units sold per day since first sale
        cursor.execute(
            "SELECT MIN(sale_date) AS first FROM Sales WHERE product_id=%s AND is_deleted=FALSE",
            (product_id,)
        )
        first_sale = cursor.fetchone()["first"]
        if first_sale and sales["total_sold"] > 0:
            days = max((datetime.now().date() - first_sale).days, 1)
            velocity = sales["total_sold"] / days
            days_of_stock = (stock["total_stock"] or 0) / velocity if velocity > 0 else None
        else:
            velocity = 0; days_of_stock = None

        W = 62
        print(f"\n{'═'*W}")
        print(f"  Product Insights — {p['product_name']}  (#{product_id})")
        print(f"{'═'*W}")
        print(f"  SKU: {p['sku'] or '—'}   Brand: {p['brand'] or '—'}")
        print(f"  Category : {p['category_name'] or '—'}")
        print(f"  Vendor   : {p['vendor_name'] or '—'}")
        print(f"  Unit     : {p['unit']}")
        print(f"{'─'*W}")
        print(f"  💰  Buying Price  : ₹{p['buying_price']:>10,.2f}")
        print(f"  💵  Selling Price : ₹{p['selling_price']:>10,.2f}")
        print(f"  📊  Margin        : {margin_pct:>7.1f}%")
        print(f"  🏷️   GST           : {p['gst_percent']}%")
        print(f"{'─'*W}")
        print(f"  📦  Stock Qty     : {stock['total_stock']:>8}  (in {stock['lots']} lot(s))")
        print(f"  🔔  Reorder Level : {p['reorder_level']:>8}")
        print(f"  💲  Stock Value   : ₹{stock_value:>10,.2f}")
        if stock["nearest_expiry"]:
            print(f"  📅  Nearest Expiry: {stock['nearest_expiry']}")
        print(f"{'─'*W}")
        print(f"  🏪  Total Sold    : {sales['total_sold']:>8} units")
        print(f"  💰  Revenue       : ₹{sales['revenue']:>10,.2f}")
        print(f"  🚚  Total Bought  : {pur['total_bought']:>8} units")
        print(f"  📈  Avg Unit Cost : ₹{pur['avg_cost']:>10,.2f}")
        print(f"  🔄  Velocity      : {velocity:.2f} units/day")
        if days_of_stock is not None:
            flag = "🔴 RESTOCK SOON" if days_of_stock < 14 else "✅"
            print(f"  📆  Stock for     : {days_of_stock:.0f} days  {flag}")
        print(f"{'═'*W}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# LOW STOCK REPORT
# ─────────────────────────────────────────────────────────────────────────────

def low_stock_report():
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """SELECT p.product_id, p.product_name, p.sku,
                      COALESCE(SUM(il.quantity),0) AS current_stock,
                      p.reorder_level,
                      (p.reorder_level - COALESCE(SUM(il.quantity),0)) AS shortfall,
                      v.vendor_name, v.phone AS vendor_phone
               FROM Products p
               LEFT JOIN Inventory_Lots il ON il.product_id=p.product_id AND il.is_deleted=FALSE
               LEFT JOIN Vendors v         ON v.vendor_id=p.vendor_id
               WHERE p.is_deleted=FALSE
               GROUP BY p.product_id
               HAVING current_stock <= p.reorder_level
               ORDER BY shortfall DESC"""
        )
        rows = cursor.fetchall()
        display_table(rows, f"⚠️  Low Stock Report — {len(rows)} product(s) need restocking")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MANUAL INVENTORY ADJUSTMENT
# ─────────────────────────────────────────────────────────────────────────────

def adjust_inventory(product_id: int):
    """
    Manual stock correction (damaged, expired, miscounted, etc.).
    Every adjustment is recorded in Inventory_Movements and Audit_Log.
    Admin / manager role required.
    """
    user = Session.require_role("admin", "manager")
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT COALESCE(SUM(quantity),0) AS qty
               FROM Inventory_Lots WHERE product_id=%s AND is_deleted=FALSE""",
            (product_id,)
        )
        current_qty = cursor.fetchone()["qty"]

        print(f"\nCurrent stock: {current_qty} units")
        print("Adjustment type:")
        print("  1. Add (adjustment_in)")
        print("  2. Remove (adjustment_out / damaged / expired)")
        adj_type = input("Select (1/2): ").strip()
        if adj_type not in ("1", "2"):
            print("❌ Invalid."); return

        qty   = safe_int("Quantity to adjust  : ")
        reason = input("Reason              : ").strip()
        if not reason:
            print("❌ Reason is required."); return

        movement_type = "adjustment_in" if adj_type == "1" else "adjustment_out"
        qty_change    = qty if adj_type == "1" else -qty
        qty_after     = current_qty + qty_change

        if qty_after < 0:
            print(f"❌ Cannot remove {qty} units — only {current_qty} available."); return

        conn.begin()

        # Update the oldest lot (FIFO) for removals
        if adj_type == "2":
            remaining = qty
            cursor.execute(
                """SELECT lot_id, quantity FROM Inventory_Lots
                   WHERE product_id=%s AND is_deleted=FALSE AND quantity>0
                   ORDER BY lot_id ASC""",
                (product_id,)
            )
            lots = cursor.fetchall()
            for lot in lots:
                if remaining <= 0: break
                deduct = min(lot["quantity"], remaining)
                cursor.execute(
                    "UPDATE Inventory_Lots SET quantity=quantity-%s WHERE lot_id=%s",
                    (deduct, lot["lot_id"])
                )
                remaining -= deduct
        else:
            # Add to a generic adjustment lot
            cursor.execute(
                """INSERT INTO Inventory_Lots (product_id, quantity, cost_price)
                   VALUES (%s, %s,
                       (SELECT buying_price FROM Products WHERE product_id=%s))""",
                (product_id, qty, product_id)
            )

        # Record movement
        cursor.execute(
            """INSERT INTO Inventory_Movements
               (product_id, movement_type, reference_type, reference_id,
                qty_before, qty_change, qty_after, reason, performed_by)
               VALUES(%s,%s,'ADJUSTMENT',0,%s,%s,%s,%s,%s)""",
            (product_id, movement_type, current_qty, qty_change,
             qty_after, reason, user["user_id"])
        )
        conn.commit()

        log_audit("Inventory_Lots", product_id, "UPDATE",
                  old_value={"stock": current_qty},
                  new_value={"stock": qty_after, "adjustment": qty_change},
                  changed_fields="quantity", reason=reason)
        print(f"✅ Inventory adjusted: {current_qty} → {qty_after} units. Reason: {reason}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────────────────────────────────────

def products_menu():
    while True:
        print("""
╔══════════════════════════════════╗
║    PRODUCT & INVENTORY MENU      ║
╠══════════════════════════════════╣
║  1. Add Product                  ║
║  2. View All Products            ║
║  3. Search Products              ║
║  4. Update Product               ║
║  5. Soft-Delete Product          ║
║  6. Restore Product              ║
║  7. Product Insights             ║
║  8. Low Stock Report             ║
║  9. Manual Inventory Adjustment  ║
║  0. Back                         ║
╚══════════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": add_product()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                view_products(page=pg)
            elif choice == "3":
                kw  = input("Keyword (name/SKU/brand)   : ").strip() or None
                cid = safe_int("Category ID (blank=all)    : ", allow_blank=True)
                ls  = input("Low stock only? (y/n)      : ").strip().lower() == "y"
                search_products(keyword=kw, category_id=cid, low_stock_only=ls)
            elif choice == "4":
                pid = safe_int("Product ID to update       : ")
                if pid: update_product(pid)
            elif choice == "5":
                pid = safe_int("Product ID to delete       : ")
                if pid: soft_delete_product(pid)
            elif choice == "6":
                pid = safe_int("Product ID to restore      : ")
                if pid: restore_product(pid)
            elif choice == "7":
                pid = safe_int("Product ID for insights    : ")
                if pid: product_insights(pid)
            elif choice == "8": low_stock_report()
            elif choice == "9":
                pid = safe_int("Product ID to adjust       : ")
                if pid: adjust_inventory(pid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")

if __name__ == "__main__":
    products_menu()
