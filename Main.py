from Sales import record_sale, view_sales, run_sales_viewer
from SalesReturn import record_sales_return, view_sales_return, run_sales_return_viewer

def main_menu():
    while True:
        print("\n--- Shop Management ---")
        print("1. Record Sale")
        print("2. View Sales")
        print("3. Record Sales Return")
        print("4. View Sales Returns")
        print("5. Exit")

        choice = input("Choose an option: ").strip()
        if choice == "1":
            record_sale()
        elif choice == "2":
            form = input("Form (raw/tabular/line/bar): ").strip().lower()
            period = input("Period (weekly/monthly/yearly): ").strip().lower()
            view_sales(form=form, period=period)
        elif choice == "3":
            record_sales_return()
        elif choice == "4":
            form = input("Form (raw/tabular/line/bar): ").strip().lower()
            period = input("Period (weekly/monthly/yearly): ").strip().lower()
            view_sales(form=form, period=period)
        elif choice == "5":
            break
        else:
            print("❌ Invalid choice")

if __name__ == "__main__":
    main_menu()

