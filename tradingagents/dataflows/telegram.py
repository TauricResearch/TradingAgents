import asyncio
from telethon import TelegramClient
from datetime import datetime, timedelta, timezone
from tradingagents.config import settings

def get_api_credentials():
    """Retrieve Telegram API credentials from environment variables."""
    api_id = settings.TELEGRAM_API_ID
    api_hash = settings.TELEGRAM_API_HASH  
    session_name = settings.TELEGRAM_SESSION_NAME
    
    if not api_id or not api_hash or not session_name:
        raise ValueError("Missing required Telegram credentials: TELEGRAM_API_ID, TELEGRAM_API_HASH, or TELEGRAM_SESSION_NAME")
    
    return int(api_id), api_hash, session_name

async def _get_channel_history_async(start_date_str, end_date_str):
    """
    The internal async logic that does the actual work.
    """

    username = "WatcherGuru"

    api_id, api_hash, session_name = get_api_credentials()

    # 1. Start the client using 'async with'
    # This automatically handles connecting AND disconnecting (releasing the DB lock)
    async with TelegramClient(session_name, api_id, api_hash) as client:
        
        # Date parsing logic
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        lookback_days = (end_date_obj - start_date).days
        end_date = end_date_obj + timedelta(days=1) - timedelta(seconds=1)

        formatted_log = ""
        
        # Fetching messages
        n_records = 0
        async for message in client.iter_messages(username, offset_date=end_date, reverse=False):
            if message.date < start_date:
                break
            
            if message.text:
                date_str = message.date.strftime('%Y-%m-%d')
                clean_text = message.text.replace('\n', ' ')
                formatted_log += f"[{date_str}] {clean_text}\n"
                n_records += 1
        
        intro = f"# News data from Telegram channel @{username} from {start_date_str} to {end_date_str} ({lookback_days} days):\n# Total records: {n_records}\n# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return intro + formatted_log

def get_crypto_news_telegram(curr_date, look_back_days=7, limit=100):
    # ignore limit for now
    # convert curr_date from yyyy-mm-dd to datetime
    curr_date = datetime.strptime(curr_date, '%Y-%m-%d')
    start_date = curr_date - timedelta(days=look_back_days)
    end_date = curr_date

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    return asyncio.run(_get_channel_history_async(start_date_str, end_date_str))
