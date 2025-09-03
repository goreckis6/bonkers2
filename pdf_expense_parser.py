# Universal PDF Parser - Converts ANY PDF to Structured Data
# Fast conversion to Excel/CSV format with columns and rows

import PyPDF2
import re
import pandas as pd
from typing import List, Dict, Any, Optional
try:
    import pdfplumber  # Layout-aware PDF text extraction
except Exception:
    pdfplumber = None

class UniversalPDFParser:
    def __init__(self):
        # Enhanced patterns for banking data
        self.amount_patterns = [
            r'\$?[\d,]+\.?\d*',  # $1,234.56 or 1234.56
            r'[\d,]+\.?\d*',     # 1,234.56 or 1234.56
            r'[-+]?\d+\.?\d*',   # -123.45 or +123.45
        ]
        
        self.date_patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',  # MM/DD/YYYY or MM-DD-YYYY or DD-MM-YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY/MM/DD or YYYY-MM-DD
            r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}',  # DD Mon YYYY
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:,\s*\d{4})?',  # Mon DD[, YYYY]
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,\s*\d{4})?',  # Month DD[, YYYY]
            r'\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s*,?\s*\d{4})?',  # DD Month [YYYY]
            r'\b\d{1,2}/\d{1,2}\b',  # MM/DD without year
            r'\b\d{1,2}-\d{1,2}\b',  # MM-DD without year
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
        
        # Indian bank statement patterns
        self.indian_bank_patterns = {
            'transaction_type': r'\b(DR|CR|DEBIT|CREDIT)\b',
            'balance': r'BALANCE\s*\(INR\)|Balance\s*\(INR\)',
            'amount': r'Amount\s*\(INR\)',
            'transaction_particulars': r'Transaction\s+Particulars',
            'branch_name': r'Branch\s+Name'
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

    def extract_lines_with_layout(self, pdf_path: str) -> List[str]:
        """Extract lines using pdfplumber to preserve layout and line integrity."""
        if pdfplumber is None:
            return []
        lines: List[str] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    # Tight tolerances to keep columns separate but join words on the same line
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ''
                    if not text:
                        continue
                    for raw_line in text.split('\n'):
                        line = (raw_line or '').strip()
                        if line:
                            lines.append(line)
        except Exception as e:
            print(f"Error extracting layout lines: {e}")
        return lines

    def parse_pdf_to_structured_data(self, pdf_path: str) -> Dict[str, Any]:
        """Parse PDF and return structured data with enhanced banking support"""
        try:
            # 1) Try layout-aware extraction first for best "line = Date Description Amount"
            structured_data: List[Dict[str, Any]] = []
            text: str = ""
            layout_lines = self.extract_lines_with_layout(pdf_path)
            if layout_lines:
                structured_data = self._extract_from_lines_with_layout(layout_lines)
            
            # 2) Fallback to simple text extraction if needed
            if not structured_data:
                text = self.extract_text_from_pdf(pdf_path)
                if not text.strip():
                    return {'success': False, 'error': 'No text extracted from PDF'}
                structured_data = self._extract_structured_data_enhanced(text)
            
            if not structured_data:
                return {'success': False, 'error': 'No structured data found'}
            
            # Compute text length from whichever source we used
            text_source = text if text else "\n".join(layout_lines)
            return {
                'success': True,
                'structured_data': structured_data,
                'total_lines': len(structured_data),
                'text_length': len(text_source)
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
        
        # Keep rows that have either a date OR an amount OR meaningful description
        filtered = []
        for row in structured_data:
            date_str = str(row.get('date') or '').strip()
            amount_val = row.get('amount')
            description = str(row.get('description') or '').strip()
            
            try:
                amount_num = float(amount_val) if amount_val is not None else 0.0
            except Exception:
                amount_num = 0.0
            
            # Keep row if it has date OR amount OR meaningful description
            if date_str or amount_num != 0.0 or (description and len(description) > 3):
                filtered.append(row)
        
        return filtered

    def _extract_from_lines_with_layout(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse already line-broken text (layout-aware) into structured transactions only."""
        structured_data: List[Dict[str, Any]] = []
        current_section = 'general'
        for line_num, raw_line in enumerate(lines):
            line = (raw_line or '').strip()
            if not line:
                continue
            if self._is_non_transaction_line(line):
                continue
            detected_section = self._detect_banking_section(line)
            if detected_section:
                current_section = detected_section
                continue
            if self._looks_like_transaction(line):
                parsed_line = self._parse_transaction_only(line, current_section, line_num)
                if parsed_line:
                    structured_data.append(parsed_line)
        # Keep rows that have either a date OR an amount OR meaningful description
        filtered: List[Dict[str, Any]] = []
        for row in structured_data:
            date_str = str(row.get('date') or '').strip()
            amount_val = row.get('amount')
            description = str(row.get('description') or '').strip()
            
            try:
                amount_num = float(amount_val) if amount_val is not None else 0.0
            except Exception:
                amount_num = 0.0
            
            # Keep row if it has date OR amount OR meaningful description
            if date_str or amount_num != 0.0 or (description and len(description) > 3):
                filtered.append(row)
        return filtered

    def _is_non_transaction_line(self, line: str) -> bool:
        """Check if line should be skipped - comprehensive filtering for Chase statements"""
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
            
            # Additional garbage patterns
            r'^\d{5,}$',  # Just numbers (5+ digits)
            r'^[A-Z\s]{20,}$',  # Very long all caps text
            r'^[A-Z\s]+\d{5,}',  # Text followed by many numbers
        ]
        
        for pattern in skip_patterns:
            if re.search(pattern, line_upper, re.IGNORECASE):
                return True
        
        return False

    def _looks_like_transaction(self, line: str) -> bool:
        """Check if line looks like a transaction - more inclusive filtering to catch all rows"""
        # Must have sufficient text for a real transaction
        has_text = len(line.split()) >= 2  # Reduced from 3 to catch more rows
        
        # Must have EITHER a valid date format OR amount OR transaction keywords
        has_valid_date = bool(re.search(r'\d{4}-\d{1,2}-\d{1,2}', line)) or \
                        bool(re.search(r'\d{1,2}/\d{1,2}/\d{4}', line)) or \
                        bool(re.search(r'\d{1,2}-\d{1,2}-\d{4}', line)) or \
                        bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}', line, re.IGNORECASE))
        
        # Check for amounts (decimal numbers)
        has_amount = bool(re.search(r'[\d,]+\.?\d{2}', line))
        
        # Check for transaction type indicators
        has_transaction_type = bool(re.search(r'\b(DR|CR|DEBIT|CREDIT)\b', line, re.IGNORECASE))
        
        # Expanded transaction keywords to include Indian bank terms
        transaction_keywords = [
            'Direct Deposit', 'ATM', 'Cash', 'Deposit', 'Withdraw', 'Card Purchase', 
            'Payment Sent', 'Square Inc', 'Recurring', 'With Pin', 'CA Card', 'Confirmation',
            'Check Deposit', 'Electronic Deposit', 'ACH', 'Credit', 'Debit', 'Purchase',
            'Transfer', 'Online', 'PMT', 'Merchant', 'Service', 'VISA', 'Mastercard',
            'Deposit', 'Withdrawal', 'Transaction', 'Purchase', 'Payment', 'Transfer',
            'UPI', 'NEFT', 'RTGS', 'IMPS', 'Bank', 'Payment', 'Refund', 'Fee', 'Charge',
            'Opening Balance', 'Closing Balance', 'Balance', 'Statement'
        ]
        has_keywords = any(keyword.lower() in line.lower() for keyword in transaction_keywords)
        
        # Must NOT contain obvious garbage indicators
        obvious_garbage_indicators = [
            'P O Box', 'Columbus OH', 'Deal and Hard', 'Para Espanol', 'International Calls',
            'Congratulations', 'thanks to your', 'waived', 'monthly service fee', 'cutoff time',
            'Eastern Time', 'Minimum Daily Balance', 'Business Complete', 'aggregated spending',
            'NNNNNNNNNNN', 'T 1 000000000', 'DRE 021 142 30321'
        ]
        has_obvious_garbage = any(indicator.lower() in line.lower() for indicator in obvious_garbage_indicators)
        
        # Line is a transaction if it has text AND (valid date OR amount OR transaction type OR keywords) AND NO obvious garbage
        return has_text and (has_valid_date or has_amount or has_transaction_type or has_keywords) and not has_obvious_garbage

    def _parse_transaction_only(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse transaction data - enhanced for Chase statements and Indian bank statements with improved column matching"""

        # First, try tabular bank data parsing (handles better column separation)
        tabular_result = self._parse_tabular_bank_data(line, section, line_num)
        if tabular_result:
            return tabular_result

        # Second, try Indian bank statement format (DD-MM-YYYY Description Amount DR/CR Balance Branch)
        indian_result = self._parse_indian_bank_transaction(line, section, line_num)
        if indian_result:
            return indian_result

        # Enhanced approach: better date detection and amount extraction
        date_match = None
        date_patterns_generic = [
            r'\d{4}-\d{1,2}-\d{1,2}',            # YYYY-MM-DD
            r'\d{1,2}/\d{1,2}/\d{4}',            # MM/DD/YYYY or DD/MM/YYYY
            r'\d{1,2}-\d{1,2}-\d{4}',            # DD-MM-YYYY (Indian format)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d{4})?',  # Mon DD [YYYY]
            r'\b\d{1,2}/\d{1,2}\b',             # MM/DD
        ]
        
        # Find the first valid date match
        for pat in date_patterns_generic:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                date_match = m
                break
        
        # Enhanced amount extraction - look for the last valid currency amount
        last_amount_str = self._find_last_amount_string(line)
        
        if date_match and last_amount_str:
            raw_date = date_match.group(0)
            parsed_date = self._format_date(raw_date)
            
            # Better description extraction - remove date and amount, keep the middle
            description = line
            # Remove the date
            description = description[:date_match.start()] + description[date_match.end():]
            # Remove the amount (find it again in the modified string)
            amount_idx = description.rfind(last_amount_str)
            if amount_idx != -1:
                description = description[:amount_idx] + description[amount_idx + len(last_amount_str):]
            
            # Clean up the description
            description = re.sub(r'\s+', ' ', description).strip()
            
            # Validate that we have meaningful data
            if len(description) < 3:  # Too short description
                description = "Transaction"
            
            return {
                'date': parsed_date,
                'description': description,
                'amount': self._parse_amount(last_amount_str),
                'amount_raw': last_amount_str,
                'section': section,
                'line_number': line_num,
                'full_text': line
            }

        # Enhanced transaction patterns for Chase
        transaction_patterns = [
            # 0: MM/DD/YYYY Description Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([\d,]+\.?\d*)',
            # 1: Month DD Description Amount (Feb 17 ATM Cash Deposit... 9549.00)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+?)\s+([\d,]+\.?\d*)',
            # 2: Description Date Amount
            r'(.+?)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+\.?\d*)',
            # 3: Date Description Ref Amount
            r'(\d{1,2}/\d{1,2}/\d{4})\s+(.+?)\s+([A-Z0-9]+)\s+([\d,]+\.?\d*)',
            # 4: Month DD Description (more flexible)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+)',
            # 5: Month DD Description Amount (without spaces)
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+?)([\d,]+\.?\d*)',
            # 6: YYYY-MM-DD Description (new format)
            r'(\d{4}-\d{1,2}-\d{1,2})\s+(.+)',
            # 7: Description YYYY-MM-DD (reversed)
            r'(.+?)\s+(\d{4}-\d{1,2}-\d{1,2})',
            # 8: MM/DD Description Amount (no year)
            r'(\d{1,2}/\d{1,2})\s+(.+?)\s+([\d,]+\.?\d*)',
        ]
        
        for idx, pattern in enumerate(transaction_patterns):
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            groups = match.groups()
            
            if idx == 0:  # MM/DD/YYYY Description Amount
                date, description, amount = groups
                parsed_date = self._format_date(date.strip())
                return {
                    'date': parsed_date,
                    'description': description.strip(),
                    'amount': self._parse_amount(amount),
                    'amount_raw': amount,
                    'section': section,
                    'line_number': line_num,
                    'full_text': line
                }
            if idx == 1:  # Month DD Description Amount
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
            if idx == 2:  # Description Date Amount
                description, date, amount = groups
                return {
                    'date': self._format_date(date.strip()),
                    'description': description.strip(),
                    'amount': self._parse_amount(amount),
                    'amount_raw': amount,
                    'section': section,
                    'line_number': line_num,
                    'full_text': line
                }
            if idx == 3:  # Date Description Ref Amount
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
            if idx == 4:  # Month DD Description (find amount later)
                month, day, description = groups
                date = self._convert_month_day_to_date(month, day)
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
            if idx == 5:  # Month DD Description Amount (tight)
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
            if idx == 6:  # YYYY-MM-DD Description
                date, description = groups
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
            if idx == 7:  # Description YYYY-MM-DD
                description, date = groups
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
            if idx == 8:  # MM/DD Description Amount (no year)
                mmdd, description, amount = groups
                date = self._format_date(mmdd)
                return {
                    'date': date,
                    'description': description.strip(),
                    'amount': self._parse_amount(amount),
                    'amount_raw': amount,
                    'section': section,
                    'line_number': line_num,
                    'full_text': line
                }
        
        # If no pattern matches, try to extract what we can
        fallback_result = self._extract_fallback_transaction(line, section, line_num)
        if fallback_result:
            return fallback_result
        
        # Last resort: try to extract any data from the line
        return self._extract_any_data_from_line(line, section, line_num)

    def _extract_amount_from_text(self, text: str) -> float:
        """Extract amount from text - prefer the LAST currency-like number on the line."""
        # Match currency-like numbers including optional $ and parentheses for negatives
        matches = re.findall(r'(\(?-?\$?[\d,]+(?:\.\d{2})?\)?)', text)
        if not matches:
            return 0.0
        last = matches[-1]
        return self._parse_amount(last)

    def _find_last_amount_string(self, text: str) -> str:
        """Return the last currency-like number substring from text with improved detection."""
        # Enhanced patterns for better currency detection
        patterns = [
            r'\(?-?\$?[\d,]+(?:\.\d{2})?\)?',  # Standard currency format
            r'\(?-?[\d,]+(?:\.\d{2})?\)?',      # Numbers with parentheses for negatives
            r'-?\$?[\d,]+(?:\.\d{2})?',         # Standard positive/negative amounts
            r'[\d,]+(?:\.\d{2})?',              # Just numbers with commas and decimals
        ]
        
        all_matches = []
        for pattern in patterns:
            matches = re.findall(pattern, text)
            all_matches.extend(matches)
        
        # Filter out very small numbers that are likely not amounts (like years, reference numbers)
        valid_matches = []
        for match in all_matches:
            # Clean the match to get just the number
            clean_match = re.sub(r'[^\d.,-]', '', match)
            try:
                # Remove commas and convert to float
                num_value = float(clean_match.replace(',', ''))
                # Only consider amounts that are reasonable (not years, not tiny decimals)
                if 0.01 <= abs(num_value) <= 999999.99:
                    valid_matches.append(match)
            except ValueError:
                continue
        
        return valid_matches[-1] if valid_matches else ''

    def _format_date(self, date_str: str) -> str:
        """Format date to YYYY-MM-DD format with improved DD-MM-YYYY support"""
        try:
            # Handle DD-MM-YYYY format (Indian bank statements)
            if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_str):
                day, month, year = date_str.split('-')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Handle DD/MM/YYYY format
            if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                parts = date_str.split('/')
                # Check if it's likely DD/MM/YYYY (day > 12) or MM/DD/YYYY (month > 12)
                if len(parts) == 3:
                    first, second, year = parts
                    if int(first) > 12:  # First part is day (DD/MM/YYYY)
                        day, month = first, second
                    else:  # First part is month (MM/DD/YYYY)
                        month, day = first, second
                    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Handle MM/DD/YYYY format (US format)
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                month, day, year = date_str.split('/')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Handle MM/DD without year -> assume current year
            if re.match(r'^\d{1,2}/\d{1,2}$', date_str):
                month, day = date_str.split('/')
                year = str(pd.Timestamp.now().year)
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # Handle MM-DD-YYYY (US format)
            if re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_str):
                month, day, year = date_str.split('-')
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            # Handle MM-DD without year -> assume current year
            if re.match(r'^\d{1,2}-\d{1,2}$', date_str):
                month, day = date_str.split('-')
                year = str(pd.Timestamp.now().year)
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            
            # Handle YYYY-MM-DD format (already correct)
            elif re.match(r'\d{4}-\d{1,2}-\d{1,2}', date_str):
                return date_str
            
            # Handle other formats - try to parse
            else:
                # Normalize month names (short/full) and remove commas
                normalized = re.sub(r',', '', date_str).strip()
                # Try pandas to_datetime for various formats
                parsed_date = pd.to_datetime(normalized, errors='coerce')
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
        """Fallback extraction when no pattern matches - more inclusive to catch all rows"""
        # Only process lines that look like real transactions
        if not self._looks_like_transaction(line):
            return None
            
        # Try to find any date and amount - enhanced date detection
        date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', line)
        month_match = re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})', line, re.IGNORECASE)
        yyyy_mm_dd_match = re.search(r'\d{4}-\d{1,2}-\d{1,2}', line)
        dd_mm_yyyy_match = re.search(r'\d{1,2}-\d{1,2}-\d{4}', line)
        amount_match = re.search(r'[\d,]+\.?\d*', line)
        
        # If we have any date-like pattern and some text, create a transaction
        if (date_match or month_match or yyyy_mm_dd_match or dd_mm_yyyy_match) and len(line.split()) >= 2:
            if date_match:
                date = date_match.group()
            elif month_match:
                month, day = month_match.groups()
                date = self._convert_month_day_to_date(month, day)
            elif yyyy_mm_dd_match:
                date = yyyy_mm_dd_match.group()
            elif dd_mm_yyyy_match:
                date = dd_mm_yyyy_match.group()
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
            elif dd_mm_yyyy_match:
                description = description.replace(dd_mm_yyyy_match.group(), '')
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
        
        # If still no match but line looks promising, create a basic entry
        if len(line.split()) >= 2 and not self._is_non_transaction_line(line):
            # Try to extract any amount from the line
            amount = self._extract_amount_from_text(line)
            
            return {
                'date': '',
                'description': line,
                'amount': amount,
                'amount_raw': str(amount),
                'section': section,
                'line_number': line_num,
                'full_text': line
            }
        
        return None

    def _extract_any_data_from_line(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Last resort: extract any data from line to avoid missing rows"""
        # Skip if line is too short or obviously not a transaction
        if len(line.strip()) < 5 or self._is_non_transaction_line(line):
            return None
        
        # Try to find any date
        date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{4}', line)
        date = self._format_date(date_match.group()) if date_match else ''
        
        # Try to find any amount
        amount = self._extract_amount_from_text(line)
        
        # Try to find transaction type
        type_match = re.search(r'\b(DR|CR|DEBIT|CREDIT)\b', line, re.IGNORECASE)
        trans_type = type_match.group().upper() if type_match else ''
        
        # Use the whole line as description if we can't parse it better
        description = line.strip()
        
        # Only return if we found something meaningful
        if date or amount != 0.0 or trans_type or len(description) > 5:
            return {
                'date': date,
                'description': description,
                'amount': amount,
                'amount_raw': str(amount),
                'transaction_type': trans_type,
                'section': section,
                'line_number': line_num,
                'full_text': line
            }
        
        return None

    def _parse_indian_bank_transaction(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse Indian bank statement transaction format with improved column separation"""
        
        # First, try to detect if this is a tabular format by looking for multiple amounts/numbers
        # Pattern: Date Description Amount Type Balance Branch (with proper spacing)
        
        # Enhanced pattern that handles various spacing and separators
        # This pattern looks for: DD-MM-YYYY + description + amount + DR/CR + balance + branch
        indian_pattern = r'(\d{1,2}-\d{1,2}-\d{4})\s+(.+?)\s+([\d,]+\.?\d{2})\s+(DR|CR)\s+([\d,]+\.?\d{2})\s+(.+)'
        
        match = re.search(indian_pattern, line)
        if match:
            date, description, amount, trans_type, balance, branch = match.groups()
            
            return {
                'date': self._format_date(date.strip()),
                'description': description.strip(),
                'amount': self._parse_amount(amount),
                'amount_raw': amount,
                'transaction_type': trans_type.strip(),
                'balance': self._parse_amount(balance),
                'balance_raw': balance,
                'branch': branch.strip(),
                'section': section,
                'line_number': line_num,
                'full_text': line
            }
        
        # Alternative pattern without branch
        indian_pattern_no_branch = r'(\d{1,2}-\d{1,2}-\d{4})\s+(.+?)\s+([\d,]+\.?\d{2})\s+(DR|CR)\s+([\d,]+\.?\d{2})'
        match = re.search(indian_pattern_no_branch, line)
        if match:
            date, description, amount, trans_type, balance = match.groups()
            
            return {
                'date': self._format_date(date.strip()),
                'description': description.strip(),
                'amount': self._parse_amount(amount),
                'amount_raw': amount,
                'transaction_type': trans_type.strip(),
                'balance': self._parse_amount(balance),
                'balance_raw': balance,
                'branch': '',
                'section': section,
                'line_number': line_num,
                'full_text': line
            }
        
        # If the above patterns don't work, try a more flexible approach
        # Look for the structure: Date + Description + Amount + Type + Balance + Branch
        # This handles cases where spacing might be irregular
        
        # Find date first
        date_match = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', line)
        if not date_match:
            return None
        
        date = date_match.group(1)
        remaining_line = line[date_match.end():].strip()
        
        # Find all amounts in the remaining line
        amounts = re.findall(r'([\d,]+\.?\d{2})', remaining_line)
        if len(amounts) < 2:  # Need at least amount and balance
            return None
        
        # Find transaction type (DR/CR)
        type_match = re.search(r'\b(DR|CR)\b', remaining_line)
        if not type_match:
            return None
        
        trans_type = type_match.group(1)
        
        # Split the line by the transaction type to separate description from balance/branch
        parts = remaining_line.split(trans_type, 1)
        if len(parts) != 2:
            return None
        
        description_part = parts[0].strip()
        balance_branch_part = parts[1].strip()
        
        # Extract amounts from description part (should be the main transaction amount)
        desc_amounts = re.findall(r'([\d,]+\.?\d{2})', description_part)
        if desc_amounts:
            amount = desc_amounts[-1]  # Take the last amount in description
            # Remove the amount from description
            description = description_part.replace(amount, '').strip()
        else:
            amount = amounts[0]  # Fallback to first amount
            description = description_part
        
        # Extract balance from balance_branch_part
        balance_amounts = re.findall(r'([\d,]+\.?\d{2})', balance_branch_part)
        if balance_amounts:
            balance = balance_amounts[0]  # First amount after DR/CR should be balance
            # Remove balance from the part to get branch
            branch = balance_branch_part.replace(balance, '').strip()
        else:
            balance = amounts[1] if len(amounts) > 1 else '0.00'
            branch = balance_branch_part
        
        return {
            'date': self._format_date(date.strip()),
            'description': description.strip(),
            'amount': self._parse_amount(amount),
            'amount_raw': amount,
            'transaction_type': trans_type.strip(),
            'balance': self._parse_amount(balance),
            'balance_raw': balance,
            'branch': branch.strip(),
            'section': section,
            'line_number': line_num,
            'full_text': line
        }

    def _parse_tabular_bank_data(self, line: str, section: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse tabular bank data with better column separation"""
        
        # Check if line contains tab-separated or fixed-width data
        # Look for multiple amounts and DR/CR indicators
        
        # Split by tabs first
        if '\t' in line:
            parts = line.split('\t')
            if len(parts) >= 4:  # Date, Description, Amount, Type, Balance, Branch
                try:
                    date = parts[0].strip()
                    description = parts[1].strip()
                    amount = parts[2].strip()
                    trans_type = parts[3].strip()
                    balance = parts[4].strip() if len(parts) > 4 else ''
                    branch = parts[5].strip() if len(parts) > 5 else ''
                    
                    return {
                        'date': self._format_date(date),
                        'description': description,
                        'amount': self._parse_amount(amount),
                        'amount_raw': amount,
                        'transaction_type': trans_type.upper(),
                        'balance': self._parse_amount(balance),
                        'balance_raw': balance,
                        'branch': branch,
                        'section': section,
                        'line_number': line_num,
                        'full_text': line
                    }
                except:
                    pass
        
        # Try to parse as space-separated columns with multiple amounts
        # Pattern: Date Description Amount Type Balance Branch
        # Look for the structure with multiple decimal amounts
        
        # Find all decimal amounts in the line
        amounts = re.findall(r'([\d,]+\.?\d{2})', line)
        if len(amounts) >= 2:  # Need at least transaction amount and balance
            
            # Find date
            date_match = re.search(r'(\d{1,2}-\d{1,2}-\d{4})', line)
            if not date_match:
                return None
            
            date = date_match.group(1)
            
            # Find transaction type
            type_match = re.search(r'\b(DR|CR)\b', line)
            if not type_match:
                return None
            
            trans_type = type_match.group(1)
            
            # Split line by transaction type to separate parts
            parts = line.split(trans_type, 1)
            if len(parts) != 2:
                return None
            
            before_type = parts[0].strip()
            after_type = parts[1].strip()
            
            # Extract description and amount from before_type part
            # Remove date from before_type
            before_type_clean = before_type.replace(date, '').strip()
            
            # Find amount in before_type_clean
            before_amounts = re.findall(r'([\d,]+\.?\d{2})', before_type_clean)
            if before_amounts:
                amount = before_amounts[-1]  # Last amount should be transaction amount
                description = before_type_clean.replace(amount, '').strip()
            else:
                amount = amounts[0]
                description = before_type_clean
            
            # Extract balance and branch from after_type part
            after_amounts = re.findall(r'([\d,]+\.?\d{2})', after_type)
            if after_amounts:
                balance = after_amounts[0]  # First amount after type should be balance
                branch = after_type.replace(balance, '').strip()
            else:
                balance = amounts[1] if len(amounts) > 1 else '0.00'
                branch = after_type
            
            return {
                'date': self._format_date(date),
                'description': description,
                'amount': self._parse_amount(amount),
                'amount_raw': amount,
                'transaction_type': trans_type.upper(),
                'balance': self._parse_amount(balance),
                'balance_raw': balance,
                'branch': branch,
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
            s = amount_str.strip()
            # Parentheses mean negative
            is_negative = s.startswith('(') and s.endswith(')')
            # Remove everything except digits, comma, dot, minus
            cleaned = re.sub(r'[^\d.,-]', '', s)
            # Remove thousands separators
            cleaned = cleaned.replace(',', '')
            if cleaned.count('-') > 1:
                cleaned = cleaned.replace('-', '', cleaned.count('-') - 1)
            value = float(cleaned) if cleaned else 0.0
            if is_negative and value > 0:
                value = -value
            return value
        except:
            return 0.0

    def create_dataframe(self, data: List[Dict[str, Any]]) -> pd.DataFrame:
        """Create DataFrame with only essential columns: Date, Description, Amount - enhanced formatting and validation"""
        if not data:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Filter essential columns for clean output (including new Indian bank fields)
        essential_columns = ['date', 'description', 'amount', 'transaction_type', 'balance', 'branch']
        available_columns = [col for col in essential_columns if col in df.columns]
        
        # Create clean DataFrame with available essential columns
        clean_df = df[available_columns].copy()
        
        # Rename columns to match desired format
        column_mapping = {
            'date': 'Date',
            'description': 'Description', 
            'amount': 'Amount',
            'transaction_type': 'Type',
            'balance': 'Balance',
            'branch': 'Branch'
        }
        
        clean_df = clean_df.rename(columns=column_mapping)
        
        # Handle NaN values and empty strings
        clean_df = clean_df.fillna('')
        
        # Data validation and cleaning
        if 'Date' in clean_df.columns:
            # Ensure dates are properly formatted strings
            clean_df['Date'] = clean_df['Date'].astype(str)
            # Replace empty or invalid dates
            clean_df['Date'] = clean_df['Date'].apply(lambda x: '' if x in ['', 'nan', 'None'] else x)
        
        if 'Description' in clean_df.columns:
            # Clean descriptions
            clean_df['Description'] = clean_df['Description'].astype(str)
            clean_df['Description'] = clean_df['Description'].apply(lambda x: x.strip() if x and x != 'nan' else '')
            # Replace empty descriptions
            clean_df['Description'] = clean_df['Description'].apply(lambda x: 'Transaction' if not x or x == '' else x)
        
        if 'Amount' in clean_df.columns:
            # Convert amount to numeric with better error handling
            clean_df['Amount'] = pd.to_numeric(clean_df['Amount'], errors='coerce').fillna(0)
            
            # Validate amounts (remove obviously wrong values)
            clean_df['Amount'] = clean_df['Amount'].apply(lambda x: 0 if abs(x) > 999999.99 or (x != 0 and abs(x) < 0.01) else x)
            
            # Format amounts with commas and 2 decimal places
            clean_df['Amount'] = clean_df['Amount'].apply(
                lambda x: f"{x:,.2f}" if x != 0 else "0.00"
            )
        
        if 'Type' in clean_df.columns:
            # Clean transaction type (DR/CR)
            clean_df['Type'] = clean_df['Type'].astype(str)
            clean_df['Type'] = clean_df['Type'].apply(lambda x: x.strip().upper() if x and x != 'nan' else '')
        
        if 'Balance' in clean_df.columns:
            # Convert balance to numeric and format
            clean_df['Balance'] = pd.to_numeric(clean_df['Balance'], errors='coerce').fillna(0)
            clean_df['Balance'] = clean_df['Balance'].apply(
                lambda x: f"{x:,.2f}" if x != 0 else "0.00"
            )
        
        if 'Branch' in clean_df.columns:
            # Clean branch names
            clean_df['Branch'] = clean_df['Branch'].astype(str)
            clean_df['Branch'] = clean_df['Branch'].apply(lambda x: x.strip() if x and x != 'nan' else '')
        
        # Final validation: remove rows where all essential fields are empty
        if len(clean_df) > 0:
            # Keep rows that have at least a date or description
            mask = (clean_df['Date'].str.strip() != '') | (clean_df['Description'].str.strip() != '')
            clean_df = clean_df[mask].reset_index(drop=True)
        
        return clean_df

    def validate_and_fix_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate and fix column alignment issues in the DataFrame"""
        if df.empty:
            return df
        
        # Create a copy to work with
        fixed_df = df.copy()
        
        # Check for common column misalignment issues
        for idx, row in fixed_df.iterrows():
            # If Date column contains non-date data, try to fix it
            if 'Date' in fixed_df.columns:
                date_val = str(row['Date']).strip()
                if date_val and not re.match(r'\d{4}-\d{2}-\d{2}', date_val):
                    # Try to extract a proper date from the description
                    desc = str(row['Description']).strip()
                    date_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{4}', desc)
                    if date_match:
                        fixed_df.at[idx, 'Date'] = self._format_date(date_match.group())
                        # Remove the date from description
                        fixed_df.at[idx, 'Description'] = desc.replace(date_match.group(), '').strip()
            
            # If Amount column contains non-numeric data, try to fix it
            if 'Amount' in fixed_df.columns:
                amount_val = str(row['Amount']).strip()
                if amount_val and not re.match(r'[\d,]+\.?\d{2}', amount_val):
                    # Try to extract amount from description
                    desc = str(row['Description']).strip()
                    amount_match = self._find_last_amount_string(desc)
                    if amount_match:
                        fixed_df.at[idx, 'Amount'] = f"{self._parse_amount(amount_match):,.2f}"
                        # Remove the amount from description
                        fixed_df.at[idx, 'Description'] = desc.replace(amount_match, '').strip()
            
            # If Type column is empty, try to extract DR/CR from description
            if 'Type' in fixed_df.columns:
                type_val = str(row['Type']).strip()
                if not type_val or type_val == '':
                    desc = str(row['Description']).strip()
                    type_match = re.search(r'\b(DR|CR|DEBIT|CREDIT)\b', desc, re.IGNORECASE)
                    if type_match:
                        fixed_df.at[idx, 'Type'] = type_match.group().upper()
                        # Remove the type from description
                        fixed_df.at[idx, 'Description'] = desc.replace(type_match.group(), '').strip()
            
            # If Balance column is empty, try to extract balance from description
            if 'Balance' in fixed_df.columns:
                balance_val = str(row['Balance']).strip()
                if not balance_val or balance_val == '0.00':
                    desc = str(row['Description']).strip()
                    # Look for balance pattern (large number that could be balance)
                    balance_matches = re.findall(r'[\d,]+\.?\d{2}', desc)
                    if balance_matches:
                        # Take the last large number as potential balance
                        for match in reversed(balance_matches):
                            amount = self._parse_amount(match)
                            if amount > 1000:  # Reasonable balance threshold
                                fixed_df.at[idx, 'Balance'] = f"{amount:,.2f}"
                                # Remove the balance from description
                                fixed_df.at[idx, 'Description'] = desc.replace(match, '').strip()
                                break
        
        return fixed_df

    def export_to_excel(self, data: List[Dict[str, Any]], filename: str = None) -> str:
        """Export to Excel with only main data sheet - no extra sheets, with improved column validation"""
        df = self.create_dataframe(data)
        
        if df.empty:
            raise ValueError("No data to export")
        
        # Apply column validation and fixing
        df = self.validate_and_fix_columns(df)
        
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