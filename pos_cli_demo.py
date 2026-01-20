"""
Simple CLI demo showing how to use the backend
This can be replaced with Textual TUI or GUI
"""
from pos_db_layer import Database, InventoryRepository, SalesRepository, InvoiceRepository, UnifiedSalesRepository
from pos_business_logic import POSService, ReportService, InvoiceItem, PaymentInfo, DailyReportService
import pandas as pd


class SimpleCLI:
    """Simple command-line interface (temporary, before Textual)"""
    
    def __init__(self):
        # Initialize backend
        db = Database("data.db")
        inv_repo = InventoryRepository(db)
        sales_repo = SalesRepository(db)
        unified_sales_repo = UnifiedSalesRepository(db)

        self.pos = POSService(
            inv_repo,
            sales_repo,
            InvoiceRepository(db),
            unified_sales_repo=unified_sales_repo
        )
        self.reports = ReportService(inv_repo, sales_repo)
        self.daily_report = DailyReportService(
            sales_repo,
            None,
            inv_repo,
            unified_sales_repo
        )

        self.menu = {
            1: ("Prodaja", self.sell_items),
            2: ("Izveštaji", self.show_reports),
            3: ("Pregled inventara", self.view_inventory),
            4: ("Unos fakture", self.add_invoice),
            5: ("Pregled fakture", self.view_invoice),
            6: ("Ponovna štampa računa", self.reprint_receipt),
            7: ("Kreiranje korisnika", self.create_user),
            0: ("Izlaz", None),
        }
    
    def run(self):
        """Main loop"""
        while True:
            print("\n" + "="*50)
            print("POS SISTEM")
            print("="*50)
            for key, (label, _) in self.menu.items():
                print(f"{key} - {label}")
            
            try:
                choice = int(input("\nOdaberite radnju: "))
                if choice == 0:
                    print("Izlaz...")
                    break
                
                if choice in self.menu:
                    action = self.menu[choice][1]
                    if action:
                        action()
                else:
                    print("❌ Nepoznata opcija!")
            except ValueError:
                print("❌ Unesite broj!")
            except KeyboardInterrupt:
                print("\n\nIzlaz...")
                break
    
    def sell_items(self):
        """Handle sales"""
        print("\n--- PRODAJA ---")
        
        # Show inventory
        items = self.pos.search_inventory()
        if not items:
            print("❌ Nema artikala u magacinu!")
            return
        
        df = pd.DataFrame(items)
        print("\n📦 Dostupni artikli:")
        print(df[['id', 'item', 'barcode', 'price', 'quantity']].to_string(index=False))
        
        try:
            id_or_barcode = input("\nUnesite ID ili skenirajte barkod: ").strip()
            quantity = float(input("Unesite količinu: "))
            
            # First, get the item to calculate total
            item = None
            item_id = None
            
            try:
                potential_id = int(id_or_barcode)
                item = self.pos.get_inventory_item(potential_id)
                if item:
                    # Found by ID
                    item_id = potential_id
                else:
                    # Not found by ID, try as barcode
                    item = self.pos.find_item_by_barcode(id_or_barcode)
                    if item:
                        item_id = item['id'] # Use the item's actual ID from barcode lookup
            except ValueError:
                # Not a number - must be barcode
                item = self.pos.find_item_by_barcode(id_or_barcode)
                if item:
                    item_id = item['id']
            
            if not item:
                print("❌ Artikal nije pronađen!")
                return
            
            # Calculate total
            total = item['price'] * quantity
            print(f"\n💰 Ukupno za naplatu: {total:.2f} RSD")
            
            # Ask for payment method
            print("\nNačin plaćanja:")
            print("1 - Gotovina")
            print("2 - Kartica")
            print("3 - Kombinovano")
            
            payment_choice = input("Izaberite (1/2/3): ").strip()
            
            payment_info = None
            
            if payment_choice == '1':
                # Cash payment
                amount_tendered = float(input(f"Primljeno gotovine: "))
                if amount_tendered < total:
                    print(f"❌ Nedovoljno! Potrebno još {total - amount_tendered:.2f} RSD")
                    return
                
                change = amount_tendered - total
                payment_info = PaymentInfo(
                    payment_type='cash',
                    cash_amount=total,
                    amount_tendered=amount_tendered,
                    change_given=change
                )
                
                if change > 0:
                    print(f"💵 Kusur: {change:.2f} RSD")
            
            elif payment_choice == '2':
                # Card payment
                print("💳 Kartica - procesuiranje...")
                payment_info = PaymentInfo(
                    payment_type='card',
                    card_amount=total
                )
            
            elif payment_choice == '3':
                # Split payment
                cash_amount = float(input("Gotovina: "))
                card_amount = total - cash_amount
                
                if card_amount < 0:
                    print("❌ Gotovina je veća od ukupnog iznosa!")
                    return
                
                print(f"💳 Kartica: {card_amount:.2f} RSD")
                
                # If paying more cash than needed, calculate change
                if cash_amount > total:
                    change = cash_amount - total
                    cash_amount = total
                    card_amount = 0
                else:
                    change = 0
                
                payment_info = PaymentInfo(
                    payment_type='split',
                    cash_amount=cash_amount,
                    card_amount=card_amount,
                    change_given=change
                )
                
                if change > 0:
                    print(f"💵 Kusur: {change:.2f} RSD")
            
            else:
                print("❌ Nepoznat način plaćanja!")
                return
            
            # Now process the sale with payment info
            result = self.pos.sell_items(
                items=[{'id': item_id, 'quantity': quantity}],
                payment_info=payment_info,
                allow_oversell=False
            )
            if not result.success:
                # Ask if they want to oversell
                print(f"\n⚠️  {result.message}")
                if result.remaining_quantity is not None:
                    choice = input("Nastaviti prodaju? (d/n): ")
                    if choice.lower() == 'd':
                        result = self.pos.sell_items(
                            items=[{'id': item_id, 'quantity': quantity}],
                            payment_info=payment_info,
                            allow_oversell=True
                        )
            
            if result.success:
                print(f"\n✅ {result.message}")
                print(f"Preostalo: {result.remaining_quantity:.2f} komada")
            else:
                print(f"\n❌ {result.message}")
                
        except ValueError:
            print("❌ Neispravan unos!")
    
    def show_reports(self):
        """Show reports menu"""
        print("\n--- IZVEŠTAJI ---")
        print("1 - Prodati artikli")
        print("2 - Vrednost inventara")
        print("3 - Nisko stanje zaliha")
        print("4 - Dnevni izveštaj")
        print("5 - Zatvaranje kase")
        
        try:
            choice = int(input("\nOdaberite izveštaj: "))
            
            if choice == 1:
                sales = self.reports.sales_summary(50)
                print(f"\n📊 Ukupna prodaja: {sales['total_sales']} transakcija")
                print(f"💰 Ukupan prihod: {sales['total_revenue']:.2f} RSD")
                
                if sales['sales']:
                    df = pd.DataFrame(sales['sales'])
                    print("\n🧾 Nedavne prodaje:")
                    print(df[['id', 'item', 'quantity', 'total', 'time']].to_string(index=False))
            
            elif choice == 2:
                report = self.reports.inventory_value_report()
                print(f"\n📦 Ukupno artikala: {report['total_items']}")
                print(f"💰 Ukupna vrednost: {report['total_value']:.2f} RSD")
                
                df = pd.DataFrame(report['items'])
                print("\n📋 Detalji:")
                print(df[['id', 'item', 'price', 'quantity']].to_string(index=False))
            
            elif choice == 3:
                threshold = float(input("Unesite minimum stanja: "))
                low_stock = self.reports.low_stock_report(threshold)
                
                if low_stock:
                    print(f"\n⚠️  Pronađeno {len(low_stock)} artikala sa niskim stanjem:")
                    df = pd.DataFrame(low_stock)
                    print(df[['id', 'item', 'quantity']].to_string(index=False))
                else:
                    print("✅ Svi artikli imaju dovoljno zaliha!")

            elif choice == 4:
                self.show_daily_report()

            elif choice == 5:
                self.cash_reconciliation()
                    
        except ValueError:
            print("❌ Neispravan unos!")
    
    def view_inventory(self):
        """View inventory"""
        print("\n--- PREGLED INVENTARA ---")
        
        search = input("Pretraga (Enter za sve): ").strip()
        items = self.pos.search_inventory(search)
        
        if items:
            df = pd.DataFrame(items)
            print(df[['id', 'item', 'barcode', 'price', 'quantity']].to_string(index=False))
        else:
            print("❌ Nema rezultata!")
    
    def add_invoice(self):
        """Add invoice and items"""
        print("\n--- UNOS FAKTURE ---")
        
        invoice_number = input("Broj fakture: ").strip()
        if not invoice_number:
            print("❌ Broj fakture ne može biti prazan!")
            return
        
        items = []
        
        while True:
            print("\n--- Dodaj artikal ---")
            item_name = input("Ime artikla (Enter za kraj): ").strip()
            if not item_name:
                break
            
            try:
                price = float(input("Cena: "))
                quantity = float(input("Količina: "))
                # Ask for barcode - optional
                barcode = input("Barkod (Enter za preskakanje): ").strip()
                if not barcode:
                    barcode = None
                
                items.append(InvoiceItem(item_name, price, quantity, barcode))
                print(f"✅ Dodato: {item_name}")
                
            except ValueError:
                print("❌ Neispravan unos!")
        
        if items:
            success, message, invoice_id = self.pos.create_invoice_from_items(
                invoice_number, items
            )
            
            if success:
                print(f"\n✅ {message} (ID: {invoice_id})")
            else:
                print(f"\n❌ {message}")
        else:
            print("❌ Faktura mora imati barem jedan artikal!")
    
    def view_invoice(self):
        """View invoice details"""
        print("\n--- PREGLED FAKTURE ---")
        
        invoices = self.pos.get_all_invoices()
        if not invoices:
            print("❌ Nema faktura u sistemu!")
            return
        
        # Show all invoices
        df = pd.DataFrame(invoices)
        print("\n📄 Dostupne fakture:")
        print(df[['id', 'invoice', 'date', 'time']].to_string(index=False))
        
        try:
            invoice_id = int(input("\nUnesite ID fakture: "))
            details = self.pos.get_invoice_details(invoice_id)
            
            if details:
                header = details['header']
                print(f"\n📄 Faktura: {header['invoice']}")
                print(f"📅 Datum: {header['date']}, Vreme: {header['time']}")
                print("-" * 60)
                
                df_items = pd.DataFrame(details['items'])
                print(df_items[['item', 'price', 'quantity', 'total']].to_string(index=False))
                print("-" * 60)
                print(f"💰 UKUPNO: {details['total']:.2f} RSD")
            else:
                print("❌ Faktura nije pronađena!")
                
        except ValueError:
            print("❌ Neispravan ID!")


    def reprint_receipt(self):
        """Reprint a previous receipt"""
        print("\n--- PONOVNA ŠTAMPA RAČUNA ---")

        # Show recent sales with receipts
        sales = self.pos.get_recent_sales(20)
        if not sales:
            print("❌ Nema sačuvanih računa!")
            return

        print("\n📋 Nedavne prodaje:")
        df = pd.DataFrame(sales)
        print(df[['id', 'item', 'total', 'time']].to_string(index=False))

        try:
            sale_id = int(input("\nUnesite ID prodaje za štampu računa: "))

            # Get receipt from database
            receipt_data = self.pos.receipts.get_receipt_by_sale_id(sale_id)

            if receipt_data:
                print("\n" + "=" * 50)
                print("KOPIJA FISKALNOG RAČUNA")
                print("=" * 50)
                print(receipt_data['receipt_text'])
            else:
                print("❌ Račun nije pronađen za ovu prodaju!")

        except ValueError:
            print("❌ Neispravan ID!")

    def show_daily_report(self):
        """Display daily sales report"""
        print("\n--- DNEVNI IZVEŠTAJ ---")

        date_input = input("Datum (YYYY-MM-DD) ili Enter za danas: ").strip()
        if not date_input:
            from datetime import datetime
            date_input = datetime.now().strftime("%Y-%m-%d")

        report = self.daily_report.generate_daily_report(date_input)

        if not report['has_sales']:
            print(f"\n{report['message']}")
            return

        print("\n" + "=" * 60)
        print(f"DNEVNI IZVEŠTAJ ZA {date_input}".center(60))
        print("=" * 60)

        # Summary
        summary = report['summary']
        print(f"\n📊 OSNOVNI PODACI:")
        print(f"   Ukupan prihod:        {summary['total_revenue']:>12.2f} RSD")
        print(f"   Broj transakcija:     {summary['total_transactions']:>12}")
        print(f"   Prodato artikala:     {summary['total_items_sold']:>12.2f}")
        print(f"   Prosečna transakcija: {summary['avg_transaction']:>12.2f} RSD")

        # Payment breakdown
        payments = report['payments']
        print(f"\n💳 NAČIN PLAĆANJA:")
        print(f"   Gotovina:             {payments['cash']:>12.2f} RSD")
        print(f"   Kartica:              {payments['card']:>12.2f} RSD")
        print(f"   {'─' * 40}")
        print(f"   UKUPNO:               {payments['total']:>12.2f} RSD")

        # VAT breakdown
        print(f"\n📋 PDV REKAPITULACIJA:")
        for vat_rate, data in report['vat_breakdown'].items():
            vat_percent = int(vat_rate * 100)
            print(f"   Stopa {vat_percent}%:")
            print(f"      Osnovica:          {data['base']:>12.2f} RSD")
            print(f"      PDV:               {data['vat']:>12.2f} RSD")
            print(f"      Ukupno:            {data['total']:>12.2f} RSD")

        # Top items
        print(f"\n🏆 TOP 10 ARTIKALA:")
        for i, (item_name, data) in enumerate(report['top_items'], 1):
            print(f"   {i:2}. {item_name:<30} {data['quantity']:>6.0f} kom  {data['revenue']:>10.2f} RSD")

        # Hourly breakdown
        print(f"\n⏰ PRODAJA PO SATIMA:")
        for hour, data in report['hourly_sales']:
            bar_length = int(data['revenue'] / 100)  # Scale for display
            bar = '█' * min(bar_length, 40)
            print(f"   {hour}:00  {data['transactions']:>3} trans  {data['revenue']:>10.2f} RSD  {bar}")

        print("\n" + "=" * 60)

    def cash_reconciliation(self):
        """Cash drawer reconciliation"""
        print("\n--- ZATVARANJE KASE ---")

        date_input = input("Datum (YYYY-MM-DD) ili Enter za danas: ").strip()
        if not date_input:
            from datetime import datetime
            date_input = datetime.now().strftime("%Y-%m-%d")

        try:
            actual_cash = float(input("Prebrojana gotovina u kasi: "))

            reconciliation = self.daily_report.generate_cash_reconciliation(date_input, actual_cash)

            print("\n" + "=" * 50)
            print("ZATVARANJE KASE")
            print("=" * 50)
            print(f"\nDatum: {reconciliation['date']}")
            print(f"\nOčekivana gotovina:    {reconciliation['expected_cash']:>12.2f} RSD")
            print(f"Prebrojana gotovina:   {actual_cash:>12.2f} RSD")
            print(f"Izdati kusur:          {reconciliation['total_change_given']:>12.2f} RSD")
            print("─" * 50)

            diff = reconciliation['difference']
            if reconciliation['is_balanced']:
                print(f"Status: ✅ URAVNOTEŽENO")
            elif diff > 0:
                print(f"Status: ⚠️  VIŠAK: {diff:>12.2f} RSD")
            else:
                print(f"Status: ❌ MANJAK: {abs(diff):>12.2f} RSD")

            print("=" * 50)

        except ValueError:
            print("❌ Neispravan unos!")

    def create_user(self):
        """Create new user (admin function)"""
        print("\n--- KREIRANJE KORISNIKA ---")

        username = input("Korisnicko ime: ").strip()
        password = input("Lozinka: ").strip()
        full_name = input("Puno ime: ").strip()

        print("\nUloga:")
        print("1 - Kasir")
        print("2 - Administrator")
        role_choice = input("Izaberite (1/2): ").strip()

        role = "admin" if role_choice == 2 else "cachier"

        from pos_db_layer import Database, UserRepository
        from pos_business_logic import UserService

        db = Database('data.db')
        user_service = UserService(UserRepository(db))

        try:
            user_id = user_service.users.create_user(username, password, full_name, role)
            print(f"\n✅ Korisnik {username} uspešno kreiran!")
        except Exception as e:
            print(f"\n❌ Greška: {str(e)}")

if __name__ == "__main__":
    cli = SimpleCLI()
    cli.run()
