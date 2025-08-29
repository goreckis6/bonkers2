# Flask API Server dla parsowania PDF
# Serwer API do integracji z aplikacją React/Bolt

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
from datetime import datetime
import pandas as pd
from pdf_expense_parser import UniversalPDFParser

app = Flask(__name__)

# --- CORS: czytane z ENV, z sensownym domyślnym zestawem ---
# USTAW w Render: ALLOWED_ORIGINS="https://apis.dupajasia.com,https://bank-statement-conve-grtt.bolt.host,https://pdf-to-excel-csv-con-226z.bolt.host,http://localhost:3000"
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://apis.dupajasia.com,https://bank-statement-conve-grtt.bolt.host,https://pdf-to-excel-csv-con-226z.bolt.host,http://localhost:3000"
).split(",")

# Apply CORS to all routes
CORS(
    app,
    origins=[o.strip() for o in ALLOWED_ORIGINS],
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

parser = UniversalPDFParser()

# --- Supabase (opcjonalnie) ---
SUPABASE_ENABLED = False
supabase_manager = None
try:
    from supabase_client import SupabaseExpenseManager
    supabase_manager = SupabaseExpenseManager()
    SUPABASE_ENABLED = True
    print("✓ Supabase connection initialized")
except Exception as e:
    print(f"⚠ Supabase not configured: {e}")

@app.route('/api/parse-pdf', methods=['POST', 'GET'])
def parse_pdf_endpoint():
    """Parsowanie pojedynczego PDF (multipart/form-data, pole 'pdf')"""
    
    if request.method == 'GET':
        return jsonify({
            'message': 'PDF Parser Endpoint',
            'method': 'POST',
            'description': 'Send PDF file via POST request with form-data field "pdf"',
            'example': 'Use POST method with multipart/form-data containing PDF file'
        })
    
    # POST method - actual PDF parsing
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'Brak pliku PDF'}), 400
        file = request.files['pdf']
        if not file.filename:
            return jsonify({'error': 'Nie wybrano pliku'}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            result = parser.parse_pdf_to_structured_data(tmp_file.name)
            os.unlink(tmp_file.name)

        if SUPABASE_ENABLED and result.get('success'):
            try:
                supabase_result = supabase_manager.save_expense(result)
                result['supabase_saved'] = supabase_result.get('success', False)
            except Exception as e:
                result['supabase_saved'] = False
                result['supabase_error'] = str(e)

        # Return data in format that frontend can export
        if result.get('success') and result.get('structured_data'):
            # Add the structured data for export
            result['export_data'] = result['structured_data']
            result['total_rows'] = len(result['structured_data'])
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/parse-multiple-pdfs', methods=['POST', 'GET'])
def parse_multiple_pdfs_endpoint():
    """Parsowanie wielu PDF (multipart/form-data, pola 'pdfs')"""
    
    if request.method == 'GET':
        return jsonify({
            'message': 'Multiple PDF Parser Endpoint',
            'method': 'POST',
            'description': 'Send multiple PDF files via POST request with form-data field "pdfs"',
            'example': 'Use POST method with multipart/form-data containing multiple PDF files',
            'note': 'This endpoint processes multiple PDFs and returns combined results'
        })
    
    # POST method - actual PDF parsing
    try:
        files = request.files.getlist('pdfs')
        if not files:
            return jsonify({'error': 'Brak plików PDF'}), 400

        results = []
        for f in files:
            if f and f.filename.endswith('.pdf'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    f.save(tmp_file.name)
                    try:
                        results.append(parser.parse_pdf_to_structured_data(tmp_file.name))
                    finally:
                        os.unlink(tmp_file.name)

        df = parser.create_dataframe(results[0]['structured_data'] if results else [])
        # Generate basic summary since generate_summary_report method doesn't exist
        summary = {
            'total_rows': len(df) if hasattr(df, "empty") and not df.empty else 0,
            'columns': list(df.columns) if hasattr(df, "empty") and not df.empty else [],
            'data_types': {col: str(dtype) for col, dtype in df.dtypes.items()} if hasattr(df, "empty") and not df.empty else {}
        }

        # Add export_data for consistency with single PDF endpoint
        export_data = results[0]['structured_data'] if results and results[0].get('success') else []
        total_rows = len(export_data)

        supabase_saved = False
        if SUPABASE_ENABLED:
            try:
                supabase_result = supabase_manager.save_multiple_expenses(results)
                supabase_saved = supabase_result.get('success', False)
            except Exception:
                supabase_saved = False

        return jsonify({
            'results': results,
            'summary': summary,
            'total_files': len(files),
            'successful_files': len([r for r in results if r.get('success')]),
            'supabase_saved': supabase_saved,
            'export_data': export_data,      # ✅ Added for consistency
            'total_rows': total_rows,        # ✅ Added for consistency
            'success': len([r for r in results if r.get('success')]) > 0  # ✅ Added success flag
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-csv', methods=['POST'])
def export_csv_endpoint():
    """Eksport CSV z danych z frontu: JSON { "expenses": [...] }"""
    try:
        data = request.json or {}
        expenses = data.get('expenses', [])
        if not expenses:
            return jsonify({'error': 'Brak danych do eksportu'}), 400

        # Convert to DataFrame first for universal parser
        try:
            df = parser.create_dataframe(expenses)
            if df.empty:
                return jsonify({'error': 'No data to export'}), 400
        except Exception as e:
            return jsonify({'error': f'Error creating DataFrame: {str(e)}'}), 500
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8-sig') as tmp_file:
            df.to_csv(tmp_file.name, index=False, encoding='utf-8-sig')
            with open(tmp_file.name, 'r', encoding='utf-8-sig') as f:
                csv_content = f.read()
            os.unlink(tmp_file.name)

        return jsonify({
            'csv_content': csv_content,
            'filename': f'wydatki_{datetime.now().strftime("%Y%m%d")}.csv'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-pdf-data-csv', methods=['POST'])
def export_pdf_data_csv_endpoint():
    """Eksport CSV z danych PDF (nowy endpoint dla universal parser)"""
    try:
        data = request.json or {}
        pdf_data = data.get('pdf_data', [])
        if not pdf_data:
            return jsonify({'error': 'Brak danych PDF do eksportu'}), 400
        


        # Convert to DataFrame
        try:
            df = parser.create_dataframe(pdf_data)
            if df.empty:
                return jsonify({'error': 'No data to export'}), 400
        except Exception as e:
            return jsonify({'error': f'Error creating DataFrame: {str(e)}'}), 500
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8-sig') as tmp_file:
            df.to_csv(tmp_file.name, index=False, encoding='utf-8-sig')
            with open(tmp_file.name, 'r', encoding='utf-8-sig') as f:
                csv_content = f.read()
            os.unlink(tmp_file.name)

        return jsonify({
            'csv_content': csv_content,
            'filename': f'pdf_data_{datetime.now().strftime("%Y%m%d")}.csv'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-excel', methods=['POST'])
def export_excel_endpoint():
    """Eksport Excel (base64) z danych z frontu: JSON { "expenses": [...] }"""
    try:
        import base64
        data = request.json or {}
        expenses = data.get('expenses', [])
        if not expenses:
            return jsonify({'error': 'Brak danych do eksportu'}), 400
        


        # Convert to DataFrame first for universal parser
        try:
            df = parser.create_dataframe(expenses)
            if df.empty:
                return jsonify({'error': 'No data to export'}), 400
        except Exception as e:
            return jsonify({'error': f'Error creating DataFrame: {str(e)}'}), 500
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            with pd.ExcelWriter(tmp_file.name, engine='openpyxl') as writer:
                # Main data sheet
                df.to_excel(writer, sheet_name='Extracted Data', index=False)
                
                # Summary sheet
                summary_data = [
                    ['Total Rows', len(df)],
                    ['Lines with Amounts', len(df[df['amounts'].str.len() > 0]) if 'amounts' in df.columns else 0],
                    ['Lines with Dates', len(df[df['dates'].str.len() > 0]) if 'dates' in df.columns else 0],
                    ['Lines with Emails', len(df[df['emails'].str.len() > 0]) if 'emails' in df.columns else 0],
                    ['Lines with Phones', len(df[df['phones'].str.len() > 0]) if 'phones' in df.columns else 0],
                    ['Lines with Numbers', df['has_numbers'].sum() if 'has_numbers' in df.columns else 0],
                    ['Lines with Currency', df['has_currency'].sum() if 'has_currency' in df.columns else 0],
                    ['Total Word Count', df['word_count'].sum() if 'word_count' in df.columns else 0]
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
            
            with open(tmp_file.name, 'rb') as f:
                excel_content = f.read()
            os.unlink(tmp_file.name)

        excel_b64 = base64.b64encode(excel_content).decode('utf-8')
        return jsonify({
            'excel_content': excel_b64,
            'filename': f'wydatki_{datetime.now().strftime("%Y%m%d")}.xlsx'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-pdf-data-excel', methods=['POST'])
def export_pdf_data_excel_endpoint():
    """Eksport Excel z danych PDF (nowy endpoint dla universal parser)"""
    try:
        import base64
        data = request.json or {}
        pdf_data = data.get('pdf_data', [])
        if not pdf_data:
            return jsonify({'error': 'Brak danych PDF do eksportu'}), 400
        


        # Convert to DataFrame
        try:
            df = parser.create_dataframe(pdf_data)
            if df.empty:
                return jsonify({'error': 'No data to export'}), 400
        except Exception as e:
            return jsonify({'error': f'Error creating DataFrame: {str(e)}'}), 500
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            with pd.ExcelWriter(tmp_file.name, engine='openpyxl') as writer:
                # Main data sheet
                df.to_excel(writer, sheet_name='Extracted Data', index=False)
                
                # Summary sheet
                summary_data = [
                    ['Total Rows', len(df)],
                    ['Lines with Amounts', len(df[df['amounts'].str.len() > 0]) if 'amounts' in df.columns else 0],
                    ['Lines with Dates', len(df[df['dates'].str.len() > 0]) if 'dates' in df.columns else 0],
                    ['Lines with Emails', len(df[df['emails'].str.len() > 0]) if 'emails' in df.columns else 0],
                    ['Lines with Phones', len(df[df['phones'].str.len() > 0]) if 'phones' in df.columns else 0],
                    ['Lines with Numbers', df['has_numbers'].sum() if 'has_numbers' in df.columns else 0],
                    ['Lines with Currency', df['has_currency'].sum() if 'has_currency' in df.columns else 0],
                    ['Total Word Count', df['word_count'].sum() if 'word_count' in df.columns else 0]
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
            
            with open(tmp_file.name, 'rb') as f:
                excel_content = f.read()
            os.unlink(tmp_file.name)

        excel_b64 = base64.b64encode(excel_content).decode('utf-8')
        return jsonify({
            'excel_content': excel_b64,
            'filename': f'pdf_data_{datetime.now().strftime("%Y%m%d")}.xlsx'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/expenses', methods=['GET'])
def get_expenses_endpoint():
    """Odczyt z Supabase (opcjonalne)"""
    if not SUPABASE_ENABLED:
        return jsonify({'error': 'Supabase not configured'}), 400
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        result = supabase_manager.get_expenses(limit, offset)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/expenses/summary', methods=['GET'])
def get_expense_summary_endpoint():
    """Podsumowanie z Supabase (opcjonalne)"""
    if not SUPABASE_ENABLED:
        return jsonify({'error': 'Supabase not configured'}), 400
    try:
        result = supabase_manager.get_expense_summary()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
def update_expense_endpoint(expense_id):
    """Aktualizacja w Supabase (opcjonalne)"""
    if not SUPABASE_ENABLED:
        return jsonify({'error': 'Supabase not configured'}), 400
    try:
        data = request.json or {}
        result = supabase_manager.update_expense(expense_id, data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense_endpoint(expense_id):
    """Usuwanie w Supabase (opcjonalne)"""
    if not SUPABASE_ENABLED:
        return jsonify({'error': 'Supabase not configured'}), 400
    try:
        result = supabase_manager.delete_expense(expense_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Healthcheck dla ALB/EB"""
    return jsonify({
        'status': 'OK',
        'message': 'Enhanced PDF Parser API działa poprawnie',
        'supabase_enabled': SUPABASE_ENABLED,
    })

@app.route('/api/health', methods=['GET'])
def api_health_check():
    """API Healthcheck endpoint"""
    return jsonify({
        'status': 'OK',
        'message': 'Enhanced PDF Parser API działa poprawnie',
        'supabase_enabled': SUPABASE_ENABLED,
        'endpoints': {
            'parse_pdf': '/api/parse-pdf',
            'parse_multiple': '/api/parse-multiple-pdfs',
            'export_csv': '/api/export-csv',
            'export_excel': '/api/export-excel',
            'export_pdf_data_csv': '/api/export-pdf-data-csv',
            'export_pdf_data_excel': '/api/export-pdf-data-excel',
            'analyze': '/api/analyze'
        }
    })

@app.route('/api/analyze', methods=['POST'])
def analyze_endpoint():
    """Analiza wydatków: JSON { "expenses": [...] }"""
    try:
        data = request.json or {}
        expenses = data.get('expenses', [])
        if not expenses:
            return jsonify({'error': 'Brak danych do analizy'}), 400

        df = parser.create_dataframe(expenses)
        summary = {
            'total_rows': len(df),
            'columns': list(df.columns),
            'data_types': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'non_empty_counts': {col: df[col].astype(str).str.strip().ne('').sum() for col in df.columns}
        }
        return jsonify({'summary': summary, 'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Lokalne uruchomienie (na EB i tak odpali Gunicorn przez wsgi.py)
    app.run(debug=False, host='0.0.0.0', port=5000)
