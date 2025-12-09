import requests
import os

def test_upload():
    url = "http://localhost:5001/upload"
    file_path = "SalesOrderLCL GHSO-941211 for KeHEDistributorsLLCUSD.pdf"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Uploading {file_path}...")
    with open(file_path, 'rb') as f:
        files = {'file': f}
        try:
            response = requests.post(url, files=files)
            
            if response.status_code == 200:
                print("Success!")
                print("Headers:", response.headers)
                print("\n--- CSV Content ---")
                print(response.text)
                print("-------------------")
            else:
                print(f"Error: {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    test_upload()
