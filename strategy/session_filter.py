"""
strategy/session_filter.py
Trading Session Filter.

Forex pairs have optimal trading windows based on market sessions.
Trading outside these windows increases false signals and slippage.

Sessions (UTC):
  Tokyo:   00:00 - 09:00 UTC
  London:  07:00 - 16:00 UTC
  New York: 12:00 - 21:00 UTC
  Overlap:  12:00 - 16:00 UTC (highest liquidity)
"""

from datetime import datetime, timezone
from typing import Tuple, Dict, List
from core.logger import get_logger

logger = get_logger("SessionFilter")

# Optimal trading hours per symbol (UTC)
SESSION_MAP: Dict[str, List[Tuple[int, int]]] = {
    "EURUSD":  [(7, 20)],  "EURUSDm": [(7, 20)],
    "EURGBP":  [(7, 16)],  "EURGBPm": [(7, 16)],
    "EURJPY":  [(7, 16)],  "EURJPYm": [(7, 16)],
    "GBPUSD":  [(7, 20)],  "GBPUSDm": [(7, 20)],
    "GBPJPY":  [(7, 16)],  "GBPJPYm": [(7, 16)],
    "USDJPY":  [(0, 9), (12, 20)],  "USDJPYm": [(0, 9), (12, 20)],
    "XAUUSD":  [(7, 21)],  "XAUUSDm": [(7, 21)],
    "USDCAD":  [(12, 21)], "USDCADm": [(12, 21)],
    "USDCHF":  [(7, 20)],  "USDCHFm": [(7, 20)],
    "AUDUSD":  [(0, 9), (12, 20)],  "AUDUSDm": [(0, 9), (12, 20)],
    "NZDUSD":  [(0, 9), (12, 20)],  "NZDUSDm": [(0, 9), (12, 20)],
}

DEFAULT_HOURS: List[Tuple[int, int]] = [(7, 21)]


class SessionFilter:
    """Filters trades based on optimal market session hours."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_optimal_session(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if current UTC time is within optimal trading hours for this symbol.
        Returns (is_optimal: bool, reason: str)
        """
        if not self.enabled:
            return True, ""

        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour

        # Weekend check
        if now_utc.weekday() >= 5:
            return False, "Weekend — forex markets closed"

        # Normalize symbol to base (e.g. EURUSDr -> EURUSD) to match map keys
        normalized = symbol.replace(".", "").upper()
        for suffix in ["M", "R", "Z", "X", "C"]:
            if normalized.endswith(suffix) and len(normalized) > 6:
                normalized = normalized[:-1]

        windows = SESSION_MAP.get(normalized, SESSION_MAP.get(symbol, DEFAULT_HOURS))

        for start_h, end_h in windows:
            if start_h <= current_hour < end_h:
                session = self._identify_session(current_hour)
                return True, f"Active: {session}"

        next_w = self._next_window(windows, current_hour)
        return False, f"Off-session for {symbol} — next: {next_w}"

    def _identify_session(self, hour: int) -> str:
        """Identify which market session is currently active."""
        if 0 <= hour < 9:
            return "Tokyo/Asian"
        elif 7 <= hour < 12:
            return "London"
        elif 12 <= hour < 16:
            return "London-NY Overlap"
        elif 16 <= hour < 21:
            return "New York"
        else:
            return "Off-hours"

    def _next_window(self, windows: List[Tuple[int, int]],
                     current_hour: int) -> str:
        """Find the next trading window."""
        for start_h, end_h in sorted(windows):
            if start_h > current_hour:
                return f"{start_h:02d}:00 UTC"
        if windows:
            return f"{windows[0][0]:02d}:00 UTC (tomorrow)"
        return "Unknown"

    def get_session_info(self) -> str:
        """Current session info for dashboard."""
        now_utc = datetime.now(timezone.utc)
        session = self._identify_session(now_utc.hour)
        return f"{session} ({now_utc.strftime('%H:%M')} UTC)"
