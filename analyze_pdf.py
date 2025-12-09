import pdfplumber
import sys

def analyze_pdf(pdf_path):
    print(f"Analyzing: {pdf_path}")
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                print(f"\n--- Page {i+1} ---")
                
                # Extract Text
                text = page.extract_text()
                print("\n[Raw Text Layout]")
                print(text)
                
                # Extract Tables
                print("\n[Tables]")
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    print(f"Table {j+1}:")
                    for row in table:
                        print(row)
                        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    pdf_path = "SalesOrderLCL GHSO-941211 for KeHEDistributorsLLCUSD.pdf"
    analyze_pdf(pdf_path)
