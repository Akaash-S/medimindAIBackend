import httpx
import json

def test_chatbot(query):
    url = "https://lakia-hyperexcursive-broderick.ngrok-free.dev/query"
    payload = {"query": query}
    headers = {"Content-Type": "application/json"}

    print(f"\nSending query: {query}")
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        response.raise_for_status()
        
        result = response.json()
        print("Response received successfully!")
        # Try different common keys for the response
        answer = result.get('answer') or result.get('response') or result.get('text')
        if answer:
            print(f"Chatbot: {answer}")
        else:
            print(f"Chatbot (Full JSON): {json.dumps(result, indent=2)}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP error occurred: {e}")
        try:
            print(f"Response detail: {e.response.text}")
        except:
            pass
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    queries = [
        "What is cardiac resynchronization therapy (CRT) and how does it help?",
        "What are the common symptoms of heart failure mentioned in the documents?",
        "How should a doctor communicate with a pediatric patient according to the context?",
        "What is the role of prosthetic therapy in medical treatments?"
    ]

    for q in queries:
        test_chatbot(q)
