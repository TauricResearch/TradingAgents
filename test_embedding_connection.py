
import os
from openai import OpenAI
import httpx

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="sk-dummy"
)

print("Testing connection to http://localhost:11434/v1/embeddings...")

try:
    response = client.embeddings.create(
        input="The food was delicious and the waiter...",
        model="sentence-transformers/all-MiniLM-L6-v2"
    )
    print("Success!")
    print(response.data[0].embedding[:5])
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting with httpx directly to 127.0.0.1...")
try:
    r = httpx.post("http://127.0.0.1:11434/v1/embeddings", 
                  json={"input": "test", "model": "sentence-transformers/all-MiniLM-L6-v2"},
                  timeout=5.0)
    print(f"HTTPX 127.0.0.1 Status: {r.status_code}")
except Exception as e:
    print(f"HTTPX 127.0.0.1 Failed: {e}")
