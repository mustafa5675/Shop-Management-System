import csv
from datetime import datetime
from Database import get_connection
import pandas as pd

customer_cache = [] # in-memory backup

def add_customer():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input
        customer_name = input("Enter Customer Name: ").strip().capitalize()
        email = input("Enter Email: ").strip()
        phone = int(input("Enter Phone Number: "))
        address = input("Enter Address: ").strip().capitalize()
        city = input("Enter City: ").strip().capitalize()
        state = input("Enter State: ").strip().capitalize()
        postal_code = int(input("Enter Postal Code: "))
        country = input("Enter Country: ").strip().capitalize()
        registration_date = datetime.now()

       # Quick validations
        if not customer_name:
            print("❌ First name is required.")
            return
        if "@" not in email:
            print("❌ Invalid email address.")
            return 

        customer = {
            "Customer_Name": customer_name,
            "Email": email,
            "Phone_No": phone,
            "Address": address,
            "City": city,
            "State": state,
            "Postal_Code": postal_code,
            "Country": country,
        }
        customer_cache.append(customer)

        # Insert into DB
        sql = """
            INSERT INTO Customers
            (Customer_Name, Email, Phone_No, Address, City, State, Postal_Code, Country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, tuple(customer.values()))
        conn.commit()

        print("✅ Customer added to database.")

        # Backup CSV
        with open("customers_backup.csv", mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=customer.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(customer)

        print("💾 Backup written into customers_backup.csv")

    except Exception as e:
        print("Error adding customer:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def view_customers():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Customers")
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No customers found.")
            return None

        df = pd.DataFrame(rows)
        print("\n--- Customer Records ---")
        print(df.to_string(index=False))
        return df

    except Exception as e:
        print("âŒ Error viewing customers:", e)
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def search_customer(keyword):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        query = """
            SELECT * FROM Customers
            WHERE FirstName LIKE %s OR LastName LIKE %s OR Email LIKE %s OR PhoneNumber LIKE %s
        """
        like_kw = f"%{keyword}%"
        cursor.execute(query, (like_kw, like_kw, like_kw, like_kw))
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No matching customers found.")
            return None

        df = pd.DataFrame(rows)
        print("\n--- Search Results ---")
        print(df.to_string(index=False))
        return df

    except Exception as e:
        print("âŒ Error searching customers:", e)
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def delete_customer(customer_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check if customer has sales
        cursor.execute("SELECT COUNT(*) AS cnt FROM Sales WHERE CustomerID=%s", (customer_id,))
        count = cursor.fetchone()["cnt"]
        if count > 0:
            print("⚠ Customer has linked sales. Delete aborted.")
            return

        cursor.execute("DELETE FROM Customers WHERE CustomerID=%s", (customer_id,))
        conn.commit()
        print("✅ Customer deleted successfully.")

    except Exception as e:
        print("âŒ Error deleting customer:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def update_customer(customer_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        new_email = input("Enter new Email (leave blank to keep): ").strip().capitalize()
        new_phone = input("Enter new Phone (leave blank to keep): ").strip()
        new_address = input("Enter new Address (leave blank to keep): ").strip()

        updates = []
        values = []

        if new_email:
            updates.append("Email=%s")
            values.append(new_email)
        if new_phone:
            updates.append("PhoneNumber=%s")
            values.append(new_phone)
        if new_address:
            updates.append("Address=%s")
            values.append(new_address)

        if not updates:
            print("⚠ Nothing to update.")
            return

        sql = f"UPDATE Customers SET {', '.join(updates)} WHERE CustomerID=%s"
        values.append(customer_id)
        cursor.execute(sql, values)
        conn.commit()

        print("✅ Customer updated successfully.")

    except Exception as e:
        print("âŒ Error updating customer:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def customer_insights(customer_id):
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Total purchases
        cursor.execute("""
            SELECT COUNT(*) AS total_purchases, SUM(TotalAmount) AS total_spent
            FROM Sales WHERE CustomerID=%s
        """, (customer_id,))
        purchase_data = cursor.fetchone()

        # Last purchase date
        cursor.execute("""
            SELECT MAX(SaleDate) AS last_purchase
            FROM Sales WHERE CustomerID=%s
        """, (customer_id,))
        last_purchase = cursor.fetchone()["last_purchase"]

        print("\n--- Customer Insights ---")
        print(f"Total Purchases: {purchase_data['total_purchases'] or 0}")
        print(f"Total Amount Spent: ${purchase_data['total_spent'] or 0:.2f}")
        print(f"Last Purchase Date: {last_purchase or 'N/A'}")

    except Exception as e:
        print("âŒ Error fetching customer insights:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def customers_menu():
    print("\n--- Customer Menu ---")
    print("1. Add Customer")
    print("2. View All Customers")
    print("3. Search Customer")
    print("4. Update Customer")
    print("5. Delete Customer")
    print("6. Customer Insights")

    while True:
        choice = input("Choose option: ").strip()
        if choice == "1":
            add_customer()
        elif choice == "2":
            view_customers()
        elif choice == "3":
            keyword = input("Enter name/email/phone to search: ")
            search_customer(keyword)
        elif choice == "4":
            cid = int(input("Enter Customer ID to update: "))
            update_customer(cid)
        elif choice == "5":
            cid = int(input("Enter Customer ID to delete: "))
            delete_customer(cid)
        elif choice == "6":
            cid = int(input("Enter Customer ID for insights: "))
            customer_insights(cid)
        else:

            print("❌ Invalid option.")

if __name__ == "__main__":
    customers_menu()

