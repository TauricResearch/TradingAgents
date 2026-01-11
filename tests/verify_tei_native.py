#!/usr/bin/env python3
"""
Verify local embedding service using the native TEI /embed endpoint.
This uses pure HTTP requests without the OpenAI client.
"""

import sys
import requests
import json
import time

def test_native_endpoint():
    url = "http://localhost:11434/embed"
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing Native TEI Endpoint: {url}")
    print("-" * 50)
    
    test_inputs = [
        "This is a test using the native /embed endpoint.",
        "It should be slightly faster than the OpenAI-compatible one."
    ]
    
    payload = {"inputs": test_inputs}
    
    try:
        start_time = time.time()
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        duration = time.time() - start_time
        
        embeddings = response.json()
        
        print("✅ SUCCESS!")
        print(f"Time taken: {duration:.4f}s")
        print(f"Received {len(embeddings)} embeddings")
        print(f"Dimensions: {len(embeddings[0])}")
        print(f"First 5 values: {embeddings[0][:5]}")
        print("-" * 50)
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ FAILED: Connection refused.")
        print("Make sure the container is running: ./startEmbedding.sh")
        return False
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        if hasattr(e, 'response') and e.response:
            print(f"Status: {e.response.status_code}")
            print(f"Response: {e.response.text}")
        return False

if __name__ == "__main__":
    if test_native_endpoint():
        sys.exit(0)
    else:
        sys.exit(1)
