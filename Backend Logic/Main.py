"""
Main.py
=======
Application entry point.

Responsibilities
----------------
1.  Authenticate the user via username + password (bcrypt verified against
    the Users table in Shop_Management).
2.  Log the session into User_Sessions for IP / activity tracking.
3.  Route to the correct sub-menu based on the user's role.
4.  On exit, flush any pending BatchLedger entries so no financial
    transaction is left un-posted to the accounting layer.

Role → Menu access
------------------
admin           All menus
manager         Sales, Returns, Purchases, Customers, Vendors, Products
cashier         Sales, Sales Returns only
accountant      View-only on Sales / Purchases + financial ledger flush trigger
inventory_staff Products and Purchases only

Install dependency:  pip install bcrypt
"""

import sys
import socket
import bcrypt
from datetime   import datetime
from Database   import get_connection
from Session    import Session
from AuditLogger import BatchLedger, log_audit

# ── lazy imports so modules only load after login ────────────────────────────
def _import_menus():
    from Customers        import customers_menu
    from Vendors          import vendors_menu
    from Products         import products_menu
    from Sales            import sales_menu
    from SalesReturn      import sales_return_menu
    from Purchase         import purchase_menu
    from PurchaseReturn   import purchase_return_menu
    return {
        "customers"        : customers_menu,
        "vendors"          : vendors_menu,
        "products"         : products_menu,
        "sales"            : sales_menu,
        "sales_returns"    : sales_return_menu,
        "purchases"        : purchase_menu,
        "purchase_returns" : purchase_return_menu,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────

def _get_device_info() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def login() -> bool:
    """
    Prompt for credentials, verify bcrypt hash, populate Session,
    and log the session start in User_Sessions.
    Returns True on success, False on failure.
    """
    print("\n" + "═" * 50)
    print("  SHOP MANAGEMENT SYSTEM  —  Login")
    print("═" * 50)

    username = input("  Username : ").strip()
    password = input("  Password : ").strip()     # In production use getpass.getpass()

    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT u.user_id, u.username, u.full_name,
                      u.password_hash, u.is_active, u.is_deleted,
                      r.role_name
               FROM Users u
               JOIN Roles r ON r.role_id = u.role_id
               WHERE u.username = %s""",
            (username,)
        )
        row = cursor.fetchone()

        if not row:
            print("  ❌ Invalid username or password.")
            _log_failed_login(username)
            return False

        if not row["is_active"] or row["is_deleted"]:
            print("  ❌ Account is inactive. Contact your administrator.")
            return False

        # bcrypt verification
        try:
            password_matches = bcrypt.checkpw(
                password.encode("utf-8"),
                row["password_hash"].encode("utf-8")
            )
        except Exception:
            # Fallback for plain-text passwords in development / fresh setup
            password_matches = (password == row["password_hash"])

        if not password_matches:
            print("  ❌ Invalid username or password.")
            _log_failed_login(username)
            return False

        # Populate session
        Session.login(
            user_id   = row["user_id"],
            username  = row["username"],
            role      = row["role_name"],
            full_name = row["full_name"],
        )

        # Log session start
        conn.begin()
        cursor.execute(
            """INSERT INTO User_Sessions (user_id, ip_address, device_info)
               VALUES (%s, %s, %s)""",
            (row["user_id"], "127.0.0.1", _get_device_info())
        )
        cursor.execute(
            "UPDATE Users SET last_login_at=NOW() WHERE user_id=%s",
            (row["user_id"],)
        )
        conn.commit()

        # Audit login
        log_audit("Users", row["user_id"], "LOGIN",
                  new_value={"action": "login", "device": _get_device_info()})

        print(f"\n  ✅ Welcome, {row['full_name']}!  Role: {row['role_name'].upper()}")
        return True

    except Exception as e:
        if conn: conn.rollback()
        print(f"  ❌ Login error: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def _log_failed_login(username: str):
    """Write a LOGIN_FAILED entry to Audit_Log (no Session set yet)."""
    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO Audit_Log
               (table_name, record_id, operation, new_value, performed_by)
               VALUES ('Users', 0, 'LOGIN_FAILED',
                       JSON_OBJECT('attempted_username', %s), NULL)""",
            (username,)
        )
        conn.commit()
    except Exception:
        pass
    finally:
        try:
            if cursor: cursor.close()
            if conn:   conn.close()
        except Exception:
            pass


def logout():
    """Close the current session in User_Sessions and clear Session."""
    user = Session.current()
    if not user:
        return

    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        conn.begin()
        cursor.execute(
            """UPDATE User_Sessions
               SET logout_at=NOW(), is_active=FALSE
               WHERE user_id=%s AND is_active=TRUE""",
            (user["user_id"],)
        )
        conn.commit()
        log_audit("Users", user["user_id"], "LOGOUT",
                  new_value={"action": "logout"})
    except Exception:
        pass
    finally:
        try:
            if cursor: cursor.close()
            if conn:   conn.close()
        except Exception:
            pass

    Session.logout()
    print(f"\n  👋 Goodbye, {user['full_name']}!")


# ─────────────────────────────────────────────────────────────────────────────
# MENU DEFINITIONS  (per role)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_MENUS = {
    "admin": [
        ("1", "Sales",             "sales"),
        ("2", "Sales Returns",     "sales_returns"),
        ("3", "Purchases",         "purchases"),
        ("4", "Purchase Returns",  "purchase_returns"),
        ("5", "Customers",         "customers"),
        ("6", "Vendors",           "vendors"),
        ("7", "Products",          "products"),
    ],
    "manager": [
        ("1", "Sales",             "sales"),
        ("2", "Sales Returns",     "sales_returns"),
        ("3", "Purchases",         "purchases"),
        ("4", "Purchase Returns",  "purchase_returns"),
        ("5", "Customers",         "customers"),
        ("6", "Vendors",           "vendors"),
        ("7", "Products",          "products"),
    ],
    "cashier": [
        ("1", "Sales",             "sales"),
        ("2", "Sales Returns",     "sales_returns"),
    ],
    "accountant": [
        ("1", "Sales (View)",      "sales"),
        ("2", "Purchases (View)",  "purchases"),
        ("3", "Customers",         "customers"),
        ("4", "Vendors",           "vendors"),
    ],
    "inventory_staff": [
        ("1", "Products",          "products"),
        ("2", "Purchases",         "purchases"),
        ("3", "Purchase Returns",  "purchase_returns"),
    ],
}


def _build_menu_string(role: str, full_name: str) -> str:
    entries = ROLE_MENUS.get(role, [])
    lines   = [
        "",
        "╔" + "═" * 34 + "╗",
        f"║  {'MAIN MENU':^30}  ║",
        f"║  {('👤 ' + full_name):<30}  ║",
        f"║  {'🔑 ' + role.upper():<30}  ║",
        "╠" + "═" * 34 + "╣",
    ]
    for key, label, _ in entries:
        lines.append(f"║  {key}.  {label:<27}  ║")
    lines += [
        "║  F.  Flush Ledger Queue          ║",
        "║  L.  Logout                      ║",
        "╚" + "═" * 34 + "╝",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # ── Login loop ───────────────────────────────────────────────────────────
    attempts = 0
    while not Session.current():
        if attempts >= 3:
            print("\n  ❌ Too many failed attempts. Exiting.")
            sys.exit(1)
        if not login():
            attempts += 1
        else:
            attempts = 0

    # ── Load menus after successful login ─────────────────────────────────
    menus = _import_menus()
    user  = Session.current()
    role  = user["role"]

    if role not in ROLE_MENUS:
        print(f"  ❌ Role '{role}' has no menu configured. Contact admin.")
        logout()
        sys.exit(1)

    menu_entries = ROLE_MENUS[role]
    key_map      = {key: module_key for key, _, module_key in menu_entries}

    # ── Application loop ──────────────────────────────────────────────────
    while True:
        print(_build_menu_string(role, user["full_name"]))

        # Show pending batch count if any
        if BatchLedger.pending() > 0:
            print(f"  ⚠️  Ledger queue: {BatchLedger.pending()} pending transaction(s).")

        choice = input("\n  Select: ").strip().upper()

        if choice == "L":
            # Flush before logout so nothing is lost
            if BatchLedger.pending() > 0:
                print("\n  Flushing pending ledger entries before logout...")
                BatchLedger.flush()
            logout()
            break

        elif choice == "F":
            # Manual flush (admin / accountant action)
            print(f"\n  Flushing {BatchLedger.pending()} pending entries...")
            BatchLedger.flush()

        elif choice in key_map:
            module_key = key_map[choice]
            menu_fn    = menus.get(module_key)
            if menu_fn:
                try:
                    menu_fn()
                except PermissionError as e:
                    print(f"\n  🔒 {e}")
                except Exception as e:
                    print(f"\n  ❌ Unexpected error: {e}")
            else:
                print("  ❌ Menu not available.")
        else:
            print("  ❌ Invalid option.")

    # ── Final flush on exit ──────────────────────────────────────────────
    if BatchLedger.pending() > 0:
        print(f"\n  Flushing {BatchLedger.pending()} remaining ledger entries...")
        BatchLedger.flush()

    print("\n  System closed.\n")


# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP  (first-time admin account creation)
# ─────────────────────────────────────────────────────────────────────────────

def create_admin_account():
    """
    One-time setup: creates the initial admin user.
    Run this once after deploying the schema:
        python Main.py --setup
    """
    print("\n  ─── First-Time Admin Setup ───")
    username  = input("  Admin Username  : ").strip()
    password  = input("  Admin Password  : ").strip()
    full_name = input("  Full Name       : ").strip()
    email     = input("  Email           : ").strip()

    pw_hash = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    conn = cursor = None
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role_id FROM Roles WHERE role_name='admin' LIMIT 1"
        )
        role = cursor.fetchone()
        if not role:
            print("  ❌ Roles table not populated. Run shop_management.sql first.")
            return

        conn.begin()
        cursor.execute(
            """INSERT INTO Users
               (role_id, username, password_hash, full_name, email)
               VALUES (%s, %s, %s, %s, %s)""",
            (role["role_id"], username, pw_hash, full_name, email)
        )
        conn.commit()
        print(f"\n  ✅ Admin account '{username}' created successfully.")
        print("     Run 'python Main.py' to log in.")
    except Exception as e:
        if conn: conn.rollback()
        print(f"  ❌ Error: {e}")
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--setup":
        create_admin_account()
    else:
        main()
