# Frontend-Backend Integration Guide

## Backend API Endpoints

Your backend is now running at: `https://bonkers-1.onrender.com`

### Health Check Endpoints
- **GET** `/health` - Basic health check
- **GET** `/api/health` - API health check with endpoint information

### PDF Parsing Endpoints
- **POST** `/api/parse-pdf` - Parse single PDF file
  - Form data: `pdf` (file)
  - Returns: Parsed expense data

- **POST** `/api/parse-multiple-pdfs` - Parse multiple PDF files
  - Form data: `pdfs` (multiple files)
  - Returns: Array of parsed results + summary

### Data Export Endpoints
- **POST** `/api/export-csv` - Export expenses to CSV
  - JSON body: `{"expenses": [...]}`
  - Returns: CSV content + filename

- **POST** `/api/export-excel` - Export expenses to Excel
  - JSON body: `{"expenses": [...]}`
  - Returns: Base64 encoded Excel file + filename

### Analysis Endpoints
- **POST** `/api/analyze` - Analyze expense data
  - JSON body: `{"expenses": [...]}`
  - Returns: Summary and analysis

## Frontend Configuration

### 1. Set Backend URL
In your frontend, configure the backend URL:

```javascript
// Environment variable or config
const BACKEND_URL = 'https://bonkers-1.onrender.com';

// Or for development
const BACKEND_URL = process.env.NODE_ENV === 'production' 
  ? 'https://bonkers-1.onrender.com'
  : 'http://localhost:5000';
```

### 2. API Service Functions

```javascript
// PDF Parsing
export const parsePDF = async (file) => {
  const formData = new FormData();
  formData.append('pdf', file);
  
  const response = await fetch(`${BACKEND_URL}/api/parse-pdf`, {
    method: 'POST',
    body: formData,
  });
  
  return response.json();
};

// Multiple PDFs
export const parseMultiplePDFs = async (files) => {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('pdfs', file);
  });
  
  const response = await fetch(`${BACKEND_URL}/api/parse-multiple-pdfs`, {
    method: 'POST',
    body: formData,
  });
  
  return response.json();
};

// Export CSV
export const exportToCSV = async (expenses) => {
  const response = await fetch(`${BACKEND_URL}/api/export-csv`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ expenses }),
  });
  
  const result = await response.json();
  
  // Download CSV
  const blob = new Blob([result.csv_content], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = result.filename;
  a.click();
  window.URL.revokeObjectURL(url);
};

// Export Excel
export const exportToExcel = async (expenses) => {
  const response = await fetch(`${BACKEND_URL}/api/export-excel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ expenses }),
  });
  
  const result = await response.json();
  
  // Download Excel
  const binaryString = atob(result.excel_content);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  
  const blob = new Blob([bytes], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = result.filename;
  a.click();
  window.URL.revokeObjectURL(url);
};
```

### 3. Error Handling

```javascript
const handleAPIError = (error) => {
  console.error('API Error:', error);
  
  if (error.status === 400) {
    // Bad request - validation error
    alert('Invalid data provided');
  } else if (error.status === 500) {
    // Server error
    alert('Server error occurred. Please try again.');
  } else {
    // Network or other error
    alert('Connection error. Please check your internet connection.');
  }
};
```

## Environment Variables in Render

Set these in your Render dashboard under Environment Variables:

```
ALLOWED_ORIGINS=https://bank-statement-conve-ywup.bolt.host,https://bank2converter.com,https://statement2sheet.com,http://localhost:3000
```

## Testing the Integration

1. **Test Health Endpoint**:
   ```bash
   curl https://bonkers-1.onrender.com/api/health
   ```

2. **Test CORS** (from browser console):
   ```javascript
   fetch('https://bonkers-1.onrender.com/api/health')
     .then(r => r.json())
     .then(console.log)
     .catch(console.error);
   ```

## Common Issues & Solutions

### CORS Errors
- Ensure `ALLOWED_ORIGINS` includes your frontend domain
- Check that the domain matches exactly (including protocol)

### File Upload Issues
- Ensure files are sent as `multipart/form-data`
- Check file size limits (Render has default limits)

### Network Errors
- Verify backend URL is correct
- Check if backend is running and accessible

## Next Steps

1. **Deploy the updated backend** with the new CORS configuration
2. **Update your frontend** to use the new API endpoints
3. **Test the integration** with a simple PDF upload
4. **Monitor the logs** in Render for any errors

Your backend is now properly configured for frontend integration! 🚀
