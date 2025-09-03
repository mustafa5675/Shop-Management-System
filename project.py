import pymysql
import csv
import pandas as pd
import matplotlib.pyplot as plt
import datetime 

# Create a database connection
connection = pymysql.connect(
    host="localhost",
    user="root",
    password="hello",
    database="Shop_management"
)
cursor=connection.cursor()

# Start recording sales
def record_sales():
    # Take input from user
    sale_date = input("Enter Sale Date (YYYY-MM-DD): ")
    customer_id = int(input("Enter Customer ID: "))
    product_id = int(input("Enter Product ID: "))
    quantity = int(input("Enter Quantity Sold: "))
    unit_price = float(input("Enter Unit Price: "))
    payment_method = input("Enter Payment Method (cash/card/online): ")

# Save to list (backup in Python memory)
    sales_data = []
    sale = {
        "SaleDate": sale_date,
        "CustomerID": customer_id,
        "ProductID": product_id,
        "Quantity": quantity,
        "UnitPrice": unit_price,
        "PaymentMethod": payment_method
    }
    sales_data.append(sale)

#Insert into SQL table
    sql = """
        INSERT INTO Sales (SaleDate, CustomerID, ProductID, Quantity, UnitPrice, PaymentMethod)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    values = (sale_date, customer_id, product_id, quantity, unit_price, payment_method)

    cursor.execute(sql, values)
    connection.commit()
    print("Sale inserted successfully into database.")

#Also write backup into CSV
    with open("sales_backup.csv", mode="a", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=sale.keys())
        if file.tell() == 0:  # if file is empty, write header
            writer.writeheader()
        writer.writerow(sale)

    print("Backup written into sales_backup.csv")

def view_sales():
    try:
        # 1. Fetch all sales
        cursor.execute("SELECT * FROM Sales")
        rows = cursor.fetchall()

        if not rows:
            print("No sales records found.")
            return

        # 2. Convert to Pandas DataFrame
        df = pd.DataFrame(rows)

        # 3. Display neatly
        print("\n--- Sales Records (Pandas Table) ---")
        print(df.to_string(index=False))  # no index for cleaner display

        # 4. Export backup CSV
        df.to_csv("sales_view_backup.csv", index=False)
        print("\nSales records exported to sales_view_backup.csv")

        # 5. Sales Analysis Graphs
        # Weekly sales trend
        weekly = df.resample('W', on='SaleDate')['TotalAmount'].sum()
        monthly = df.resample('M', on='SaleDate')['TotalAmount'].sum()
        yearly = df.resample('Y', on='SaleDate')['TotalAmount'].sum()

        # Plot graphs
        plt.figure(figsize=(14, 6))

        plt.subplot(1, 3, 1)
        weekly.plot(kind='bar')
        plt.title("Weekly Sales Trend")
        plt.ylabel("Total Sales")

        plt.subplot(1, 3, 2)
        monthly.plot(kind='bar', color='orange')
        plt.title("Monthly Sales Trend")

        plt.subplot(1, 3, 3)
        yearly.plot(kind='bar', color='green')
        plt.title("Yearly Sales Trend")

        plt.tight_layout()
        plt.show()

        return df  # Return dataframe if needed

    except Exception as e:
        print("❌ Error fetching sales:", e)





    

