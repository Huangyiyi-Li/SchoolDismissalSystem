import requests
import json
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.services.config_manager import ConfigManager

def test_api():
    config = ConfigManager()
    school_id = config.get("school_id")
    print(f"Testing API with School ID: {school_id}")

    url = "https://rest.xxt.cn/kq-http/school-dismissal-system/get-classes"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    payload = {"schoolId": school_id}

    try:
        print(f"Sending POST to {url}...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        try:
            data = response.json()
            print(f"Response Body: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except:
            print(f"Raw Response: {response.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
