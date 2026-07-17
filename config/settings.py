"""
config/settings.py
Loads and validates all configuration from .env
"""

import os
from dotenv import load_dotenv, set_key
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).parent / ".env.example"
load_dotenv(env_path)


def _get(key, default=None, cast=str):
    val = os.getenv(key, default)
    if val is None:
        return None
    try:
        return cast(val)
    except (ValueError, TypeError):
        return default


class Settings:
    # MT5
    MT5_LOGIN        = _get("MT5_LOGIN", cast=int)
    MT5_PASSWORD     = _get("MT5_PASSWORD")
    MT5_SERVER       = _get("MT5_SERVER", "Exness-MT5Real")
    MT5_PATH         = _get("MT5_PATH", "")

    # Symbols & timeframe
    SYMBOLS          = [s.strip() for s in _get("SYMBOLS", "EURUSD").split(",") if s.strip()]
    TIMEFRAME        = _get("TIMEFRAME", "H1")

    # Daily risk limits
    DAILY_PROFIT_TARGET_PCT = _get("DAILY_PROFIT_TARGET_PCT", 4.0, float)
    DAILY_LOSS_LIMIT_PCT    = _get("DAILY_LOSS_LIMIT_PCT",    2.0, float)
    RISK_PER_TRADE_PCT      = _get("RISK_PER_TRADE_PCT",      1.0, float)
    MAX_OPEN_TRADES         = _get("MAX_OPEN_TRADES",         3,   int)

    # Trailing stop
    ATR_TRAIL_MULTIPLIER = _get("ATR_TRAIL_MULTIPLIER", 1.5, float)
    ATR_PERIOD           = _get("ATR_PERIOD",           14,  int)

    # Strategy
    CHANDELIER_PERIOD     = _get("CHANDELIER_PERIOD",     22,  int)
    CHANDELIER_MULTIPLIER = _get("CHANDELIER_MULTIPLIER", 3.0, float)
    RSI_PERIOD            = _get("RSI_PERIOD",            14,  int)
    RSI_OVERBOUGHT        = _get("RSI_OVERBOUGHT",        70,  int)
    RSI_OVERSOLD          = _get("RSI_OVERSOLD",          30,  int)

    # Telegram
    TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID   = _get("TELEGRAM_CHAT_ID")

    # News filter
    NEWS_FILTER_ENABLED = _get("NEWS_FILTER_ENABLED", "true").lower() == "true"
    NEWS_PAUSE_MINUTES  = _get("NEWS_PAUSE_MINUTES", 30, int)

    # Gemini AI Advisor
    GEMINI_API_KEY         = _get("GEMINI_API_KEY")
    GEMINI_MODEL           = _get("GEMINI_MODEL", "gemini-2.0-flash")
    GEMINI_ENABLED         = _get("GEMINI_ENABLED", "true").lower() == "true"
    GEMINI_HIGH_RISK_PCT   = _get("GEMINI_HIGH_RISK_PCT", 2.0, float)
    GEMINI_MEDIUM_RISK_PCT = _get("GEMINI_MEDIUM_RISK_PCT", 1.0, float)

    # Session Filter
    SESSION_FILTER_ENABLED = _get("SESSION_FILTER_ENABLED", "true").lower() == "true"

    # Multi-Timeframe Filter
    MTF_ENABLED = _get("MTF_ENABLED", "true").lower() == "true"

    # ADX Regime Filter
    ADX_FILTER_ENABLED = _get("ADX_FILTER_ENABLED", "true").lower() == "true"
    ADX_MIN_TREND      = _get("ADX_MIN_TREND", 20, int)

    # Discord Notifications (webhook — no bot token needed)
    DISCORD_WEBHOOK_URL = _get("DISCORD_WEBHOOK_URL")
    DISCORD_BOT_NAME    = _get("DISCORD_BOT_NAME", "Exness AutoTrader")
    DISCORD_AVATAR_URL  = _get("DISCORD_AVATAR_URL")

    # Logging
    LOG_LEVEL = _get("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls):
        errors = []
        if not cls.MT5_LOGIN:
            errors.append("MT5_LOGIN is not set")
        if not cls.MT5_PASSWORD:
            errors.append("MT5_PASSWORD is not set")
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
        return True

    @classmethod
    def update_setting(cls, key: str, value: str, cast_type=str):
        """Update live memory and rewrite to .env file."""
        # 1. Update live attribute
        if hasattr(cls, key):
            try:
                # Handle special boolean parsing
                if cast_type == bool:
                    cast_val = str(value).lower() == "true"
                elif cast_type == list:
                    cast_val = [s.strip() for s in str(value).split(",") if s.strip()]
                else:
                    cast_val = cast_type(value)
                setattr(cls, key, cast_val)
            except Exception as e:
                print(f"Failed to cast {key}: {e}")
                
        # 2. Update .env file
        try:
            set_key(str(env_path), key, str(value))
        except Exception as e:
            print(f"Failed to save {key} to .env: {e}")

settings = Settings()
