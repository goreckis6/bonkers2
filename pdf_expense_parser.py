# Enhanced PDF Expense Parser with Bank Statements Support
# Funkcja do wyodrębniania danych o wydatkach z plików PDF oraz wyciągów bankowych
# Obsługuje banki z całego świata używając pandas do analizy danych

import re
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

class ExpenseParser:
    def __init__(self):
        # Wzorce regex do znajdowania różnych typów danych - rozszerzone o formaty międzynarodowe
        self.amount_patterns = [
            # Polski format
            r'(?:łącznie|suma|total|do zapłaty):?\s*(\d+[.,]\d{2})\s*(?:pln|zł)?',
            r'(\d+[.,]\d{2})\s*(?:pln|zł)',
            r'kwota:?\s*(\d+[.,]\d{2})',
            
            # Formaty międzynarodowe
            r'(?:total|amount|sum):?\s*([€$£¥₹]\s*\d+[.,]\d{2})',
            r'([€$£¥₹]\s*\d+[.,]\d{2})',
            r'(\d+[.,]\d{2})\s*(?:eur|usd|gbp|jpy|inr)',
            
            # Wyciągi bankowe - różne formaty
            r'(?:debit|credit|amount|kwota):?\s*[-+]?(\d+[.,]\d{2})',
            r'[-+]?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})',  # Duże kwoty z separatorami tysięcy
        ]
        
        self.date_patterns = [
            # Polski format
            r'data\s*(?:wystawienia|sprzedaży|faktury|operacji)?:?\s*(\d{1,2}[.-]\d{1,2}[.-]\d{4})',
            r'(\d{1,2}[.-]\d{1,2}[.-]\d{4})',
            r'(\d{4}[.-]\d{1,2}[.-]\d{1,2})',
            
            # Formaty międzynarodowe
            r'(?:date|datum|fecha|data):?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
            r'(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            
            # Format amerykański MM/DD/YYYY
            r'(\d{1,2}/\d{1,2}/\d{4})',
            
            # Format ISO
            r'(\d{4}-\d{2}-\d{2})',
        ]
        
        self.vendor_patterns = [
            # Polski
            r'(?:sprzedawca|firma|dostawca):?\s*([^\n]+)',
            r'nazwa\s*firmy:?\s*([^\n]+)',
            
            # Międzynarodowe
            r'(?:vendor|merchant|company|payee|beneficiary):?\s*([^\n]+)',
            r'(?:von|de|para|to):?\s*([^\n]+)',
            
            # Wyciągi bankowe
            r'(?:transfer|payment|płatność)\s*(?:to|do|für):?\s*([^\n]+)',
        ]

        # Wzorce dla różnych typów transakcji bankowych
        self.bank_transaction_patterns = {
            'transfer': r'(?:transfer|przelew|überweisung|virement)',
            'card_payment': r'(?:card|karta|carte|tarjeta)',
            'atm': r'(?:atm|bankomat|geldautomat)',
            'direct_debit': r'(?:direct debit|polecenie zapłaty|lastschrift)',
            'standing_order': r'(?:standing order|zlecenie stałe|dauerauftrag)',
        }

        # Waluty międzynarodowe
        self.currencies = {
            'PLN': ['pln', 'zł', 'złoty', 'złote'],
            'EUR': ['eur', '€', 'euro'],
            'USD': ['usd', '$', 'dollar'],
            'GBP': ['gbp', '£', 'pound'],
            'JPY': ['jpy', '¥', 'yen'],
            'CHF': ['chf', 'franc'],
            'CAD': ['cad', 'c$'],
            'AUD': ['aud', 'a$'],
        }

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Wyodrębnia tekst z pliku PDF z lepszą obsługą różnych formatów
        """
        try:
            import PyPDF2
            
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            return text.lower()
        except ImportError:
            raise Exception("Biblioteka PyPDF2 nie jest zainstalowana. Użyj: pip install PyPDF2")
        except Exception as e:
            raise Exception(f"Błąd podczas czytania PDF: {str(e)}")

    def detect_currency(self, text: str) -> str:
        """Wykrywa walutę w tekście"""
        for currency, patterns in self.currencies.items():
            for pattern in patterns:
                if pattern in text.lower():
                    return currency
        return 'PLN'  # Domyślna waluta

    def extract_amount_with_currency(self, text: str) -> Tuple[Optional[float], str]:
        """Wyodrębnia kwotę wraz z walutą"""
        currency = self.detect_currency(text)
        
        for pattern in self.amount_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                amount_str = matches[-1]
                # Usuń symbole walut z kwoty
                amount_str = re.sub(r'[€$£¥₹]', '', amount_str).strip()
                amount_str = amount_str.replace(',', '.')
                
                try:
                    amount = float(amount_str)
                    return amount, currency
                except ValueError:
                    continue
        return None, currency

    def extract_date_advanced(self, text: str) -> Optional[str]:
        """Zaawansowane wyodrębnianie dat z różnych formatów międzynarodowych"""
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                date_str = matches[0]
                # Normalizuj separatory
                date_str = re.sub(r'[./-]', '-', date_str)
                
                try:
                    # Spróbuj różne formaty daty
                    date_formats = [
                        '%d-%m-%Y', '%Y-%m-%d', '%m-%d-%Y',
                        '%d-%m-%y', '%y-%m-%d', '%m-%d-%y'
                    ]
                    
                    for date_format in date_formats:
                        try:
                            parsed_date = datetime.strptime(date_str, date_format)
                            # Jeśli rok jest dwucyfrowy i < 50, dodaj 2000
                            if parsed_date.year < 1950:
                                parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                            return parsed_date.strftime('%Y-%m-%d')
                        except ValueError:
                            continue
                except ValueError:
                    continue
        return None

    def detect_document_type(self, text: str) -> str:
        """Wykrywa typ dokumentu (faktura, paragon, wyciąg bankowy)"""
        text_lower = text.lower()
        
        bank_keywords = ['bank statement', 'wyciąg bankowy', 'kontoauszug', 'relevé bancaire', 
                        'account statement', 'transaction history', 'historia transakcji']
        invoice_keywords = ['faktura', 'invoice', 'rechnung', 'facture', 'bill']
        receipt_keywords = ['paragon', 'receipt', 'quittung', 'reçu', 'ricevuta']
        
        if any(keyword in text_lower for keyword in bank_keywords):
            return 'bank_statement'
        elif any(keyword in text_lower for keyword in invoice_keywords):
            return 'invoice'
        elif any(keyword in text_lower for keyword in receipt_keywords):
            return 'receipt'
        
        return 'unknown'

    def parse_bank_statement(self, text: str) -> List[Dict]:
        """Specjalne parsowanie wyciągów bankowych"""
        transactions = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Szukaj linii z datą i kwotą
            date_match = None
            for pattern in self.date_patterns:
                date_match = re.search(pattern, line)
                if date_match:
                    break
            
            if date_match:
                amount, currency = self.extract_amount_with_currency(line)
                if amount:
                    # Spróbuj znaleźć opis w tej samej linii lub następnych
                    description = line.strip()
                    
                    # Usuń datę i kwotę z opisu
                    description = re.sub(r'\d{1,2}[./-]\d{1,2}[./-]\d{4}', '', description)
                    description = re.sub(r'[-+]?\d+[.,]\d{2}', '', description)
                    description = description.strip()
                    
                    if not description and i + 1 < len(lines):
                        description = lines[i + 1].strip()
                    
                    transaction = {
                        'date': self.extract_date_advanced(line),
                        'amount': abs(amount),  # Zawsze dodatnia wartość
                        'description': description or 'Transakcja bankowa',
                        'currency': currency,
                        'type': 'bank_transaction'
                    }
                    transactions.append(transaction)
        
        return transactions

    def categorize_expense_advanced(self, description: str, amount: float, doc_type: str) -> str:
        """Zaawansowana kategoryzacja z uwzględnieniem typu dokumentu i kwoty"""
        description_lower = description.lower()
        
        # Kategorie z słowami kluczowymi w różnych językach
        categories = {
            'Transport': [
                'paliwo', 'benzyna', 'diesel', 'autobus', 'taxi', 'uber', 'parking',
                'fuel', 'gas', 'petrol', 'bus', 'train', 'flight', 'car',
                'kraftstoff', 'benzin', 'zug', 'flug', 'auto'
            ],
            'Żywność': [
                'restauracja', 'jedzenie', 'lunch', 'kawa', 'catering', 'sklep',
                'restaurant', 'food', 'lunch', 'coffee', 'grocery', 'supermarket',
                'restaurant', 'essen', 'kaffee', 'supermarkt'
            ],
            'Biuro': [
                'papier', 'długopisy', 'biuro', 'materiały', 'kancelaria',
                'office', 'paper', 'supplies', 'stationery',
                'büro', 'papier', 'büromaterial'
            ],
            'IT': [
                'komputer', 'laptop', 'software', 'internet', 'hosting', 'domena',
                'computer', 'software', 'internet', 'hosting', 'domain',
                'computer', 'software', 'internet'
            ],
            'Usługi bankowe': [
                'prowizja', 'opłata', 'commission', 'fee', 'gebühr', 'bank'
            ],
            'Zakupy': [
                'sklep', 'market', 'shop', 'store', 'geschäft', 'magasin'
            ]
        }
        
        # Kategoryzacja na podstawie kwoty (dla transakcji bankowych)
        if doc_type == 'bank_statement':
            if amount < 10:
                return 'Opłaty bankowe'
            elif amount > 1000:
                return 'Duże wydatki'
        
        # Standardowa kategoryzacja
        for category, keywords in categories.items():
            if any(keyword in description_lower for keyword in keywords):
                return category
        
        return 'Inne'

    def parse_pdf_file(self, pdf_path: str) -> Dict:
        """
        Główna funkcja do parsowania pliku PDF z obsługą różnych typów dokumentów
        """
        try:
            # Wyodrębnij tekst z PDF
            text = self.extract_text_from_pdf(pdf_path)
            
            if not text.strip():
                return {
                    'error': 'Nie udało się wyodrębnić tekstu z PDF',
                    'fileName': pdf_path.split('/')[-1],
                    'success': False
                }
            
            # Wykryj typ dokumentu
            doc_type = self.detect_document_type(text)
            
            if doc_type == 'bank_statement':
                # Parsuj wyciąg bankowy
                transactions = self.parse_bank_statement(text)
                return {
                    'transactions': transactions,
                    'document_type': doc_type,
                    'fileName': pdf_path.split('/')[-1],
                    'success': True
                }
            else:
                # Parsuj standardowy dokument (faktura/paragon)
                amount, currency = self.extract_amount_with_currency(text)
                date = self.extract_date_advanced(text)
                vendor = self.extract_vendor(text)
                description = self.generate_description(text, vendor)
                category = self.categorize_expense_advanced(description, amount or 0, doc_type)
                
                return {
                    'description': description,
                    'amount': amount or 0.0,
                    'currency': currency,
                    'date': date or datetime.now().strftime('%Y-%m-%d'),
                    'category': category,
                    'vendor': vendor,
                    'document_type': doc_type,
                    'fileName': pdf_path.split('/')[-1],
                    'success': True
                }
                
        except Exception as e:
            return {
                'error': str(e),
                'fileName': pdf_path.split('/')[-1],
                'success': False
            }

    def extract_vendor(self, text: str) -> Optional[str]:
        """Wyodrębnia nazwę dostawcy z tekstu - rozszerzone o formaty międzynarodowe"""
        for pattern in self.vendor_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
            if matches:
                vendor = matches[0].strip()
                if len(vendor) > 3 and not vendor.isdigit():
                    return vendor
        return None

    def generate_description(self, text: str, vendor: Optional[str]) -> str:
        """Generuje opis wydatku na podstawie dostępnych danych"""
        if vendor:
            return f"Wydatek - {vendor}"
        
        # Spróbuj wyodrębnić znaczące słowa z tekstu
        words = re.findall(r'\b[a-ząćęłńóśźż]{4,}\b', text, re.IGNORECASE)
        if words:
            return f"Wydatek - {' '.join(words[:3])}"
        
        return "Nierozpoznany wydatek"

    def create_expense_dataframe(self, expenses_data: List[Dict]) -> pd.DataFrame:
        """
        Tworzy DataFrame pandas z danych o wydatkach
        """
        successful_expenses = [exp for exp in expenses_data if exp.get('success')]
        
        if not successful_expenses:
            return pd.DataFrame()
        
        # Rozwiń transakcje bankowe
        all_expenses = []
        for expense in successful_expenses:
            if 'transactions' in expense:
                # Wyciąg bankowy z wieloma transakcjami
                for transaction in expense['transactions']:
                    all_expenses.append({
                        'description': transaction['description'],
                        'amount': transaction['amount'],
                        'currency': transaction.get('currency', 'PLN'),
                        'date': transaction['date'],
                        'category': self.categorize_expense_advanced(
                            transaction['description'], 
                            transaction['amount'], 
                            'bank_statement'
                        ),
                        'vendor': '',
                        'document_type': 'bank_statement',
                        'fileName': expense['fileName']
                    })
            else:
                # Pojedynczy dokument
                all_expenses.append(expense)
        
        df = pd.DataFrame(all_expenses)
        
        # Konwersja typów danych
        if not df.empty:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            
            # Sortuj po dacie
            df = df.sort_values('date', ascending=False)
        
        return df

    def generate_summary_report(self, df: pd.DataFrame) -> Dict:
        """
        Generuje raport podsumowujący z analizą wydatków
        """
        if df.empty:
            return {}
        
        summary = {
            'total_expenses': len(df),
            'total_amount': df['amount'].sum(),
            'date_range': {
                'from': df['date'].min().strftime('%Y-%m-%d') if not df['date'].isna().all() else None,
                'to': df['date'].max().strftime('%Y-%m-%d') if not df['date'].isna().all() else None
            },
            'by_category': df.groupby('category')['amount'].agg(['sum', 'count']).to_dict('index'),
            'by_currency': df.groupby('currency')['amount'].sum().to_dict(),
            'by_month': df.groupby(df['date'].dt.to_period('M'))['amount'].sum().to_dict(),
            'average_expense': df['amount'].mean(),
            'largest_expense': {
                'amount': df['amount'].max(),
                'description': df.loc[df['amount'].idxmax(), 'description']
            }
        }
        
        return summary

    def export_to_excel_advanced(self, expenses_data: List[Dict], output_path: str):
        """
        Zaawansowany eksport do Excel z wieloma arkuszami i analizą
        """
        df = self.create_expense_dataframe(expenses_data)
        
        if df.empty:
            raise Exception("Brak danych do eksportu")
        
        # Zmień nazwy kolumn na polskie
        column_mapping = {
            'description': 'Opis wydatku',
            'amount': 'Kwota',
            'currency': 'Waluta',
            'date': 'Data',
            'category': 'Kategoria',
            'vendor': 'Dostawca',
            'document_type': 'Typ dokumentu',
            'fileName': 'Plik źródłowy'
        }
        
        df_export = df.rename(columns=column_mapping)
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Arkusz główny z wszystkimi wydatkami
            df_export.to_excel(writer, sheet_name='Wszystkie wydatki', index=False)
            
            # Arkusz z podsumowaniem
            summary = self.generate_summary_report(df)
            if summary:
                summary_df = pd.DataFrame([
                    ['Łączna liczba wydatków', summary['total_expenses']],
                    ['Łączna kwota', f"{summary['total_amount']:.2f}"],
                    ['Średni wydatek', f"{summary['average_expense']:.2f}"],
                    ['Największy wydatek', f"{summary['largest_expense']['amount']:.2f} - {summary['largest_expense']['description']}"],
                    ['Okres', f"{summary['date_range']['from']} do {summary['date_range']['to']}"]
                ], columns=['Metryka', 'Wartość'])
                
                summary_df.to_excel(writer, sheet_name='Podsumowanie', index=False)
            
            # Arkusz z wydatkami per kategoria
            if not df.empty:
                category_summary = df.groupby('category').agg({
                    'amount': ['sum', 'count', 'mean']
                }).round(2)
                category_summary.columns = ['Suma', 'Liczba', 'Średnia']
                category_summary.to_excel(writer, sheet_name='Per kategoria')

    def export_to_csv_advanced(self, expenses_data: List[Dict], output_path: str):
        """
        Zaawansowany eksport do CSV z polskimi znakami
        """
        df = self.create_expense_dataframe(expenses_data)
        
        if df.empty:
            raise Exception("Brak danych do eksportu")
        
        # Zmień nazwy kolumn na polskie
        column_mapping = {
            'description': 'Opis wydatku',
            'amount': 'Kwota',
            'currency': 'Waluta', 
            'date': 'Data',
            'category': 'Kategoria',
            'vendor': 'Dostawca',
            'document_type': 'Typ dokumentu',
            'fileName': 'Plik źródłowy'
        }
        
        df_export = df.rename(columns=column_mapping)
        df_export.to_csv(output_path, index=False, encoding='utf-8-sig', sep=';')

# Przykład użycia
def main():
    """
    Przykład użycia rozszerzonego parsera PDF
    """
    parser = ExpenseParser()
    
    # Lista plików PDF do przetworzenia
    pdf_files = [
        'faktura1.pdf',
        'wyciag_bankowy.pdf',
        'paragon1.pdf', 
        'bank_statement_en.pdf'
    ]
    
    # Przetwórz wszystkie pliki
    print("Rozpoczynam parsowanie plików PDF...")
    results = []
    
    for pdf_file in pdf_files:
        try:
            result = parser.parse_pdf_file(pdf_file)
            results.append(result)
            
            if result['success']:
                if 'transactions' in result:
                    print(f"✓ {result['fileName']}: Wyciąg bankowy - {len(result['transactions'])} transakcji")
                else:
                    print(f"✓ {result['fileName']}: {result['description']} - {result['amount']} {result.get('currency', 'PLN')}")
            else:
                print(f"✗ {result['fileName']}: Błąd - {result['error']}")
        except FileNotFoundError:
            print(f"✗ {pdf_file}: Plik nie został znaleziony")
    
    # Eksportuj do plików
    if results:
        try:
            parser.export_to_csv_advanced(results, 'wydatki_advanced.csv')
            parser.export_to_excel_advanced(results, 'wydatki_advanced.xlsx')
            print("\nPliki zostały wyeksportowane:")
            print("- wydatki_advanced.csv")
            print("- wydatki_advanced.xlsx")
            
            # Pokaż podsumowanie
            df = parser.create_expense_dataframe(results)
            if not df.empty:
                summary = parser.generate_summary_report(df)
                print(f"\nPodsumowanie:")
                print(f"- Łączna liczba wydatków: {summary['total_expenses']}")
                print(f"- Łączna kwota: {summary['total_amount']:.2f}")
                print(f"- Średni wydatek: {summary['average_expense']:.2f}")
                
        except Exception as e:
            print(f"Błąd podczas eksportu: {e}")

if __name__ == "__main__":
    main()