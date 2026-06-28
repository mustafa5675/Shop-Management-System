# Generate the enhanced Products.py with audit functionality
enhanced_products_py = """Enhanced Products module with complete audit trail implementation.

Implements CRUD for `Products` and `Inventory_lots` tables,
helper functions for filtering, interactive menu, and comprehensive
audit logging and reporting capabilities.
"""

from datetime import datetime, date, timedelta
import pandas as pd
from typing import Optional, Dict, List, Tuple
import csv
import os
from Database import get_connection

product_cache = []  # in-memory cache similar to purchases.py


# =====================================================
# AUDIT LOGGING HELPERS
# =====================================================

def log_audit_action(
    table_name: str,
    action: str,
    record_id: int,
    user: str,
    old_values: dict = None,
    new_values: dict = None,
    ip_address: str = None,
    session_id: str = None
) -> bool:
    """Manually log an audit action. Used as fallback or for additional logging.
    
    Args:
        table_name: 'Products' or 'Inventory_lots'
        action: 'INSERT', 'UPDATE', or 'DELETE'
        record_id: The ID of the affected record
        user: Username/operator who performed the action
        old_values: Previous values (for UPDATE/DELETE)
        new_values: New values (for INSERT/UPDATE)
        ip_address: Optional IP address for traceability
        session_id: Optional session ID for traceability
    
    Returns:
        True if logged successfully, False otherwise
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Determine which audit table to use
        if table_name == 'Products':
            audit_table = 'Products_audit'
            id_column = 'product_id'
            data_columns = ['product_name', 'is_expirable', 'action_by', 'action_at']
        else:
            audit_table = 'Inventory_lots_audit'
            id_column = 'lot_id'
            data_columns = ['product_id', 'quantity', 'expiry_date', 'action_by', 'action_at']
        
        # Build dynamic insert based on available data
        columns = [id_column, 'action', 'action_by', 'action_at']
        values = [record_id, action, user, datetime.now()]
        
        if new_values:
            for col in data_columns:
                if col in new_values:
                    columns.append(col)
                    values.append(new_values[col])
        
        placeholders = ', '.join(['%s'] * len(values))
        sql = f"INSERT INTO {audit_table} ({', '.join(columns)}) VALUES ({placeholders})"
        
        cursor.execute(sql, tuple(values))
        conn.commit()
        return True
        
    except Exception as e:
        print(f"❌ Error logging audit action: {e}")
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

""" waiting for when the enplloyee managemnt system is fully created
def get_current_user_context() -> Dict[str, Optional[str]]:
    Get current user context including IP and session if available.
    context = {
        'user': None,
        'ip_address': None,
        'session_id': None
    }
    
    # Try to get from environment or prompt
    try:
        context['user'] = os.getenv('CURRENT_USER') or input("Operator name: ").strip() or 'SYSTEM'
    except Exception as e:
        print(f"⚠️ Error getting user context: {e}")
        context['user'] = 'SYSTEM'
    
    # In a web context, these would come from request objects
    context['ip_address'] = os.getenv('CLIENT_IP', '127.0.0.1')
    context['session_id'] = os.getenv('SESSION_ID', 'CONSOLE_SESSION')
    
    return context"""


# =====================================================
# CRUD OPERATIONS (Enhanced with Audit Context)
# =====================================================

def add_product(product_name: str, is_expirable: bool = False, action_by: str = None):
    """Create a new product and return the inserted product_id.
    
    Automatically triggers audit logging via database triggers.
    """

    try:
        conn = get_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO Products (product_name, is_expirable, action_by, action_at)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (product_name, bool(is_expirable), action_by, datetime.now()))
        conn.commit()
        product_id = cursor.lastrowid

        product_cache.append({
            'product_id': product_id,
            'product_name': product_name,
            'is_expirable': bool(is_expirable),
            'action_at': datetime.now(),
            'action_by': action_by
        })

        print(f"✅ Product inserted with id {product_id}. Audit trail created.")
        return product_id

    except Exception as e:
        print("❌ Error inserting product:", e)
        # Attempt manual audit logging of the failure
        log_audit_action('Products', 'INSERT_FAILED', 0, action_by, 
                        new_values={'error': str(e), 'product_name': product_name})
        return None
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def get_product(product_id: int, include_audit_info: bool = False):
    """Fetch a single product by id.
    
    Args:
        product_id: The product ID to fetch
        include_audit_info: If True, includes created_by, updated_by, etc.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if include_audit_info:
            sql = """
                SELECT product_id, product_name, is_expirable, action_by, actioon_at
                FROM Products 
                WHERE product_id = %s AND deleted_at IS NULL
            """
        else:
            sql = """
                SELECT product_id, product_name, is_expirable, created_at 
                FROM Products 
                WHERE product_id = %s AND deleted_at IS NULL
            """
        
        cursor.execute(sql, (product_id,))
        row = cursor.fetchone()
        if not row:
            print("⚠️ Product not found or deleted.")
            return None

        if include_audit_info:
            return {
                'product_id': row[0],
                'product_name': row[1],
                'is_expirable': bool(row[2]),
                'action_by': row[3],
                'action_at': row[4]
            }
        else:
            return {
                'product_id': row[0],
                'product_name': row[1],
                'is_expirable': bool(row[2]),
                'created_at': row[3]
            }

    except Exception as e:
        print("❌ Error fetching product:", e)
        return None
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def update_product(product_id: int, product_name: str = None, is_expirable: bool = None, 
                   action_by: str = None):
    """Update product fields. Records `updated_by` and `updated_at`."""

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get old values for audit comparison
        cursor.execute("SELECT * FROM Products WHERE product_id = %s", (product_id,))
        old_row = cursor.fetchone()
        if not old_row:
            print("⚠️ Product not found.")
            return False
        
        updates = []
        params = []

        if product_name is not None:
            updates.append("product_name = %s")
            params.append(product_name)
        if is_expirable is not None:
            updates.append("is_expirable = %s")
            params.append(bool(is_expirable))

        # Always record updater when making changes
        updates.append("updated_by = %s")
        params.append(action_by)
        updates.append("updated_at = NOW()")

        if not updates:
            print("⚠️ Nothing to update.")
            return False

        params.append(product_id)
        sql = f"UPDATE Products SET {', '.join(updates)} WHERE product_id = %s AND deleted_at IS NULL"
        cursor.execute(sql, tuple(params))
        conn.commit()

        if cursor.rowcount > 0:
            print("✅ Product updated. Audit trail created.")
            return True
        else:
            print("⚠️ No changes made.")
            return False

    except Exception as e:
        print("❌ Error updating product:", e)
        return False
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def delete_product(product_name: str, action_by: str = None):
    # Soft-delete a product and its inventory lots by default.

    action_at = datetime.now

    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get product info before deletion for audit
        cursor.execute("SELECT product_id FROM Products WHERE product_name = %s", (product_name))
        product_info = cursor.fetchone()
        product_id = product_info[0] if product_info else "Unknown"

        query = ("""
                    UPDATE Products SET is_deleted = True
                    WHERE product_id = %s""")
        params = (product_id)
        cursor.execute(query,params)

        query = ("""
                    UPDATE Inventory_lots SET is_deleted = True
                    WHERE product_id = %s""")
        params = (product_id)
        cursor.execute(query,params)

        query = ("""
                       UPDATE Products_audit SET action = 'DELETE', action_by = %s, action_at = %s
                       WHERE product_id = %s""")
        params = (action_by, action_at, product_id)
        cursor.execute(query, params)

        query = ("""
                    UPDATE Inventory_lots_audit SET action = 'DELETE', action_by = %s, action_at = %s 
                    WHERE product_id = %s""")
        params = (action_by, action_at, product_id)
        cursor.execute(query,params)

        print("✅ Product and related inventory lots permanently deleted.")

        conn.commit()
        return True

    except Exception as e:
        print("❌ Error deleting product:", e)
        return False
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def add_inventory_lot(product_id: int, quantity: int, expiry_date: str = None, 
                      created_by: str = None):
    """Add inventory lot for a product. expiry_date should be 'YYYY-MM-DD' or None."""
        
    try:
        conn = get_connection()
        cursor = conn.cursor()

        sql = """
            INSERT INTO Inventory_lots (product_id, quantity, expiry_date, created_by, created_at) 
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (product_id, quantity, expiry_date, created_by, datetime.datetime.now))
        conn.commit()
        lot_id = cursor.lastrowid

        print(f"✅ Inventory lot added with id {lot_id}. Audit trail created.")
        return lot_id

    except Exception as e:
        print("❌ Error adding inventory lot:", e)
        return None
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def get_inventory_lots(product_id: int = None, include_deleted: bool = False):
    """Fetch inventory lots; optionally filter by product_id.
    
    Args:
        product_id: Filter by specific product
        include_deleted: If True, includes soft-deleted lots
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        base_sql = """
            SELECT lot_id, product_id, quantity, expiry_date, created_at, created_by,
                   updated_at, updated_by, deleted_at, deleted_by
            FROM Inventory_lots
            WHERE 1=1
        """
        params = []
        
        if product_id is not None:
            base_sql += " AND product_id = %s"
            params.append(product_id)
            
        if not include_deleted:
            base_sql += " AND deleted_at IS NULL"
            
        base_sql += " ORDER BY created_at DESC"
        
        cursor.execute(base_sql, tuple(params))
        rows = cursor.fetchall()
        
        lots = []
        for r in rows:
            lots.append({
                'lot_id': r[0],
                'product_id': r[1],
                'quantity': r[2],
                'expiry_date': r[3],
                'created_at': r[4],
                'created_by': r[5],
                'updated_at': r[6],
                'updated_by': r[7],
                'deleted_at': r[8],
                'deleted_by': r[9]
            })
        return lots

    except Exception as e:
        print("❌ Error fetching inventory lots:", e)
        return []
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def update_inventory_lot(lot_id: int, quantity: int = None, expiry_date: str = None,
                        updated_by: str = None):
        
    try:
        conn = get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        
        if quantity is not None:
            updates.append("quantity = %s")
            params.append(quantity)
        if expiry_date is not None:
            updates.append("expiry_date = %s")
            params.append(expiry_date)
            
        updates.append("updated_by = %s")
        params.append(updated_by)
        updates.append("updated_at = NOW()")
        
        if not updates:
            print("⚠️ Nothing to update for lot.")
            return False
            
        params.append(lot_id)
        sql = f"UPDATE Inventory_lots SET {', '.join(updates)} WHERE lot_id = %s AND deleted_at IS NULL"
        cursor.execute(sql, tuple(params))
        conn.commit()
        
        if cursor.rowcount > 0:
            print("✅ Inventory lot updated. Audit trail created.")
            return True
        return False

    except Exception as e:
        print("❌ Error updating inventory lot:", e)
        return False
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# =====================================================
# AUDIT QUERY & REPORTING INTERFACE
# =====================================================

def get_product_audit_history(
    product_id: int = None,
    date_range: Tuple[str, str] = None,
    user: str = None,
    action: str = None
) -> pd.DataFrame:
    """Retrieve audit history for products.
    
    Args:
        product_id: Filter by specific product
        date_range: Tuple of (start_date, end_date) in 'YYYY-MM-DD' format
        user: Filter by username who performed actions
        action: Filter by action type ('INSERT', 'UPDATE', 'DELETE')
    
    Returns:
        DataFrame with audit records
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                audit_id,
                product_id,
                action,
                action_by,
                action_at,
                product_name,
                is_expirable,
                action_at,
                action_by
            FROM Products_audit
            WHERE 1=1
        """
        params = []
        
        if product_id is not None:
            query += " AND product_id = %s"
            params.append(product_id)
            
        if date_range:
            start_date, end_date = date_range
            if start_date:
                query += " AND action_at >= %s"
                params.append(start_date)
            if end_date:
                query += " AND action_at <= %s"
                params.append(end_date + " 23:59:59")
                
        if user:
            query += " AND action_by = %s"
            params.append(user)
            
        if action:
            query += " AND action = %s"
            params.append(action)
            
        query += " ORDER BY action_at DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
            
        columns = ['audit_id', 'product_id', 'action', 'action_by', 'action_at',
                   'product_name', 'is_expirable', 'created_at', 'created_by',
                   'updated_at', 'updated_by', 'deleted_at', 'deleted_by']
        
        df = pd.DataFrame(rows, columns=columns)
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
    date_range: Tuple[str, str] = None,
    user: str = None
) -> pd.DataFrame:
    """Retrieve audit history for inventory lots.
    
    Args:
        lot_id: Filter by specific lot
        product_id: Filter by product ID
        date_range: Tuple of (start_date, end_date)
        user: Filter by username
    
    Returns:
        DataFrame with audit records
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                audit_id,
                lot_id,
                product_id,
                action,
                action_by,
                action_at,
                quantity,
                expiry_date,
                action_at,
                action_by
            FROM Inventory_lots_audit
            WHERE 1=1
        """
        params = []
        
        if lot_id is not None:
            query += " AND lot_id = %s"
            params.append(lot_id)
            
        if product_id is not None:
            query += " AND product_id = %s"
            params.append(product_id)
            
        if date_range:
            start_date, end_date = date_range
            if start_date:
                query += " AND action_at >= %s"
                params.append(start_date)
            if end_date:
                query += " AND action_at <= %s"
                params.append(end_date + " 23:59:59")
                
        if user:
            query += " AND action_by = %s"
            params.append(user)
            
        query += " ORDER BY action_at DESC"
        
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
            
        columns = ['audit_id', 'lot_id', 'product_id', 'action', 'action_by', 'action_at',
                   'quantity', 'expiry_date', 'created_at', 'created_by',
                   'updated_at', 'updated_by', 'deleted_at', 'deleted_by']
        
        df = pd.DataFrame(rows, columns=columns)
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


def get_complete_audit_trail(
    start_date: str = None,
    end_date: str = None,
    user: str = None,
    action: str = None,
    limit: int = 1000
) -> pd.DataFrame:
    """Get unified view of both products and inventory audit trails.
    
    Returns chronological view of all changes.
    """
    try:
        conn = get_connection()
        
        # Build the unified query
        query = """
            SELECT * FROM (
                SELECT 
                    'PRODUCT' as entity_type,
                    audit_id,
                    product_id as entity_id,
                    product_name as entity_name,
                    action,
                    action_by,
                    action_at,
                    NULL as quantity,
                    NULL as expiry_date,
                    is_expirable,
                    action_by,
                    action_at
                FROM Products_audit
                
                UNION ALL
                
                SELECT 
                    'INVENTORY' as entity_type,
                    audit_id,
                    lot_id as entity_id,
                    CONCAT('Lot #', lot_id, ' (Prod: ', product_id, ')') as entity_name,
                    action,
                    action_by,
                    action_at,
                    quantity,
                    expiry_date,
                    NULL as is_expirable,
                    action_by,
                    action_at
                FROM Inventory_lots_audit
            ) combined
            WHERE 1=1
        """
        params = []
        
        if start_date:
            query += " AND action_at >= %s"
            params.append(start_date)
        if end_date:
            query += " AND action_at <= %s"
            params.append(end_date + " 23:59:59")
        if user:
            query += " AND action_by = %s"
            params.append(user)
        if action:
            query += " AND action = %s"
            params.append(action)
            
        query += " ORDER BY action_at DESC LIMIT %s"
        params.append(limit)
        
        df = pd.read_sql(query, conn, params=tuple(params))
        return df
        
    except Exception as e:
        print(f"❌ Error fetching complete audit trail: {e}")
        return pd.DataFrame()
    finally:
        try:
            conn.close()
        except:
            pass


def generate_audit_report(
    start_date: str,
    end_date: str,
    user: str = None,
    export_format: str = 'console'
) -> pd.DataFrame:
    """Generate comprehensive audit report with statistics.
    
    Args:
        start_date: Start date 'YYYY-MM-DD'
        end_date: End date 'YYYY-MM-DD'
        user: Optional user filter
        export_format: 'console', 'csv', or 'excel'
    
    Returns:
        DataFrame with summary statistics
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Summary statistics query
        summary_query = """
            SELECT 
                action_by,
                entity_type,
                action,
                COUNT(*) as count,
                MIN(action_at) as first_action,
                MAX(action_at) as last_action
            FROM (
                SELECT 
                    action_by,
                    'PRODUCT' as entity_type,
                    action,
                    action_at
                FROM Products_audit
                WHERE action_at BETWEEN %s AND %s
                
                UNION ALL
                
                SELECT 
                    action_by,
                    'INVENTORY' as entity_type,
                    action,
                    action_at
                FROM Inventory_lots_audit
                WHERE action_at BETWEEN %s AND %s
            ) combined
            WHERE 1=1
        """
        
        params = [start_date, end_date + " 23:59:59", start_date, end_date + " 23:59:59"]
        
        if user:
            summary_query += " AND action_by = %s"
            params.append(user)
            
        summary_query += " GROUP BY action_by, entity_type, action ORDER BY count DESC"
        
        cursor.execute(summary_query, tuple(params))
        rows = cursor.fetchall()
        
        if not rows:
            print("No audit records found for the specified period.")
            return pd.DataFrame()
        
        columns = ['user', 'entity_type', 'action', 'count', 'first_action', 'last_action']
        df = pd.DataFrame(rows, columns=columns)
        
        # Calculate additional metrics
        total_actions = df['count'].sum()
        unique_users = df['user'].nunique()
        
        print(f"\\n📊 AUDIT REPORT: {start_date} to {end_date}")
        print(f"   Total Actions: {total_actions}")
        print(f"   Unique Users: {unique_users}")
        print(f"   Period: {df['first_action'].min()} to {df['last_action'].max()}")
        print("\\n" + "="*60)
        
        # Display breakdown
        pivot = df.pivot_table(
            index='user',
            columns=['entity_type', 'action'],
            values='count',
            aggfunc='sum',
            fill_value=0
        )
        print("\\nBreakdown by User:")
        print(pivot)
        
        # Export if requested
        if export_format == 'csv':
            filename = f"audit_report_{start_date}_{end_date}.csv"
            df.to_csv(filename, index=False)
            print(f"\\n💾 Report exported to: {filename}")
        elif export_format == 'excel':
            filename = f"audit_report_{start_date}_{end_date}.xlsx"
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Add detailed sheets
                products_df = get_product_audit_history(date_range=(start_date, end_date))
                if not products_df.empty:
                    products_df.to_excel(writer, sheet_name='Product_Details', index=False)
                    
                inventory_df = get_inventory_audit_history(date_range=(start_date, end_date))
                if not inventory_df.empty:
                    inventory_df.to_excel(writer, sheet_name='Inventory_Details', index=False)
                    
            print(f"\\n💾 Report exported to: {filename}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error generating audit report: {e}")
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


def detect_suspicious_activity(
    days_back: int = 7,
    after_hours_threshold: int = 22,
    before_hours_threshold: int = 6,
    mass_action_threshold: int = 10
) -> pd.DataFrame:
    """Detect suspicious patterns in audit trail.
    
    Flags:
    - After-hours activity (before 6 AM or after 10 PM)
    - Mass deletions (>10 deletes in an hour)
    - Rapid successive changes
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        query = """
            SELECT 
                action_by,
                DATE(action_at) as action_date,
                HOUR(action_at) as action_hour,
                action,
                entity_type,
                COUNT(*) as action_count,
                GROUP_CONCAT(DISTINCT entity_id) as affected_ids
            FROM (
                SELECT 
                    action_by,
                    action_at,
                    action,
                    'PRODUCT' as entity_type,
                    CAST(product_id AS CHAR) as entity_id
                FROM Products_audit
                WHERE action_at >= %s
                
                UNION ALL
                
                SELECT 
                    action_by,
                    action_at,
                    action,
                    'INVENTORY' as entity_type,
                    CAST(lot_id AS CHAR) as entity_id
                FROM Inventory_lots_audit
                WHERE action_at >= %s
            ) combined
            GROUP BY action_by, DATE(action_at), HOUR(action_at), action, entity_type
            HAVING 
                COUNT(*) >= %s 
                OR HOUR(action_at) >= %s 
                OR HOUR(action_at) <= %s
            ORDER BY action_count DESC, action_date DESC
        """
        
        cursor.execute(query, (
            start_date, start_date,
            mass_action_threshold,
            after_hours_threshold,
            before_hours_threshold
        ))
        
        rows = cursor.fetchall()
        
        if not rows:
            print("✅ No suspicious activity detected in the last {} days.".format(days_back))
            return pd.DataFrame()
        
        # Add alert classification
        alerts = []
        for row in rows:
            alert_type = []
            if row[2] >= after_hours_threshold or row[2] <= before_hours_threshold:
                alert_type.append("AFTER_HOURS")
            if row[5] >= mass_action_threshold:
                alert_type.append("MASS_ACTION")
            
            alerts.append({
                'user': row[0],
                'date': row[1],
                'hour': row[2],
                'action': row[3],
                'entity_type': row[4],
                'count': row[5],
                'affected_ids': row[6][:100] + "..." if len(row[6]) > 100 else row[6],
                'alert_type': " + ".join(alert_type)
            })
        
        df = pd.DataFrame(alerts)
        
        print(f"\\n🚨 SUSPICIOUS ACTIVITY DETECTED (Last {days_back} days)")
        print("="*80)
        print(df.to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"❌ Error detecting suspicious activity: {e}")
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


def get_product_lifecycle(product_id: int) -> Dict:
    """Get complete lifecycle information for a product including all changes."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get current state
        cursor.execute("""
            SELECT product_id, product_name, is_expirable, created_at, created_by,
                   updated_at, updated_by, deleted_at, deleted_by
            FROM Products WHERE product_id = %s
        """, (product_id,))
        
        current = cursor.fetchone()
        if not current:
            return {"error": "Product not found"}
        
        # Get audit history
        audit_df = get_product_audit_history(product_id=product_id)
        
        # Get inventory lots history
        inventory_df = get_inventory_audit_history(product_id=product_id)
        
        # Calculate statistics
        total_changes = len(audit_df)
        last_modified = audit_df['action_at'].max() if not audit_df.empty else current[3]
        last_modified_by = audit_df[audit_df['action_at'] == last_modified]['action_by'].iloc[0] if not audit_df.empty else current[4]
        
        # Check for deletions
        deletion_record = audit_df[audit_df['action'] == 'DELETE'] if not audit_df.empty else pd.DataFrame()
        
        lifecycle = {
            'product_id': current[0],
            'product_name': current[1],
            'is_expirable': current[2],
            'created_at': current[3],
            'created_by': current[4],
            'last_modified_at': last_modified,
            'last_modified_by': last_modified_by,
            'status': 'DELETED' if current[7] else 'ACTIVE',
            'deleted_at': current[7],
            'deleted_by': current[8],
            'total_changes': total_changes,
            'inventory_lots_count': len(inventory_df['lot_id'].unique()) if not inventory_df.empty else 0,
            'audit_history': audit_df,
            'inventory_history': inventory_df
        }
        
        # Print summary
        print(f"\\n📦 PRODUCT LIFECYCLE: {current[1]} (ID: {product_id})")
        print("="*60)
        print(f"Status: {'🔴 DELETED' if current[7] else '🟢 ACTIVE'}")
        print(f"Created: {current[3]} by {current[4]}")
        print(f"Last Modified: {last_modified} by {last_modified_by}")
        print(f"Total Changes: {total_changes}")
        if current[7]:
            print(f"Deleted: {current[7]} by {current[8]}")
        print("\\n📋 Complete Audit Trail:")
        if not audit_df.empty:
            print(audit_df[['action', 'action_by', 'action_at', 'product_name']].to_string(index=False))
        
        return lifecycle
        
    except Exception as e:
        print(f"❌ Error getting product lifecycle: {e}")
        return {"error": str(e)}
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
# FILTERING FUNCTIONS (Original)
# =====================================================

def get_user_filters():
    """Prompt user for product filters (keeps same style as Purchase.py)."""
    print("\\n=== Product Data Filters ===")
    product_name = input("Enter product name (or 'all'): ").strip()
    if product_name.lower() == 'all':
        product_name = None

    expiry_choice = input("Filter by expiry? (yes/no/all): ").strip().lower()
    if expiry_choice not in ('yes', 'no', 'all'):
        expiry_choice = 'all'

    start_date = None
    end_date = None
    if expiry_choice == 'yes':
        start_date = input("Enter start expiry date (YYYY-MM-DD) or 'all': ").strip()
        if start_date.lower() == 'all':
            start_date = None
        end_date = input("Enter end expiry date (YYYY-MM-DD) or 'all': ").strip()
        if end_date.lower() == 'all':
            end_date = None

    stock_filter = input("Stock filter (in/out/all): ").strip().lower()
    if stock_filter not in ('in', 'out', 'all'):
        stock_filter = 'all'

    min_q = None
    max_q = None
    if stock_filter == 'in':
        q_choice = input("Filter by quantity range? (yes/no): ").strip().lower()
        if q_choice == 'yes':
            min_q = input("Min quantity or 'all': ").strip()
            if min_q.lower() == 'all':
                min_q = None
            else:
                try:
                    min_q = int(min_q)
                except ValueError:
                    min_q = None
            max_q = input("Max quantity or 'all': ").strip()
            if max_q.lower() == 'all':
                max_q = None
            else:
                try:
                    max_q = int(max_q)
                except ValueError:
                    max_q = None

    return {
        'product_name': product_name,
        'expiry_choice': expiry_choice,
        'start_date': start_date,
        'end_date': end_date,
        'stock_filter': stock_filter,
        'min_q': min_q,
        'max_q': max_q
    }


def fetch_filtered_products(filters: dict):
    """Fetch products joined with inventory lots according to filters. Returns a pandas DataFrame."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                pr.product_id,
                pr.product_name,
                pr.is_expirable,
                il.lot_id,
                il.quantity,
                il.expiry_date,
                pr.created_at,
                pr.created_by,
                pr.updated_at,
                pr.updated_by
            FROM Products pr
            LEFT JOIN Inventory_lots il ON pr.product_id = il.product_id AND il.deleted_at IS NULL
            WHERE pr.deleted_at IS NULL
        """
        params = []

        if filters.get('product_name'):
            query += " AND pr.product_name LIKE %s"
            params.append(f"%{filters['product_name']}%")

        if filters.get('expiry_choice') == 'yes':
            if filters.get('start_date'):
                query += " AND il.expiry_date >= %s"
                params.append(filters['start_date'])
            if filters.get('end_date'):
                query += " AND il.expiry_date <= %s"
                params.append(filters['end_date'])

        # Stock filters
        if filters.get('stock_filter') == 'in':
            query += " AND COALESCE(il.quantity, 0) > 0"
            if filters.get('min_q') is not None:
                query += " AND il.quantity >= %s"
                params.append(filters['min_q'])
            if filters.get('max_q') is not None:
                query += " AND il.quantity <= %s"
                params.append(filters['max_q'])
        elif filters.get('stock_filter') == 'out':
            query += " AND (il.quantity IS NULL OR il.quantity = 0)"

        query += " ORDER BY pr.product_name, il.expiry_date"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        if not rows:
            print("⚠️ No products match the specified criteria.")
            return pd.DataFrame()

        columns = ['product_id', 'product_name', 'is_expirable', 'lot_id', 
                   'quantity', 'expiry_date', 'created_at', 'created_by',
                   'updated_at', 'updated_by']
        df = pd.DataFrame(rows, columns=columns)
        
        # Add "last modified" column for transparency
        df['last_modified'] = df['updated_at'].fillna(df['created_at'])
        df['last_modified_by'] = df['updated_by'].fillna(df['created_by'])
        
        return df

    except Exception as e:
        print("❌ Error fetching products:", e)
        return pd.DataFrame()
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# =====================================================
# ENHANCED MENU WITH AUDIT OPTIONS
# =====================================================

def audit_menu():
    """Interactive audit menu for compliance and reporting."""
    while True:
        print("\\n" + "="*60)
        print("🔍 AUDIT & COMPLIANCE MENU")
        print("="*60)
        print("1. View Product Audit History")
        print("2. View Inventory Audit History")
        print("3. View Complete Audit Trail (Unified)")
        print("4. Generate Audit Report")
        print("5. Detect Suspicious Activity")
        print("6. View Product Lifecycle")
        print("7. Export Audit Data")
        print("8. Back to Main Menu")
        
        choice = input("\\nSelect an option: ").strip()
        
        if choice == '1':
            print("\\n--- Product Audit History ---")
            pid = input("Product ID (or \'all\'): ").strip()
            user = input("Filter by user (or \'all\'): ").strip()
            start = input("Start date (YYYY-MM-DD) or \'all\': ").strip()
            end = input("End date (YYYY-MM-DD) or \'all\': ").strip()
            
            pid = int(pid) if pid.isdigit() else None
            user = user if user != 'all' else None
            date_range = (start, end) if start != 'all' and end != 'all' else None
            
            df = get_product_audit_history(product_id=pid, user=user, date_range=date_range)
            if not df.empty:
                print(f"\\nFound {len(df)} records:")
                print(df.to_string(index=False))
            else:
                print("No records found.")
                
        elif choice == '2':
            print("\\n--- Inventory Audit History ---")
            lid = input("Lot ID (or \'all\'): ").strip()
            pid = input("Product ID (or \'all\'): ").strip()
            
            lid = int(lid) if lid.isdigit() else None
            pid = int(pid) if pid.isdigit() else None
            
            df = get_inventory_audit_history(lot_id=lid, product_id=pid)
            if not df.empty:
                print(f"\\nFound {len(df)} records:")
                print(df.to_string(index=False))
            else:
                print("No records found.")
                
        elif choice == '3':
            print("\\n--- Complete Audit Trail ---")
            limit = input("Number of records (default 100): ").strip()
            limit = int(limit) if limit.isdigit() else 100
            
            df = get_complete_audit_trail(limit=limit)
            if not df.empty:
                print(f"\\nShowing {len(df)} records:")
                print(df.to_string(index=False))
            else:
                print("No records found.")
                
        elif choice == '4':
            print("\\n--- Generate Audit Report ---")
            start = input("Start date (YYYY-MM-DD): ").strip()
            end = input("End date (YYYY-MM-DD): ").strip()
            user = input("Filter by user (or \'all\'): ").strip()
            fmt = input("Export format (console/csv/excel): ").strip().lower()
            
            user = user if user != 'all' else None
            if fmt not in ['console', 'csv', 'excel']:
                fmt = 'console'
                
            generate_audit_report(start, end, user=user, export_format=fmt)
            
        elif choice == '5':
            print("\\n--- Suspicious Activity Detection ---")
            days = input("Days to analyze (default 7): ").strip()
            days = int(days) if days.isdigit() else 7
            detect_suspicious_activity(days_back=days)
            
        elif choice == '6':
            print("\\n--- Product Lifecycle ---")
            pid = input("Product ID: ").strip()
            if pid.isdigit():
                get_product_lifecycle(int(pid))
            else:
                print("Invalid Product ID.")
                
        elif choice == '7':
            print("\\n--- Export Audit Data ---")
            start = input("Start date (YYYY-MM-DD): ").strip()
            end = input("End date (YYYY-MM-DD): ").strip()
            fmt = input("Format (csv/excel): ").strip().lower()
            
            if fmt == 'csv':
                df = get_complete_audit_trail(start_date=start, end_date=end)
                if not df.empty:
                    filename = f"audit_export_{start}_to_{end}.csv"
                    df.to_csv(filename, index=False)
                    print(f"✅ Exported to {filename}")
            elif fmt == 'excel':
                generate_audit_report(start, end, export_format='excel')
            else:
                print("Invalid format.")
                
        elif choice == '8':
            break
        else:
            print("⚠️ Invalid choice.")


def products_menu():
    """Interactive products menu with audit integration."""
    while True:
        print("\\n" + "="*60)
        print("PRODUCTS & INVENTORY MENU")
        print("="*60)
        print("1. Add Product")
        print("2. Add Inventory Lot")
        print("3. List / Filter Products")
        print("4. Update Product")
        print("5. Delete Product")
        print("6. Update Inventory Lot")
        print("7. Audit & Compliance (🔒 Admin)")
        print("8. Exit")
        
        choice = input("\\nSelect an option: ").strip()
        
        if choice == '1':
            name = input("Product name: ").strip()
            exp = input("Is expirable? (yes/no): ").strip().lower() == 'yes'
            action_by = input("Who is performing this action").strip().lower()
            add_product(name, exp, action_by)
            
        elif choice == '2':
            try:

                conn = get_connection()
                cursor = conn.cursor()

                name = int(input("Product name: ").strip())
                qty = int(input("Quantity: ").strip())
                action_by = input("Who is performing this action").strip().lower()

                # GEtting the value of product id by giving product name
                product_id = cursor.execute("SELECT product_id FROM Products WHERE product_name = %s",name)
                result = cursor.fetchone()
                if not result:
                    print("⚠️ Product not found.")
                    continue
                product_id = result[0]
                
                # Check if product is expirable
                prod = get_product(product_id)
                expiry = None
                if prod and prod.get('is_expirable'):
                    expiry = input("Expiry date (YYYY-MM-DD): ").strip() or None
                    
                add_inventory_lot(product_id, qty, expiry)
            except ValueError:
                print("⚠️ Invalid numeric input.")
                
        elif choice == '3':
            filters = get_user_filters()
            df = fetch_filtered_products(filters)
            if df is not None and not df.empty:
                # Display with last modified info
                display_cols = ['product_id', 'product_name', 'is_expirable', 
                               'quantity', 'expiry_date', 'last_modified', 'last_modified_by']
                print(df[display_cols].to_string(index=False))
            else:
                print("No products found.")
                
        elif choice == '4':
            try:
                product_id = int(input("Product ID to update: ").strip())
                action_by = input("Who is performing this action").strip().lower()
                print("\\nCurrent product:")
                current = get_product(product_id, include_audit_info=True)
                if current:
                    print(f"Name: {current['product_name']}, Expirable: {current['is_expirable']}")
                    new_name = input("New name (leave blank to keep): ").strip() or None
                    new_exp = input("Is expirable? (yes/no/leave blank): ").strip().lower()
                    new_exp_bool = None
                    if new_exp == 'yes':
                        new_exp_bool = True
                    elif new_exp == 'no':
                        new_exp_bool = False
                    update_product(product_id, new_name, new_exp_bool)
                else:
                    print("Product not found.")
            except ValueError:
                print("⚠️ Invalid product id.")
                
        elif choice == '5':
            try:
                product_name = input("Product name to delete: ").strip()
                action_by = input("Who is performing this action").strip().lower()
                confirm = input(f"Delete product {product_name}? This will remove inventory lots too (y/n): ").strip().lower()
                delete_product(product_name, action_by)
            except ValueError:
                print("⚠️ Invalid product name.")
                
        elif choice == '6':
            try:
                lid = int(input("Lot ID to update: ").strip())
                qty_input = input("New quantity (leave blank to keep): ").strip()
                qty = int(qty_input) if qty_input else None
                expiry = input("New expiry date (leave blank to keep): ").strip() or None
                action_by = input("Who is performing this action").strip().lower()
                if expiry == '':
                    expiry = None
                update_inventory_lot(lid, qty, expiry)
            except ValueError:
                print("⚠️ Invalid input.")
                
        elif choice == '7':
            audit_menu()
            
        elif choice == '8':
            print("Goodbye!")
            break
        else:
            print("⚠️ Invalid choice. Please select a valid option.")


if __name__ == '__main__':
    products_menu()

print("Generated enhanced Products.py with audit functionality")
print(f"Length: {len(enhanced_products_py)} characters")

# Save to file
with open('/mnt/kimi/output/Products_Enhanced.py', 'w') as f:
    f.write(enhanced_products_py)

print("✅ Enhanced Products.py saved to /mnt/kimi/output/Products_Enhanced.py")
