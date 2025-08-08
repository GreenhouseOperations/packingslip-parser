from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pdfplumber
import pandas as pd
import io
import json
import os
from dotenv import load_dotenv
import google.generativeai as genai
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure Gemini AI
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
GEMINI_TEMPERATURE = float(os.getenv('GEMINI_TEMPERATURE', '0.1'))

if not GEMINI_API_KEY or GEMINI_API_KEY.strip() == '':
    raise ValueError("GEMINI_API_KEY not found in .env file. Please add your API key.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(GEMINI_MODEL)

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

@app.route('/upload', methods=['POST'])
def upload_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        pdf_file = request.files['file']
        if pdf_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        if not pdf_file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "File must be a PDF"}), 400
        
        records = []
        with pdfplumber.open(pdf_file.stream) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text:
                        # Use AI to parse the packing slip
                        data = parse_packing_slip_with_ai(text)
                        
                        # Only add records that have essential data
                        if data.get('customerId') != 'Not found' or data.get('attention') != 'Not found':
                            records.append(data)
                            
                except Exception as e:
                    continue
        
        if not records:
            return jsonify({"error": "No valid packing slip data found in PDF"}), 400
        
        # Create CSV
        df = pd.DataFrame(records)
        
        # Calculate packages (2 * quantity) and total weight
        df['packages'] = df['quantity'] * 2
        df['packageWeight'] = '4.5kg'
        df['type'] = '24 Pack'
        df['totalWeight'] = (df['quantity'] * 9).astype(str) + 'kg'  # 4.5kg * 2 packages = 9kg per quantity
        df['shipper'] = 'K100C4'
        df['billTransportationTo'] = 'shipper'
        df['countryTerritory'] = 'Canada'
        
        # Reorder columns to match reference CSV
        column_order = ['customerId', 'companyName', 'attention', 'address1', 
                       'stateProvinceCounty', 'countryTerritory', 'postalCode', 
                       'cityOrTown', 'telephone', 'upsService', 'packages', 
                       'packageWeight', 'type', 'totalWeight', 'shipper', 'billTransportationTo']
        
        df = df.reindex(columns=column_order, fill_value='Not found')
        
        # Convert to CSV
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name='packing_slip_data.csv'
        )
        
    except Exception as e:
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
