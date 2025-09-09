#start with sales recording
import datetime
import csv
from database import get_connection
def record_sale():
    try:
        connection = get_connection()
        cursor = connection.cursor()
        print("Enter sale details:")
        saledate = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        quantity = int(input("Quantity: "))
        unitprice = float(input("Unit Price: "))
        paymentmethod = input("Payment Method (Cash/Card/Online): ")

        sales = {
            "SaleDate": saledate,
            "Quantity": quantity,
            "UnitPrice": unitprice,
            "PaymentMethod": paymentmethod
        }

        cursor.execute("""
            INSERT INTO Sales (SaleDate, Quantity, UnitPrice, PaymentMethod) VALUES (%s,%s,%s,%s)
                """, tuple(sales.values()))
        connection.commit()
        print('Sale recorded successfully.')

        #csv backup
        with open ('sales.csv',mode = 'a' newline = '') as f:
            writer = csv.DictWriter(f, fieldnames = sales.keys())
            if f.tell() == 0:
                writer.writeheader()
            writer.writerows(sales)
    except Exception as e:
        print("Error recording sale:", e)
    finally:    
        cursor.close()
        connection.close()