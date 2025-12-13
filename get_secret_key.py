import base64
import json
import os

def generate_secret():
    """Generates the exact Base64 string needed for GitHub Secrets."""
    print("🔑 GENERATING SECURE SECRET...\n")
    
    file_path = "service_account.json"
    
    if not os.path.exists(file_path):
        print(f"❌ Error: {file_path} not found!")
        return

    try:
        # Read JSON
        with open(file_path, "r") as f:
            data = json.load(f)
            
        # Compact JSON (no spaces/newlines) to be safe
        json_str = json.dumps(data, separators=(',', ':'))
        
        # Base64 Encode
        b64_bytes = base64.b64encode(json_str.encode('utf-8'))
        b64_str = b64_bytes.decode('utf-8')
        
        print("✅ SUCCESS! Copy the string below (between the lines):\n")
        print("-" * 20)
        print(b64_str)
        print("-" * 20)
        print("\n👉 Paste this EXACTLY into GitHub Secret: GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    generate_secret()
