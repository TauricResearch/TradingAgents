"""Seed the database with sample data from the Jan 30, 2025 analysis."""
import database as db

# Sample data from the Jan 30, 2025 analysis
SAMPLE_DATA = {
    "date": "2025-01-30",
    "analysis": {
        "RELIANCE": {"symbol": "RELIANCE", "company_name": "Reliance Industries Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "TCS": {"symbol": "TCS", "company_name": "Tata Consultancy Services Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "HDFCBANK": {"symbol": "HDFCBANK", "company_name": "HDFC Bank Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "INFY": {"symbol": "INFY", "company_name": "Infosys Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "ICICIBANK": {"symbol": "ICICIBANK", "company_name": "ICICI Bank Ltd", "decision": "BUY", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "HINDUNILVR": {"symbol": "HINDUNILVR", "company_name": "Hindustan Unilever Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "ITC": {"symbol": "ITC", "company_name": "ITC Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "SBIN": {"symbol": "SBIN", "company_name": "State Bank of India", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BHARTIARTL": {"symbol": "BHARTIARTL", "company_name": "Bharti Airtel Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "KOTAKBANK": {"symbol": "KOTAKBANK", "company_name": "Kotak Mahindra Bank Ltd", "decision": "BUY", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "LT": {"symbol": "LT", "company_name": "Larsen & Toubro Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "AXISBANK": {"symbol": "AXISBANK", "company_name": "Axis Bank Ltd", "decision": "SELL", "confidence": "HIGH", "risk": "HIGH"},
        "ASIANPAINT": {"symbol": "ASIANPAINT", "company_name": "Asian Paints Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "MARUTI": {"symbol": "MARUTI", "company_name": "Maruti Suzuki India Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "HCLTECH": {"symbol": "HCLTECH", "company_name": "HCL Technologies Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "HIGH"},
        "SUNPHARMA": {"symbol": "SUNPHARMA", "company_name": "Sun Pharmaceutical Industries Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "TITAN": {"symbol": "TITAN", "company_name": "Titan Company Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BAJFINANCE": {"symbol": "BAJFINANCE", "company_name": "Bajaj Finance Ltd", "decision": "BUY", "confidence": "HIGH", "risk": "MEDIUM"},
        "WIPRO": {"symbol": "WIPRO", "company_name": "Wipro Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "ULTRACEMCO": {"symbol": "ULTRACEMCO", "company_name": "UltraTech Cement Ltd", "decision": "BUY", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "NESTLEIND": {"symbol": "NESTLEIND", "company_name": "Nestle India Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "NTPC": {"symbol": "NTPC", "company_name": "NTPC Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "POWERGRID": {"symbol": "POWERGRID", "company_name": "Power Grid Corporation of India Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "M&M": {"symbol": "M&M", "company_name": "Mahindra & Mahindra Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "TATAMOTORS": {"symbol": "TATAMOTORS", "company_name": "Tata Motors Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "ONGC": {"symbol": "ONGC", "company_name": "Oil & Natural Gas Corporation Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "HIGH"},
        "JSWSTEEL": {"symbol": "JSWSTEEL", "company_name": "JSW Steel Ltd", "decision": "BUY", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "TATASTEEL": {"symbol": "TATASTEEL", "company_name": "Tata Steel Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "ADANIENT": {"symbol": "ADANIENT", "company_name": "Adani Enterprises Ltd", "decision": "HOLD", "confidence": "LOW", "risk": "HIGH"},
        "ADANIPORTS": {"symbol": "ADANIPORTS", "company_name": "Adani Ports and SEZ Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "HIGH"},
        "COALINDIA": {"symbol": "COALINDIA", "company_name": "Coal India Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BAJAJFINSV": {"symbol": "BAJAJFINSV", "company_name": "Bajaj Finserv Ltd", "decision": "BUY", "confidence": "HIGH", "risk": "MEDIUM"},
        "TECHM": {"symbol": "TECHM", "company_name": "Tech Mahindra Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "HDFCLIFE": {"symbol": "HDFCLIFE", "company_name": "HDFC Life Insurance Company Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "SBILIFE": {"symbol": "SBILIFE", "company_name": "SBI Life Insurance Company Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "GRASIM": {"symbol": "GRASIM", "company_name": "Grasim Industries Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "DIVISLAB": {"symbol": "DIVISLAB", "company_name": "Divi's Laboratories Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "DRREDDY": {"symbol": "DRREDDY", "company_name": "Dr. Reddy's Laboratories Ltd", "decision": "SELL", "confidence": "HIGH", "risk": "HIGH"},
        "CIPLA": {"symbol": "CIPLA", "company_name": "Cipla Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BRITANNIA": {"symbol": "BRITANNIA", "company_name": "Britannia Industries Ltd", "decision": "BUY", "confidence": "MEDIUM", "risk": "LOW"},
        "EICHERMOT": {"symbol": "EICHERMOT", "company_name": "Eicher Motors Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "APOLLOHOSP": {"symbol": "APOLLOHOSP", "company_name": "Apollo Hospitals Enterprise Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "INDUSINDBK": {"symbol": "INDUSINDBK", "company_name": "IndusInd Bank Ltd", "decision": "SELL", "confidence": "HIGH", "risk": "HIGH"},
        "HEROMOTOCO": {"symbol": "HEROMOTOCO", "company_name": "Hero MotoCorp Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "TATACONSUM": {"symbol": "TATACONSUM", "company_name": "Tata Consumer Products Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BPCL": {"symbol": "BPCL", "company_name": "Bharat Petroleum Corporation Ltd", "decision": "SELL", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "UPL": {"symbol": "UPL", "company_name": "UPL Ltd", "decision": "HOLD", "confidence": "LOW", "risk": "HIGH"},
        "HINDALCO": {"symbol": "HINDALCO", "company_name": "Hindalco Industries Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "BAJAJ-AUTO": {"symbol": "BAJAJ-AUTO", "company_name": "Bajaj Auto Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
        "LTIM": {"symbol": "LTIM", "company_name": "LTIMindtree Ltd", "decision": "HOLD", "confidence": "MEDIUM", "risk": "MEDIUM"},
    },
    "summary": {
        "total": 50,
        "buy": 7,
        "sell": 10,
        "hold": 33,
    },
    "top_picks": [
        {
            "rank": 1,
            "symbol": "BAJFINANCE",
            "company_name": "Bajaj Finance Ltd",
            "decision": "BUY",
            "reason": "13.7% gain over 30 days (Rs.678 to Rs.771), strongest bullish momentum with robust upward trend.",
            "risk_level": "MEDIUM",
        },
        {
            "rank": 2,
            "symbol": "BAJAJFINSV",
            "company_name": "Bajaj Finserv Ltd",
            "decision": "BUY",
            "reason": "14% gain in one month (Rs.1,567 to Rs.1,789) demonstrates clear bullish momentum with sector-wide tailwinds.",
            "risk_level": "MEDIUM",
        },
        {
            "rank": 3,
            "symbol": "KOTAKBANK",
            "company_name": "Kotak Mahindra Bank Ltd",
            "decision": "BUY",
            "reason": "Significant breakout on January 20th with 9.2% gain on exceptionally high volume (66.6M shares).",
            "risk_level": "MEDIUM",
        },
    ],
    "stocks_to_avoid": [
        {
            "symbol": "DRREDDY",
            "company_name": "Dr. Reddy's Laboratories Ltd",
            "reason": "HIGH CONFIDENCE SELL with 14.9% decline in one month. Severe downtrend with high risk.",
        },
        {
            "symbol": "AXISBANK",
            "company_name": "Axis Bank Ltd",
            "reason": "HIGH CONFIDENCE SELL with 10.5% sustained decline. Clear and persistent downtrend.",
        },
        {
            "symbol": "HCLTECH",
            "company_name": "HCL Technologies Ltd",
            "reason": "SELL with 9.4% drop from recent highs. High risk rating with continued selling pressure.",
        },
        {
            "symbol": "ADANIPORTS",
            "company_name": "Adani Ports and SEZ Ltd",
            "reason": "SELL with 12% monthly decline and consistently lower lows. High risk profile.",
        },
    ],
}


def seed_database():
    """Seed the database with sample data."""
    print("Seeding database...")

    db.save_recommendation(
        date=SAMPLE_DATA["date"],
        analysis_data=SAMPLE_DATA["analysis"],
        summary=SAMPLE_DATA["summary"],
        top_picks=SAMPLE_DATA["top_picks"],
        stocks_to_avoid=SAMPLE_DATA["stocks_to_avoid"],
    )

    print(f"Saved recommendation for {SAMPLE_DATA['date']}")
    print(f"  - {len(SAMPLE_DATA['analysis'])} stocks analyzed")
    print(f"  - Summary: {SAMPLE_DATA['summary']['buy']} BUY, {SAMPLE_DATA['summary']['sell']} SELL, {SAMPLE_DATA['summary']['hold']} HOLD")
    print("Database seeded successfully!")


if __name__ == "__main__":
    seed_database()
