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

# View purchases with options for timeline and form of data
def view_purchases(form_of_data="tabular", timeline="monthly"):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        #!. Fetch purchases linked with vendors, due dates and due amounts 
        vendor_name = input("Enter Vendor Name (or part of it) or enter all for all of them: ").strip()
        due_date = input("Enter Due Date (YYYY-MM-DD) of bills you want to be printed or enter all for all of them: ").strip()
        due_amount = input("Enter Amount of Bills you want to be printed or for all of them: ").strip()

        query = """
            SELECT p.PurchaseID, p.PurchaseDate, p.ProductID, p.Quantity, p.TotalAmount, v.VendorName
            FROM Purchases p
            JOIN Vendors v ON p.VendorID = v.VendorID
            WHERE v.VendorName LIKE %s
        """
        cursor.execute(query, (f"%{vendor_name}%",))
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No purchases records found.")
            return None

        

        # 2. Load into Pandas for analysis
        df = pd.DataFrame(rows)

        # Ensure SaleDate is datetime for resampling
        df['SaleDate'] = pd.to_datetime(df['SaleDate'])
        df.set_index('SaleDate', inplace=True)

        # 3. Group by timeline
        if timeline == "weekly":
            grouped = df.resample('W')['TotalAmount'].sum()
        elif timeline == "yearly":
            grouped = df.resample('Y')['TotalAmount'].sum()
        else:  # monthly default
            grouped = df.resample('M')['TotalAmount'].sum()

        # 4. Output choice
        if form_of_data == "tabular":
            return grouped.to_frame()
        elif form_of_data == "line":
            grouped.plot(kind='line', marker='o')
            plt.title(f"Sales Summary ({timeline.capitalize()})")
            plt.ylabel("Total Sales Amount")
            plt.xlabel(timeline.capitalize())
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.show()
            return grouped
        elif form_of_data == "bar":
            grouped.plot(kind='bar')
            plt.title(f"Sales Summary ({timeline.capitalize()})")
            plt.ylabel("Total Sales Amount")
            plt.xlabel(timeline.capitalize())
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.show()
            return grouped
        else:
            print("❌ Invalid input. Choose: tabular, line, bar")
            return None

    except Exception as e:
        print("❌ Error fetching sales:", e)
        return None
    finally:
        cursor.close()
        conn.close()

def run_purchases_viewer():
    valid_forms = ("tabular", "line", "bar")
    valid_timelines = ("weekly", "monthly", "yearly")

    print("\nChoose display type: [tabular / line / bar]")
    form_of_data = input("Enter option: ").strip().lower()

    print("Choose timeline: [weekly / monthly / yearly]")
    timeline = input("Enter option: ").strip().lower()

    if form_of_data not in valid_forms or timeline not in valid_timelines:
        print("❌ Invalid input. Please try again.")
        return
    
    result = view_sales(form_of_data=form_of_data, timeline=timeline)
            
    if result is not None and form_of_data == "tabular":
        print(f"\n--- Sales Summary ({timeline.capitalize()}) ---")
        print(result)

        print("\n✅ Sales viewer ran successfully.")

def update_credit_period():
    vendor_id = int(input("Enter Vendor ID To Be Updated: "))
    credit_period_days = int(input("Enter Credit Period: "))
    product_id = int(input("Enter Product ID To Be Updated: "))

def purchases_menu():
    print("\n--- Purchases Menu ---")
    print("1. Record Purchases")
    print("2. View Purchases")
    print("3. Update Credit Period")
    print("4. Back to Main Menu")

    while True:
        choice = input("Enter option: ").strip()
        if choice == "1":
            record_purchases()
        elif choice == "2":
            run_purchases_viewer()
        elif choice == "3":
            update_credit_period()
        elif choice == "4":
            break
        else:
            print("❌ Invalid option.")
