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

        # 5. Add graphs (Monthly & Yearly Analysis)
        # Convert SaleDate to datetime
        df['SaleDate'] = pd.to_datetime(df['SaleDate'])

        # Monthly Sales (group by Year-Month)
        df['YearMonth'] = df['SaleDate'].dt.to_period('M')
        monthly_sales = df.groupby('YearMonth')['TotalAmount'].sum()

        # Yearly Sales (group by Year)
        df['Year'] = df['SaleDate'].dt.year
        yearly_sales = df.groupby('Year')['TotalAmount'].sum()

        # --- Plot Graphs ---
        plt.figure(figsize=(12, 5))

        # Monthly Sales Graph
        plt.subplot(1, 2, 1)
        monthly_sales.plot(kind='bar', color='skyblue')
        plt.title("Monthly Sales")
        plt.xlabel("Month")
        plt.ylabel("Total Sales")

        # Yearly Sales Graph
        plt.subplot(1, 2, 2)
        yearly_sales.plot(kind='bar', color='lightgreen')
        plt.title("Yearly Sales")
        plt.xlabel("Year")
        plt.ylabel("Total Sales")

        plt.tight_layout()
        plt.show()

        return df  # Return dataframe if needed

    except Exception as e:
        print("❌ Error fetching sales:", e)





    
