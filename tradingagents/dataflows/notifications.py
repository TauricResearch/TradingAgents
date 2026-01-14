import requests
import urllib.parse
import os
import logging

class CallMeBotNotifier:
    """
    Sends WhatsApp notifications via the free CallMeBot API.
    URL: https://api.callmebot.com/whatsapp.php?phone=[phone]&text=[text]&apikey=[apikey]
    """
    def __init__(self, phone=None, api_key=None):
        self.phone = phone or os.getenv("CALLMEBOT_PHONE")
        self.api_key = api_key or os.getenv("CALLMEBOT_API_KEY")
        self.base_url = "https://api.callmebot.com/whatsapp.php"

    def send_signal(self, ticker: str, signal: str, reason: str):
        """
        Sends a formatted trading signal to WhatsApp.
        """
        if not self.phone or not self.api_key:
            logging.warning("⚠️ CallMeBot Not Configured: Missing CALLMEBOT_PHONE or CALLMEBOT_API_KEY.")
            return

        message_text = self._format_message(ticker, signal, reason)
        try:
            # URL Encode
            encoded_text = urllib.parse.quote(message_text)
            url = f"{self.base_url}?phone={self.phone}&text={encoded_text}&apikey={self.api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logging.info(f"✅ WhatsApp (CallMeBot) Notification sent for {ticker}")
            else:
                logging.error(f"❌ CallMeBot Failed: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"❌ CallMeBot Error: {str(e)}")

    def _format_message(self, ticker, signal, reason):
        emoji = "⚪"
        if "BUY" in signal.upper(): emoji = "🟢"
        elif "SELL" in signal.upper(): emoji = "🔴"
        elif "HOLD" in signal.upper(): emoji = "🟡"
        return f"{emoji} *TRADING SIGNAL: {ticker}*\n\n*Decision:* {signal}\n*Reason:* {reason}\n\n_Sent by TradingAgents 🤖_"


class TwilioNotifier:
    """
    Sends WhatsApp notifications via Twilio API.
    """
    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER") # e.g., 'whatsapp:+14155238886'
        self.to_number = os.getenv("TWILIO_TO_NUMBER")     # e.g., 'whatsapp:+1234567890'

    def send_signal(self, ticker: str, signal: str, reason: str):
        if not self.account_sid or not self.auth_token:
            logging.warning("⚠️ Twilio Not Configured: Missing SID or TOKEN.")
            return

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            
            message_text = self._format_message(ticker, signal, reason)
            
            message = client.messages.create(
                from_=self.from_number,
                body=message_text,
                to=self.to_number
            )
            logging.info(f"✅ WhatsApp (Twilio) Notification sent! SID: {message.sid}")
            
        except ImportError:
            logging.error("❌ Twilio Library not found. Run: pip install twilio")
        except Exception as e:
            logging.error(f"❌ Twilio Error: {str(e)}")

    def _format_message(self, ticker, signal, reason):
        # Same format, maybe different max length logic if needed
        emoji = "⚪"
        if "BUY" in signal.upper(): emoji = "🟢"
        elif "SELL" in signal.upper(): emoji = "🔴"
        elif "HOLD" in signal.upper(): emoji = "🟡"
        return f"{emoji} *TRADING SIGNAL: {ticker}*\n\n*Decision:* {signal}\n*Reason:* {reason}\n\n_Sent by TradingAgents 🤖_"


class TelegramNotifier:
    """
    Sends notifications via Telegram Bot API.
    """
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def send_signal(self, ticker: str, signal: str, reason: str):
        if not self.bot_token or not self.chat_id:
            logging.warning("⚠️ Telegram Not Configured: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
            return

        message_text = self._format_message(ticker, signal, reason)
        
        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message_text,
                "parse_mode": "Markdown"
            }
            response = requests.post(self.base_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logging.info(f"✅ Telegram Notification sent for {ticker}")
            else:
                logging.error(f"❌ Telegram Failed: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"❌ Telegram Error: {str(e)}")

    def _format_message(self, ticker, signal, reason):
        # MarkdownV2 or HTML style can be used, but simple Markdown is safer
        emoji = "⚪"
        if "BUY" in signal.upper(): emoji = "🟢"
        elif "SELL" in signal.upper(): emoji = "🔴"
        elif "HOLD" in signal.upper(): emoji = "🟡"
        # Telegram Markdown requires escaping some chars if using MarkdownV2, using generic Markdown here
        return f"{emoji} *TRADING SIGNAL: {ticker}*\n\n*Decision:* {signal}\n*Reason:* {reason}\n\n_Sent by TradingAgents 🤖_"


def get_notifier():
    """Factory to return the configured notifier."""
    provider = os.getenv("NOTIFICATION_PROVIDER", "callmebot").lower()
    
    if provider == "twilio":
        return TwilioNotifier()
    elif provider == "telegram":
        return TelegramNotifier()
    elif provider == "callmebot":
        return CallMeBotNotifier()
    else:
        logging.warning(f"⚠️ Unknown NOTIFICATION_PROVIDER: {provider}. Defaulting to CallMeBot.")
        return CallMeBotNotifier()
