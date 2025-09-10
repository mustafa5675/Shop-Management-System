# sales.py
import pandas as pd
import matplotlib.pyplot as plt
import datetime 
import csv
from Database import get_connection

sales_cache = []  # in-memory backup

def record_sales():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input
        sale_date = input("Enter Sale Date (YYYY-MM-DD): ").strip()
        customer_id = int(input("Enter Customer ID: "))
        product_id = int(input("Enter Product ID: "))
        quantity = int(input("Enter Quantity Sold: "))
        unit_price = float(input("Enter Unit Price: "))
        payment_method = input("Enter Payment Method (cash/card/online): ").strip().lower()

        # Validation
        if quantity <= 0 or unit_price <= 0:
            print("❌ Quantity and Unit Price must be positive.")
            return

        # Prepare data
        sale = {
            "SaleDate": sale_date,
            "CustomerID": customer_id,
            "ProductID": product_id,
            "Quantity": quantity,
            "UnitPrice": unit_price,
            "PaymentMethod": payment_method
        }
        sales_cache.append(sale)

        # Insert into DB
        sql = """
            INSERT INTO Sales (SaleDate, CustomerID, ProductID, Quantity, UnitPrice, PaymentMethod)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, tuple(sale.values()))
        conn.commit()

        print("✅ Sale inserted into database.")

        # Backup CSV
        with open("sales_backup.csv", mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sale.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(sale)

        print("💾 Backup written into sales_backup.csv")

    except Exception as e:
        print("❌ Error recording sale:", e)
    finally:
        cursor.close()
        conn.close()

# View sales with options for timeline and form of data
def view_sales(form_of_data="tabular", timeline="monthly"):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Fetch all sales
        cursor.execute("SELECT SaleID, SaleDate, CustomerID, ProductID, Quantity, UnitPrice, TotalAmount, PaymentMethod FROM Sales")
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No sales records found.")
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


def run_sales_viewer():
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

def sales_menu():
    print("\n--- Sales Menu ---")
    print("1. Record Sales")
    print("2. View Sales")

    while True:
        if choice == "1":
            record_sales()
        elif choice == "2":
            run_sales_viewer()
        else:
            print("❌ Invalid option.")