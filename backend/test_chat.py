import asyncio
import httpx
import json

async def test():
    # create a large dummy report ~1MB
    large_reports = {"market": "dummy " * 100000}
    
    payload = {
        "message": "test context",
        "reports": large_reports,
        "ticker": "NVDA",
        "analysis_date": "2025-01-01",
        "model": "gpt-4o-mini",
        "api_key": "dummy_key",
        "base_url": "https://api.openai.com/v1",
        "language": "zh-TW"
    }

    print("Payload size:", len(json.dumps(payload)))
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post("http://localhost:8000/api/chat", json=payload, timeout=10)
            print("Status:", resp.status_code)
            print("Response:", resp.text[:200])
        except Exception as e:
            print("Failed:", e)

asyncio.run(test())
