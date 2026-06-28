import csv
from Database import get_connection
import pandas as pd

vendor_cache = [] # in-memory backup

def add_customer():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input
        vendor_name = input("Enter Vendor Name: ").strip().capitalize()
        email = input("Enter Email: ").strip()
        phone = int(input("Enter Phone Number: "))
        address = input("Enter Address: ").strip().capitalize()
        city = input("Enter City: ").strip().capitalize()
        state = input("Enter State: ").strip().capitalize()
        postal_code = int(input("Enter Postal Code: "))
        country = input("Enter Country: ").strip().capitalize()

       # Quick validations
        if not vendor_name:
            print("❌ First name is required.")
            return
        if "@" not in email:
            print("❌ Invalid email address.")
            return 

        vendor = {
            "Vendor_Name": vendor_name,
            "Email": email,
            "Phone_No": phone,
            "Address": address,
            "City": city,
            "State": state,
            "Postal_Code": postal_code,
            "Country": country,
        }
        vendor_cache.append(vendor)

        # Insert into DB
        sql = """
            INSERT INTO Vendors
            (Vendor_Name, Email, Phone_No, Address, City, State, Postal_Code, Country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, tuple(vendor.values()))
        conn.commit()

        print("✅ Customer added to database.")

        # Backup CSV
        with open("vendors_backup.csv", mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=vendor.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(vendor)

        print("💾 Backup written into vendors_backup.csv")

    except Exception as e:
        print("âŒ Error adding vendor", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
