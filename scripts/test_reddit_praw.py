#!/usr/bin/env python3
"""Test Reddit PRAW OAuth setup and verify credentials work.

Run this after adding REDDIT_* env vars to your .env file:
    uv run python scripts/test_reddit_praw.py
"""
import os
import sys

from dotenv import load_dotenv


def test_env_vars():
    """Check that required environment variables are set."""
    print("=" * 60)
    print("Step 1: Checking environment variables")
    print("=" * 60)

    load_dotenv()

    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    username = os.getenv("REDDIT_USERNAME", "").strip()
    password = os.getenv("REDDIT_PASSWORD", "").strip()

    if not client_id:
        print("\n❌ REDDIT_CLIENT_ID is not set")
        print("   Add it to your .env file:")
        print('   REDDIT_CLIENT_ID=your_client_id_here')
        return False

    print(f"\n✅ REDDIT_CLIENT_ID: {client_id[:8]}...")

    if client_secret:
        print(f"✅ REDDIT_CLIENT_SECRET: {client_secret[:8]}...")
    else:
        print("⚠️  REDDIT_CLIENT_SECRET not set (read-only mode)")

    if username:
        print(f"✅ REDDIT_USERNAME: {username}")
    else:
        print("⚠️  REDDIT_USERNAME not set (read-only mode)")

    if password:
        print(f"✅ REDDIT_PASSWORD: {'*' * len(password)}")
    else:
        print("⚠️  REDDIT_PASSWORD not set (read-only mode)")

    if not client_secret:
        print("\n💡 Tip: Add client_secret for full access with score/comment counts")
    if not username or not password:
        print("�¼ Tip: Add username/password for full access with score/comment counts")

    return True


def test_praw_connection():
    """Test that PRAW can connect to Reddit with the credentials."""
    print("\n" + "=" * 60)
    print("Step 2: Testing PRAW connection")
    print("=" * 60)

    try:
        import praw
    except ImportError:
        print("\n❌ PRAW is not installed")
        print("   Run: uv pip install praw")
        return False

    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip() or None
    username = os.getenv("REDDIT_USERNAME", "").strip() or None
    password = os.getenv("REDDIT_PASSWORD", "").strip() or None

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent="tradingagents/0.2 (test script)",
        )

        # Test connection by fetching user info
        if username and password:
            me = reddit.user.me()
            if me:
                print(f"\n✅ Successfully authenticated as: u/{me.name}")
                print(f"   Karma: {me.link_karma + me.comment_karma:,}")
            else:
                print("\n⚠️  Authenticated but user info not available")
        else:
            # Read-only: just verify we can access Reddit
            subreddit = reddit.subreddit("stocks")
            post = next(subreddit.new(limit=1))
            print("\n✅ Read-only connection successful")
            print(f"   Latest post on r/stocks: {post.title[:60]}...")

        return True

    except Exception as exc:
        print(f"\n❌ PRAW connection failed: {exc}")
        print("\nTroubleshooting:")
        print("1. Double-check your credentials are correct")
        print("2. If using 2FA, you need a special app password")
        print("3. Make sure your Reddit app is 'script' type")
        print("4. Try logging into Reddit in a browser first")
        return False


def test_search():
    """Test searching for a ticker symbol."""
    print("\n" + "=" * 60)
    print("Step 3: Testing ticker search")
    print("=" * 60)

    try:
        import praw
    except ImportError:
        return False

    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip() or None
    username = os.getenv("REDDIT_USERNAME", "").strip() or None
    password = os.getenv("REDDIT_PASSWORD", "").strip() or None

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent="tradingagents/0.2 (test script)",
        )

        ticker = "AAPL"
        subreddit = reddit.subreddit("stocks")
        posts = list(subreddit.search(ticker, sort="new", time_filter="week", limit=3))

        if posts:
            print(f"\n✅ Found {len(posts)} posts mentioning {ticker} on r/stocks")
            for p in posts:
                print(f"   • {p.title[:70]}... (Score: {p.score})")
        else:
            print(f"\n⚠️  No posts found for {ticker} (but connection works)")

        return True

    except Exception as exc:
        print(f"\n❌ Search test failed: {exc}")
        return False


def main():
    print("Reddit PRAW OAuth Setup Test")
    print("This script verifies your Reddit API credentials are working.\n")

    if not test_env_vars():
        print("\n" + "=" * 60)
        print("Setup incomplete. Please add your Reddit credentials to .env")
        print("=" * 60)
        sys.exit(1)

    if not test_praw_connection():
        print("\n" + "=" * 60)
        print("Connection failed. Check your credentials and try again.")
        print("=" * 60)
        sys.exit(1)

    if not test_search():
        print("\n" + "=" * 60)
        print("Search test failed.")
        print("=" * 60)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ All tests passed! Reddit PRAW is ready.")
    print("=" * 60)
    print("\nThe tradingagents app will now use PRAW for Reddit data,")
    print("giving you ~60 requests/min with full score/comment counts.\n")


if __name__ == "__main__":
    main()
