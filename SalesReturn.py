import csv
from Database import get_connection
import pandas as pd
import matplotlib.pyplot as plt
import datetime 

sales_return_cache = []  # in-memory backup

def record_sales_return():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input
        sale_id = int(input("Enter Sale ID being returned: "))
        customer_id = int(input("Enter Customer ID: "))
        product_id = int(input("Enter Product ID: "))
        employee_id = int(input("Enter Employee ID (who processed return): "))
        quantity_returned = int(input("Enter Quantity Returned: "))
        refund_amount = float(input("Enter Refund Amount: "))
        reason = input("Enter Reason for Return: ").strip()

        # Validation
        if quantity_returned <= 0 or refund_amount < 0:
            print("❌ Quantity must be > 0 and Refund Amount must be >= 0.")
            return

        sale_return = {
            "SaleID": sale_id,
            "CustomerID": customer_id,
            "ProductID": product_id,
            "EmployeeID": employee_id,
            "QuantityReturned": quantity_returned,
            "RefundAmount": refund_amount,
            "Reason": reason
        }
        sales_return_cache.append(sale_return)

        # Insert into DB
        sql = """
            INSERT INTO SalesReturn (SaleID, CustomerID, ProductID, EmployeeID, QuantityReturned, RefundAmount, Reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, tuple(sale_return.values()))
        conn.commit()

        print("✅ Sales Return recorded in database.")

        # Backup CSV
        with open("sales_return_backup.csv", mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=sale_return.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(sale_return)

        print("💾 Backup written into sales_return_backup.csv")

    except Exception as e:
        print("❌ Error recording sales return:", e)
    finally:
        cursor.close()
        conn.close()

import pandas as pd
import matplotlib.pyplot as plt

def view_sales_return(form_of_data="tabular", timeline="monthly"):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ReturnID, ReturnDate, SaleID, CustomerID, ProductID, EmployeeID, QuantityReturned, RefundAmount, Reason, Status
            FROM SalesReturn
        """)
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No sales return records found.")
            return None

        df = pd.DataFrame(rows)
        df['ReturnDate'] = pd.to_datetime(df['ReturnDate'])
        df.set_index('ReturnDate', inplace=True)

        # Grouping by timeline
        if timeline == "weekly":
            grouped = df.resample('W')['RefundAmount'].sum()
        elif timeline == "yearly":
            grouped = df.resample('Y')['RefundAmount'].sum()
        else:  # monthly default
            grouped = df.resample('M')['RefundAmount'].sum()

        # Display
        if form_of_data == "tabular":
            return grouped.to_frame()
        elif form_of_data == "line":
            grouped.plot(kind='line', marker='o')
            plt.title(f"Sales Returns Summary ({timeline.capitalize()})")
            plt.ylabel("Total Refund Amount")
            plt.xlabel(timeline.capitalize())
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.show()
            return grouped
        elif form_of_data == "bar":
            grouped.plot(kind='bar')
            plt.title(f"Sales Returns Summary ({timeline.capitalize()})")
            plt.ylabel("Total Refund Amount")
            plt.xlabel(timeline.capitalize())
            plt.grid(True, linestyle="--", alpha=0.6)
            plt.show()
            return grouped
        else:
            print("❌ Invalid input. Choose: tabular, line, bar")
            return None

    except Exception as e:
        print("❌ Error viewing sales returns:", e)
        return None
    finally:
        cursor.close()
        conn.close()


def run_sales_return_viewer():
    valid_forms = ("tabular", "line", "bar")
    valid_timelines = ("weekly", "monthly", "yearly")

    print("\nChoose display type for Sales Returns: [tabular / line / bar]")
    form_of_data = input("Enter option: ").strip().lower()

    print("Choose timeline: [weekly / monthly / yearly]")
    timeline = input("Enter option: ").strip().lower()

    if form_of_data not in valid_forms or timeline not in valid_timelines:
        print("❌ Invalid input. Please try again.")
        return

    result = view_sales_return(form_of_data=form_of_data, timeline=timeline)

    if result is not None and form_of_data == "tabular":
        print(f"\n--- Sales Returns Summary ({timeline.capitalize()}) ---")
        print(result)
        print("\n✅ Sales return viewer ran successfully.")

def sales_return_menu():
    print("\n--- Sales Return Menu ---")
    print("1. Record Sales Return")
    print("2. View Sales Return")

    while True:
        if choice == "1":
            record_sales_return()
        elif choice == "2":
            run_sales_return_viewer()
        else:
            print("❌ Invalid option.")