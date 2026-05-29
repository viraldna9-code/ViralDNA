"""
Audience Channel Manager v1.0
H3.6: WhatsApp and Telegram audience engagement channels.
Sends video notifications, community updates, and engagement messages
to configured messaging channels.
"""
import os, json, requests
from datetime import datetime


class AudienceChannelManager:
    """
    Manages audience engagement via WhatsApp and Telegram.
    H3.6: Multi-channel audience building outside YouTube.
    """

    def __init__(self, config_instance=None, *args, **kwargs):
        self.config = config_instance
        self.channels_config = {}

        if config_instance:
            self.channels_config = getattr(config_instance, "NOTIFICATION_CONFIG", {}).get("channels", {})
        else:
            # Fallback: load from config module
            try:
                import config as cfg
                self.channels_config = cfg.NOTIFICATION_CONFIG.get("channels", {})
            except Exception:
                pass

        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        # Track channel engagement stats
        self.channel_stats_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "channel_engagement.json"
        )

    # ── Channel Status ──

    def get_channel_status(self) -> dict:
        """Returns status of all configured channels."""
        status = {
            "telegram": {"enabled": False, "configured": False},
            "whatsapp": {"enabled": False, "configured": False},
        }

        tg = self.channels_config.get("telegram", {})
        if tg.get("bot_token") and tg.get("chat_id"):
            status["telegram"] = {"enabled": tg.get("enabled", False), "configured": True}
        elif tg.get("bot_token") or tg.get("chat_id"):
            status["telegram"] = {"enabled": False, "configured": False, "note": "Incomplete config"}

        # WhatsApp via Twilio or WhatsApp Business API
        wa = self.channels_config.get("whatsapp", {})
        if wa.get("enabled") and (wa.get("twilio_sid") or wa.get("api_key")):
            status["whatsapp"] = {"enabled": True, "configured": True}
        elif wa.get("api_key") or wa.get("twilio_sid"):
            status["whatsapp"] = {"enabled": wa.get("enabled", False), "configured": True}

        return status

    # ── Video Notification ──

    def send_video_notification(self, title: str, video_url: str,
                                 description: str = "",
                                 channels: list = None) -> dict:
        """
        Send a new video notification to configured channels.
        H3.6: Audience building through multi-channel distribution.
        """
        results = {}
        channels = channels or ["telegram"]

        for channel in channels:
            if channel == "telegram":
                results["telegram"] = self._send_telegram_notification(title, video_url, description)
            elif channel == "whatsapp":
                results["whatsapp"] = self._send_whatsapp_notification(title, video_url, description)

        # Log to engagement stats
        self._log_engagement("video_notification", results)
        return results

    def _send_telegram_notification(self, title: str, video_url: str,
                                     description: str = "") -> dict:
        """Send notification via Telegram Bot API."""
        tg = self.channels_config.get("telegram", {})
        bot_token = tg.get("bot_token", "")
        chat_id = tg.get("chat_id", "")

        if not bot_token or not chat_id:
            return {"sent": False, "reason": "telegram_not_configured"}

        try:
            emoji = "🎬"
            if any(w in title.lower() for w in ["breaking", "urgent", "alert"]):
                emoji = "🚨"
            elif "?" in title:
                emoji = "❓"

            message = (
                f"{emoji} **New Video: {title}**\n\n"
                f"{description[:200] if description else 'Watch now on ViralDNA!'}\n\n"
                f"▶️ {video_url}\n\n"
                f"#TeluguNews #ViralDNA"
            )

            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = requests.post(api_url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            }, timeout=10)

            if resp.status_code == 200:
                result = resp.json()
                if result.get("ok"):
                    return {"sent": True, "channel": "telegram", "message_id": result["result"]["message_id"]}
                return {"sent": False, "channel": "telegram", "reason": result.get("description", "unknown")}
            return {"sent": False, "channel": "telegram", "reason": f"HTTP {resp.status_code}"}

        except Exception as e:
            return {"sent": False, "channel": "telegram", "reason": str(e)[:100]}

    def _send_whatsapp_notification(self, title: str, video_url: str,
                                     description: str = "") -> dict:
        """
        Send notification via WhatsApp Business API or Twilio.
        Supports: Twilio WhatsApp, WhatsApp Business API, or WhatsApp Link.
        """
        wa = self.channels_config.get("whatsapp", {})

        # Method 1: Twilio WhatsApp
        if wa.get("twilio_sid") and wa.get("twilio_token"):
            return self._send_twilio_whatsapp(title, video_url, description, wa)

        # Method 2: WhatsApp Business API (direct)
        if wa.get("api_key") and wa.get("phone_id"):
            return self._send_wa_business_api(title, video_url, description, wa)

        # Method 3: WhatsApp share link (no API needed)
        return {
            "sent": False,
            "channel": "whatsapp",
            "reason": "no_api_configured",
            "note": "WhatsApp share link can be used manually",
            "share_link": f"https://wa.me/?text={requests.utils.quote(f'New ViralDNA video: {title} {video_url}')}",
        }

    def _send_twilio_whatsapp(self, title, video_url, description, wa) -> dict:
        """Send via Twilio WhatsApp API."""
        try:
            from requests.auth import HTTPBasicAuth
            message = f"🎬 New ViralDNA Video: {title}\n\n{video_url}"
            api_url = (
                f"https://api.twilio.com/2010-04-01/Accounts/{wa['twilio_sid']}/Messages.json"
            )
            resp = requests.post(api_url, auth=HTTPBasicAuth(wa["twilio_sid"], wa["twilio_token"]), data={
                "From": f"whatsapp:{wa.get('from_number', '')}",
                "To": f"whatsapp:{wa.get('to_number', '')}",
                "Body": message,
            }, timeout=10)
            if resp.status_code in (200, 201):
                return {"sent": True, "channel": "whatsapp", "method": "twilio"}
            return {"sent": False, "channel": "whatsapp", "method": "twilio",
                    "reason": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"sent": False, "channel": "whatsapp", "method": "twilio", "reason": str(e)[:100]}

    def _send_wa_business_api(self, title, video_url, description, wa) -> dict:
        """Send via WhatsApp Business API (Meta/Facebook)."""
        try:
            message = {
                "messaging_product": "whatsapp",
                "to": wa.get("to_number", ""),
                "type": "text",
                "text": {"body": f"🎬 New ViralDNA Video: {title}\n\n{video_url}"}
            }
            api_url = (
                f"https://graph.facebook.com/v17.0/{wa['phone_id']}/messages"
            )
            resp = requests.post(api_url, json=message, headers={
                "Authorization": f"Bearer {wa['api_key']}",
                "Content-Type": "application/json",
            }, timeout=10)
            if resp.status_code == 200:
                return {"sent": True, "channel": "whatsapp", "method": "business_api"}
            return {"sent": False, "channel": "whatsapp", "method": "business_api",
                    "reason": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"sent": False, "channel": "whatsapp", "method": "business_api",
                    "reason": str(e)[:100]}

    # ── Community Engagement Messages ──

    def send_milestone_update(self, milestone: int, subscriber_count: int) -> dict:
        """Send milestone celebration to all configured channels."""
        text = f"🎉 ViralDNA just hit {milestone:,} subscribers! Thank you, Telugu community!"
        results = {}

        if self.channels_config.get("telegram", {}).get("enabled"):
            results["telegram"] = self._send_telegram_notification(
                f"Milestone: {milestone:,} subscribers!", "", text
            )

        return results

    def send_daily_digest(self, videos_today: int, top_video: str = "") -> dict:
        """Send daily video digest to audience channels."""
        text = (
            f"📰 ViralDNA Daily Digest\n\n"
            f"🎬 Videos today: {videos_today}\n"
        )
        if top_video:
            text += f"🔥 Top video: {top_video}\n"
        text += "\n#TeluguNews #ViralDNA"

        results = {}
        if self.channels_config.get("telegram", {}).get("enabled"):
            results["telegram"] = self._send_telegram_notification(
                "Daily Digest", "", text
            )
        return results

    # ── Engagement Stats ──

    def _log_engagement(self, action: str, results: dict):
        """Log channel engagement to stats file."""
        try:
            stats = {
                "action": action,
                "results": results,
                "timestamp": datetime.now().isoformat(),
            }
            existing = []
            if os.path.exists(self.channel_stats_path):
                with open(self.channel_stats_path, "r") as f:
                    existing = json.load(f)
            existing.append(stats)
            os.makedirs(os.path.dirname(self.channel_stats_path), exist_ok=True)
            with open(self.channel_stats_path, "w") as f:
                json.dump(existing[-200:], f, indent=2)  # keep last 200
        except Exception:
            pass

    # ── Legacy pass-through ──

    def execute(self, state):
        return state
