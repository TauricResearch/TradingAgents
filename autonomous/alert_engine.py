"""
Alert Engine
===========

Multi-channel notification system for trading alerts.
Supports Discord, Telegram, Email, and console output.
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import os

# Optional imports for different notification channels
try:
    import discord
    from discord import Webhook
    import aiohttp
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    print("Discord not installed. Install with: pip install discord.py")

try:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False

logger = logging.getLogger(__name__)


class AlertPriority(Enum):
    """Alert priority levels"""
    CRITICAL = "critical"  # Immediate action required
    HIGH = "high"  # Important, time-sensitive
    MEDIUM = "medium"  # Standard alerts
    LOW = "low"  # Informational
    INFO = "info"  # Non-actionable info


class AlertType(Enum):
    """Types of alerts"""
    TRADING_SIGNAL = "trading_signal"
    PORTFOLIO_UPDATE = "portfolio_update"
    RISK_WARNING = "risk_warning"
    CONGRESSIONAL_TRADE = "congressional_trade"
    INSIDER_TRADE = "insider_trade"
    EARNINGS = "earnings"
    MARKET_MOVE = "market_move"
    SYSTEM = "system"


class AlertEngine:
    """
    Manages multi-channel alert distribution
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize alert engine

        Args:
            config: Configuration with API keys and settings
        """
        self.config = config or {}
        self.discord_webhook_url = self.config.get('discord_webhook_url')
        self.telegram_bot_token = self.config.get('telegram_bot_token')
        self.telegram_chat_id = self.config.get('telegram_chat_id')
        self.email_config = self.config.get('email', {})

        # Track sent alerts to avoid duplicates
        self.sent_alerts: List[Dict] = []
        self.alert_history: List[Dict] = []

    async def send_alert(self,
                        title: str,
                        message: str,
                        alert_type: AlertType,
                        priority: AlertPriority,
                        data: Optional[Dict] = None,
                        channels: Optional[List[str]] = None) -> bool:
        """
        Send alert through specified channels

        Args:
            title: Alert title
            message: Alert message
            alert_type: Type of alert
            priority: Alert priority
            data: Additional data
            channels: List of channels to use (discord, telegram, email, console)

        Returns:
            True if alert sent successfully
        """
        # Default channels based on priority
        if channels is None:
            if priority == AlertPriority.CRITICAL:
                channels = ['discord', 'telegram', 'email', 'console']
            elif priority == AlertPriority.HIGH:
                channels = ['discord', 'telegram', 'console']
            elif priority == AlertPriority.MEDIUM:
                channels = ['discord', 'console']
            else:
                channels = ['console']

        # Check for duplicate alerts
        alert_hash = f"{title}_{message}_{datetime.now().strftime('%Y%m%d%H')}"
        if alert_hash in [a.get('hash') for a in self.sent_alerts[-100:]]:
            logger.info("Skipping duplicate alert")
            return False

        # Create alert record
        alert_record = {
            'hash': alert_hash,
            'title': title,
            'message': message,
            'type': alert_type.value,
            'priority': priority.value,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

        success = False

        # Send to each channel
        tasks = []
        if 'discord' in channels and self.discord_webhook_url:
            tasks.append(self._send_discord(title, message, alert_type, priority, data))

        if 'telegram' in channels and self.telegram_bot_token:
            tasks.append(self._send_telegram(title, message, alert_type, priority, data))

        if 'email' in channels and self.email_config:
            tasks.append(self._send_email(title, message, alert_type, priority, data))

        if 'console' in channels:
            self._send_console(title, message, alert_type, priority, data)
            success = True

        # Execute all sends in parallel
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success = any(r is True for r in results if not isinstance(r, Exception))

        # Record alert
        if success:
            self.sent_alerts.append(alert_record)
            self.alert_history.append(alert_record)

        return success

    async def _send_discord(self,
                           title: str,
                           message: str,
                           alert_type: AlertType,
                           priority: AlertPriority,
                           data: Optional[Dict]) -> bool:
        """Send alert to Discord via webhook"""
        if not DISCORD_AVAILABLE or not self.discord_webhook_url:
            return False

        try:
            # Color based on priority
            colors = {
                AlertPriority.CRITICAL: 0xFF0000,  # Red
                AlertPriority.HIGH: 0FFA500,  # Orange
                AlertPriority.MEDIUM: 0x00FF00,  # Green
                AlertPriority.LOW: 0x0000FF,  # Blue
                AlertPriority.INFO: 0x808080  # Gray
            }

            # Icons for different alert types
            icons = {
                AlertType.TRADING_SIGNAL: "🎯",
                AlertType.PORTFOLIO_UPDATE: "📊",
                AlertType.RISK_WARNING: "⚠️",
                AlertType.CONGRESSIONAL_TRADE: "🏛️",
                AlertType.INSIDER_TRADE: "👔",
                AlertType.EARNINGS: "📈",
                AlertType.MARKET_MOVE: "📉",
                AlertType.SYSTEM: "🔧"
            }

            icon = icons.get(alert_type, "📢")

            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url(self.discord_webhook_url, session=session)

                # Create embed
                embed = discord.Embed(
                    title=f"{icon} {title}",
                    description=message,
                    color=colors.get(priority, 0x000000),
                    timestamp=datetime.now()
                )

                # Add fields from data
                if data:
                    for key, value in list(data.items())[:5]:  # Limit to 5 fields
                        if isinstance(value, (str, int, float)):
                            embed.add_field(name=key.replace('_', ' ').title(),
                                         value=str(value),
                                         inline=True)

                embed.set_footer(text=f"Alert Type: {alert_type.value} | Priority: {priority.value}")

                await webhook.send(embed=embed)
                logger.info(f"Discord alert sent: {title}")
                return True

        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False

    async def _send_telegram(self,
                           title: str,
                           message: str,
                           alert_type: AlertType,
                           priority: AlertPriority,
                           data: Optional[Dict]) -> bool:
        """Send alert to Telegram"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return False

        try:
            import aiohttp

            # Format message for Telegram
            icons = {
                AlertPriority.CRITICAL: "🚨",
                AlertPriority.HIGH: "⚠️",
                AlertPriority.MEDIUM: "📊",
                AlertPriority.LOW: "ℹ️",
                AlertPriority.INFO: "💡"
            }

            icon = icons.get(priority, "📢")
            telegram_message = f"{icon} *{title}*\n\n{message}"

            if data:
                telegram_message += "\n\n*Details:*\n"
                for key, value in list(data.items())[:5]:
                    if isinstance(value, (str, int, float)):
                        telegram_message += f"• {key}: {value}\n"

            # Send via Telegram Bot API
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': telegram_message,
                'parse_mode': 'Markdown'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"Telegram alert sent: {title}")
                        return True
                    else:
                        logger.error(f"Telegram API error: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

    async def _send_email(self,
                         title: str,
                         message: str,
                         alert_type: AlertType,
                         priority: AlertPriority,
                         data: Optional[Dict]) -> bool:
        """Send alert via email"""
        if not EMAIL_AVAILABLE or not self.email_config:
            return False

        try:
            # Email configuration
            smtp_server = self.email_config.get('smtp_server', 'smtp.gmail.com')
            smtp_port = self.email_config.get('smtp_port', 587)
            sender_email = self.email_config.get('sender_email')
            sender_password = self.email_config.get('sender_password')
            recipient_email = self.email_config.get('recipient_email')

            if not all([sender_email, sender_password, recipient_email]):
                return False

            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{priority.value.upper()}] {title}"
            msg['From'] = sender_email
            msg['To'] = recipient_email

            # Create HTML content
            html_content = f"""
            <html>
              <body>
                <h2>{title}</h2>
                <p>{message.replace(chr(10), '<br>')}</p>
                <hr>
                <p><small>Alert Type: {alert_type.value} | Priority: {priority.value}</small></p>
              </body>
            </html>
            """

            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)

            logger.info(f"Email alert sent: {title}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False

    def _send_console(self,
                     title: str,
                     message: str,
                     alert_type: AlertType,
                     priority: AlertPriority,
                     data: Optional[Dict]):
        """Display alert in console"""
        # Color codes for terminal
        colors = {
            AlertPriority.CRITICAL: "\033[91m",  # Red
            AlertPriority.HIGH: "\033[93m",  # Yellow
            AlertPriority.MEDIUM: "\033[92m",  # Green
            AlertPriority.LOW: "\033[94m",  # Blue
            AlertPriority.INFO: "\033[95m"  # Magenta
        }
        reset_color = "\033[0m"

        color = colors.get(priority, "")

        print(f"\n{color}{'='*60}")
        print(f"🔔 ALERT: {title}")
        print(f"{'='*60}{reset_color}")
        print(f"Type: {alert_type.value} | Priority: {priority.value}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n{message}")

        if data:
            print("\nAdditional Data:")
            for key, value in data.items():
                print(f"  {key}: {value}")

        print(f"{color}{'='*60}{reset_color}\n")

    async def send_trading_signal(self, recommendation):
        """
        Send a trading signal alert

        Args:
            recommendation: TradingRecommendation object
        """
        from .signal_processor import TradingRecommendation

        if isinstance(recommendation, TradingRecommendation):
            # Format title based on action
            emoji = "🟢" if recommendation.action == "BUY" else "🔴"
            title = f"{emoji} {recommendation.action} Signal: {recommendation.ticker}"

            # Calculate potential gains
            gain_1 = ((recommendation.target_price_1 - recommendation.current_price) /
                     recommendation.current_price) * 100
            stop_loss_pct = ((recommendation.stop_loss - recommendation.current_price) /
                           recommendation.current_price) * 100

            message = f"""
Action: {recommendation.action}
Current Price: ${recommendation.current_price:.2f}
Entry Range: ${recommendation.entry_price_min:.2f} - ${recommendation.entry_price_max:.2f}
Target 1: ${recommendation.target_price_1:.2f} ({gain_1:+.1f}%)
Stop Loss: ${recommendation.stop_loss:.2f} ({stop_loss_pct:.1f}%)
Confidence: {recommendation.confidence:.0f}%
Position Size: {recommendation.position_size:.1%}
Risk Level: {recommendation.risk_level}

Reasoning: {recommendation.reasoning[:200]}
"""

            # Determine priority based on confidence
            if recommendation.confidence >= 85:
                priority = AlertPriority.HIGH
            elif recommendation.confidence >= 70:
                priority = AlertPriority.MEDIUM
            else:
                priority = AlertPriority.LOW

            await self.send_alert(
                title=title,
                message=message,
                alert_type=AlertType.TRADING_SIGNAL,
                priority=priority,
                data={
                    'ticker': recommendation.ticker,
                    'action': recommendation.action,
                    'confidence': recommendation.confidence
                }
            )

    async def send_portfolio_summary(self, portfolio_data: Dict):
        """Send daily portfolio summary"""
        title = "📊 Daily Portfolio Summary"

        total_value = portfolio_data.get('total_value', 0)
        total_pnl = portfolio_data.get('total_unrealized_pnl', 0)
        pnl_percent = portfolio_data.get('total_percent_change', 0)

        message = f"""
Total Value: ${total_value:,.2f}
Unrealized P&L: ${total_pnl:+,.2f} ({pnl_percent:+.2f}%)
Positions: {portfolio_data.get('position_count', 0)}

Top Performers:
"""
        # Add top positions
        positions = portfolio_data.get('positions', [])
        sorted_positions = sorted(positions, key=lambda x: x['percent'], reverse=True)

        for pos in sorted_positions[:3]:
            message += f"  • {pos['ticker']}: ${pos['value']:,.2f} ({pos['percent']:+.2f}%)\n"

        await self.send_alert(
            title=title,
            message=message,
            alert_type=AlertType.PORTFOLIO_UPDATE,
            priority=AlertPriority.INFO
        )


# Example usage
async def main():
    """Example of using the alert engine"""
    config = {
        'discord_webhook_url': os.getenv('DISCORD_WEBHOOK_URL'),
        'telegram_bot_token': os.getenv('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.getenv('TELEGRAM_CHAT_ID'),
    }

    alert_engine = AlertEngine(config)

    # Send test alert
    await alert_engine.send_alert(
        title="Test Trading Alert",
        message="NVDA showing strong buy signals based on congressional activity",
        alert_type=AlertType.TRADING_SIGNAL,
        priority=AlertPriority.HIGH,
        data={'ticker': 'NVDA', 'confidence': 85}
    )


if __name__ == "__main__":
    asyncio.run(main())