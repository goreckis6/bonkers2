from setuptools import setup, find_packages

setup(
    name="bonkers",
    version="1.0.0",
    description="Enhanced PDF Expense Parser with Bank Statements Support",
    packages=find_packages(),
    install_requires=[
        "PyPDF2==3.0.1",
        "pandas==1.5.3",
        "openpyxl==3.1.2",
        "regex==2023.8.8",
        "numpy==1.24.3",
        "python-dateutil==2.8.2",
        "flask==2.3.2",
        "flask-cors==4.0.0",
        "xlsxwriter==3.1.2",
        "python-dotenv==1.0.0",
        "gunicorn==20.1.0"
    ],
    python_requires=">=3.9,<3.11",
)