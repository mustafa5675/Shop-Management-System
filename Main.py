from Sales import sales_menu
from SalesReturn import sales_return_menu
from Customers import customers_menu
from Purchase import purchase_menu
from PurchaseReturn import purchase_return_menu

def main_menu():
    while True:
        print("\n--- Shop Management ---")
        print("1. Sales Menu")
        print("2. Sales Return Menu")
        print("3. Customers Menu")
        print("4. Purchase Menu")
        print("5. Purchase Return Menu")
        print("6. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            sales_menu()
        elif choice == "2":
            sales_return_menu()
        elif choice == "3":
            customers_menu()
        elif choice == "4":
            purchase_menu()
        elif choice == "5":
            purchase_return_menu()
        elif choice == "6":
            break
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main_menu()

