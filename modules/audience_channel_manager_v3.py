"""
Audience Channel Manager v3.0 — VDNA 3.0 Port
Audience notification dispatch to Telegram/WhatsApp after upload.
Uses existing AudienceChannelManager from audience_channel_manager.py.
Ported from old pipeline's AudienceChannelManagerAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from audience_channel_manager import AudienceChannelManager
from datetime import datetime


class AudienceChannelManagerV3:
    """
    Post-pipeline audience channel manager: sends video notifications
    to configured messaging channels (Telegram, WhatsApp) after successful upload.
    """

    def __init__(self, *args, **kwargs):
        try:
            import config
            acm_config = getattr(config, 'AUDIENCE_CHANNEL_CONFIG', {})
        except Exception:
            acm_config = {}
        self.manager = AudienceChannelManager(acm_config)

    def notify(self, title: str = "", video_url: str = "", youtube_id: str = "") -> dict:
        """Send audience channel notifications. Returns result dict."""
        result = {
            "telegram_sent": False,
            "telegram_reason": "not_attempted",
            "notified_at": datetime.now().isoformat(),
        }

        try:
            channel_status = self.manager.get_channel_status()
            tg_configured = channel_status.get("telegram", {}).get("configured", False)
            tg_enabled = channel_status.get("telegram", {}).get("enabled", False)

            if tg_configured and tg_enabled:
                notify_result = self.manager.send_video_notification(
                    title=title,
                    video_url=video_url,
                    channels=["telegram"],
                )
                tg_result = notify_result.get("telegram", {})
                result["telegram_sent"] = tg_result.get("sent", False)
                result["telegram_reason"] = tg_result.get("reason", "unknown")
            else:
                result["telegram_reason"] = "not_configured"
        except Exception as e:
            result["telegram_reason"] = str(e)[:100]

        return result

    def execute(self, state):
        return state
