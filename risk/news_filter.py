"""
risk/news_filter.py
Fetches ForexFactory calendar and pauses trading around high-impact news events.
"""

import requests
from datetime import datetime, timedelta
from typing import Tuple
from core.logger import get_logger

logger = get_logger("NewsFilter")

# Pairs to monitor by currency
CURRENCY_SYMBOL_MAP = {
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD"],
    "EUR": ["EURUSD", "EURGBP", "EURJPY"],
    "GBP": ["GBPUSD", "EURGBP", "GBPJPY"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY"],
}


class NewsFilter:
    def __init__(self, settings):
        self.settings   = settings
        self._cache     = []
        self._cache_time = None

    def is_safe_to_trade(self, symbol: str) -> Tuple[bool, str]:
        """
        Returns (True, "") if it's safe to trade this symbol.
        Returns (False, reason) if a high-impact news event is imminent.
        """
        if not self.settings.NEWS_FILTER_ENABLED:
            return True, ""

        try:
            events = self._get_events()
            now    = datetime.utcnow()
            pause  = timedelta(minutes=self.settings.NEWS_PAUSE_MINUTES)

            # Get currencies in this symbol
            currencies = self._symbol_currencies(symbol)

            for event in events:
                event_time = event.get("datetime")
                currency   = event.get("currency", "")
                impact     = event.get("impact", "")
                title      = event.get("title", "")

                if impact != "High":
                    continue
                if currency not in currencies:
                    continue
                if not event_time:
                    continue

                time_diff = abs((event_time - now).total_seconds())
                if time_diff <= pause.total_seconds():
                    reason = (
                        f"High-impact news in {int(time_diff/60)}min: "
                        f"{currency} — {title}"
                    )
                    logger.warning(f"⚠️  News filter active: {reason}")
                    return False, reason

        except Exception as e:
            logger.error(f"News filter error (allowing trade): {e}")
            return True, ""  # Fail open — don't block trading on API error

        return True, ""

    def _get_events(self) -> list:
        """Fetch today's economic calendar. Cached for 60 minutes."""
        now = datetime.utcnow()
        if (self._cache_time and
                (now - self._cache_time).total_seconds() < 3600 and
                self._cache):
            return self._cache

        try:
            # ForexFactory doesn't have an official API; use a free proxy
            NEWS_URLS = [
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
            ]

            raw = None
            for url in NEWS_URLS:
                try:
                    resp = requests.get(url, timeout=10)
                    resp.raise_for_status()
                    raw = resp.json()
                    break
                except Exception:
                    continue

            if raw is None:
                logger.warning("All news API sources failed")
                return []

            events = []
            for item in raw:
                try:
                    dt_str = item.get("date", "") + " " + item.get("time", "")
                    dt_str = dt_str.strip()
                    # Parse format: "01-15-2024 8:30am"
                    try:
                        dt = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    except ValueError:
                        dt = None

                    events.append({
                        "datetime": dt,
                        "currency": item.get("country", "").upper(),
                        "impact":   item.get("impact", ""),
                        "title":    item.get("title", ""),
                    })
                except Exception:
                    continue

            self._cache      = events
            self._cache_time = now
            logger.info(f"News calendar loaded: {len(events)} events")
            return events

        except Exception as e:
            logger.error(f"Could not fetch news calendar: {e}")
            return []

    def _symbol_currencies(self, symbol: str) -> list:
        """Extract base and quote currencies from symbol."""
        # Strip common Exness suffixes like 'm'
        symbol = symbol.replace(".", "").upper()
        for suffix in ["M", "C", "S", "B"]:
            if symbol.endswith(suffix) and len(symbol) > 6:
                symbol = symbol[:-1]
        if len(symbol) >= 6:
            return [symbol[:3], symbol[3:6]]
        return []
