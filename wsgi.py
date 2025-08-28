# WSGI entry point for Render.com deployment
from api_server import app

# Expose the Flask app for WSGI
application = app