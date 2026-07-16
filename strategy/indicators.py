"""
strategy/indicators.py
Computes Chandelier Exit and ATR for the new trend-following core.
"""

import pandas as pd
import numpy as np
from core.logger import get_logger

logger = get_logger("Indicators")


def add_indicators(df: pd.DataFrame, settings) -> pd.DataFrame:
    df = df.copy()

    # ── ATR ───────────────────────────────────────────────────────────────────
    # We use a Wilder's Smoothing / exponential moving average for ATR
    hl  = df["high"] - df["low"]
    hc  = (df["high"] - df["close"].shift()).abs()
    lc  = (df["low"]  - df["close"].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=settings.CHANDELIER_PERIOD, adjust=False).mean()

    # ── Chandelier Exit ───────────────────────────────────────────────────────
    period = settings.CHANDELIER_PERIOD
    mult   = settings.CHANDELIER_MULTIPLIER

    # Rolling Highest High and Lowest Low
    df["highest_high"] = df["high"].rolling(window=period).max()
    df["lowest_low"]   = df["low"].rolling(window=period).min()

    # Chandelier Exit Lines
    df["chandelier_long"]  = df["highest_high"] - (df["atr"] * mult)
    df["chandelier_short"] = df["lowest_low"]   + (df["atr"] * mult)

    # Determine Trend Direction (1 for Bullish, -1 for Bearish)
    # A close above the Short line flips the trend to Bullish.
    # A close below the Long line flips the trend to Bearish.
    trend = np.zeros(len(df))
    close = df["close"].values
    c_long = df["chandelier_long"].values
    c_short = df["chandelier_short"].values

    current_trend = 1
    for i in range(len(df)):
        if close[i] > c_short[i]:
            current_trend = 1
        elif close[i] < c_long[i]:
            current_trend = -1
        trend[i] = current_trend

    df["chandelier_trend"] = trend

    # Determine Crosses
    prev_trend = df["chandelier_trend"].shift(1).fillna(0)
    df["chandelier_cross"] = np.where(
        (df["chandelier_trend"] == 1) & (prev_trend == -1), 1,
        np.where((df["chandelier_trend"] == -1) & (prev_trend == 1), -1, 0)
    )

    # ── RSI (Kept for basic context) ──────────────────────────────────────────
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=settings.RSI_PERIOD - 1, adjust=False).mean()
    avg_l = loss.ewm(com=settings.RSI_PERIOD - 1, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    df["rsi"] = (100 - (100 / (1 + rs))).fillna(50)

    return df


def get_latest(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    return {
        "close":            round(float(row["close"]), 5),
        "atr":              round(float(row["atr"]), 6),
        "chandelier_long":  round(float(row["chandelier_long"]), 5),
        "chandelier_short": round(float(row["chandelier_short"]), 5),
        "chandelier_trend": int(row["chandelier_trend"]),
        "chandelier_cross": int(row["chandelier_cross"]),
        "rsi":              round(float(row["rsi"]), 2),
        "timestamp":        str(df.index[-1]),
    }
