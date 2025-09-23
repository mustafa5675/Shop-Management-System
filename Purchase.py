import pandas as pd
import matplotlib.pyplot as plt
import datetime 
import csv
from Database import get_connection

purchase_cache = []  # in-memory backup 

def record_purchases():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input
        purchase_date = now.strftime("%Y-%m-%d")
        quantity = int(input("Enter Quantity Sold: "))
        unit_price = float(input("Enter Unit Price: "))
        Due_date = purchase_date + timedelta(days = credit_period_days)
        payment_method = input("Enter Payment Method (cash/card/online): ").strip().lower()

        # Validation
        if quantity <= 0 or unit_price <= 0:
            print("❌ Quantity and Unit Price must be positive.")
            return

        # Prepare data
        purchase = {
            "PurchaseDate": purchase_date,
            "Quantity": quantity,
            "UnitPrice": unit_price,
            "CreditPeriodDays": update_credit_period(credit_period_days),
            "DueDate":Due_date,
            "PaymentMethod": payment_method
        }
        purchase_cache.append(purchase)

        # Insert into DB
        sql = """
            INSERT INTO Sales (PurchaseDate, ProductID, Quantity, UnitPrice, CreditPeriodDays, PaymentMethod)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, tuple(purchase.values()))
        conn.commit()

        print("✅ Purchase inserted into database.")

        # Backup CSV
        with open("purchases_backup.csv", mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=purchase.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(purchase)

        print("💾 Backup written into purchases_backup.csv")

    except Exception as e:
        print("❌ Error recording sale:", e)
    finally:
        cursor.close()
        conn.close()

def get_user_filters():
    """Get filtering criteria from user"""
    print("\n=== Purchase Data Filters ===")
    
    # Vendor filter
    print("1. Vendor Filter:")
    vendor_filter = input("Enter Vendor Name (or part of it) or 'all' for all vendors: ").strip()
    if vendor_filter.lower() == 'all':
        vendor_filter = None
    
    # Date range filter
    print("\n2. Date Range Filter:")
    start_date = input("Enter Start Date (YYYY-MM-DD) or 'all' for no start limit: ").strip()
    if start_date.lower() == 'all':
        start_date = None
    
    end_date = input("Enter End Date (YYYY-MM-DD) or 'all' for no end limit: ").strip()
    if end_date.lower() == 'all':
        end_date = None
    
    # Payment status filter
    print("\n3. Payment Status Filter:")
    payment_status = input("Enter Payment Status (paid/unpaid) or 'all' for both: ").strip().lower()
    if payment_status == 'all':
        payment_status = None
    
    # Amount filter
    print("\n4. Amount Filter:")
    max_amount = input("Enter Maximum Bill Amount (bills under this amount) or 'all' for no limit: ").strip()
    if max_amount.lower() == 'all':
        max_amount = None
    else:
        try:
            max_amount = float(max_amount)
        except ValueError:
            print("❌ Invalid amount format. Using no limit.")
            max_amount = None
    
    return {
        'vendor_filter': vendor_filter,
        'start_date': start_date,
        'end_date': end_date,
        'payment_status': payment_status,
        'max_amount': max_amount
    }