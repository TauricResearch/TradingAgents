"""Reproduce the real Market Analyst call to see whether it actually
completes or is genuinely hanging. This bypasses the full graph and
measures raw elapsed time for the LLM roundtrip.
"""
import os
import sys
import time

os.environ.setdefault("AWS_PROFILE", "sandbox")
os.environ.setdefault("AWS_BEDROCK_REGION", "us-east-1")

# Long ceiling so we can see the real duration instead of hitting a cap.
os.environ["BEDROCK_TIMEOUT"] = "900"

from langchain_core.messages import HumanMessage

from tradingagents.llm_clients.bedrock_client import BedrockClient
from tradingagents.agents.analysts.market_analyst import create_market_analyst


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "us.anthropic.claude-sonnet-4-6"
    ticker = sys.argv[2] if len(sys.argv) > 2 else "AAPL"
    date = sys.argv[3] if len(sys.argv) > 3 else "2026-05-08"

    print(f"[config] model={model} ticker={ticker} date={date}")
    print(f"[config] region={os.environ.get('AWS_BEDROCK_REGION')} "
          f"profile={os.environ.get('AWS_PROFILE')} "
          f"timeout={os.environ.get('BEDROCK_TIMEOUT')}s")

    client = BedrockClient(model)
    llm = client.get_llm()
    print(f"[config] boto3 read_timeout={llm.client.meta.config.read_timeout}s "
          f"connect_timeout={llm.client.meta.config.connect_timeout}s")

    node = create_market_analyst(llm)

    state = {
        "trade_date": date,
        "company_of_interest": ticker,
        "messages": [HumanMessage(content=f"Analyze {ticker} for {date}.")],
    }

    print(f"\n[call] invoking Market Analyst with tools bound ...")
    t0 = time.monotonic()
    try:
        result = node(state)
        elapsed = time.monotonic() - t0
        print(f"[done] elapsed={elapsed:.1f}s")
        msg = result["messages"][0]
        print(f"[done] tool_calls={len(getattr(msg, 'tool_calls', []) or [])}")
        content = getattr(msg, "content", "")
        if isinstance(content, list):
            # Claude returns list of blocks; flatten
            text = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
            )
        else:
            text = str(content)
        print(f"[done] content_preview={text[:200]!r}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"[fail] elapsed={elapsed:.1f}s error_type={type(e).__name__}")
        print(f"[fail] error={e}")
        raise


if __name__ == "__main__":
    main()
