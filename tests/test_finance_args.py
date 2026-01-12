
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from tradingagents.dataflows.y_finance import get_income_statement, get_balance_sheet, get_cashflow

def verify_relaxed_types():
    print("🔍 VERIFYING RELAXED TYPE VALIDATION...")
    
    ticker = "AAPL"
    # This dictionary mimics the user's error case where LLM passed reasoning in the date field
    bad_date_arg = {"reason": "Analyzing trends", "date": "2026-01-01"}
    
    try:
        print("Testing get_income_statement with DICT in curr_date...")
        try:
           # This should NOT assume it's a string anymore.
           res = get_income_statement(ticker, curr_date=bad_date_arg)
           print("✅ get_income_statement ACCEPTED dict in curr_date (no Pydantic/Type Error)")
        except Exception as e:
           print(f"❌ get_income_statement FAILED: {e}")
           
        print("Testing get_balance_sheet with DICT in curr_date...")
        try:
           res = get_balance_sheet(ticker, curr_date=bad_date_arg)
           print("✅ get_balance_sheet ACCEPTED dict in curr_date")
        except Exception as e:
           print(f"❌ get_balance_sheet FAILED: {e}")

        print("Testing get_cashflow with DICT in curr_date...")
        try:
           res = get_cashflow(ticker, curr_date=bad_date_arg)
           print("✅ get_cashflow ACCEPTED dict in curr_date")
        except Exception as e:
           print(f"❌ get_cashflow FAILED: {e}")
           
    except Exception as e:
        print(f"⚠️ General Error: {e}")

if __name__ == "__main__":
    verify_relaxed_types()
