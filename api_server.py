# Flask API Server dla parsowania PDF
# Serwer API do integracji z aplikacją React/Bolt

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
from datetime import datetime
from pdf_expense_parser import UniversalPDFParser

app = Flask(__name__)

# --- CORS: czytane z ENV, z sensownym domyślnym zestawem ---
# USTAW w Render: ALLOWED_ORIGINS="https://apis.dupajasia.com,https://pdf-to-excel-csv-con-226z.bolt.host,http://localhost:3000"
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://apis.dupajasia.com,https://pdf-to-excel-csv-con-226z.bolt.host,http://localhost:3000"
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

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/parse-multiple-pdfs', methods=['POST'])
def parse_multiple_pdfs_endpoint():
    """Parsowanie wielu PDF (multipart/form-data, pola 'pdfs')"""
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
        summary = parser.generate_summary_report(df) if hasattr(df, "empty") and not df.empty else {}

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
            'supabase_saved': supabase_saved
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

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8-sig') as tmp_file:
            parser.export_to_csv(expenses, tmp_file.name)
            with open(tmp_file.name, 'r', encoding='utf-8-sig') as f:
                csv_content = f.read()
            os.unlink(tmp_file.name)

        return jsonify({
            'csv_content': csv_content,
            'filename': f'wydatki_{datetime.now().strftime("%Y%m%d")}.csv'
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

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            parser.export_to_excel(expenses, tmp_file.name)
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

        df = parser.create_expense_dataframe(expenses)
        summary = parser.generate_summary_report(df)
        return jsonify({'summary': summary, 'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Lokalne uruchomienie (na EB i tak odpali Gunicorn przez wsgi.py)
    app.run(debug=False, host='0.0.0.0', port=5000)
