"""
execution/discord_notifier.py
═══════════════════════════════════════════════════════════════
Discord notifications via Webhook.

Uses Discord webhooks (no bot token required).
Setup:
  1. In Discord → Server Settings → Integrations → Webhooks
  2. Create webhook → Copy URL
  3. Paste into config/.env → DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

Supports rich embeds with colors, fields, and trade details.
═══════════════════════════════════════════════════════════════
"""

import requests
from datetime import datetime, timezone
from typing import Optional, List, Dict
from core.logger import get_logger

logger = get_logger("Discord")

# Discord embed color codes (decimal)
COLOR_GREEN  = 0x2ECC71   # Win / Buy / Startup
COLOR_RED    = 0xE74C3C   # Loss / Sell / Limit hit
COLOR_GOLD   = 0xF1C40F   # Warning / Medium risk
COLOR_BLUE   = 0x3498DB   # Info / Summary
COLOR_PURPLE = 0x9B59B6   # AI Advisor


class DiscordNotifier:
    """
    Sends rich embed notifications to a Discord channel via webhook.
    """

    def __init__(self, settings):
        self.webhook_url = getattr(settings, "DISCORD_WEBHOOK_URL", "")
        self.username    = getattr(settings, "DISCORD_BOT_NAME", "Exness AutoTrader")
        self.avatar_url  = getattr(settings, "DISCORD_AVATAR_URL", "")
        self.enabled     = bool(self.webhook_url)

        if self.enabled:
            logger.info("Discord notifications enabled.")
        else:
            logger.info("Discord notifications disabled (no webhook URL).")

    def send_embed(self, title: str, description: str = "",
                   color: int = COLOR_BLUE,
                   fields: Optional[List[Dict]] = None,
                   footer: str = ""):
        """Send a rich embed to the Discord webhook."""
        if not self.enabled:
            return

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if fields:
            embed["fields"] = fields

        if footer:
            embed["footer"] = {"text": footer}

        payload = {
            "username": self.username,
            "embeds": [embed],
        }

        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                logger.warning(f"Discord send failed [{resp.status_code}]: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Discord error: {e}")

    def send_message(self, content: str):
        """Send a plain text message."""
        if not self.enabled:
            return
        try:
            payload = {"username": self.username, "content": content}
            if self.avatar_url:
                payload["avatar_url"] = self.avatar_url
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code not in (200, 204):
                logger.warning(f"Discord send failed: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"Discord error: {e}")

    # ── Trade Alerts ──────────────────────────────────────────────────────

    def send_trade_alert(self, signal, lot: float,
                         ticket: int, daily_pnl: float):
        """Send rich embed for a new trade execution."""
        d_emoji = "📈" if signal.direction == "BUY" else "📉"
        color   = COLOR_GREEN if signal.direction == "BUY" else COLOR_RED

        reasons_str = "\n".join(f"• {r}" for r in signal.reasons[:8])

        # Build regime/AI info if available
        extra_info = ""
        if hasattr(signal, 'regime') and signal.regime != "UNKNOWN":
            extra_info += f"**Regime:** {signal.regime} (ADX:{signal.adx:.0f})\n"
        if hasattr(signal, 'gemini_decision') and signal.gemini_decision:
            extra_info += f"**🤖 AI:** {signal.gemini_decision}\n"
        if hasattr(signal, 'session') and signal.session:
            extra_info += f"**Session:** {signal.session}\n"

        fields = [
            {"name": "🎯 Order Details", "value": f"**Entry:** `{signal.entry:.5f}`\n**SL:** `{signal.stop_loss:.5f}`\n**TP:** `{signal.take_profit:.5f}`", "inline": True},
            {"name": "⚖️ Risk Profile", "value": f"**Lot:** `{lot}`\n**Risk:** `{signal.risk_level}`\n**P&L:** `{daily_pnl:+.2f}%`", "inline": True},
            {"name": "📊 Market State", "value": f"**Regime:** `{signal.regime}`\n**Ticket:** `#{ticket}`", "inline": True},
        ]

        desc = f"{reasons_str}"
        if extra_info:
            desc += f"\n\n{extra_info}"

        self.send_embed(
            title=f"{d_emoji} EXECUTED: {signal.direction} {signal.symbol}",
            description=desc,
            color=color,
            fields=fields,
            footer=signal.timestamp,
        )

    # ── AI Advisor Decision ───────────────────────────────────────────────

    def send_ai_decision(self, symbol: str, direction: str,
                         decision: str, confidence: int,
                         reasoning: str):
        """Send Gemini AI advisor's trade review decision."""
        icon_map = {"APPROVE": "✅", "REJECT": "❌", "REDUCE_SIZE": "⚠️"}
        color_map = {"APPROVE": COLOR_GREEN, "REJECT": COLOR_RED,
                     "REDUCE_SIZE": COLOR_GOLD}

        icon  = icon_map.get(decision, "❓")
        color = color_map.get(decision, COLOR_BLUE)

        self.send_embed(
            title=f"🤖 AI Verdict: {icon} {decision} — {direction} {symbol}",
            description=reasoning[:2000],
            color=color,
            fields=[
                {"name": "AI Confidence", "value": f"`{confidence}%`", "inline": True},
            ],
        )

    # ── Trade Closed ─────────────────────────────────────────────────────

    def send_trade_closed(self, symbol: str, direction: str,
                          ticket: int, profit: float, hit_tp: bool):
        """Send notification when a trade closes."""
        emoji = "✅" if hit_tp else "❌"
        color = COLOR_GREEN if hit_tp else COLOR_RED
        result = "WIN" if hit_tp else "LOSS"

        self.send_embed(
            title=f"{emoji} Trade Closed — {result}",
            description=f"**{direction} {symbol}** (#{ticket})",
            color=color,
            fields=[
                {"name": "Profit", "value": f"`{profit:+.2f}`", "inline": True},
                {"name": "Result", "value": f"`{result}`", "inline": True},
            ],
        )

    # ── Daily Summary ────────────────────────────────────────────────────

    def send_daily_summary(self, summary: dict, account: dict):
        """Send end-of-day performance summary."""
        pnl     = summary.get("pnl_pct", 0)
        trades  = summary.get("trades", 0)
        stopped = summary.get("stopped", False)
        color   = COLOR_GREEN if pnl >= 0 else COLOR_RED
        emoji   = "🎯" if pnl >= 0 else "🛑"

        stop_info = ""
        if stopped:
            stop_info = f"\n⏹ **Stopped:** {summary.get('stop_reason', 'Unknown')}"

        fields = [
            {"name": "Balance", "value": f"`{account['balance']:.2f} {account['currency']}`", "inline": True},
            {"name": "Daily P&L", "value": f"`{pnl:+.2f}%`", "inline": True},
            {"name": "Trades", "value": f"`{trades}`", "inline": True},
        ]

        self.send_embed(
            title=f"{emoji} Daily Summary — {summary.get('date', 'Today')}",
            description=stop_info if stop_info else "Trading day complete.",
            color=color,
            fields=fields,
        )

    # ── Startup ──────────────────────────────────────────────────────────

    def send_startup(self, symbols: list, balance: float, currency: str):
        """Send bot startup notification."""
        syms = ", ".join(symbols)
        self.send_embed(
            title="🚀 Exness AutoTrader v2.0 Started",
            description=(
                f"**Balance:** {balance:.2f} {currency}\n"
                f"**Pairs:** {syms}\n"
                f"**Filters:** Rules → ADX → H4 → Session → ML → Gemini AI\n\n"
                f"System online and monitoring markets."
            ),
            color=COLOR_GREEN,
        )

    # ── Daily Limit ──────────────────────────────────────────────────────

    def send_daily_limit_hit(self, reason: str, pnl: float):
        """Send alert when daily P&L limit is reached."""
        emoji = "🎯" if pnl > 0 else "🛑"
        color = COLOR_GREEN if pnl > 0 else COLOR_RED

        self.send_embed(
            title=f"{emoji} Daily Limit Hit — Trading Paused",
            description=f"{reason}\nDaily P&L: `{pnl:+.2f}%`\nBot will resume tomorrow.",
            color=color,
        )

    # ── Custom Alert ─────────────────────────────────────────────────────

    def send_alert(self, title: str, message: str,
                   color: int = COLOR_GOLD):
        """Send a custom alert (errors, warnings, etc.)."""
        self.send_embed(title=title, description=message, color=color)
