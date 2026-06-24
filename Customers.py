"""
Customers.py
============
Full customer lifecycle management.

Operations
----------
add_customer()           Validated insert | audit log | CSV backup
view_customers()         Paginated listing
search_customers()       Multi-filter: name / phone / email / city / state
update_customer()        Soft-update: logs old → new in Audit_Log, record updated in-place
soft_delete_customer()   Sets is_deleted=TRUE; blocks if AR outstanding
restore_customer()       Reverses a soft-delete
customer_insights()      Purchase totals, AR balance, top products, payment breakdown

Accountability
--------------
Every write logs to Audit_Log with:  table, record_id, operation,
old_value (JSON), new_value (JSON), changed_fields, performed_by (user_id), reason.
Session.require() enforces that a user must be authenticated before any write.
"""

import re
from datetime import datetime
from Database    import get_connection
from Session     import Session
from AuditLogger import log_audit
from Utils       import backup_to_csv, display_table, confirm, safe_int

BACKUP_FILE = "backups/customers_backup.csv"
TABLE       = "Customers"
BACKUP_COLS = [
    "customer_id","customer_name","phone","email","address",
    "city","state","postal_code","country","created_by","backed_up_at"
]


# ─────────────────────────────────────────────────────────────────────────────
# ADD
# ─────────────────────────────────────────────────────────────────────────────

def add_customer():
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        name    = input("Customer Name        : ").strip().title()
        phone   = input("Phone Number         : ").strip()
        email   = input("Email                : ").strip().lower()
        address = input("Address              : ").strip()
        city    = input("City                 : ").strip().title()
        state   = input("State                : ").strip().title()
        postal  = input("Postal Code          : ").strip()
        country = input("Country [India]      : ").strip().title() or "India"

        # Validation
        if not name:
            print("❌ Customer name is required."); return
        clean_phone = re.sub(r"[\s\-]", "", phone)
        if not re.match(r"^\+?\d{7,15}$", clean_phone):
            print("❌ Phone must be 7–15 digits."); return
        if "@" not in email or "." not in email.split("@")[-1]:
            print("❌ Invalid email address."); return
        if not postal:
            print("❌ Postal code is required."); return

        # Duplicate guard
        cursor.execute(
            "SELECT customer_id FROM Customers WHERE (phone=%s OR email=%s) AND is_deleted=FALSE",
            (phone, email)
        )
        if cursor.fetchone():
            print("❌ A customer with this phone or email already exists."); return

        conn.begin()
        cursor.execute(
            """INSERT INTO Customers
               (customer_name, phone, email, address, city, state,
                postal_code, country, created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (name, phone, email, address, city, state, postal, country, user["user_id"])
        )
        new_id = cursor.lastrowid
        conn.commit()

        log_audit(TABLE, new_id, "INSERT", new_value={
            "customer_name": name, "phone": phone, "email": email,
            "city": city, "state": state, "created_by": user["username"]
        })
        backup_to_csv(BACKUP_FILE, {
            "customer_id": new_id, "customer_name": name, "phone": phone,
            "email": email, "address": address, "city": city, "state": state,
            "postal_code": postal, "country": country,
            "created_by": user["username"], "backed_up_at": datetime.now()
        }, BACKUP_COLS)
        print(f"✅ Customer added. ID: {new_id}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error adding customer: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# VIEW  (paginated)
# ─────────────────────────────────────────────────────────────────────────────

def view_customers(page: int = 1, page_size: int = 20):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS n FROM Customers WHERE is_deleted=FALSE")
        total  = cursor.fetchone()["n"]
        pages  = max(1, -(-total // page_size))
        offset = (page - 1) * page_size

        cursor.execute(
            """SELECT customer_id, customer_name, phone, email,
                      city, state, country, loyalty_points, created_at
               FROM   Customers
               WHERE  is_deleted=FALSE
               ORDER  BY customer_id DESC
               LIMIT  %s OFFSET %s""",
            (page_size, offset)
        )
        display_table(cursor.fetchall(),
                      f"Customers — page {page}/{pages}, total {total}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SEARCH
# ─────────────────────────────────────────────────────────────────────────────

def search_customers(keyword=None, city=None, state=None, country=None):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        conds, vals = ["is_deleted=FALSE"], []

        if keyword:
            conds.append("(customer_name LIKE %s OR phone LIKE %s OR email LIKE %s)")
            kw = f"%{keyword}%"; vals += [kw, kw, kw]
        if city:
            conds.append("city LIKE %s"); vals.append(f"%{city}%")
        if state:
            conds.append("state LIKE %s"); vals.append(f"%{state}%")
        if country:
            conds.append("country LIKE %s"); vals.append(f"%{country}%")

        cursor.execute(
            f"""SELECT customer_id, customer_name, phone, email,
                       city, state, country, loyalty_points
                FROM   Customers WHERE {' AND '.join(conds)}
                ORDER  BY customer_name""",
            vals
        )
        rows = cursor.fetchall()
        display_table(rows, "Customer Search Results")
        return rows
    except Exception as e:
        print(f"❌ Error: {e}"); return []
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT UPDATE  — original values never lost; full diff captured in Audit_Log
# ─────────────────────────────────────────────────────────────────────────────

def update_customer(customer_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Customers WHERE customer_id=%s AND is_deleted=FALSE",
            (customer_id,)
        )
        old = cursor.fetchone()
        if not old:
            print("❌ Customer not found."); return

        print(f"\nEditing: {old['customer_name']}  (press Enter to keep current value)")
        fields = {
            "customer_name" : ("Name    ", lambda v: v.title()),
            "phone"         : ("Phone   ", lambda v: v),
            "email"         : ("Email   ", lambda v: v.lower()),
            "address"       : ("Address ", lambda v: v),
            "city"          : ("City    ", lambda v: v.title()),
            "state"         : ("State   ", lambda v: v.title()),
            "postal_code"   : ("Postal  ", lambda v: v),
        }
        updates, values, changed = [], [], {}

        for col, (label, transform) in fields.items():
            raw = input(f"  {label} [{old[col]}]: ").strip()
            if raw:
                new_val = transform(raw)
                if str(new_val) != str(old[col]):
                    updates.append(f"{col}=%s")
                    values.append(new_val)
                    changed[col] = {"old": old[col], "new": new_val}

        if not updates:
            print("⚠️  No changes detected."); return

        reason = input("Reason for update    : ").strip() or None
        values.append(customer_id)

        conn.begin()
        cursor.execute(
            f"UPDATE Customers SET {', '.join(updates)} WHERE customer_id=%s",
            values
        )
        conn.commit()

        log_audit(
            TABLE, customer_id, "UPDATE",
            old_value={k: old[k] for k in changed},
            new_value={k: v["new"] for k, v in changed.items()},
            changed_fields=", ".join(changed.keys()),
            reason=reason
        )
        print(f"✅ Updated. Changed fields: {', '.join(changed.keys())}")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# SOFT DELETE
# ─────────────────────────────────────────────────────────────────────────────

def soft_delete_customer(customer_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Customers WHERE customer_id=%s AND is_deleted=FALSE",
            (customer_id,)
        )
        record = cursor.fetchone()
        if not record:
            print("❌ Customer not found or already deleted."); return

        # Block if outstanding AR balance exists
        cursor.execute(
            """SELECT COALESCE(SUM(debit_amount - credit_amount), 0) AS bal
               FROM sub_ledger_ar WHERE customer_id=%s AND is_settled=FALSE""",
            (customer_id,)
        )
        bal = cursor.fetchone()["bal"]
        if bal and bal > 0:
            print(f"⚠️  Customer has ₹{bal:,.2f} outstanding. Settle balance first."); return

        reason = input("Reason for deletion  : ").strip()
        if not reason:
            print("❌ Reason is required for accountability."); return
        if not confirm(f"Soft-delete '{record['customer_name']}'? (y/n): "):
            print("Cancelled."); return

        conn.begin()
        cursor.execute(
            "UPDATE Customers SET is_deleted=TRUE WHERE customer_id=%s", (customer_id,)
        )
        conn.commit()

        log_audit(TABLE, customer_id, "SOFT_DELETE",
                  old_value=dict(record), reason=reason)
        print(f"✅ Customer soft-deleted. Record preserved in Audit_Log.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────────────────────

def restore_customer(customer_id: int):
    user = Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT customer_name FROM Customers WHERE customer_id=%s AND is_deleted=TRUE",
            (customer_id,)
        )
        record = cursor.fetchone()
        if not record:
            print("❌ No soft-deleted customer found with that ID."); return

        conn.begin()
        cursor.execute(
            "UPDATE Customers SET is_deleted=FALSE WHERE customer_id=%s", (customer_id,)
        )
        conn.commit()

        log_audit(TABLE, customer_id, "RESTORE",
                  new_value={"is_deleted": False, "restored_by": user["username"]})
        print(f"✅ Customer '{record['customer_name']}' restored successfully.")

    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHTS
# ─────────────────────────────────────────────────────────────────────────────

def customer_insights(customer_id: int):
    Session.require()
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM Customers WHERE customer_id=%s AND is_deleted=FALSE",
            (customer_id,)
        )
        c = cursor.fetchone()
        if not c:
            print("❌ Customer not found."); return

        # Purchase summary
        cursor.execute(
            """SELECT COUNT(*)           AS orders,
                      COALESCE(SUM(total),0)   AS total_spent,
                      COALESCE(AVG(total),0)   AS avg_order,
                      MAX(sale_date)            AS last_order,
                      MIN(sale_date)            AS first_order
               FROM Sales WHERE customer_id=%s AND is_deleted=FALSE""",
            (customer_id,)
        )
        s = cursor.fetchone()

        # Outstanding AR balance
        cursor.execute(
            """SELECT COALESCE(SUM(debit_amount-credit_amount),0) AS bal
               FROM sub_ledger_ar WHERE customer_id=%s AND is_settled=FALSE""",
            (customer_id,)
        )
        ar_bal = cursor.fetchone()["bal"] or 0

        # Top 5 products
        cursor.execute(
            """SELECT p.product_name, SUM(s.qty_sold) AS qty,
                      SUM(s.total) AS spend
               FROM Sales s JOIN Products p ON p.product_id=s.product_id
               WHERE s.customer_id=%s AND s.is_deleted=FALSE
               GROUP BY p.product_id ORDER BY spend DESC LIMIT 5""",
            (customer_id,)
        )
        top5 = cursor.fetchall()

        # Payment method breakdown
        cursor.execute(
            """SELECT payment_method, COUNT(*) AS cnt, SUM(total) AS amt
               FROM Sales WHERE customer_id=%s AND is_deleted=FALSE
               GROUP BY payment_method""",
            (customer_id,)
        )
        pm = cursor.fetchall()

        # Returns
        cursor.execute(
            """SELECT COUNT(*) AS returns, COALESCE(SUM(refund_amount),0) AS refunded
               FROM Sales_Return WHERE customer_id=%s AND is_deleted=FALSE""",
            (customer_id,)
        )
        ret = cursor.fetchone()

        W = 62
        print(f"\n{'═'*W}")
        print(f"  Customer Insights — {c['customer_name']}  (#{customer_id})")
        print(f"{'═'*W}")
        print(f"  📍  {c['address']}, {c['city']}, {c['state']} {c['postal_code']}, {c['country']}")
        print(f"  📞  {c['phone']}    ✉  {c['email']}")
        print(f"  🎯  Loyalty Points  : {c['loyalty_points']}")
        print(f"{'─'*W}")
        print(f"  📦  Total Orders    : {s['orders']}")
        print(f"  💰  Total Spent     : ₹{s['total_spent']:>12,.2f}")
        print(f"  📊  Avg Order Value : ₹{s['avg_order']:>12,.2f}")
        print(f"  📅  First Order     : {s['first_order'] or '—'}")
        print(f"  📅  Last Order      : {s['last_order']  or '—'}")
        print(f"  🔴  AR Outstanding  : ₹{ar_bal:>12,.2f}")
        print(f"  🔄  Returns         : {ret['returns']}   Refunded: ₹{ret['refunded']:,.2f}")

        if top5:
            print(f"{'─'*W}")
            print("  🏆  Top Products:")
            for p in top5:
                print(f"      {p['product_name']:<30} qty:{p['qty']:>5}  ₹{p['spend']:>10,.2f}")

        if pm:
            print(f"{'─'*W}")
            print("  💳  Payment Methods:")
            for p in pm:
                print(f"      {p['payment_method']:<16} {p['cnt']:>4} orders  ₹{p['amt']:>10,.2f}")

        print(f"{'═'*W}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────────────────────────────────────

def customers_menu():
    while True:
        print("""
╔══════════════════════════════╗
║     CUSTOMER MANAGEMENT      ║
╠══════════════════════════════╣
║  1. Add Customer             ║
║  2. View All Customers       ║
║  3. Search Customers         ║
║  4. Update Customer          ║
║  5. Soft-Delete Customer     ║
║  6. Restore Customer         ║
║  7. Customer Insights        ║
║  0. Back                     ║
╚══════════════════════════════╝""")
        choice = input("Select: ").strip()
        try:
            if   choice == "1": add_customer()
            elif choice == "2":
                pg = safe_int("Page [1]: ", allow_blank=True) or 1
                view_customers(page=pg)
            elif choice == "3":
                kw    = input("Keyword (name/phone/email): ").strip() or None
                city  = input("City filter               : ").strip() or None
                state = input("State filter              : ").strip() or None
                search_customers(keyword=kw, city=city, state=state)
            elif choice == "4":
                cid = safe_int("Customer ID to update  : ")
                if cid: update_customer(cid)
            elif choice == "5":
                cid = safe_int("Customer ID to delete  : ")
                if cid: soft_delete_customer(cid)
            elif choice == "6":
                cid = safe_int("Customer ID to restore : ")
                if cid: restore_customer(cid)
            elif choice == "7":
                cid = safe_int("Customer ID for insights: ")
                if cid: customer_insights(cid)
            elif choice == "0": break
            else: print("❌ Invalid option.")
        except PermissionError as e:
            print(f"🔒 {e}")

if __name__ == "__main__":
    customers_menu()
