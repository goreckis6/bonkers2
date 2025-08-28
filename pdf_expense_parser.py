# Universal PDF Parser - Converts ANY PDF to Structured Data
# Fast conversion to Excel/CSV format with columns and rows

import PyPDF2
import re
import pandas as pd
from typing import List, Dict, Any, Optional

class UniversalPDFParser:
    def __init__(self):
        # Enhanced patterns for banking data
        self.amount_patterns = [
            r'\$?[\d,]+\.?\d*',  # $1,234.56 or 1234.56
            r'[\d,]+\.?\d*',     # 1,234.56 or 1234.56
            r'[-+]?\d+\.?\d*',   # -123.45 or +123.45
        ]
        
        self.date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',  # MM/DD/YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY/MM/DD
            r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',  # DD MMM YYYY
        ]
        
        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        self.phone_pattern = r'[\+]?[1-9][\d]{0,15}'
        
        # Chase-specific patterns
        self.chase_section_patterns = {
            'withdrawals': r'WITHDRAWALS|DEBITS|CHARGES',
            'deposits': r'DEPOSITS|ADDITIONS|CREDITS',
            'balance': r'BALANCE|ACCOUNT\s+SUMMARY|ENDING\s+BALANCE',
            'transactions': r'TRANSACTIONS|ACTIVITY|SUMMARY'
        }
        
        self.chase_transaction_patterns = [
            # Date Description Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([\d,]+\.?\d*)',
            # Date Description Ref Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([A-Z0-9]+)\s+([\d,]+\.?\d*)',
            # Description Date Amount
            r'(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+\.?\d*)',
        ]
        
        self.currency_symbols = ['$', '€', '£', '¥', '₽', '₹', '₩', '₪', '₦', '₨', '₴', '₸', '₺', '₼', '₾', '₿']

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF using PyPDF2"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    def parse_pdf_to_structured_data(self, pdf_path: str) -> Dict[str, Any]:
        """Parse PDF and return structured data with enhanced banking support"""
        try:
            text = self.extract_text_from_pdf(pdf_path)
            if not text.strip():
                return {'success': False, 'error': 'No text extracted from PDF'}
            
            # Enhanced parsing for banking documents
            structured_data = self._extract_structured_data_enhanced(text)
            
            if not structured_data:
                return {'success': False, 'error': 'No structured data found'}
            
            return {
                'success': True,
                'structured_data': structured_data,
                'total_lines': len(structured_data),
                'text_length': len(text)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _extract_structured_data_enhanced(self, text: str) -> List[Dict[str, Any]]:
        """Enhanced extraction with banking section recognition - focused on transactions only"""
        lines = text.split('\n')
        structured_data = []
        current_section = 'general'
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Skip header lines, footers, and non-transaction content
            if self._is_non_transaction_line(line):
                continue
            
            # Detect banking sections
            detected_section = self._detect_banking_section(line)
            if detected_section:
                current_section = detected_section
                print(f"🔍 Detected section: {current_section}")
                continue
            
            # Only process lines that look like transactions
            if self._looks_like_transaction(line):
                parsed_line = self._parse_transaction_only(line, current_section, line_num)
                if parsed_line:
                    structured_data.append(parsed_line)
        
        return structured_data

    def _is_non_transaction_line(self, line: str) -> bool:
        """Check if line should be skipped - enhanced filtering for Chase statements"""
        line_upper = line.upper()
        
        # Skip these types of lines - comprehensive filtering
        skip_patterns = [
            # Page and document info
            r'^PAGE\s+\d+$',  # Page numbers
            r'^ACCOUNT\s+SUMMARY$',  # Account summary headers
            r'^BALANCE\s+FORWARD$',  # Balance forward
            r'^ENDING\s+BALANCE$',   # Ending balance
            r'^TOTAL\s+$',           # Just "TOTAL"
            r'^[A-Z\s]+BANK\s*$',    # Just bank names
            r'^STATEMENT\s+PERIOD\s*$', # Statement period
            r'^FROM\s+\d{1,2}/\d{1,2}/\d{4}\s*$',  # Just date ranges
            r'^TO\s+\d{1,2}/\d{1,2}/\d{4}\s*$',    # Just date ranges
            
            # Address and contact info
            r'^P\s+O\s+BOX\s+\d+',  # P O Box addresses
            r'^\d+\s+[A-Z\s]+\s+[A-Z\s]+\s+[A-Z]{2}\s+\d{5}',  # Street addresses
            r'^[A-Z\s]+\,\s+[A-Z]{2}\s+\d{5}',  # City, State ZIP
            r'^1-\d{3}-\d{3}-\d{4}',  # Phone numbers
            r'^DEAL\s+AND\s+HARD\s+OF\s+HEARING',  # Accessibility info
            r'^PARA\s+ESPANOL',  # Spanish info
            r'^INTERNATIONAL\s+CALLS',  # International calls
            
            # Account and routing info
            r'^\d{9,12}',  # Long account numbers
            r'^[A-Z]{2}\s+\d{3}\s+\d{3}',  # Routing numbers
            r'^NNNNNNNNNNN',  # Placeholder numbers
            r'^T\s+\d+\s+\d+',  # Transaction codes
            
            # Terms and conditions
            r'^CONGRATULATIONS',  # Congratulations messages
            r'^THANKS\s+TO\s+YOUR',  # Thank you messages
            r'^WE\s+WAIVED',  # Fee waiver messages
            r'^MONTHLY\s+SERVICE\s+FEE',  # Fee information
            r'^BASED\s+ON\s+AGGREGATED',  # Terms
            r'^BUSINESS\s+COMPLETE\s+CHECKING',  # Account types
            r'^CUTOFF\s+TIME',  # Cutoff information
            r'^MINIMUM\s+DAILY\s+BALANCE',  # Balance requirements
            r'^EASTERN\s+TIME',  # Time zone info
            
            # Empty or very short lines
            r'^\s*$',  # Empty lines
            r'^[A-Z\s]{1,3}$',  # Very short all caps
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, line_upper, re.IGNORECASE):
                return True
        
        return False

    def _looks_like_transaction(self, line: str) -> bool:
        """Check if line looks like a transaction - strict filtering for Chase"""
        # Must have sufficient text for a real transaction
        has_text = len(line.split()) >= 4  # At least 4 words for real transactions
        
        # Must have a valid date format
        has_valid_date = bool(re.search(r'\d{4}-\d{1,2}-\d{1,2}', line)) or \
                        bool(re.search(r'\d{1,2}/\d{1,2}/\d{4}', line)) or \
                        bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}', line, re.IGNORECASE))
        
        # Must have Chase transaction keywords
        chase_transaction_keywords = [
            'Direct Deposit', 'ATM', 'Cash', 'Deposit', 'Withdraw', 'Card Purchase', 
            'Payment Sent', 'Square Inc', 'Recurring', 'With Pin', 'CA Card', 'Confirmation',
            'Check Deposit', 'Electronic Deposit', 'ACH', 'Credit', 'Debit', 'Purchase',
            'Transfer', 'Online', 'PMT', 'Merchant', 'Service'
        ]
        has_chase_keywords = any(keyword.lower() in line.lower() for keyword in chase_transaction_keywords)
        
        # Must NOT contain garbage indicators
        garbage_indicators = [
            'P O Box', 'Columbus OH', 'Deal and Hard', 'Para Espanol', 'International Calls',
            'Congratulations', 'thanks to your', 'waived', 'monthly service fee', 'cutoff time',
            'Eastern Time', 'Minimum Daily Balance', 'Business Complete', 'aggregated spending'
        ]
        has_garbage = any(indicator.lower() in line.lower() for indicator in garbage_indicators)
        
        # Line is a transaction if it has text AND valid date AND Chase keywords AND NO garbage
        return has_text and has_valid_date and has_chase_keywords and not has_garbage

    def _parse_transaction_only(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse transaction data - enhanced for Chase statements"""
        
        # Enhanced transaction patterns for Chase
        transaction_patterns = [
            # Pattern 1: MM/DD/YYYY Description Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([\d,]+\.?\d*)',
            # Pattern 2: Month DD Description Amount (Feb 17 ATM Cash Deposit... 9549.00)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+?)\s+([\d,]+\.?\d*)',
            # Pattern 3: Description Date Amount
            r'(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+\.?\d*)',
            # Pattern 4: Date Description Ref Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([A-Z0-9]+)\s+([\d,]+\.?\d*)',
            # Pattern 5: Month DD Description (more flexible)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+)',
            # Pattern 6: Month DD Description Amount (without spaces)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+?)([\d,]+\.?\d*)',
            # Pattern 7: YYYY-MM-DD Description (new format)
            r'(\d{4}-\d{1,2}-\d{1,2})\s+(.+)',
            # Pattern 8: Description YYYY-MM-DD (reversed)
            r'(.+?)\s+(\d{4}-\d{1,2}-\d{1,2})',
        ]
        
        for pattern in transaction_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) == 3:  # Date Description Amount
                    if pattern == transaction_patterns[1]:  # Month DD Description Amount
                        month, day, description, amount = groups[0], groups[1], groups[2], groups[3]
                        date = self._convert_month_day_to_date(month, day)
                    else:
                        date, description, amount = groups
                    
                    return {
                        'date': self._format_date(date.strip()),
                        'description': description.strip(),
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                
                elif len(groups) == 4:  # Date Description Ref Amount
                    date, description, ref, amount = groups
                    return {
                        'date': self._format_date(date.strip()),
                        'description': f"{description.strip()} (Ref: {ref.strip()})",
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                
                elif len(groups) == 3 and pattern == transaction_patterns[4]:  # Month DD Description
                    month, day, description = groups
                    date = self._convert_month_day_to_date(month, day)
                    # Try to find amount in description - improved extraction
                    amount = self._extract_amount_from_text(description)
                    
                    return {
                        'date': self._format_date(date),
                        'description': description.strip(),
                        'amount': amount,
                        'amount_raw': str(amount),
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                
                elif len(groups) == 4 and pattern == transaction_patterns[5]:  # Month DD Description Amount
                    month, day, description, amount = groups
                    date = self._convert_month_day_to_date(month, day)
                    
                    return {
                        'date': self._format_date(date),
                        'description': description.strip(),
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                
                elif len(groups) == 2 and pattern == transaction_patterns[6]:  # YYYY-MM-DD Description
                    date, description = groups
                    # Try to find amount in description
                    amount = self._extract_amount_from_text(description)
                    
                    return {
                        'date': self._format_date(date),
                        'description': description.strip(),
                        'amount': amount,
                        'amount_raw': str(amount),
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                
                elif len(groups) == 2 and pattern == transaction_patterns[7]:  # Description YYYY-MM-DD
                    description, date = groups
                    # Try to find amount in description
                    amount = self._extract_amount_from_text(description)
                    
                    return {
                        'date': self._format_date(date),
                        'description': description.strip(),
                        'amount': amount,
                        'amount_raw': str(amount),
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
        
        # If no pattern matches, try to extract what we can
        return self._extract_fallback_transaction(line, section, line_num)

    def _extract_amount_from_text(self, text: str) -> float:
        """Extract amount from text - improved extraction"""
        # Look for amounts with various patterns
        amount_patterns = [
            r'[\d,]+\.?\d*',  # 9549 or 9549.00
            r'\$[\d,]+\.?\d*',  # $9549.00
            r'[\d,]+\.\d{2}',  # 9549.00
        ]
        
        for pattern in amount_patterns:
            matches = re.findall(pattern, text)
            if matches:
                # Try to find the largest number (likely the transaction amount)
                amounts = [self._parse_amount(match) for match in matches]
                if amounts:
                    return max(amounts)
        
        return 0.0

    def _format_date(self, date_str: str) -> str:
        """Format date to YYYY-MM-DD format"""
        try:
            # Handle MM/DD/YYYY format
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                month, day, year = date_str.split('/')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Handle YYYY-MM-DD format (already correct)
            elif re.match(r'\d{4}-\d{1,2}-\d{1,2}', date_str):
                return date_str
            
            # Handle other formats - try to parse
            else:
                # Try pandas to_datetime for various formats
                parsed_date = pd.to_datetime(date_str, errors='coerce')
                if pd.notna(parsed_date):
                    return parsed_date.strftime('%Y-%m-%d')
                
        except Exception as e:
            print(f"Error formatting date {date_str}: {e}")
        
        return date_str

    def _convert_month_day_to_date(self, month: str, day: str) -> str:
        """Convert month abbreviation and day to YYYY-MM-DD format"""
        month_map = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        
        current_year = pd.Timestamp.now().year
        month_num = month_map.get(month, '01')
        day_num = day.zfill(2)
        
        return f"{current_year}-{month_num}-{day_num}"

    def _extract_fallback_transaction(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Fallback extraction when no pattern matches - strict filtering"""
        # Only process lines that look like real transactions
        if not self._looks_like_transaction(line):
            return None
            
        # Try to find any date and amount - enhanced date detection
        date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', line)
        month_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})', line, re.IGNORECASE)
        yyyy_mm_dd_match = re.search(r'\d{4}-\d{1,2}-\d{1,2}', line)
        amount_match = re.search(r'[\d,]+\.?\d*', line)
        
        # If we have any date-like pattern and some text, create a transaction
        if (date_match or month_match or yyyy_mm_dd_match) and len(line.split()) >= 4:
            if date_match:
                date = date_match.group()
            elif month_match:
                month, day = month_match.groups()
                date = self._convert_month_day_to_date(month, day)
            elif yyyy_mm_dd_match:
                date = yyyy_mm_dd_match.group()
            else:
                date = ''
            
            # Improved amount extraction
            amount = self._extract_amount_from_text(line) if not amount_match else self._parse_amount(amount_match.group())
            
            # Remove date and amount from line to get description
            description = line
            if date_match:
                description = description.replace(date_match.group(), '')
            elif month_match:
                description = description.replace(month_match.group(), '')
            elif yyyy_mm_dd_match:
                description = description.replace(yyyy_mm_dd_match.group(), '')
            if amount_match:
                description = description.replace(amount_match.group(), '')
            description = re.sub(r'\s+', ' ', description.strip())  # Clean up extra spaces
            
            return {
                'date': self._format_date(date),
                'description': description if description else 'Transaction',
                'amount': amount,
                'amount_raw': str(amount),
                'section': section,
                'line_number': line_num,
                'full_text': line
            }
        
        return None

    def _detect_banking_section(self, line: str) -> Optional[str]:
        """Detect banking document sections"""
        line_upper = line.upper()
        
        for section, pattern in self.chase_section_patterns.items():
            if re.search(pattern, line_upper, re.IGNORECASE):
                return section
        
        return None

    def _parse_line_by_section(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse line based on detected banking section"""
        if section in ['withdrawals', 'deposits']:
            return self._parse_transaction_line(line, section)
        elif section == 'balance':
            return self._parse_balance_line(line)
        else:
            return self._parse_general_line(line, line_num)

    def _parse_transaction_line(self, line: str, section: str) -> Optional[Dict[str, Any]]:
        """Parse transaction lines (withdrawals/deposits) - improved amount extraction"""
        for pattern in self.chase_transaction_patterns:
            match = re.search(pattern, line)
            if match:
                groups = match.groups()
                
                if len(groups) == 3:  # Date Description Amount
                    date, description, amount = groups
                    return {
                        'transaction_type': section,
                        'date': self._format_date(date.strip()),
                        'description': description.strip(),
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'ref_number': '',
                        'full_text': line,
                        'has_amount': True,
                        'has_date': True,
                        'word_count': len(line.split())
                    }
                elif len(groups) == 4:  # Date Description Ref Amount
                    date, description, ref, amount = groups
                    return {
                        'transaction_type': section,
                        'date': self._format_date(date.strip()),
                        'description': f"{description.strip()} (Ref: {ref.strip()})",
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'ref_number': ref.strip(),
                        'full_text': line,
                        'has_amount': True,
                        'has_date': True,
                        'word_count': len(line.split())
                    }
        
        # Fallback: try to extract any recognizable data
        return self._parse_general_line(line, 0)

    def _parse_balance_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse balance-related lines"""
        # Look for balance amounts
        amount_match = re.search(r'[\d,]+\.?\d*', line)
        if amount_match:
            return {
                'transaction_type': 'balance',
                'date': '',
                'description': line,
                'amount': self._parse_amount(amount_match.group()),
                'amount_raw': amount_match.group(),
                'ref_number': '',
                'full_text': line,
                'has_amount': True,
                'has_date': False,
                'word_count': len(line.split())
            }
        return None

    def _parse_general_line(self, line: str, line_num: int) -> Dict[str, Any]:
        """Parse general lines with enhanced banking support"""
        # Extract amounts
        amounts = []
        for pattern in self.amount_patterns:
            found = re.findall(pattern, line)
            amounts.extend(found)
        
        # Extract dates
        dates = []
        for pattern in self.date_patterns:
            found = re.findall(pattern, line)
            dates.extend(found)
        
        # Extract emails
        emails = re.findall(self.email_pattern, line)
        
        # Extract phones
        phones = re.findall(self.phone_pattern, line)
        
        # Check for currency symbols
        has_currency = any(symbol in line for symbol in self.currency_symbols)
        
        # Check for numbers
        has_numbers = bool(re.search(r'\d', line))
        
        # Word count
        word_count = len(line.split())
        
        return {
            'transaction_type': 'general',
            'date': dates[0] if dates else '',
            'description': line,
            'amount': self._parse_amount(amounts[0]) if amounts else 0,
            'amount_raw': amounts[0] if amounts else '',
            'ref_number': '',
            'full_text': line,
            'amounts': amounts,
            'dates': dates,
            'emails': emails,
            'phones': phones,
            'has_amount': bool(amounts),
            'has_date': bool(dates),
            'has_numbers': has_numbers,
            'has_currency': has_currency,
            'word_count': word_count
        }

    def _parse_amount(self, amount_str: str) -> float:
        """Parse amount string to float"""
        try:
            # Remove currency symbols and commas
            cleaned = re.sub(r'[^\d.-]', '', amount_str)
            return float(cleaned) if cleaned else 0.0
        except:
            return 0.0

    def create_dataframe(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Create DataFrame with only essential columns: Date, Description, Amount"""
        if not data:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Filter only essential columns for clean output
        essential_columns = ['date', 'description', 'amount']
        available_columns = [col for col in essential_columns if col in df.columns]
        
        # Create clean DataFrame with only essential columns
        clean_df = df[available_columns].copy()
        
        # Rename columns to match desired format
        column_mapping = {
            'date': 'Date',
            'description': 'Description', 
            'amount': 'Amount'
        }
        
        clean_df = clean_df.rename(columns=column_mapping)
        
        # Handle NaN values
        clean_df = clean_df.fillna('')
        
        # Convert amount to numeric and remove decimals if they're 0
        if 'Amount' in clean_df.columns:
            clean_df['Amount'] = pd.to_numeric(clean_df['Amount'], errors='coerce').fillna(0)
            # Remove .0 if amount is whole number
            clean_df['Amount'] = clean_df['Amount'].apply(lambda x: int(x) if x == int(x) else x)
        
        # Convert to strings for export
        for col in clean_df.columns:
            if clean_df[col].dtype == 'object':
                clean_df[col] = clean_df[col].astype(str)
        
        return clean_df

    def export_to_excel(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """Export to Excel with only main data sheet - no extra sheets"""
        df = self.create_dataframe(data)
        
        if df.empty:
            raise ValueError("No data to export")
        
        if not filename:
            filename = f"enhanced_pdf_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            # Only main data sheet - no extra sheets
            df.to_excel(writer, sheet_name='Extracted Data', index=False)
        
        return filename

    def _create_banking_summary_sheet(self, writer, df: pd.DataFrame):
        """Create banking-specific summary sheet"""
        summary_data = []
        
        # Section breakdown
        if 'section' in df.columns:
            section_counts = df['section'].value_counts()
            for section, count in section_counts.items():
                summary_data.append(['Section', section, count])
        
        # Transaction type breakdown
        if 'transaction_type' in df.columns:
            type_counts = df['transaction_type'].value_counts()
            for trans_type, count in type_counts.items():
                summary_data.append(['Transaction Type', trans_type, count])
        
        # Amount statistics
        if 'amount' in df.columns:
            amounts = pd.to_numeric(df['amount'], errors='coerce').dropna()
            if not amounts.empty:
                summary_data.extend([
                    ['Total Amount', 'Sum', amounts.sum()],
                    ['Average Amount', 'Mean', amounts.mean()],
                    ['Largest Amount', 'Max', amounts.max()],
                    ['Smallest Amount', 'Min', amounts.min()]
                ])
        
        # Date range
        if 'date' in df.columns:
            valid_dates = pd.to_datetime(df['date'], errors='coerce').dropna()
            if not valid_dates.empty:
                summary_data.extend([
                    ['Date Range', 'Start', valid_dates.min().strftime('%Y-%m-%d')],
                    ['Date Range', 'End', valid_dates.max().strftime('%Y-%m-%d')]
                ])
        
        summary_df = pd.DataFrame(summary_data, columns=['Category', 'Value', 'Count'])
        summary_df.to_excel(writer, sheet_name='Banking Summary', index=False)

    def _create_data_types_sheet(self, writer, df: pd.DataFrame):
        """Create data types analysis sheet"""
        data_types = []
        for col in df.columns:
            non_empty = df[col].astype(str).str.strip().ne('').sum()
            data_types.append([col, non_empty, len(df) - non_empty])
        
        types_df = pd.DataFrame(data_types, columns=['Column', 'Non-Empty', 'Empty'])
        types_df.to_excel(writer, sheet_name='Data Types', index=False)

    def export_to_csv(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """Export to CSV"""
        df = self.create_dataframe(data)
        
        if df.empty:
            raise ValueError("No data to export")
        
        if not filename:
            filename = f"enhanced_pdf_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        return filename

def main():
    """Test the parser"""
    parser = UniversalPDFParser()
    
    # Test with a sample PDF
    pdf_path = "test.pdf"  # Replace with actual PDF path
    
    try:
        result = parser.parse_pdf_to_structured_data(pdf_path)
        
        if result['success']:
            print(f"✅ Successfully parsed {result['total_lines']} lines")
            
            # Export to Excel and CSV
            excel_file = parser.export_to_excel(result['structured_data'])
            csv_file = parser.export_to_csv(result['structured_data'])
            
            print(f"✅ Excel exported: {excel_file}")
            print(f"✅ CSV exported: {csv_file}")
        else:
            print(f"❌ Error: {result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()