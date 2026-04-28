import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient, DESCENDING

load_dotenv()

MONGO_URI = os.getenv("TRADINGAGENTS_MONGO_URI") or os.getenv("MONGO_URI")
MONGO_DB = os.getenv("TRADINGAGENTS_MONGO_DB", "tradingagents")

if not MONGO_URI:
    print("Error: MONGO_URI not found in environment variables.")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
col = db["macro_memory"]

def deduplicate():
    print(f"Checking for duplicates in '{MONGO_DB}.macro_memory'...")
    
    # Pipeline to find duplicate (regime_date, run_id) pairs
    pipeline = [
        {
            "$group": {
                "_id": { "regime_date": "$regime_date", "run_id": "$run_id" },
                "unique_ids": { "$addToSet": "$_id" },
                "count": { "$sum": 1 }
            }
        },
        {
            "$match": {
                "count": { "$gt": 1 }
            }
        }
    ]
    
    duplicates = list(col.aggregate(pipeline))
    if not duplicates:
        print("No duplicates found.")
        return

    print(f"Found {len(duplicates)} duplicate key pairs. Cleaning up...")
    total_deleted = 0
    
    for dup in duplicates:
        # Keep the latest one (highest _id or we could sort by created_at)
        ids = sorted(dup["unique_ids"])
        to_delete = ids[:-1]  # All but the last one
        
        res = col.delete_many({"_id": {"$in": to_delete}})
        total_deleted += res.deleted_count
        print(f"  Deleted {res.deleted_count} stale records for {dup['_id']}")

    print(f"Deduplication complete. Total deleted: {total_deleted}")

if __name__ == "__main__":
    deduplicate()
