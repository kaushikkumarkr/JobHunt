import requests
import logging
import os
from typing import List
from sources.base import JobLead
from config.loader import get_config

logger = logging.getLogger(__name__)

class InstantNotifier:
    def __init__(self):
        self.config = get_config()
        
        # Telegram
        self.tg_enabled = self.config["notifications"]["telegram"]["enabled"]
        self.tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        # Discord
        self.discord_enabled = self.config["notifications"]["discord"]["enabled"]
        self.discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    def notify(self, lead: JobLead):
        """Send instant notification for a single high-value lead."""
        msg = self._format_message(lead)
        
        if self.tg_enabled and self.tg_token and self.tg_chat_id:
            self._send_telegram(msg)
            
        if self.discord_enabled and self.discord_webhook:
            self._send_discord(msg)

    def _format_message(self, lead: JobLead) -> str:
        # Markdown format
        score = int(lead.match_score * 100)
        return (
            f"🔥 **New High Match: {score}%**\n"
            f"**Role:** {lead.role_title}\n"
            f"**Company:** {lead.company}\n"
            f"**Location:** {lead.location_raw}\n"
            f"**Link:** [Apply Here]({lead.link})\n"
            f"**Why:** {lead.matched_keywords}"
        )

    def _send_telegram(self, text: str):
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            payload = {"chat_id": self.tg_chat_id, "text": text, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Telegram fail: {e}")

    def _send_discord(self, text: str):
        try:
            # Discord uses 'content'
            payload = {"content": text}
            requests.post(self.discord_webhook, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Discord fail: {e}")
