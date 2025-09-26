import pandas as pd
import matplotlib.pyplot as plt
import datetime 
import csv
from datetime import timedelta  # Added missing import
from Database import get_connection

purchase_cache = []  # in-memory backup 

def record_purchases():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Input - Fixed undefined variables
        now = datetime.datetime.now()  # Fixed: defined 'now'
        purchase_date = now.strftime("%Y-%m-%d")
        
        # Get additional required inputs
        vendor_id = int(input("Enter Vendor ID: "))
        product_id = int(input("Enter Product ID: "))
        quantity = int(input("Enter Quantity Purchased: "))  # Fixed: Should be "Purchased" not "Sold"
        unit_price = float(input("Enter Unit Price: "))
        credit_period_days = int(input("Enter Credit Period Days: "))  # Fixed: Get from user input
        Due_date = now + timedelta(days=credit_period_days)  # Fixed: Use datetime object
        payment_method = input("Enter Payment Method (cash/card/online): ").strip().lower()
        payment_status = input("Enter Payment Status (paid/unpaid): ").strip().lower()  # Added missing field

        # Validation
        if quantity <= 0 or unit_price <= 0:
            print("❌ Quantity and Unit Price must be positive.")
            return

        # Calculate total amount
        total_amount = quantity * unit_price

        # Prepare data - Fixed structure
        purchase = {
            "PurchaseDate": purchase_date,
            "VendorID": vendor_id,
            "ProductID": product_id,
            "Quantity": quantity,
            "UnitPrice": unit_price,
            "TotalAmount": total_amount,
            "CreditPeriodDays": credit_period_days,
            "DueDate": Due_date.strftime("%Y-%m-%d"),
            "PaymentMethod": payment_method,
            "PaymentStatus": payment_status
        }
        purchase_cache.append(purchase)

        # Insert into DB - Fixed table name and SQL
        sql = """
            INSERT INTO Purchases (PurchaseDate, VendorID, ProductID, Quantity, UnitPrice, TotalAmount, CreditPeriodDays, DueDate, PaymentMethod, PaymentStatus)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (purchase_date, vendor_id, product_id, quantity, unit_price, total_amount, credit_period_days, Due_date.strftime("%Y-%m-%d"), payment_method, payment_status))
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
        print("❌ Error recording purchase:", e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_user_filters():
    """Get filtering criteria from user"""
    print("\n=== Purchase Data Filters ===")
    
    # Vendor filter
    print("1. Vendor Filter:")
    vendor_filter = input("Enter Vendor Name (or part of it) or 'all' for all vendors: ").strip()
    if vendor_filter.lower() == 'all':
        vendor_filter = None
    
    # Date range filter
    print("\n2. Date Range Filter:")
    start_date = input("Enter Start Date (YYYY-MM-DD) or 'all' for no start limit: ").strip()
    if start_date.lower() == 'all':
        start_date = None
    
    end_date = input("Enter End Date (YYYY-MM-DD) or 'all' for no end limit: ").strip()
    if end_date.lower() == 'all':
        end_date = None
    
    # Payment status filter
    print("\n3. Payment Status Filter:")
    payment_status = input("Enter Payment Status (paid/unpaid) or 'all' for both: ").strip().lower()
    if payment_status == 'all':
        payment_status = None
    
    # Amount filter
    print("\n4. Amount Filter:")
    max_amount = input("Enter Maximum Bill Amount (bills under this amount) or 'all' for no limit: ").strip()
    if max_amount.lower() == 'all':
        max_amount = None
    else:
        try:
            max_amount = float(max_amount)
        except ValueError:
            print("❌ Invalid amount format. Using no limit.")
            max_amount = None
    
    return {
        'vendor_filter': vendor_filter,
        'start_date': start_date,
        'end_date': end_date,
        'payment_status': payment_status,
        'max_amount': max_amount
    }

def fetch_filtered_purchases(filters):  # Fixed function name
    """Fetch purchases from database based on filters"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Build dynamic query - Fixed indentation and structure
        query = """
            SELECT p.PurchaseID, p.PurchaseDate, p.VendorID, v.VendorName, p.ProductID, 
                   pr.ProductName, p.Quantity, p.UnitPrice, p.TotalAmount, p.PaymentStatus,
                   p.DueDate, p.PaymentMethod
            FROM Purchases p
            JOIN Vendors v ON p.VendorID = v.VendorID
            JOIN Products pr ON p.ProductID = pr.ProductID
            WHERE 1=1
        """
        params = []

        # Add vendor filter
        if filters['vendor_filter']:
            query += " AND v.VendorName LIKE %s"
            params.append(f"%{filters['vendor_filter']}%")

        # Add date range filters
        if filters['start_date']:
            query += " AND p.PurchaseDate >= %s"
            params.append(filters['start_date'])

        if filters['end_date']:
            query += " AND p.PurchaseDate <= %s"
            params.append(filters['end_date'])

        # Add payment status filter
        if filters['payment_status']:
            query += " AND p.PaymentStatus = %s"
            params.append(filters['payment_status'])

        query += " ORDER BY v.VendorName, p.PurchaseDate, p.PurchaseID"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            print("⚠ No purchase records found matching the criteria.")
            return None

        # Convert to DataFrame
        columns = ['PurchaseID', 'PurchaseDate', 'VendorID', 'VendorName', 'ProductID', 
                  'ProductName', 'Quantity', 'UnitPrice', 'TotalAmount', 'PaymentStatus',
                  'DueDate', 'PaymentMethod']
        
        df = pd.DataFrame(rows, columns=columns)
        df['PurchaseDate'] = pd.to_datetime(df['PurchaseDate'])
        
        return df

    except Exception as e:
        print("❌ Error fetching purchases:", e)
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def group_purchases_into_bills_silent(df, max_amount=None):  # Added missing function
    """Group purchases by vendor and date to create bills (silent version for interactive mode)"""
    if df is None or df.empty:
        return [], pd.DataFrame()

    # Group by VendorName and PurchaseDate
    grouped = df.groupby(['VendorName', 'PurchaseDate'])
    
    bills = []
    bill_summaries = []
    bill_number = 1
    
    for (vendor_name, purchase_date), group in grouped:
        # Calculate bill total
        bill_total = group['TotalAmount'].sum()
        
        # Apply amount filter
        if max_amount is not None and bill_total > max_amount:
            continue
        
        # Create individual bill DataFrame
        bill_df = group.copy()
        bill_df = bill_df[['ProductName', 'Quantity', 'UnitPrice', 'TotalAmount', 'PaymentStatus', 'PaymentMethod']]
        
        # Store bill
        bills.append({
            'bill_number': bill_number,
            'vendor_name': vendor_name,
            'purchase_date': purchase_date,
            'bill_dataframe': bill_df,
            'bill_total': bill_total,
            'payment_status': group['PaymentStatus'].iloc[0]
        })
        
        # Add to summary
        bill_summaries.append({
            'Bill_Number': bill_number,
            'Vendor_Name': vendor_name,
            'Purchase_Date': purchase_date.strftime('%Y-%m-%d'),
            'Bill_Total': bill_total,
            'Payment_Status': group['PaymentStatus'].iloc[0].upper()
        })
        
        bill_number += 1

    # Create summary DataFrame
    if bill_summaries:
        summary_df = pd.DataFrame(bill_summaries)
    else:
        summary_df = pd.DataFrame()

    return bills, summary_df

def group_purchases_into_bills(df, max_amount=None):
    """Group purchases by vendor and date to create bills"""
    if df is None or df.empty:
        return [], pd.DataFrame()

    # Group by VendorName and PurchaseDate
    grouped = df.groupby(['VendorName', 'PurchaseDate'])
    
    bills = []
    bill_summaries = []

    print(f"\n{'='*60}")
    print("PURCHASE BILLS REPORT")
    print(f"{'='*60}")

    bill_number = 1
    
    for (vendor_name, purchase_date), group in grouped:
        # Calculate bill total
        bill_total = group['TotalAmount'].sum()
        
        # Apply amount filter
        if max_amount is not None and bill_total > max_amount:
            continue
            
        print(f"\n📋 BILL #{bill_number}")
        print(f"Vendor: {vendor_name}")
        print(f"Date: {purchase_date.strftime('%Y-%m-%d')}")
        print("-" * 50)
        
        # Create individual bill DataFrame
        bill_df = group.copy()
        bill_df = bill_df[['ProductName', 'Quantity', 'UnitPrice', 'TotalAmount', 'PaymentStatus', 'PaymentMethod']]
        
        print(bill_df.to_string(index=False))
        print("-" * 50)
        print(f"BILL TOTAL: ₹{bill_total:.2f}")
        print(f"Payment Status: {group['PaymentStatus'].iloc[0].upper()}")
        
        # Store bill
        bills.append({
            'bill_number': bill_number,
            'vendor_name': vendor_name,
            'purchase_date': purchase_date,
            'bill_dataframe': bill_df,
            'bill_total': bill_total,
            'payment_status': group['PaymentStatus'].iloc[0]
        })
        
        # Add to summary
        bill_summaries.append({
            'Bill_Number': bill_number,
            'Vendor_Name': vendor_name,
            'Purchase_Date': purchase_date.strftime('%Y-%m-%d'),
            'Bill_Total': bill_total,
            'Payment_Status': group['PaymentStatus'].iloc[0].upper()
        })
        
        bill_number += 1
        print(f"{'='*60}")

    # Create summary DataFrame
    if bill_summaries:
        summary_df = pd.DataFrame(bill_summaries)
        
        print(f"\n📊 BILLS SUMMARY")
        print(f"{'='*60}")
        print(summary_df.to_string(index=False))
        print(f"{'='*60}")
        print(f"Total Bills: {len(bill_summaries)}")
        print(f"Grand Total: ₹{summary_df['Bill_Total'].sum():.2f}")
        
        # Payment status breakdown
        status_breakdown = summary_df.groupby('Payment_Status')['Bill_Total'].agg(['count', 'sum'])
        print(f"\nPayment Status Breakdown:")
        for status, data in status_breakdown.iterrows():
            print(f"  {status}: {data['count']} bills, ₹{data['sum']:.2f}")
        
    else:
        summary_df = pd.DataFrame()
        print("\n⚠ No bills match the specified criteria.")

    return bills, summary_df

def export_bills_to_csv(bills, summary_df):
    """Export bills and summary to CSV files"""
    if not bills:
        print("⚠ No bills to export.")
        return
    
    export_choice = input("\nDo you want to export the bills to CSV? (y/n): ").strip().lower()
    if export_choice != 'y':
        return
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Export individual bills
    for bill in bills:
        filename = f"bill_{bill['bill_number']}_{bill['vendor_name'].replace(' ', '_')}_{timestamp}.csv"
        bill['bill_dataframe'].to_csv(filename, index=False)
        print(f"💾 Bill #{bill['bill_number']} exported to {filename}")
    
    # Export summary - Fixed missing closing parenthesis
    if not summary_df.empty:
        summary_filename = f"bills_summary_{timestamp}.csv"
        summary_df.to_csv(summary_filename, index=False)
        print(f"💾 Bills summary exported to {summary_filename}")

def display_bills_summary_with_links(bills, summary_df):
    """Display bills summary with interactive links to individual bills"""
    if not bills:
        print("⚠ No bills to display.")
        return
    
    print(f"\n{'='*80}")
    print("📋 BILLS SUMMARY - INTERACTIVE VIEW")
    print(f"{'='*80}")
    
    # Enhanced summary display with clickable bill numbers
    print(f"{'Bill#':<6} {'Vendor':<20} {'Date':<12} {'Amount':<12} {'Status':<10} {'Action'}")
    print("-" * 80)
    
    for bill in bills:
        status_indicator = "✅" if bill['payment_status'].lower() == 'paid' else "❌"
        print(f"{bill['bill_number']:<6} {bill['vendor_name']:<20} "
              f"{bill['purchase_date'].strftime('%Y-%m-%d'):<12} "
              f"₹{bill['bill_total']:<11.2f} {status_indicator} {bill['payment_status'].upper():<10} "
              f"[Click {bill['bill_number']} to view]")
    
    print("-" * 80)
    print(f"Total Bills: {len(bills)} | Grand Total: ₹{summary_df['Bill_Total'].sum():.2f}")
    
    # Payment status summary
    paid_bills = [b for b in bills if b['payment_status'].lower() == 'paid']
    unpaid_bills = [b for b in bills if b['payment_status'].lower() == 'unpaid']
    
    print(f"\n💰 Payment Summary:")
    print(f"  ✅ Paid: {len(paid_bills)} bills - ₹{sum(b['bill_total'] for b in paid_bills):.2f}")
    print(f"  ❌ Unpaid: {len(unpaid_bills)} bills - ₹{sum(b['bill_total'] for b in unpaid_bills):.2f}")
    print(f"{'='*80}")

def interactive_bill_navigator(bills, summary_df):
    """Interactive navigation system for bills"""
    if not bills:
        return
    
    while True:
        # Display summary with links
        display_bills_summary_with_links(bills, summary_df)
        
        print(f"\n🔗 Interactive Bill Navigator")
        print(f"Commands:")
        print(f"  • Enter bill number (1-{len(bills)}) to view details")
        print(f"  • Type 'compare' to compare multiple bills")
        print(f"  • Type 'search' to search within bills")
        print(f"  • Type 'export' to export bills")
        print(f"  • Type 'stats' to view statistics")
        print(f"  • Type 'back' to return to menu")
        
        user_input = input(f"\nEnter command or bill number: ").strip().lower()
        
        if user_input == 'back':
            break
        elif user_input == 'compare':
            compare_bills(bills)
        elif user_input == 'search':
            search_within_bills(bills)
        elif user_input == 'export':
            export_bills_to_csv(bills, summary_df)
        elif user_input == 'stats':
            show_bill_statistics(bills, summary_df)
        elif user_input.isdigit():
            bill_num = int(user_input)
            if 1 <= bill_num <= len(bills):
                display_individual_bill_with_options(bills[bill_num - 1], bills)
            else:
                print(f"❌ Invalid bill number. Please enter 1-{len(bills)}")
        else:
            print("❌ Invalid command. Please try again.")

def display_individual_bill_with_options(selected_bill, all_bills):
    """Display individual bill with navigation options"""
    print(f"\n{'='*70}")
    print(f"📋 BILL #{selected_bill['bill_number']} - DETAILED VIEW")
    print(f"{'='*70}")
    print(f"🏪 Vendor: {selected_bill['vendor_name']}")
    print(f"📅 Date: {selected_bill['purchase_date'].strftime('%Y-%m-%d')}")
    print(f"💳 Payment Status: {selected_bill['payment_status'].upper()}")
    print(f"💰 Bill Total: ₹{selected_bill['bill_total']:.2f}")
    print("-" * 70)
    
    # Display items in the bill
    bill_df = selected_bill['bill_dataframe']
    
    # Enhanced display with item numbers
    print(f"{'#':<3} {'Product':<20} {'Qty':<6} {'Unit Price':<12} {'Total':<12} {'Payment':<10}")
    print("-" * 70)
    
    for idx, (_, row) in enumerate(bill_df.iterrows(), 1):
        status_icon = "✅" if row['PaymentStatus'].lower() == 'paid' else "❌"
        print(f"{idx:<3} {row['ProductName'][:19]:<20} {row['Quantity']:<6} "
              f"₹{row['UnitPrice']:<11.2f} ₹{row['TotalAmount']:<11.2f} "
              f"{status_icon} {row['PaymentStatus'].upper()}")
    
    print("-" * 70)
    print(f"TOTAL: ₹{selected_bill['bill_total']:.2f}")
    print(f"{'='*70}")
    
    # Navigation options for individual bill
    while True:
        print(f"\n🔗 Bill Navigation Options:")
        print(f"  1. Go back to bills summary")
        print(f"  2. View next bill ({selected_bill['bill_number'] + 1 if selected_bill['bill_number'] < len(all_bills) else 'N/A'})")
        print(f"  3. View previous bill ({selected_bill['bill_number'] - 1 if selected_bill['bill_number'] > 1 else 'N/A'})")
        print(f"  4. Export this bill to CSV")
        print(f"  5. Mark payment status")
        print(f"  6. Add notes to bill")
        
        choice = input(f"Enter option (1-6): ").strip()
        
        if choice == '1':
            break
        elif choice == '2':
            if selected_bill['bill_number'] < len(all_bills):
                next_bill = next(b for b in all_bills if b['bill_number'] == selected_bill['bill_number'] + 1)
                display_individual_bill_with_options(next_bill, all_bills)
                break
            else:
                print("❌ This is the last bill.")
        elif choice == '3':
            if selected_bill['bill_number'] > 1:
                prev_bill = next(b for b in all_bills if b['bill_number'] == selected_bill['bill_number'] - 1)
                display_individual_bill_with_options(prev_bill, all_bills)
                break
            else:
                print("❌ This is the first bill.")
        elif choice == '4':
            export_single_bill(selected_bill)
        elif choice == '5':
            update_bill_payment_status(selected_bill)
        elif choice == '6':
            add_bill_notes(selected_bill)
        else:
            print("❌ Invalid option.")

def compare_bills(bills):
    """Compare multiple bills side by side"""
    print(f"\n🔄 Compare Bills")
    print(f"Available bills: 1-{len(bills)}")
    
    try:
        bill_numbers = input("Enter bill numbers to compare (e.g., 1,3,5): ").strip()
        selected_numbers = [int(x.strip()) for x in bill_numbers.split(',')]
        
        selected_bills = []
        for num in selected_numbers:
            if 1 <= num <= len(bills):
                selected_bills.append(bills[num - 1])
            else:
                print(f"❌ Invalid bill number: {num}")
                return
        
        print(f"\n{'='*100}")
        print(f"📊 BILL COMPARISON")
        print(f"{'='*100}")
        
        # Comparison header
        header = f"{'Metric':<20}"
        for bill in selected_bills:
            header += f"Bill #{bill['bill_number']:<15}"
        print(header)
        print("-" * 100)
        
        # Compare metrics
        metrics = [
            ("Vendor", lambda b: b['vendor_name']),
            ("Date", lambda b: b['purchase_date'].strftime('%Y-%m-%d')),
            ("Total Amount", lambda b: f"₹{b['bill_total']:.2f}"),
            ("Payment Status", lambda b: b['payment_status'].upper()),
            ("Items Count", lambda b: str(len(b['bill_dataframe']))),
        ]
        
        for metric_name, metric_func in metrics:
            row = f"{metric_name:<20}"
            for bill in selected_bills:
                row += f"{metric_func(bill):<15}"
            print(row)
        
        print(f"{'='*100}")
        
    except ValueError:
        print("❌ Invalid input format. Use comma-separated numbers.")

def search_within_bills(bills):
    """Search for specific products or vendors within bills"""
    search_term = input("Enter search term (product name/vendor): ").strip().lower()
    
    matching_bills = []
    for bill in bills:
        # Search in vendor name
        if search_term in bill['vendor_name'].lower():
            matching_bills.append((bill, "Vendor match"))
            continue
        
        # Search in products
        for _, row in bill['bill_dataframe'].iterrows():
            if search_term in row['ProductName'].lower():
                matching_bills.append((bill, f"Product: {row['ProductName']}"))
                break
    
    if matching_bills:
        print(f"\n🔍 Search Results for '{search_term}':")
        print("-" * 70)
        for bill, match_type in matching_bills:
            print(f"Bill #{bill['bill_number']} - {bill['vendor_name']} - {match_type} - ₹{bill['bill_total']:.2f}")
    else:
        print(f"❌ No matches found for '{search_term}'")

def show_bill_statistics(bills, summary_df):
    """Show detailed statistics about the bills"""
    print(f"\n📊 DETAILED BILL STATISTICS")
    print(f"{'='*60}")
    
    # Basic stats
    total_amount = summary_df['Bill_Total'].sum()
    avg_bill = summary_df['Bill_Total'].mean()
    max_bill = summary_df['Bill_Total'].max()
    min_bill = summary_df['Bill_Total'].min()
    
    print(f"📋 Total Bills: {len(bills)}")
    print(f"💰 Grand Total: ₹{total_amount:.2f}")
    print(f"📊 Average Bill: ₹{avg_bill:.2f}")
    print(f"📈 Highest Bill: ₹{max_bill:.2f}")
    print(f"📉 Lowest Bill: ₹{min_bill:.2f}")
    
    # Payment status breakdown
    paid_bills = [b for b in bills if b['payment_status'].lower() == 'paid']
    unpaid_bills = [b for b in bills if b['payment_status'].lower() == 'unpaid']
    
    print(f"\n💳 Payment Status:")
    print(f"  ✅ Paid: {len(paid_bills)} bills ({len(paid_bills)/len(bills)*100:.1f}%)")
    print(f"  ❌ Unpaid: {len(unpaid_bills)} bills ({len(unpaid_bills)/len(bills)*100:.1f}%)")
    
    # Vendor breakdown
    vendor_stats = {}
    for bill in bills:
        vendor = bill['vendor_name']
        if vendor not in vendor_stats:
            vendor_stats[vendor] = {'count': 0, 'total': 0}
        vendor_stats[vendor]['count'] += 1
        vendor_stats[vendor]['total'] += bill['bill_total']
    
    print(f"\n🏪 Top Vendors:")
    sorted_vendors = sorted(vendor_stats.items(), key=lambda x: x[1]['total'], reverse=True)
    for i, (vendor, stats) in enumerate(sorted_vendors[:5], 1):
        print(f"  {i}. {vendor}: {stats['count']} bills, ₹{stats['total']:.2f}")

def export_single_bill(bill):
    """Export a single bill to CSV"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bill_{bill['bill_number']}_{bill['vendor_name'].replace(' ', '_')}_{timestamp}.csv"
    bill['bill_dataframe'].to_csv(filename, index=False)
    print(f"💾 Bill #{bill['bill_number']} exported to {filename}")

def update_bill_payment_status(bill):
    """Update payment status of a bill"""
    current_status = bill['payment_status']
    new_status = 'paid' if current_status.lower() == 'unpaid' else 'unpaid'
    
    confirm = input(f"Change payment status from {current_status.upper()} to {new_status.upper()}? (y/n): ").strip().lower()
    if confirm == 'y':
        bill['payment_status'] = new_status
        # Here you would also update the database
        print(f"✅ Payment status updated to {new_status.upper()}")
    else:
        print("❌ Payment status unchanged.")

def add_bill_notes(bill):
    """Add notes to a bill"""
    note = input("Enter note for this bill: ").strip()
    if note:
        if 'notes' not in bill:
            bill['notes'] = []
        bill['notes'].append({
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'note': note
        })
        print("✅ Note added to bill.")
    else:
        print("❌ No note added.")

def advanced_purchases_viewer():
    """Main function for advanced purchase viewing with filtering and grouping"""
    print("\n🔍 Advanced Purchases Viewer")
    
    # Get filters from user
    filters = get_user_filters()
    
    # Fetch filtered data
    print("\n📊 Fetching purchase data...")
    df = fetch_filtered_purchases(filters)  # Fixed function name
    
    if df is None:
        return
    
    print(f"✅ Found {len(df)} purchase records matching criteria.")
    
    # Group into bills and display
    bills, summary_df = group_purchases_into_bills_silent(df, filters['max_amount'])
    
    if bills:
        # Start interactive navigation
        interactive_bill_navigator(bills, summary_df)
    
    return bills, summary_df

def show_detailed_breakdown(bills, summary_df):
    """Show detailed breakdown of specific bills"""
    if not bills:
        return
        
    print(f"\nAvailable Bills (1-{len(bills)}):")
    for bill in bills:
        print(f"  {bill['bill_number']}. {bill['vendor_name']} - {bill['purchase_date'].strftime('%Y-%m-%d')} - ₹{bill['bill_total']:.2f}")
    
    try:
        bill_num = int(input("\nEnter bill number to view details: "))
        selected_bill = next((b for b in bills if b['bill_number'] == bill_num), None)
        
        if selected_bill:
            print(f"\n📋 DETAILED VIEW - BILL #{bill_num}")
            print(f"Vendor: {selected_bill['vendor_name']}")
            print(f"Date: {selected_bill['purchase_date'].strftime('%Y-%m-%d')}")
            print(f"Payment Status: {selected_bill['payment_status'].upper()}")
            print("-" * 60)
            print(selected_bill['bill_dataframe'].to_string(index=False))
            print("-" * 60)
            print(f"TOTAL: ₹{selected_bill['bill_total']:.2f}")
        else:
            print("❌ Invalid bill number.")
            
    except ValueError:
        print("❌ Please enter a valid number.")

def generate_bill_visualizations(summary_df):
    """Generate visualizations for the bills"""
    if summary_df.empty:
        print("⚠ No data to visualize.")
        return
    
    print("\nGenerating visualizations...")
    
    try:
        # 1. Bills by Vendor
        plt.figure(figsize=(12, 6))
        vendor_totals = summary_df.groupby('Vendor_Name')['Bill_Total'].sum().sort_values(ascending=False)
        
        plt.subplot(1, 2, 1)
        vendor_totals.plot(kind='bar')
        plt.title('Total Amount by Vendor')
        plt.xlabel('Vendor')
        plt.ylabel('Amount (₹)')
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        
        # 2. Payment Status Distribution
        plt.subplot(1, 2, 2)
        payment_status = summary_df.groupby('Payment_Status')['Bill_Total'].sum()
        plt.pie(payment_status.values, labels=payment_status.index, autopct='%1.1f%%')
        plt.title('Payment Status Distribution')
        
        plt.tight_layout()
        plt.show()
        
        # 3. Timeline view
        summary_df_copy = summary_df.copy()
        summary_df_copy['Purchase_Date'] = pd.to_datetime(summary_df_copy['Purchase_Date'])
        timeline = summary_df_copy.groupby('Purchase_Date')['Bill_Total'].sum()
        
        plt.figure(figsize=(10, 6))
        timeline.plot(kind='line', marker='o')
        plt.title('Bills Timeline')
        plt.xlabel('Date')
        plt.ylabel('Amount (₹)')
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()
        
    except Exception as e:
        print(f"❌ Error generating visualizations: {e}")

def update_credit_period():
    """Update credit period for vendor-product combination"""
    try:
        vendor_id = int(input("Enter Vendor ID To Be Updated: "))
        credit_period_days = int(input("Enter New Credit Period (days): "))
        product_id = int(input("Enter Product ID To Be Updated: "))
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Update query (you may need to adjust based on your database schema)
        sql = """
            UPDATE Purchases 
            SET CreditPeriodDays = %s 
            WHERE VendorID = %s AND ProductID = %s
        """
        cursor.execute(sql, (credit_period_days, vendor_id, product_id))
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"✅ Credit period updated to {credit_period_days} days for Vendor ID {vendor_id}, Product ID {product_id}")
        else:
            print("❌ No records found to update.")
            
    except ValueError:
        print("❌ Please enter valid numeric values.")
    except Exception as e:
        print(f"❌ Error updating credit period: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def purchases_menu():
    """Main purchases menu with all options"""
    print("\n--- Enhanced Purchases Menu ---")
    print("1. Record Purchases")
    print("2. Advanced Purchases Viewer (with filters & bill grouping)")
    print("3. Update Credit Period")
    print("4. Generate Bill Visualizations")
    print("5. Back to Main Menu")

    while True:
        choice = input("Enter option (1-5): ").strip()
        if choice == "1":
            record_purchases()
        elif choice == "2":
            advanced_purchases_viewer()
        elif choice == "3":
            update_credit_period()
        elif choice == "4":
            # Quick visualization option
            filters = get_user_filters()
            df = fetch_filtered_purchases(filters)
            if df is not None:
                bills, summary_df = group_purchases_into_bills_silent(df, filters['max_amount'])
                if not summary_df.empty:
                    generate_bill_visualizations(summary_df)
                else:
                    print("⚠ No data to visualize.")
        elif choice == "5":
            break
        else:
            print("❌ Invalid option. Please choose 1-5.")

# For testing purposes
if __name__ == "__main__":
    purchases_menu()