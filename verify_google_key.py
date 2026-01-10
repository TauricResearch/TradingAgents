import os
from openai import OpenAI
from dotenv import load_dotenv

# Load env
load_dotenv()

key = os.getenv("GOOGLE_API_KEY")
print(f"Checking GOOGLE_API_KEY...")
if not key:
    print("❌ GOOGLE_API_KEY not found in environment or .env file.")
    exit(1)

print(f"✅ Key found: {key[:4]}...{key[-4:]}")

client = OpenAI(
    api_key=key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

print("Attempting to generate embedding for 'Hello World'...")
try:
    resp = client.embeddings.create(
        model="text-embedding-004",
        input="Hello world"
    )
    print("✅ Embedding Success! The API Key is valid and the model is accessible.")
    print(f"Embedding vector length: {len(resp.data[0].embedding)}")
except Exception as e:
    print(f"❌ Embedding Failed: {e}")
    print("\nTroubleshooting:")
    print("1. Ensure the API Key is from Google AI Studio (aistudio.google.com).")
    print("2. Ensure the 'Generative Language API' is enabled in Google Cloud Console if using a GCP project.")
    print("3. Verify you have not exceeded your quota.")
