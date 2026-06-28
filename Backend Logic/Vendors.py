"""
Vendors.py
==========
Full vendor lifecycle management with smart comparison analytics.

Operations
----------
add_vendor()             Validated insert | audit | CSV backup
view_vendors()           Paginated listing
search_vendors()         Filter by name / city / state / credit_period
update_vendor()          Soft-update with full diff in Audit_Log
soft_delete_vendor()     Blocks if AP outstanding
restore_vendor()         Reverses soft-delete
vendor_insights()        Purchase totals, AP balance, product breakdown
compare_vendors()        Side-by-side cost comparison for a product
"""

import re
from datetime import datetime
from Database    import get_connection
from Session     import Session
from AuditLogger import log_audit
from Utils       import backup_to_csv, display_table, confirm, safe_int, safe_float

BACKUP_FILE = "backups/vendors_backup.csv"
TABLE       = "Vendors"
BACKUP_COLS = [
    "vendor_id","vendor_name","email","phone","city","state","country",
    "credit_period_days","created_by","backed_up_at"
]


# ─────────────────────────────────────────────────────────────────────────────
# ADD
# ─────────────────────────────────────────────────────────────────────────────

def add_vendor():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        name    = input("Vendor Name          : ").strip().title()
        phone   = input("Phone Number         : ").strip()
        email   = input("Email                : ").strip().lower()
        address = input("Address              : ").strip()
        city    = input("City                 : ").strip().title()
        state   = input("State                : ").strip().title()
        postal  = input("Postal Code          : ").strip()
        country = input("Country [India]      : ").strip().title() or "India"
        credit  = safe_int("Credit Period (days) : ") or 0

        if not name:
            print("❌ Vendor name is required."); return
        if "@" not in email or "." not in email.split("@")[-1]:
            print("❌ Invalid email."); return

        cursor.execute(
            "SELECT vendor_id FROM Vendors WHERE (phone=%s OR email=%s) AND is_deleted=FALSE",
            (phone, email)
        )
        if cursor.fetchone():
            print("❌ Vendor with this phone or email already exists."); return

        conn.begin()
        cursor.execute(
            """INSERT INTO Vendors
               (vendor_name,email,phone,address,city,state,
                postal_code,country,credit_period_days,created_by)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name,email,phone,address,city,state,postal,country,credit,user["user_id"])
        )
        new_id = cursor.lastrowid
        conn.commit()

        log_audit(TABLE, new_id, "INSERT", new_value={
            "vendor_name": name, "email": email, "city": city,
            "credit_period_days": credit, "created_by": user["username"]
        })
        backup_to_csv(BACKUP_FILE, {
            "vendor_id": new_id, "vendor_name": name, "email": email,
            "phone": phone, "city": city, "state": state, "country": country,
            "credit_period_days": credit, "created_by": user["username"],
            "backed_up_at": datetime.now()
        }, BACKUP_COLS)
        print(f"✅ Vendor added. ID: {new_id}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# VIEW
# ─────────────────────────────────────────────────────────────────────────────

def view_vendors(page: int = 1, page_size: int = 20):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS n FROM Vendors WHERE is_deleted=FALSE")
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            """SELECT vendor_id, vendor_name, phone, email, city,
                      state, credit_period_days, is_active, created_at
               FROM   Vendors WHERE is_deleted=FALSE
               ORDER  BY vendor_id DESC LIMIT %s OFFSET %s""",
            (page_size, offset)
        )
        display_table(cursor.fetchall(),
                      f"Vendors — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def search_vendors(keyword=None, city=None, state=None, max_credit_days=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds, vals = ["is_deleted=FALSE"], []
        if keyword:
            conds.append("(vendor_name LIKE %s OR email LIKE %s OR phone LIKE %s)")
            kw = f"%{keyword}%"; vals += [kw, kw, kw]
        if city:
            conds.append("city LIKE %s"); vals.append(f"%{city}%")
        if state:
            conds.append("state LIKE %s"); vals.append(f"%{state}%")
        if max_credit_days is not None:
            conds.append("credit_period_days <= %s"); vals.append(max_credit_days)

        cursor.execute(
            f"""SELECT vendor_id, vendor_name, phone, email,
                       city, state, credit_period_days, is_active
                FROM Vendors WHERE {' AND '.join(conds)}
                ORDER BY vendor_name""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, "Vendor Search Results")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT UPDATE
# ─────────────────────────────────────────────────────────────────────────────

def update_vendor(vendor_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Vendors WHERE vendor_id=%s AND is_deleted=FALSE",
            (vendor_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Vendor not found."); return

        print(f"\nEditing: {old['vendor_name']}  (Enter to keep current)")
        fields = {
            "vendor_name"       : ("Name         ", lambda v: v.title()),
            "email"             : ("Email        ", lambda v: v.lower()),
            "phone"             : ("Phone        ", lambda v: v),
            "address"           : ("Address      ", lambda v: v),
            "city"              : ("City         ", lambda v: v.title()),
            "state"             : ("State        ", lambda v: v.title()),
            "postal_code"       : ("Postal Code  ", lambda v: v),
            "credit_period_days": ("Credit Days  ", lambda v: int(v)),
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
            print("⚠️  No changes detected."); return

        reason = input("Reason for update    : ").strip() or None
        values.append(vendor_id)

        conn.begin()
        cursor.execute(
            f"UPDATE Vendors SET {', '.join(updates)} WHERE vendor_id=%s", values
        )
        conn.commit()

        log_audit(TABLE, vendor_id, "UPDATE",
                  old_value={k: old[k] for k in changed},
                  new_value={k: v["new"] for k, v in changed.items()},
                  changed_fields=", ".join(changed.keys()), reason=reason)
        print(f"✅ Vendor updated. Changed: {', '.join(changed.keys())}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT DELETE
# ─────────────────────────────────────────────────────────────────────────────

def soft_delete_vendor(vendor_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Vendors WHERE vendor_id=%s AND is_deleted=FALSE", (vendor_id,)
        )
        record = cursor.fetchone()
        if not record:
            print("❌ Vendor not found or already deleted."); return

        cursor.execute(
            """SELECT COALESCE(SUM(credit_amount-debit_amount),0) AS bal
               FROM sub_ledger_ap WHERE vendor_id=%s AND is_settled=FALSE""",
            (vendor_id,)
        )
        bal = cursor.fetchone()["bal"] or 0
        if bal > 0:
            print(f"⚠️  Vendor has ₹{bal:,.2f} outstanding payable. Settle first."); return

        reason = input("Reason for deletion  : ").strip()
        if not reason:
            print("❌ Reason required."); return
        if not confirm(f"Soft-delete '{record['vendor_name']}'? (y/n): "):
            print("Cancelled."); return

        conn.begin()
        cursor.execute(
            "UPDATE Vendors SET is_deleted=TRUE WHERE vendor_id=%s", (vendor_id,)
        )
        conn.commit()

        log_audit(TABLE, vendor_id, "SOFT_DELETE",
                  old_value=dict(record), reason=reason)
        print(f"✅ Vendor soft-deleted. Record preserved in Audit_Log.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────────────────────

def restore_vendor(vendor_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT vendor_name FROM Vendors WHERE vendor_id=%s AND is_deleted=TRUE",
            (vendor_id,)
        )
        record = cursor.fetchone()
        if not record:
            print("❌ No soft-deleted vendor found."); return

        conn.begin()
        cursor.execute(
            "UPDATE Vendors SET is_deleted=FALSE WHERE vendor_id=%s", (vendor_id,)
        )
        conn.commit()
        log_audit(TABLE, vendor_id, "RESTORE",
                  new_value={"is_deleted": False, "restored_by": user["username"]})
        print(f"✅ Vendor '{record['vendor_name']}' restored.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

def vendor_insights(vendor_id: int):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Vendors WHERE vendor_id=%s AND is_deleted=FALSE",
            (vendor_id,)
        )
        v = cursor.fetchone()
        if not v:
            print("❌ Vendor not found."); return

        cursor.execute(
            """SELECT COUNT(*) AS orders,
                      COALESCE(SUM(total),0) AS total_purchased,
                      COALESCE(AVG(total),0) AS avg_order,
                      MAX(purchase_date)     AS last_order,
                      MIN(purchase_date)     AS first_order
               FROM Purchases WHERE vendor_id=%s AND is_deleted=FALSE""",
            (vendor_id,)
        )
        s = cursor.fetchone()

        cursor.execute(
            """SELECT COALESCE(SUM(credit_amount-debit_amount),0) AS bal
               FROM sub_ledger_ap WHERE vendor_id=%s AND is_settled=FALSE""",
            (vendor_id,)
        )
        ap_bal = cursor.fetchone()["bal"] or 0

        cursor.execute(
            """SELECT COUNT(*) AS cnt,
                      COALESCE(SUM(refund_amount),0) AS refunded
               FROM Purchase_Return WHERE vendor_id=%s AND is_deleted=FALSE""",
            (vendor_id,)
        )
        ret = cursor.fetchone()

        cursor.execute(
            """SELECT p.product_name, SUM(pu.qty_purchased) AS qty,
                      SUM(pu.total) AS spend
               FROM Purchases pu JOIN Products p ON p.product_id=pu.product_id
               WHERE pu.vendor_id=%s AND pu.is_deleted=FALSE
               GROUP BY p.product_id ORDER BY spend DESC LIMIT 5""",
            (vendor_id,)
        )
        top5 = cursor.fetchall()

        W = 62
        print(f"\n{'═'*W}")
        print(f"  Vendor Insights — {v['vendor_name']}  (#{vendor_id})")
        print(f"{'═'*W}")
        print(f"  📍  {v['city']}, {v['state']}, {v['country']}")
        print(f"  📞  {v['phone']}    ✉  {v['email']}")
        print(f"  📆  Credit Period: {v['credit_period_days']} days")
        print(f"{'─'*W}")
        print(f"  📦  Total Orders    : {s['orders']}")
        print(f"  💰  Total Purchased : ₹{s['total_purchased']:>12,.2f}")
        print(f"  📊  Avg Order       : ₹{s['avg_order']:>12,.2f}")
        print(f"  📅  First Order     : {s['first_order'] or '—'}")
        print(f"  📅  Last Order      : {s['last_order']  or '—'}")
        print(f"  🔴  AP Outstanding  : ₹{ap_bal:>12,.2f}")
        print(f"  🔄  Returns         : {ret['cnt']}   Refunded: ₹{ret['refunded']:,.2f}")

        if top5:
            print(f"{'─'*W}")
            print("  🏆  Top Products Sourced:")
            for p in top5:
                print(f"      {p['product_name']:<30} qty:{p['qty']:>6}  ₹{p['spend']:>10,.2f}")
        print(f"{'═'*W}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SMART VENDOR COMPARISON  (for one product across multiple vendors)
# ─────────────────────────────────────────────────────────────────────────────

def compare_vendors(product_id: int):
    """
    Compare all vendors who have supplied a product:
    unit_cost + avg_freight → landed_cost.
    Recommends cheapest landed-cost vendor.
    """
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT v.vendor_id, v.vendor_name, v.city, v.credit_period_days,
                      ROUND(AVG(pu.unit_cost),2)      AS avg_unit_cost,
                      ROUND(AVG(pu.freight_cost),2)   AS avg_freight,
                      ROUND(AVG(pu.unit_cost + pu.freight_cost / NULLIF(pu.qty_purchased,0)),2)
                                                       AS avg_landed_cost,
                      COUNT(*)                         AS purchase_count,
                      MAX(pu.purchase_date)            AS last_supplied
               FROM Purchases pu
               JOIN Vendors v ON v.vendor_id=pu.vendor_id
               WHERE pu.product_id=%s AND pu.is_deleted=FALSE AND v.is_deleted=FALSE
               GROUP BY v.vendor_id
               ORDER BY avg_landed_cost ASC""",
            (product_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            print("⚠️  No purchase history for this product."); return

        display_table(rows, f"Vendor Comparison — Product #{product_id}")
        print(f"\n  ✅ Best vendor by landed cost: {rows[0]['vendor_name']} "
              f"(₹{rows[0]['avg_landed_cost']:.2f}/unit)")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────────────────────────────────────

def vendors_menu():
    while True:
        print("""
╔══════════════════════════════╗
║      VENDOR MANAGEMENT       ║
╠══════════════════════════════╣
║  1. Add Vendor               ║
║  2. View All Vendors         ║
║  3. Search Vendors           ║
║  4. Update Vendor            ║
║  5. Soft-Delete Vendor       ║
║  6. Restore Vendor           ║
║  7. Vendor Insights          ║
║  8. Compare Vendors (Product)║
║  0. Back                     ║
╚══════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": add_vendor()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                view_vendors(page=pg)
            elif choice == "3":
                kw  = input("Keyword (name/email/phone): ").strip() or None
                cit = input("City filter               : ").strip() or None
                st  = input("State filter              : ").strip() or None
                search_vendors(keyword=kw, city=cit, state=st)
            elif choice == "4":
                vid = safe_int("Vendor ID to update  : ")
                if vid: update_vendor(vid)
            elif choice == "5":
                vid = safe_int("Vendor ID to delete  : ")
                if vid: soft_delete_vendor(vid)
            elif choice == "6":
                vid = safe_int("Vendor ID to restore : ")
                if vid: restore_vendor(vid)
            elif choice == "7":
                vid = safe_int("Vendor ID for insights: ")
                if vid: vendor_insights(vid)
            elif choice == "8":
                pid = safe_int("Product ID to compare : ")
                if pid: compare_vendors(pid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")

if __name__ == "__main__":
    vendors_menu()
