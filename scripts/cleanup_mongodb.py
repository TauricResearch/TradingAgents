import os
from datetime import UTC, datetime

from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables from .env if present
load_dotenv()

MONGO_URI = os.getenv("TRADINGAGENTS_MONGO_URI") or os.getenv("MONGO_URI")
MONGO_DB = os.getenv("TRADINGAGENTS_MONGO_DB", "tradingagents")

if not MONGO_URI:
    print("Error: MONGO_URI not found in environment variables.")
    exit(1)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

# Define 2025 range
start_2025 = datetime(2025, 1, 1, tzinfo=UTC)
end_2025 = datetime(2026, 1, 1, tzinfo=UTC)
start_2025_ts = start_2025.timestamp()
end_2025_ts = end_2025.timestamp()


def cleanup_collection(col_name, date_field, is_timestamp=False, is_iso_string=False):
    col = db[col_name]
    print(f"Cleaning up {col_name}...")

    if is_timestamp:
        query = {date_field: {"$gte": start_2025_ts, "$lt": end_2025_ts}}
    elif is_iso_string:
        query = {date_field: {"$regex": "^2025-"}}
    else:
        query = {date_field: {"$gte": start_2025, "$lt": end_2025}}

    result = col.delete_many(query)
    print(f"Deleted {result.deleted_count} documents from {col_name}.")


if __name__ == "__main__":
    # 1. reports collection (created_at is datetime)
    cleanup_collection("reports", "created_at")

    # 2. run_events collection (ts is float timestamp)
    cleanup_collection("run_events", "ts", is_timestamp=True)

    # 3. reflexion collection (decision_date is ISO string, created_at is datetime)
    cleanup_collection("reflexion", "created_at")

    # 4. macro_memory collection (regime_date is ISO string, created_at is datetime)
    cleanup_collection("macro_memory", "created_at")

    print("Cleanup complete.")
