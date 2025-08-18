from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pdfplumber
import io
import json
import os
import csv
from dotenv import load_dotenv
import google.generativeai as genai
import re
import time
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import sys
import traceback

# Configure logging for Vercel
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
logger.info("Loading environment variables...")

app = Flask(__name__)
CORS(app, origins=["https://packingslip-parser.vercel.app", "http://localhost:3000", "*"])
logger.info("Flask app initialized with CORS")

# Global error handler
@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"Unhandled exception: {str(e)}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    return jsonify({
        "error": "Internal server error",
        "message": str(e),
        "type": type(e).__name__
    }), 500

# Request logging middleware
@app.before_request
def log_request_info():
    logger.info('=== INCOMING REQUEST ===')
    logger.info(f'Method: {request.method}')
    logger.info(f'URL: {request.url}')
    logger.info(f'Remote Address: {request.remote_addr}')
    logger.info(f'User Agent: {request.headers.get("User-Agent")}')
    logger.info(f'Content Type: {request.headers.get("Content-Type")}')
    if request.method in ['POST', 'PUT', 'PATCH']:
        logger.info(f'Content Length: {request.headers.get("Content-Length")}')

@app.after_request
def log_response_info(response):
    logger.info(f'Response Status: {response.status_code}')
    logger.info('=== REQUEST COMPLETED ===')
    return response

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
GEMINI_TEMPERATURE = float(os.getenv('GEMINI_TEMPERATURE', '0.1'))

logger.info(f"Gemini Model: {GEMINI_MODEL}")
logger.info(f"Gemini Temperature: {GEMINI_TEMPERATURE}")
logger.info(f"API Key present: {'Yes' if GEMINI_API_KEY else 'No'}")
logger.info(f"API Key length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}")

# Rate limiting for Gemini 2.5 Flash Lite (15 RPM)
RATE_LIMIT_RPM = 15
RATE_LIMIT_INTERVAL = 60.0 / RATE_LIMIT_RPM  # 4 seconds between requests

@app.route('/test', methods=['GET'])
def test_api():
    """Test endpoint to verify API is working"""
    logger.info("Test API endpoint called")
    return jsonify({
        "status": "API is working!",
        "gemini_key_exists": bool(GEMINI_API_KEY),
        "timestamp": time.time()
    })

if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == '':
    error_msg = "GEMINI_API_KEY not found in environment variables"
    logger.error(error_msg)
    raise ValueError(error_msg)

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    logger.info("Gemini AI configured successfully")
except Exception as e:
    logger.error(f"Failed to configure Gemini AI: {str(e)}")
    raise

# Rate limiting mechanism
class RateLimiter:
    def __init__(self, max_calls_per_minute=15):
        self.max_calls = max_calls_per_minute
        self.calls = []
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            # Remove calls older than 1 minute
            self.calls = [call_time for call_time in self.calls if now - call_time < 60]
            
            if len(self.calls) >= self.max_calls:
                # Wait until the oldest call is more than 1 minute old
                wait_time = 60 - (now - self.calls[0]) + 0.1  # Add small buffer
                if wait_time > 0:
                    time.sleep(wait_time)
                    # Update calls list after waiting
                    now = time.time()
                    self.calls = [call_time for call_time in self.calls if now - call_time < 60]
            
            self.calls.append(now)

rate_limiter = RateLimiter(RATE_LIMIT_RPM)

def parse_multiple_packing_slips_batch(pages_text_list):
    """
    Parse multiple packing slips in a single AI call for faster processing
    """
    if len(pages_text_list) > 20:
        # If too many pages, split into smaller batches to avoid token limits
        results = []
        for i in range(0, len(pages_text_list), 20):
            batch = pages_text_list[i:i+20]
            batch_results = parse_multiple_packing_slips_batch(batch)
            results.extend(batch_results)
        return results
    
    # Create batch prompt with all packing slips
    batch_prompt = """
You are an expert data extraction system for Canadian packing slips. Process ALL packing slips below and return a JSON array with one object per packing slip.

For each packing slip, extract these fields:
{
    "customerId": "10-digit customer number (NOT purchase order number)",
    "companyName": "Company name if present, otherwise use person's name",
    "attention": "Person's name (first and last name)",
    "address1": "Street address with apartment/unit/buzzer if present",
    "cityOrTown": "City name only (e.g., 'Red Deer', 'East St Paul', 'North York')",
    "stateProvinceCounty": "2-letter province code (e.g., 'ON', 'BC', 'AB')",
    "postalCode": "Canadian postal code in format A1A1A1 (no spaces)",
    "telephone": "10-digit phone number",
    "upsService": "UPS service type (usually 'UPS Express Saver')",
    "quantity": 1
}

CRITICAL EXTRACTION RULES:
1. Customer ID: Look for "14-digit-number 10-digit-number dd/dd/yyyy" - extract ONLY the 10-digit middle number
2. Company: If no business name found, use person's name
3. Address: Include apt/unit/buzzer in address1
4. Quantity: Look for "X GINGER DEFENCE" where X is the quantity

Return ONLY a JSON array: [{"customerId": "...", ...}, {"customerId": "...", ...}]

PACKING SLIPS TO PROCESS:
"""
    
    for i, (page_num, text) in enumerate(pages_text_list):
        batch_prompt += f"\n--- PACKING SLIP {i+1} (Page {page_num+1}) ---\n{text}\n"
    
    batch_prompt += "\nReturn ONLY the JSON array with one object per packing slip:"
    
    try:
        # Apply rate limiting
        rate_limiter.wait_if_needed()
        
        response = model.generate_content(
            batch_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=4000,  # Increased for batch processing
            )
        )
        
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:-3]
        elif response_text.startswith('```'):
            response_text = response_text[3:-3]
        
        # Parse JSON array
        results = json.loads(response_text)
        
        if not isinstance(results, list):
            # If single object returned, convert to list
            results = [results] if isinstance(results, dict) else []
        
        # Process and validate each result
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, dict):
                # Ensure all required fields are present
                required_fields = ['customerId', 'companyName', 'attention', 'address1', 
                                  'cityOrTown', 'stateProvinceCounty', 'postalCode', 
                                  'telephone', 'upsService', 'quantity']
                
                for field in required_fields:
                    if field not in result:
                        result[field] = 'Not found'
                
                # Ensure quantity is integer
                if isinstance(result['quantity'], str):
                    try:
                        result['quantity'] = int(result['quantity'])
                    except:
                        result['quantity'] = 1
                
                # Company name fallback
                if (result.get('companyName') == 'Not found' or 
                    result.get('companyName') == '' or 
                    result.get('companyName') is None):
                    result['companyName'] = result.get('attention', 'Not found')
                
                # Add page reference
                if i < len(pages_text_list):
                    result['page_number'] = pages_text_list[i][0] + 1
                
                processed_results.append(result)
        
        return processed_results
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error in batch processing: {str(e)}")
        # Fallback to individual processing
        return parse_pages_individually(pages_text_list)
        
    except Exception as e:
        print(f"Batch processing error: {str(e)}")
        # Fallback to individual processing
        return parse_pages_individually(pages_text_list)

def parse_pages_individually(pages_text_list):
    """Fallback method to process pages individually"""
    results = []
    for page_num, text in pages_text_list:
        try:
            data = parse_packing_slip_with_ai(text)
            if data.get('customerId') != 'Not found' or data.get('attention') != 'Not found':
                data['page_number'] = page_num + 1
                results.append(data)
        except Exception as e:
            print(f"Error processing page {page_num + 1}: {str(e)}")
            continue
    return results

def parse_packing_slip_with_ai(text):
    """
    Parse packing slip using Gemini AI for 100% accuracy
    """
    prompt = f"""
You are an expert data extraction system for Canadian packing slips. Extract the following information from this packing slip text with 100% accuracy:

PACKING SLIP TEXT:
{text}

Extract these exact fields and return ONLY a valid JSON object:

{{
    "customerId": "10-digit customer number (NOT purchase order number)",
    "companyName": "Company name if present, otherwise same as attention",
    "attention": "Person's name (first and last name)",
    "address1": "Street address with apartment/unit/buzzer if present",
    "cityOrTown": "City name only (e.g., 'Red Deer', 'East St Paul', 'North York')",
    "stateProvinceCounty": "2-letter province code (e.g., 'ON', 'BC', 'AB')",
    "postalCode": "Canadian postal code in format A1A1A1 (no spaces)",
    "telephone": "10-digit phone number",
    "upsService": "UPS service type (usually 'UPS Express Saver')",
    "quantity": 1
}}

CRITICAL EXTRACTION RULES:
1. Customer ID: Look for the pattern "14-digit-number 10-digit-number dd/dd/yyyy" - extract ONLY the 10-digit middle number, NOT the purchase order number
   Example: "12345678901234 1214327946 01/15/2025" → customerId should be "1214327946"
2. Company vs Person: If text contains "Ltd", "Inc", "Corp", "Construction", "Company" - that's the company name. If NO company is found, use the person's name for companyName
3. Address: Include apartment numbers, unit numbers, buzzer codes in address1
4. City: Extract only the city name, not street parts (e.g., "HENDERSON HWY EAST ST PAUL" → city is "EAST ST PAUL")
5. Phone: 10-digit Canadian format, may have dashes or spaces
6. Postal Code: Canadian format like "A1A 1A1" - remove spaces for output
7. Quantity: Look for "X GINGER DEFENCE" where X is the quantity number
8. If any field cannot be found, use "Not found"

Return ONLY the JSON object, no other text.
"""

    try:
        # Apply rate limiting before making API call
        rate_limiter.wait_if_needed()
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=GEMINI_TEMPERATURE,
                max_output_tokens=1000,
            )
        )
        
        # Extract JSON from response
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith('```json'):
            response_text = response_text[7:-3]
        elif response_text.startswith('```'):
            response_text = response_text[3:-3]
        
        # Parse JSON
        result = json.loads(response_text)
        
        # Ensure all required fields are present
        required_fields = ['customerId', 'companyName', 'attention', 'address1', 
                          'cityOrTown', 'stateProvinceCounty', 'postalCode', 
                          'telephone', 'upsService', 'quantity']
        
        for field in required_fields:
            if field not in result:
                result[field] = 'Not found'
        
        # Ensure quantity is integer
        if isinstance(result['quantity'], str):
            try:
                result['quantity'] = int(result['quantity'])
            except:
                result['quantity'] = 1
        
        # If company name is not found or empty, use the person's name
        if (result.get('companyName') == 'Not found' or 
            result.get('companyName') == '' or 
            result.get('companyName') is None):
            result['companyName'] = result.get('attention', 'Not found')
        
        return result
        
    except json.JSONDecodeError as e:
        return create_empty_result()
        
    except Exception as e:
        return create_empty_result()

def create_empty_result():
    """Create empty result structure when AI extraction fails"""
    return {
        'customerId': 'Not found',
        'companyName': 'Not found', 
        'attention': 'Not found',
        'address1': 'Not found',
        'cityOrTown': 'Not found',
        'stateProvinceCounty': 'Not found',
        'postalCode': 'Not found',
        'telephone': 'Not found',
        'upsService': 'Not found',
        'quantity': 1
    }

@app.route('/', methods=['GET'])
def root():
    """Root endpoint for API"""
    return jsonify({
        "message": "Packing Slip Parser API",
        "status": "running",
        "endpoints": ["/health", "/upload", "/test-ai"]
    })

@app.route('/upload', methods=['POST'])
def upload_pdf():
    logger.info("=== UPLOAD ENDPOINT CALLED ===")
    try:
        logger.info(f"Request method: {request.method}")
        logger.info(f"Request files: {list(request.files.keys())}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        if 'file' not in request.files:
            logger.error("No file provided in request")
            return jsonify({"error": "No file provided"}), 400
        
        pdf_file = request.files['file']
        logger.info(f"File received: {pdf_file.filename}")
        
        if pdf_file.filename == '':
            logger.error("Empty filename received")
            return jsonify({"error": "No file selected"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            logger.error(f"Invalid file type: {pdf_file.filename}")
            return jsonify({"error": "File must be a PDF"}), 400
        
        logger.info(f"Processing PDF: {pdf_file.filename}")
        
        # Extract all text from PDF first
        pages_text = []
        with pdfplumber.open(pdf_file.stream) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"Total pages in PDF: {total_pages}")
            
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        pages_text.append((i, text))
                except Exception as e:
                    print(f"Error extracting text from page {i + 1}: {str(e)}")
                    continue
        
        if not pages_text:
            return jsonify({"error": "No readable text found in PDF"}), 400
        
        print(f"Found text on {len(pages_text)} pages")
        
        # Use batch processing for faster results
        # Process in batches of 10 packing slips per API call
        batch_size = 10
        records = []
        
        total_batches = (len(pages_text) + batch_size - 1) // batch_size
        print(f"Processing {len(pages_text)} pages in {total_batches} batches of up to {batch_size} pages each")
        
        for i in range(0, len(pages_text), batch_size):
            batch = pages_text[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} pages)")
            
            # Use batch processing
            batch_results = parse_multiple_packing_slips_batch(batch)
            records.extend(batch_results)
            
            # Progress update
            processed_pages = min(i + batch_size, len(pages_text))
            print(f"Completed batch {batch_num}: {len(batch_results)} records found. Total processed: {processed_pages}/{len(pages_text)} pages, {len(records)} total records")
        
        if not records:
            return jsonify({"error": "No valid packing slip data found in PDF"}), 400
        
        print(f"Final result: {len(records)} valid records extracted from {len(pages_text)} pages")
        
        # Remove page_number before creating CSV
        for record in records:
            record.pop('page_number', None)
        
        # Add calculated fields using native Python
        for record in records:
            record['packages'] = record['quantity'] * 2
            record['packageWeight'] = '4.5kg'
            record['type'] = '24 Pack'
            record['totalWeight'] = str(record['quantity'] * 9) + 'kg'  # 4.5kg * 2 packages = 9kg per quantity
            record['shipper'] = 'K100C4'
            record['billTransportationTo'] = 'shipper'
            record['countryTerritory'] = 'Canada'
        
        # Define column order to match reference CSV
        column_order = ['customerId', 'companyName', 'attention', 'address1', 
                       'stateProvinceCounty', 'countryTerritory', 'postalCode', 
                       'cityOrTown', 'telephone', 'upsService', 'packages', 
                       'packageWeight', 'type', 'totalWeight', 'shipper', 'billTransportationTo']
        
        
        # Create CSV using native Python csv module
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=column_order, extrasaction='ignore')
        writer.writeheader()
        
        # Write records, filling missing fields with 'Not found'
        for record in records:
            row = {}
            for field in column_order:
                row[field] = record.get(field, 'Not found')
            writer.writerow(row)
        
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name='packing_slip_data.csv'
        )
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

@app.route('/test-ai', methods=['POST'])
def test_ai():
    """Test endpoint to verify AI extraction on sample text"""
    try:
        data = request.get_json()
        sample_text = data.get('text', '')
        
        if not sample_text:
            return jsonify({"error": "No text provided"}), 400
        
        result = parse_packing_slip_with_ai(sample_text)
        return jsonify({"result": result})
        
    except Exception as e:
        return jsonify({"error": f"Test error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test AI connection
        test_response = model.generate_content("Hello")
        return jsonify({
            "status": "healthy",
            "ai_connection": "connected",
            "model": GEMINI_MODEL
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy", 
            "ai_connection": "failed",
            "error": str(e)
        }), 500

# For Render deployment
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
