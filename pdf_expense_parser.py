# Universal PDF Parser - Converts ANY PDF to Structured Data
# Fast conversion to Excel/CSV format with columns and rows

import re
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

class UniversalPDFParser:
    def __init__(self):
        """Universal PDF parser for any type of document"""
        # Common data patterns to look for
        self.data_patterns = {
            'amounts': [
                r'[-+]?\$?\d{1,3}(?:,\d{3})*\.\d{2}',  # $1,234.56 or 1234.56
                r'[-+]?\d+\.\d{2}',  # 123.45
                r'[-+]?\d+',  # 123
            ],
            'dates': [
                r'\d{1,2}[/-]\d{1,2}[/-]\d{4}',  # MM/DD/YYYY
                r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY/MM/DD
                r'\d{1,2}\.\d{1,2}\.\d{4}',  # MM.DD.YYYY
            ],
            'emails': [
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            ],
            'phones': [
                r'\+?1?[-.\s]?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'
            ]
        }

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        try:
            import PyPDF2
            
            text = ""
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            
            return text
        except ImportError:
            raise Exception("PyPDF2 not installed. Use: pip install PyPDF2")
        except Exception as e:
            raise Exception(f"Error reading PDF: {str(e)}")

    def parse_pdf_to_structured_data(self, pdf_path: str) -> Dict:
        """Main function: Parse ANY PDF to structured data"""
        try:
            # Extract text from PDF
            text = self.extract_text_from_pdf(pdf_path)
            
            if not text.strip():
                return {
                    'error': 'No text found in PDF',
                    'fileName': pdf_path.split('/')[-1],
                    'success': False
                }
            
            print(f"📄 PDF loaded: {len(text)} characters")
            print(f"📄 First 200 chars: {text[:200]}...")
            
            # Parse the text into structured data
            structured_data = self._extract_structured_data(text)
            
            return {
                'structured_data': structured_data,
                'raw_text': text,
                'fileName': pdf_path.split('/')[-1],
                'success': True,
                'total_rows': len(structured_data)
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'fileName': pdf_path.split('/')[-1],
                'success': False
            }

    def _extract_structured_data(self, text: str) -> List[Dict]:
        """Extract structured data from text"""
        lines = text.split('\n')
        structured_data = []
        
        print(f"🔍 Processing {len(lines)} lines...")
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or len(line) < 3:
                continue
            
            # Extract data from this line
            row_data = self._extract_line_data(line, line_num)
            if row_data:
                structured_data.append(row_data)
        
        print(f"✅ Extracted {len(structured_data)} structured rows")
        return structured_data

    def _extract_line_data(self, line: str, line_num: int) -> Optional[Dict]:
        """Extract data from a single line"""
        try:
            # Look for amounts
            amounts = []
            for pattern in self.data_patterns['amounts']:
                matches = re.findall(pattern, line)
                amounts.extend([float(match.replace('$', '').replace(',', '')) for match in matches])
            
            # Look for dates
            dates = []
            for pattern in self.data_patterns['dates']:
                matches = re.findall(pattern, line)
                dates.extend(matches)
            
            # Look for emails
            emails = []
            for pattern in self.data_patterns['emails']:
                matches = re.findall(pattern, line)
                emails.extend(matches)
            
            # Look for phones
            phones = []
            for pattern in self.data_patterns['phones']:
                matches = re.findall(pattern, line)
                phones.extend(matches)
            
            # Create row data
            row_data = {
                'line_number': line_num + 1,
                'raw_text': line,
                'amounts': amounts,
                'dates': dates,
                'emails': emails,
                'phones': phones,
                'word_count': len(line.split()),
                'has_numbers': bool(re.search(r'\d', line)),
                'has_currency': bool(re.search(r'[\$€£¥]', line))
            }
            
            # Add extracted values as separate columns
            if amounts:
                row_data['primary_amount'] = amounts[0]
                row_data['all_amounts'] = amounts
            if dates:
                row_data['primary_date'] = dates[0]
                row_data['all_dates'] = dates
            if emails:
                row_data['primary_email'] = emails[0]
                row_data['all_emails'] = emails
            if phones:
                row_data['primary_phone'] = phones[0]
                row_data['all_phones'] = phones
            
            return row_data
            
        except Exception as e:
            print(f"❌ Error processing line {line_num}: {e}")
            return None

    def create_dataframe(self, structured_data: List[Dict]) -> pd.DataFrame:
        """Convert structured data to pandas DataFrame"""
        if not structured_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(structured_data)
        
        # Clean up the DataFrame
        df = df.fillna('')
        
        # Convert lists to strings for better Excel export
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace('[', '').str.replace(']', '')
        
        return df

    def export_to_excel(self, structured_data: List[Dict], output_path: str):
        """Export to Excel with multiple sheets"""
        df = self.create_dataframe(structured_data)
        
        if df.empty:
            raise Exception("No data to export")
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Main data sheet
            df.to_excel(writer, sheet_name='Extracted Data', index=False)
            
            # Summary sheet
            summary_data = [
                ['Total Rows', len(df)],
                ['Lines with Amounts', len(df[df['amounts'].str.len() > 0])],
                ['Lines with Dates', len(df[df['dates'].str.len() > 0])],
                ['Lines with Emails', len(df[df['emails'].str.len() > 0])],
                ['Lines with Phones', len(df[df['phones'].str.len() > 0])],
                ['Lines with Numbers', df['has_numbers'].sum()],
                ['Lines with Currency', df['has_currency'].sum()],
                ['Total Word Count', df['word_count'].sum()]
            ]
            
            summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Value'])
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Data types sheet
            data_types = []
            for col in df.columns:
                non_empty = df[col].astype(str).str.strip().ne('').sum()
                data_types.append([col, non_empty, len(df) - non_empty])
            
            types_df = pd.DataFrame(data_types, columns=['Column', 'Non-Empty', 'Empty'])
            types_df.to_excel(writer, sheet_name='Data Types', index=False)
        
        print(f"✅ Excel file exported: {output_path}")

    def export_to_csv(self, structured_data: List[Dict], output_path: str):
        """Export to CSV"""
        df = self.create_dataframe(structured_data)
        
        if df.empty:
            raise Exception("No data to export")
        
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✅ CSV file exported: {output_path}")

def main():
    """Example usage"""
    parser = UniversalPDFParser()
    
    # Test with a PDF file
    pdf_file = 'test.pdf'  # Replace with your PDF path
    
    try:
        print("🚀 Starting universal PDF parsing...")
        
        # Parse PDF to structured data
        result = parser.parse_pdf_to_structured_data(pdf_file)
        
        if result['success']:
            print(f"✅ Successfully parsed {result['total_rows']} rows")
            
            # Export to Excel and CSV
            parser.export_to_excel(result['structured_data'], 'extracted_data.xlsx')
            parser.export_to_csv(result['structured_data'], 'extracted_data.csv')
            
        else:
            print(f"❌ Error: {result['error']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()