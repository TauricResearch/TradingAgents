import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("TRADINGAGENTS_MONGO_URI") or os.getenv("MONGO_URI")
MONGO_DB = os.getenv("TRADINGAGENTS_MONGO_DB", "tradingagents")

if not MONGO_URI:
    print("Error: MONGO_URI not found in environment variables.")
    exit(1)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

def delete_all(col_name):
    col = db[col_name]
    print(f"Deleting ALL documents from '{col_name}'...")
    result = col.delete_many({})
    print(f"Deleted {result.deleted_count} documents from '{col_name}'.")

if __name__ == "__main__":
    delete_all("reports")
    delete_all("run_events")
    delete_all("macro_memory")
    delete_all("micro_reflexion")
    print("Full purge complete.")
