import requests
import json
import time

# Production URL for the chatbot
BASE_URL = "https://medimind-asha.asolvitra.tech"

def test_health():
    print(f"\n[1] Testing Health Endpoint: {BASE_URL}/health")
    try:
        start_time = time.time()
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Success! ({elapsed:.2f}s)")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Failed (Status: {response.status_code})")
            print(response.text)
    except Exception as e:
        print(f"❌ Error: {e}")

def test_query(query_text):
    print(f"\n[2] Testing Query Endpoint: {BASE_URL}/query")
    print(f"Question: \"{query_text}\"")
    
    payload = {"query": query_text}
    headers = {"Content-Type": "application/json"}
    
    try:
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/query", json=payload, headers=headers, timeout=60)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            print(f"✅ Success! ({elapsed:.2f}s)")
            data = response.json()
            answer = data.get("answer") or data.get("response")
            print("-" * 50)
            print(f"AI Response:\n\n{answer}")
            print("-" * 50)
        else:
            print(f"❌ Failed (Status: {response.status_code})")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("MediMindAI Production RAG Pipeline Test")
    print("=" * 60)
    
    # 1. Check if server is alive
    test_health()
    
    # 2. Run a specific medical query
    test_query("What are the primary causes of Type 2 diabetes?")
    
    # 3. Optional: Another more technical query
    # test_query("How is heart failure classified in medical terms?")
    
    print("\nTest complete.")
