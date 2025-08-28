# Main application file for Render.com deployment
import os
from api_server import app

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))