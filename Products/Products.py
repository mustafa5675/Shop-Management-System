"""
Products.py - Complete Inventory Management Module with Audit Trail

This module provides CRUD operations for Products and Inventory_lots tables
with comprehensive audit logging and user preference-based output formatting.
"""

from datetime import datetime, date, timedelta
import pandas as pd
from typing import Optional, Dict, List, Tuple, Union
import re
from Database import get_connection

# =====================================================
# GLOBAL SESSION STATE
# =====================================================

current_user: str = None
user_preferences = {
    'output_format': 'table',
    'show_deleted': False,
    'date_format': 'YYYY-MM-DD',
    'include_audit_info': False,
    'max_records': 50,
    'sort_by': 'product_name',
    'sort_order': 'asc'
}
product_cache: List[Dict] = []


# =====================================================
# USER IDENTIFICATION SYSTEM
# =====================================================

def get_current_user() -> str:
    """
    Prompt user to identify themselves at session start.
    Cache the username for all subsequent operations.
    
    Returns:
        Uppercase string, max 100 chars.
        Validates: non-empty, alphanumeric + spaces allowed.
    """
    global current_user
    
    if current_user is not None:
        return current_user
    
    while True:
        try:
            username = input("Please identify yourself (username): ").strip()
            
            if not username:
                print("⚠️ Username cannot be empty. Please try again.")
                continue
            
            if len(username) > 100:
                print("⚠️ Username must be 100 characters or less. Please try again.")
                continue
            
            if not re.match(r'^[a-zA-Z0-9_\-\s]+$', username):
                print("⚠️ Username can only contain letters, numbers, spaces, underscores, and hyphens.")
                continue
            
            current_user = username.upper()
            print(f"✅ User identified as: {current_user}")
            return current_user
            
        except Exception as e:
            print(f"❌ Error getting user identification: {e}")
            print("⚠️ Defaulting to SYSTEM user.")
            current_user = "SYSTEM"
            return current_user


def change_user() -> str:
    """Allow changing the current user."""
    global current_user
    print(f"\nCurrent user: {current_user}")
    confirm = input("Change user? (yes/no): ").strip().lower()
    
    if confirm in ('yes', 'y'):
        current_user = None
        return get_current_user()
    
    return current_user


# =====================================================
# USER PREFERENCES SYSTEM
# =====================================================

def get_user_preferences() -> Dict:
    """Return current user preferences."""
    return user_preferences.copy()


def set_user_preferences():
    """Interactive prompt to set user preferences."""
    global user_preferences
    
    print("\n=== USER PREFERENCES CONFIGURATION ===")
    
    print("\n1. Output Format:")
    print("   - table: Tabular display (default)")
    print("   - list: Bullet point list")
    print("   - compact: One line per record")
    choice = input("   Select (table/list/compact) [current: {}]: ".format(user_preferences['output_format'])).strip().lower()
    if choice in ('table', 'list', 'compact'):
        user_preferences['output_format'] = choice
    
    print("\n2. Show Deleted Records:")
    choice = input("   Show soft-deleted records? (yes/no) [current: {}]: ".format('yes' if user_preferences['show_deleted'] else 'no')).strip().lower()
    if choice in ('yes', 'y'):
        user_preferences['show_deleted'] = True
    elif choice in ('no', 'n'):
        user_preferences['show_deleted'] = False
    
    print("\n3. Date Format:")
    print("   - YYYY-MM-DD (default)")
    print("   - DD-MM-YYYY")
    print("   - MM-DD-YYYY")
    choice = input("   Select format [current: {}]: ".format(user_preferences['date_format'])).strip().upper()
    if choice in ('YYYY-MM-DD', 'DD-MM-YYYY', 'MM-DD-YYYY'):
        user_preferences['date_format'] = choice
    
    print("\n4. Include Audit Information:")
    choice = input("   Show last action info? (yes/no) [current: {}]: ".format('yes' if user_preferences['include_audit_info'] else 'no')).strip().lower()
    if choice in ('yes', 'y'):
        user_preferences['include_audit_info'] = True
    elif choice in ('no', 'n'):
        user_preferences['include_audit_info'] = False
    
    print("\n5. Maximum Records to Display:")
    print("   Options: 10, 25, 50, 100, all")
    choice = input("   Select [current: {}]: ".format(user_preferences['max_records'])).strip().lower()
    if choice in ('10', '25', '50', '100', 'all'):
        user_preferences['max_records'] = int(choice) if choice != 'all' else 'all'
    
    print("\n6. Sort By:")
    print("   - product_name (default)")
    print("   - product_id")
    print("   - action_at")
    choice = input("   Select [current: {}]: ".format(user_preferences['sort_by'])).strip().lower()
    if choice in ('product_name', 'product_id', 'action_at'):
        user_preferences['sort_by'] = choice
    
    print("\n7. Sort Order:")
    print("   - asc: Ascending (default)")
    print("   - desc: Descending")
    choice = input("   Select [current: {}]: ".format(user_preferences['sort_order'])).strip().lower()
    if choice in ('asc', 'desc'):
        user_preferences['sort_order'] = choice
    
    print("\n✅ Preferences updated successfully!")
    print("Current settings:", user_preferences)


def format_date(date_obj: Union[date, datetime, str], fmt: str = None) -> str:
    """Format date according to user preferences."""
    if date_obj is None:
        return 'N/A'
    
    if fmt is None:
        fmt = user_preferences['date_format']
    
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
        except:
            return date_obj
    
    if fmt == 'YYYY-MM-DD':
        return date_obj.strftime('%Y-%m-%d')
    elif fmt == 'DD-MM-YYYY':
        return date_obj.strftime('%d-%m-%Y')
    elif fmt == 'MM-DD-YYYY':
        return date_obj.strftime('%m-%d-%Y')
    else:
        return str(date_obj)


def apply_preferences_to_df(df: pd.DataFrame, preferences: Dict = None) -> pd.DataFrame:
    """Apply all preferences to filter/sort/format DataFrame."""
    if preferences is None:
        preferences = user_preferences
    
    if df.empty:
        return df
    
    result_df = df.copy()
    
    if 'is_deleted' in result_df.columns and not preferences['show_deleted']:
        result_df = result_df[result_df['is_deleted'] == False]
    
    sort_col = preferences['sort_by']
    if sort_col in result_df.columns:
        ascending = preferences['sort_order'] == 'asc'
        result_df = result_df.sort_values(by=sort_col, ascending=ascending)
    
    max_records = preferences['max_records']
    if max_records != 'all' and len(result_df) > max_records:
        result_df = result_df.head(max_records)
        print(f"\nℹ️ Showing first {max_records} records (use preferences to change limit)")
    
    date_columns = [col for col in result_df.columns if 'date' in col.lower() or 'at' in col.lower()]
    for col in date_columns:
        if col in result_df.columns:
            result_df[col] = result_df[col].apply(lambda x: format_date(x, preferences['date_format']))
    
    return result_df


def format_output(data: Union[pd.DataFrame, List[Dict], Dict], preferences: Dict = None) -> str:
    """Return formatted string based on preferences."""
    if preferences is None:
        preferences = user_preferences
    
    if isinstance(data, dict):
        data = [data]
    
    if isinstance(data, list):
        if not data:
            return "No records found."
        df = pd.DataFrame(data)
    else:
        df = data.copy()
    
    if df.empty:
        return "No records found."
    
    df = apply_preferences_to_df(df, preferences)
    
    output_format = preferences['output_format']
    
    if output_format == 'table':
        return df.to_string(index=False)
    
    elif output_format == 'list':
        lines = []
        for idx, row in df.iterrows():
            lines.append(f"\n--- Record {idx + 1} ---")
            for col, val in row.items():
                lines.append(f"  {col}: {val}")
        return "\n".join(lines)
    
    elif output_format == 'compact':
        lines = []
        for _, row in df.iterrows():
            key_fields = []
            if 'product_id' in row:
                key_fields.append(f"ID:{row['product_id']}")
            if 'product_name' in row:
                key_fields.append(f"Name:{row['product_name']}")
            if 'quantity' in row:
                key_fields.append(f"Qty:{row['quantity']}")
            if 'is_deleted' in row and row['is_deleted']:
                key_fields.append("[DELETED]")
            lines.append(" | ".join(key_fields))
        return "\n".join(lines)
    
    else:
        return df.to_string(index=False)


# =====================================================
# VALIDATION HELPERS
# =====================================================

def validate_product_name(name: str) -> Tuple[bool, str]:
    """Validate product name. Returns (is_valid, error_message)."""
    if not name:
        return False, "Product name cannot be empty"
    
    if len(name) > 100:
        return False, "Product name must be 100 characters or less"
    
    return True, ""


def validate_quantity(qty: int) -> Tuple[bool, str]:
    """Validate quantity. Returns (is_valid, error_message)."""
    if not isinstance(qty, int):
        return False, "Quantity must be an integer"
    
    if qty <= 0:
        return False, "Quantity must be positive"
    
    if qty > 999999:
        return False, "Quantity exceeds maximum (999,999)"
    
    return True, ""


def validate_expiry_date(expiry_str: str, is_required: bool = False) -> Tuple[bool, str, Optional[date]]:
    """Validate expiry date string. Returns (is_valid, error_message, date_object)."""
    if not expiry_str:
        if is_required:
            return False, "Expiry date is required for expirable products", None
        return True, "", None
    
    try:
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date()
        
        if expiry_date <= date.today():
            return False, "Expiry date must be in the future", None
        
        return True, "", expiry_date
        
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD", None


def check_product_exists(product_id: int, check_deleted: bool = False) -> Tuple[bool, Optional[Dict]]:
    """Check if product exists. Returns (exists, product_data)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = "SELECT * FROM Products WHERE product_id = %s"
        if not check_deleted:
            sql += " AND is_deleted = FALSE"
        
        cursor.execute(sql, (product_id,))
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            product_data = dict(zip(columns, row))
            return True, product_data
        return False, None
        
    except Exception as e:
        print(f"❌ Error checking product: {e}")
        return False, None
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def check_lot_exists(lot_id: int, check_deleted: bool = False) -> Tuple[bool, Optional[Dict]]:
    """Check if inventory lot exists."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = "SELECT * FROM Inventory_lots WHERE lot_id = %s"
        if not check_deleted:
            sql += " AND is_deleted = FALSE"
        
        cursor.execute(sql, (lot_id,))
        row = cursor.fetchone()
        
        if row:
            columns = [desc[0] for desc in cursor.description]
            lot_data = dict(zip(columns, row))
            return True, lot_data
        return False, None
        
    except Exception as e:
        print(f"❌ Error checking lot: {e}")
        return False, None
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# =====================================================
# AUDIT LOGGING FUNCTIONS
# =====================================================

def log_product_audit(
    product_id: int,
    action: str,
    action_by: str,
    product_name: str = None,
    is_expirable: bool = None
) -> bool:
    """Explicitly log product action to Products_audit table."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO Products_audit 
            (product_id, action, action_by, action_at, product_name, is_expirable)
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """
        
        cursor.execute(sql, (product_id, action, action_by, product_name, is_expirable))
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error logging product audit: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def log_inventory_audit(
    lot_id: int,
    product_id: int,
    action: str,
    action_by: str,
    quantity: int = None,
    expiry_date: date = None
) -> bool:
    """Explicitly log inventory lot action to Inventory_lots_audit table."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO Inventory_lots_audit 
            (lot_id, product_id, action, action_by, action_at, quantity, expiry_date)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s)
        """
        
        cursor.execute(sql, (lot_id, product_id, action, action_by, quantity, expiry_date))
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error logging inventory audit: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# =====================================================
# CRUD OPERATIONS - PRODUCTS
# =====================================================

def add_product(product_name: str, is_expirable: bool = False, action_by: str = None) -> Optional[int]:
    """Create a new product and return the inserted product_id."""
    if action_by is None:
        action_by = get_current_user()
    
    is_valid, error_msg = validate_product_name(product_name)
    if not is_valid:
        print(f"⚠️ {error_msg}")
        return None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT product_id FROM Products WHERE product_name = %s AND is_deleted = FALSE", 
                      (product_name,))
        if cursor.fetchone():
            print(f"⚠️ Product '{product_name}' already exists.")
            return None
        
        sql = """
            INSERT INTO Products (product_name, is_expirable, is_deleted)
            VALUES (%s, %s, FALSE)
        """
        cursor.execute(sql, (product_name, bool(is_expirable)))
        conn.commit()
        
        product_id = cursor.lastrowid
        
        log_product_audit(
            product_id=product_id,
            action='INSERT',
            action_by=action_by,
            product_name=product_name,
            is_expirable=bool(is_expirable)
        )
        
        product_cache.append({
            'product_id': product_id,
            'product_name': product_name,
            'is_expirable': bool(is_expirable),
            'is_deleted': False
        })
        
        print(f"✅ Product '{product_name}' inserted with ID {product_id}. Audit trail created.")
        return product_id
        
    except Exception as e:
        print(f"❌ Error inserting product: {e}")
        return None
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def get_product(product_id: int, include_audit_info: bool = False) -> Optional[Dict]:
    """Fetch a single product by ID."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT product_id, product_name, is_expirable, is_deleted
            FROM Products 
            WHERE product_id = %s
        """
        cursor.execute(sql, (product_id,))
        row = cursor.fetchone()
        
        if not row:
            print("⚠️ Product not found.")
            return None
        
        product = {
            'product_id': row[0],
            'product_name': row[1],
            'is_expirable': bool(row[2]),
            'is_deleted': bool(row[3])
        }
        
        if include_audit_info:
            cursor.execute("""
                SELECT action_by, action_at, action
                FROM Products_audit
                WHERE product_id = %s
                ORDER BY action_at DESC
                LIMIT 1
            """, (product_id,))
            audit_row = cursor.fetchone()
            if audit_row:
                product['last_action_by'] = audit_row[0]
                product['last_action_at'] = audit_row[1]
                product['last_action'] = audit_row[2]
        
        return product
        
    except Exception as e:
        print(f"❌ Error fetching product: {e}")
        return None
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def update_product(
    product_id: int, 
    product_name: str = None, 
    is_expirable: bool = None, 
    action_by: str = None
) -> bool:
    """Update product fields."""
    if action_by is None:
        action_by = get_current_user()
    
    exists, product_data = check_product_exists(product_id)
    if not exists:
        print("⚠️ Product not found or is deleted.")
        return False
    
    updates = []
    params = []
    
    if product_name is not None:
        is_valid, error_msg = validate_product_name(product_name)
        if not is_valid:
            print(f"⚠️ {error_msg}")
            return False
        
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT product_id FROM Products WHERE product_name = %s AND product_id != %s AND is_deleted = FALSE",
                (product_name, product_id)
            )
            if cursor.fetchone():
                print(f"⚠️ Product name '{product_name}' already exists.")
                return False
        except Exception as e:
            print(f"❌ Error checking duplicate: {e}")
            return False
        finally:
            try:
                cursor.close()
            except:
                pass
            try:
                conn.close()
            except:
                pass
        
        updates.append("product_name = %s")
        params.append(product_name)
    
    if is_expirable is not None:
        updates.append("is_expirable = %s")
        params.append(bool(is_expirable))
    
    if not updates:
        print("⚠️ Nothing to update.")
        return False
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        params.append(product_id)
        sql = f"UPDATE Products SET {', '.join(updates)} WHERE product_id = %s AND is_deleted = FALSE"
        cursor.execute(sql, tuple(params))
        conn.commit()
        
        if cursor.rowcount == 0:
            print("⚠️ No changes made.")
            return False
        
        new_name = product_name if product_name is not None else product_data['product_name']
        new_expirable = is_expirable if is_expirable is not None else product_data['is_expirable']
        
        log_product_audit(
            product_id=product_id,
            action='UPDATE',
            action_by=action_by,
            product_name=new_name,
            is_expirable=new_expirable
        )
        
        print(f"✅ Product ID {product_id} updated. Audit trail created.")
        return True
        
    except Exception as e:
        print(f"❌ Error updating product: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def delete_product(product_id: int, action_by: str = None) -> bool:
    """Soft-delete a product and its inventory lots."""
    if action_by is None:
        action_by = get_current_user()
    
    exists, product_data = check_product_exists(product_id)
    if not exists:
        print("⚠️ Product not found or already deleted.")
        return False
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT lot_id, quantity, expiry_date 
            FROM Inventory_lots 
            WHERE product_id = %s AND is_deleted = FALSE
        """, (product_id,))
        lots = cursor.fetchall()
        
        cursor.execute("""
            UPDATE Products SET is_deleted = TRUE 
            WHERE product_id = %s AND is_deleted = FALSE
        """, (product_id,))
        
        cursor.execute("""
            UPDATE Inventory_lots SET is_deleted = TRUE 
            WHERE product_id = %s AND is_deleted = FALSE
        """, (product_id,))
        
        conn.commit()
        
        log_product_audit(
            product_id=product_id,
            action='DELETE',
            action_by=action_by,
            product_name=product_data['product_name'],
            is_expirable=product_data['is_expirable']
        )
        
        for lot in lots:
            lot_id, quantity, expiry_date = lot
            log_inventory_audit(
                lot_id=lot_id,
                product_id=product_id,
                action='DELETE',
                action_by=action_by,
                quantity=quantity,
                expiry_date=expiry_date
            )
        
        print(f"✅ Product ID {product_id} and {len(lots)} related inventory lot(s) soft-deleted.")
        return True
        
    except Exception as e:
        print(f"❌ Error deleting product: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# =====================================================
# CRUD OPERATIONS - INVENTORY LOTS
# =====================================================

def add_inventory_lot(
    product_id: int, 
    quantity: int, 
    expiry_date: str = None, 
    action_by: str = None
) -> Optional[int]:
    """Add inventory lot for a product."""
    if action_by is None:
        action_by = get_current_user()
    
    exists, product_data = check_product_exists(product_id)
    if not exists:
        print("⚠️ Product not found or is deleted.")
        return None
    
    is_valid, error_msg = validate_quantity(quantity)
    if not is_valid:
        print(f"⚠️ {error_msg}")
        return None
    
    is_expirable = product_data['is_expirable']
    is_valid, error_msg, expiry_obj = validate_expiry_date(expiry_date, is_required=is_expirable)
    if not is_valid:
        print(f"⚠️ {error_msg}")
        return None
    
    if not is_expirable:
        expiry_obj = None
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO Inventory_lots (product_id, quantity, expiry_date, is_deleted)
            VALUES (%s, %s, %s, FALSE)
        """
        cursor.execute(sql, (product_id, quantity, expiry_obj))
        conn.commit()
        
        lot_id = cursor.lastrowid
        
        log_inventory_audit(
            lot_id=lot_id,
            product_id=product_id,
            action='INSERT',
            action_by=action_by,
            quantity=quantity,
            expiry_date=expiry_obj
        )
        
        print(f"✅ Inventory lot added with ID {lot_id}. Audit trail created.")
        return lot_id
        
    except Exception as e:
        print(f"❌ Error adding inventory lot: {e}")
        return None
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def get_inventory_lots(
    product_id: int = None, 
    preferences: Dict = None,
    include_deleted: bool = None
) -> pd.DataFrame:
    """Fetch inventory lots with preference support."""
    if preferences is None:
        preferences = user_preferences.copy()
    
    if include_deleted is not None:
        preferences['show_deleted'] = include_deleted
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                il.lot_id,
                il.product_id,
                p.product_name,
                il.quantity,
                il.expiry_date,
                il.is_deleted
            FROM Inventory_lots il
            JOIN Products p ON il.product_id = p.product_id
            WHERE 1=1
        """
        params = []
        
        if product_id is not None:
            sql += " AND il.product_id = %s"
            params.append(product_id)
        
        if not preferences['show_deleted']:
            sql += " AND il.is_deleted = FALSE"
        
        sort_col = preferences['sort_by']
        if sort_col == 'product_name':
            sql += " ORDER BY p.product_name"
        elif sort_col == 'product_id':
            sql += " ORDER BY il.product_id"
        elif sort_col == 'action_at':
            sql += " ORDER BY il.lot_id"
        else:
            sql += " ORDER BY il.lot_id"
        
        if preferences['sort_order'] == 'desc':
            sql += " DESC"
        else:
            sql += " ASC"
        
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        columns = ['lot_id', 'product_id', 'product_name', 'quantity', 'expiry_date', 'is_deleted']
        df = pd.DataFrame(rows, columns=columns)
        
        if preferences['show_deleted']:
            df['status'] = df['is_deleted'].apply(lambda x: '[DELETED]' if x else 'Active')
        
        df = apply_preferences_to_df(df, preferences)
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching inventory lots: {e}")
        return pd.DataFrame()
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def update_inventory_lot(
    lot_id: int, 
    quantity: int = None, 
    expiry_date: str = None,
    action_by: str = None
) -> bool:
    """Update inventory lot fields."""
    if action_by is None:
        action_by = get_current_user()
    
    exists, lot_data = check_lot_exists(lot_id)
    if not exists:
        print("⚠️ Inventory lot not found or is deleted.")
        return False
    
    product_id = lot_data['product_id']
    exists, product_data = check_product_exists(product_id)
    if not exists:
        print("⚠️ Associated product not found.")
        return False
    
    is_expirable = product_data['is_expirable']
    
    updates = []
    params = []
    
    if quantity is not None:
        is_valid, error_msg = validate_quantity(quantity)
        if not is_valid:
            print(f"⚠️ {error_msg}")
            return False
        updates.append("quantity = %s")
        params.append(quantity)
    
    if expiry_date is not None:
        is_valid, error_msg, expiry_obj = validate_expiry_date(expiry_date, is_required=is_expirable)
        if not is_valid:
            print(f"⚠️ {error_msg}")
            return False
        updates.append("expiry_date = %s")
        params.append(expiry_obj)
    
    if not updates:
        print("⚠️ Nothing to update.")
        return False
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        params.append(lot_id)
        sql = f"UPDATE Inventory_lots SET {', '.join(updates)} WHERE lot_id = %s AND is_deleted = FALSE"
        cursor.execute(sql, tuple(params))
        conn.commit()
        
        if cursor.rowcount == 0:
            print("⚠️ No changes made.")
            return False
        
        new_quantity = quantity if quantity is not None else lot_data['quantity']
        new_expiry = expiry_date if expiry_date is not None else lot_data['expiry_date']
        
        log_inventory_audit(
            lot_id=lot_id,
            product_id=product_id,
            action='UPDATE',
            action_by=action_by,
            quantity=new_quantity,
            expiry_date=new_expiry
        )
        
        print(f"✅ Inventory lot ID {lot_id} updated. Audit trail created.")
        return True
        
    except Exception as e:
        print(f"❌ Error updating inventory lot: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def delete_inventory_lot(lot_id: int, action_by: str = None) -> bool:
    """Soft-delete an inventory lot."""
    if action_by is None:
        action_by = get_current_user()
    
    exists, lot_data = check_lot_exists(lot_id)
    if not exists:
        print("⚠️ Inventory lot not found or already deleted.")
        return False
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE Inventory_lots SET is_deleted = TRUE 
            WHERE lot_id = %s AND is_deleted = FALSE
        """, (lot_id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            print("⚠️ No changes made.")
            return False
        
        log_inventory_audit(
            lot_id=lot_id,
            product_id=lot_data['product_id'],
            action='DELETE',
            action_by=action_by,
            quantity=lot_data['quantity'],
            expiry_date=lot_data['expiry_date']
        )
        
        print(f"✅ Inventory lot ID {lot_id} soft-deleted. Audit trail created.")
        return True
        
    except Exception as e:
        print(f"❌ Error deleting inventory lot: {e}")
        return False
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# =====================================================
# QUERY FUNCTIONS WITH PREFERENCE SUPPORT
# =====================================================

def get_products(
    preferences: Dict = None,
    filters: Dict = None
) -> pd.DataFrame:
    """Get products with inventory aggregation and preference support."""
    if preferences is None:
        preferences = user_preferences.copy()
    
    if filters is None:
        filters = {}
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                p.product_id,
                p.product_name,
                p.is_expirable,
                p.is_deleted,
                COALESCE(SUM(il.quantity), 0) as total_quantity,
                COUNT(il.lot_id) as lot_count
            FROM Products p
            LEFT JOIN Inventory_lots il 
                ON p.product_id = il.product_id 
                AND il.is_deleted = FALSE
                AND il.quantity > 0
            WHERE 1=1
        """
        params = []
        
        if not preferences['show_deleted']:
            sql += " AND p.is_deleted = FALSE"
        
        if filters.get('product_name'):
            sql += " AND p.product_name LIKE %s"
            params.append(f"%{filters['product_name']}%")
        
        if filters.get('is_expirable') is not None:
            sql += " AND p.is_expirable = %s"
            params.append(filters['is_expirable'])
        
        sql += " GROUP BY p.product_id, p.product_name, p.is_expirable, p.is_deleted"
        
        if filters.get('has_stock') is True:
            sql += " HAVING total_quantity > 0"
        elif filters.get('has_stock') is False:
            sql += " HAVING total_quantity = 0"
        
        sort_col = preferences['sort_by']
        if sort_col == 'product_name':
            sql += " ORDER BY p.product_name"
        elif sort_col == 'product_id':
            sql += " ORDER BY p.product_id"
        else:
            sql += " ORDER BY p.product_name"
        
        if preferences['sort_order'] == 'desc':
            sql += " DESC"
        else:
            sql += " ASC"
        
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        columns = ['product_id', 'product_name', 'is_expirable', 'is_deleted', 'total_quantity', 'lot_count']
        df = pd.DataFrame(rows, columns=columns)
        
        if preferences['show_deleted']:
            df['status'] = df['is_deleted'].apply(lambda x: '[DELETED]' if x else 'Active')
        
        if preferences['include_audit_info']:
            audit_info = []
            for pid in df['product_id']:
                cursor.execute("""
                    SELECT action_by, action_at, action
                    FROM Products_audit
                    WHERE product_id = %s
                    ORDER BY action_at DESC
                    LIMIT 1
                """, (pid,))
                row = cursor.fetchone()
                if row:
                    audit_info.append({
                        'product_id': pid,
                        'last_action_by': row[0],
                        'last_action_at': row[1],
                        'last_action': row[2]
                    })
                else:
                    audit_info.append({
                        'product_id': pid,
                        'last_action_by': None,
                        'last_action_at': None,
                        'last_action': None
                    })
            
            audit_df = pd.DataFrame(audit_info)
            df = df.merge(audit_df, on='product_id', how='left')
        
        df = apply_preferences_to_df(df, preferences)
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching products: {e}")
        return pd.DataFrame()
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def get_product_detail(product_id: int, preferences: Dict = None) -> Dict:
    """Get detailed product information with all inventory lots."""
    if preferences is None:
        preferences = user_preferences.copy()
    
    product = get_product(product_id, include_audit_info=preferences['include_audit_info'])
    
    if not product:
        return None
    
    inventory_df = get_inventory_lots(product_id=product_id, preferences=preferences)
    
    return {
        'product': product,
        'inventory_lots': inventory_df
    }


# =====================================================
# AUDIT QUERY FUNCTIONS
# =====================================================

def get_product_audit_history(
    product_id: int = None,
    user: str = None,
    date_range: Tuple[str, str] = None,
    action: str = None
) -> pd.DataFrame:
    """Retrieve audit history for products."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                audit_id,
                product_id,
                action,
                action_by,
                action_at,
                product_name,
                is_expirable
            FROM Products_audit
            WHERE 1=1
        """
        params = []
        
        if product_id is not None:
            sql += " AND product_id = %s"
            params.append(product_id)
        
        if user:
            sql += " AND action_by = %s"
            params.append(user)
        
        if date_range:
            start_date, end_date = date_range
            if start_date:
                sql += " AND action_at >= %s"
                params.append(start_date)
            if end_date:
                sql += " AND action_at <= %s"
                params.append(end_date + " 23:59:59")
        
        if action:
            sql += " AND action = %s"
            params.append(action)
        
        sql += " ORDER BY action_at DESC"
        
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        columns = ['audit_id', 'product_id', 'action', 'action_by', 'action_at', 'product_name', 'is_expirable']
        df = pd.DataFrame(rows, columns=columns)
        
        df['action_at'] = df['action_at'].apply(lambda x: format_date(x))
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching product audit history: {e}")
        return pd.DataFrame()
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def get_inventory_audit_history(
    lot_id: int = None,
    product_id: int = None,
    user: str = None,
    date_range: Tuple[str, str] = None
) -> pd.DataFrame:
    """Retrieve audit history for inventory lots."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                audit_id,
                lot_id,
                product_id,
                action,
                action_by,
                action_at,
                quantity,
                expiry_date
            FROM Inventory_lots_audit
            WHERE 1=1
        """
        params = []
        
        if lot_id is not None:
            sql += " AND lot_id = %s"
            params.append(lot_id)
        
        if product_id is not None:
            sql += " AND product_id = %s"
            params.append(product_id)
        
        if user:
            sql += " AND action_by = %s"
            params.append(user)
        
        if date_range:
            start_date, end_date = date_range
            if start_date:
                sql += " AND action_at >= %s"
                params.append(start_date)
            if end_date:
                sql += " AND action_at <= %s"
                params.append(end_date + " 23:59:59")
        
        sql += " ORDER BY action_at DESC"
        
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        columns = ['audit_id', 'lot_id', 'product_id', 'action', 'action_by', 'action_at', 'quantity', 'expiry_date']
        df = pd.DataFrame(rows, columns=columns)
        
        df['action_at'] = df['action_at'].apply(lambda x: format_date(x))
        df['expiry_date'] = df['expiry_date'].apply(lambda x: format_date(x))
        
        return df
        
    except Exception as e:
        print(f"❌ Error fetching inventory audit history: {e}")
        return pd.DataFrame()
    finally:
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


# =====================================================
# INTERACTIVE MENU
# =====================================================

def display_menu():
    """Display main menu header."""
    user_str = current_user if current_user else "Not identified"
    pref_str = user_preferences['output_format']
    
    print("\n" + "="*60)
    print("📦 PRODUCTS & INVENTORY MANAGEMENT")
    print("="*60)
    print(f"User: {user_str} | Preferences: {pref_str}")
    print("="*60)


def products_menu():
    """Interactive products menu with audit integration."""
    global current_user
    
    if current_user is None:
        get_current_user()
    
    while True:
        display_menu()
        print("1.  Identify User (set/change current user)")
        print("2.  Manage Preferences")
        print("3.  Add Product")
        print("4.  Update Product")
        print("5.  Delete Product (Soft)")
        print("6.  Add Inventory Lot")
        print("7.  Update Inventory Lot")
        print("8.  Delete Inventory Lot (Soft)")
        print("9.  View Products (with filters & preferences)")
        print("10. View Inventory (with filters & preferences)")
        print("11. View Audit History")
        print("12. Exit")
        
        choice = input("\nSelect an option: ").strip()
        
        if choice == '1':
            change_user()
        
        elif choice == '2':
            set_user_preferences()
        
        elif choice == '3':
            print("\n--- Add Product ---")
            name = input("Product name: ").strip()
            exp_input = input("Is expirable? (yes/no): ").strip().lower()
            is_expirable = exp_input in ('yes', 'y')
            add_product(name, is_expirable)
        
        elif choice == '4':
            print("\n--- Update Product ---")
            try:
                pid = int(input("Product ID: ").strip())
                print("Leave blank to keep current value")
                new_name = input("New product name: ").strip() or None
                new_exp = input("Is expirable? (yes/no): ").strip().lower()
                
                is_expirable = None
                if new_exp in ('yes', 'y'):
                    is_expirable = True
                elif new_exp in ('no', 'n'):
                    is_expirable = False
                
                update_product(pid, new_name, is_expirable)
            except ValueError:
                print("⚠️ Invalid Product ID")
        
        elif choice == '5':
            print("\n--- Delete Product (Soft) ---")
            try:
                pid = int(input("Product ID to delete: ").strip())
                confirm = input(f"Soft-delete product {pid} and all its inventory lots? (yes/no): ").strip().lower()
                if confirm in ('yes', 'y'):
                    delete_product(pid)
            except ValueError:
                print("⚠️ Invalid Product ID")
        
        elif choice == '6':
            print("\n--- Add Inventory Lot ---")
            try:
                pid = int(input("Product ID: ").strip())
                qty = int(input("Quantity: ").strip())
                
                prod = get_product(pid)
                expiry = None
                if prod and prod.get('is_expirable'):
                    expiry = input("Expiry date (YYYY-MM-DD): ").strip() or None
                
                add_inventory_lot(pid, qty, expiry)
            except ValueError:
                print("⚠️ Invalid numeric input")
        
        elif choice == '7':
            print("\n--- Update Inventory Lot ---")
            try:
                lid = int(input("Lot ID: ").strip())
                print("Leave blank to keep current value")
                qty_input = input("New quantity: ").strip()
                qty = int(qty_input) if qty_input else None
                expiry = input("New expiry date (YYYY-MM-DD): ").strip() or None
                
                update_inventory_lot(lid, qty, expiry)
            except ValueError:
                print("⚠️ Invalid numeric input")
        
        elif choice == '8':
            print("\n--- Delete Inventory Lot (Soft) ---")
            try:
                lid = int(input("Lot ID to delete: ").strip())
                confirm = input(f"Soft-delete lot {lid}? (yes/no): ").strip().lower()
                if confirm in ('yes', 'y'):
                    delete_inventory_lot(lid)
            except ValueError:
                print("⚠️ Invalid Lot ID")
        
        elif choice == '9':
            print("\n--- View Products ---")
            filters = {}
            name_filter = input("Filter by product name (or 'all'): ").strip()
            if name_filter.lower() != 'all':
                filters['product_name'] = name_filter
            
            exp_filter = input("Filter by expirable? (yes/no/all): ").strip().lower()
            if exp_filter == 'yes':
                filters['is_expirable'] = True
            elif exp_filter == 'no':
                filters['is_expirable'] = False
            
            stock_filter = input("Filter by stock? (in/out/all): ").strip().lower()
            if stock_filter == 'in':
                filters['has_stock'] = True
            elif stock_filter == 'out':
                filters['has_stock'] = False
            
            df = get_products(filters=filters)
            if not df.empty:
                print("\n" + format_output(df))
            else:
                print("⚠️ No products found")
        
        elif choice == '10':
            print("\n--- View Inventory ---")
            try:
                pid_input = input("Filter by Product ID (or 'all'): ").strip()
                pid = int(pid_input) if pid_input.isdigit() else None
                
                df = get_inventory_lots(product_id=pid)
                if not df.empty:
                    print("\n" + format_output(df))
                else:
                    print("⚠️ No inventory lots found")
            except ValueError:
                print("⚠️ Invalid Product ID")
        
        elif choice == '11':
            audit_submenu()
        
        elif choice == '12':
            print("\n👋 Goodbye!")
            break
        
        else:
            print("⚠️ Invalid choice. Please select a valid option.")


def audit_submenu():
    """Audit history submenu."""
    while True:
        print("\n" + "="*60)
        print("🔍 AUDIT HISTORY")
        print("="*60)
        print("1. View Product Audit History")
        print("2. View Inventory Audit History")
        print("3. View Complete Audit Trail")
        print("4. Back to Main Menu")
        
        choice = input("\nSelect an option: ").strip()
        
        if choice == '1':
            print("\n--- Product Audit History ---")
            try:
                pid_input = input("Product ID (or 'all'): ").strip()
                pid = int(pid_input) if pid_input.isdigit() else None
                
                user = input("Filter by user (or 'all'): ").strip()
                user = user if user.lower() != 'all' else None
                
                df = get_product_audit_history(product_id=pid, user=user)
                if not df.empty:
                    print("\n" + format_output(df))
                else:
                    print("⚠️ No audit records found")
            except ValueError:
                print("⚠️ Invalid input")
        
        elif choice == '2':
            print("\n--- Inventory Audit History ---")
            try:
                lid_input = input("Lot ID (or 'all'): ").strip()
                lid = int(lid_input) if lid_input.isdigit() else None
                
                pid_input = input("Product ID (or 'all'): ").strip()
                pid = int(pid_input) if pid_input.isdigit() else None
                
                df = get_inventory_audit_history(lot_id=lid, product_id=pid)
                if not df.empty:
                    print("\n" + format_output(df))
                else:
                    print("⚠️ No audit records found")
            except ValueError:
                print("⚠️ Invalid input")
        
        elif choice == '3':
            print("\n--- Complete Audit Trail ---")
            print("Combined view of product and inventory audits")
            
            prod_df = get_product_audit_history()
            inv_df = get_inventory_audit_history()
            
            if not prod_df.empty or not inv_df.empty:
                if not prod_df.empty:
                    prod_df['entity_type'] = 'PRODUCT'
                if not inv_df.empty:
                    inv_df['entity_type'] = 'INVENTORY'
                
                combined = pd.concat([prod_df, inv_df], ignore_index=True, sort=False)
                combined = combined.sort_values('action_at', ascending=False)
                
                max_rec = user_preferences['max_records']
                if max_rec != 'all' and len(combined) > max_rec:
                    combined = combined.head(max_rec)
                
                print("\n" + format_output(combined))
            else:
                print("⚠️ No audit records found")
        
        elif choice == '4':
            break
        
        else:
            print("⚠️ Invalid choice")


if __name__ == '__main__':
    products_menu()