"""
strategy/regime_filter.py
Market Regime Detection using ADX (Average Directional Index).

Filters out trades during low-volatility, ranging/choppy markets
where trend-following strategies (EMA/MACD) perform poorly.

ADX interpretation:
  < 20  = No trend (ranging) -> DO NOT TRADE
  20-25 = Weak trend -> Trade with caution (reduce size)
  25-50 = Strong trend -> TRADE NORMALLY
  50-75 = Very strong trend -> TRADE (watch for exhaustion)
  > 75  = Extremely strong -> Cautious (trend exhaustion likely)
"""

import pandas as pd
import numpy as np
from typing import Tuple
from core.logger import get_logger

logger = get_logger("RegimeFilter")


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Compute ADX (Average Directional Index) and +DI/-DI.
    Returns DataFrame with 'adx', 'plus_di', 'minus_di' columns added.
    """
    df = df.copy()
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smoothed averages (Wilder's smoothing)
    atr_s = pd.Series(tr, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()

    # Directional Indicators
    plus_di = (plus_dm_smooth / atr_s.replace(0, np.nan)) * 100
    minus_di = (minus_dm_smooth / atr_s.replace(0, np.nan)) * 100

    # DX and ADX
    di_sum = plus_di + minus_di
    dx = ((plus_di - minus_di).abs() / di_sum.replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    df["adx"] = adx.fillna(0)
    df["plus_di"] = plus_di.fillna(0)
    df["minus_di"] = minus_di.fillna(0)

    return df


class RegimeFilter:
    """
    Market regime detector using ADX.
    Prevents trend-following strategies from trading in ranging markets.
    """

    ADX_NO_TREND = 20
    ADX_WEAK_TREND = 25
    ADX_STRONG_TREND = 50
    ADX_EXHAUSTION = 75

    def __init__(self, min_adx: int = 20):
        self.ADX_NO_TREND = min_adx
        self._cache = {}

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict:
        """Analyze market regime for the given dataframe."""
        try:
            df_adx = compute_adx(df)
            latest = df_adx.iloc[-1]

            adx = float(latest["adx"])
            plus_di = float(latest["plus_di"])
            minus_di = float(latest["minus_di"])

            if adx < self.ADX_NO_TREND:
                regime = "RANGING"
            elif adx < self.ADX_WEAK_TREND:
                regime = "WEAK_TREND"
            elif adx < self.ADX_STRONG_TREND:
                regime = "TRENDING"
            elif adx < self.ADX_EXHAUSTION:
                regime = "STRONG_TREND"
            else:
                regime = "EXHAUSTION"

            di_direction = "BULL" if plus_di > minus_di else "BEAR"

            result = {
                "adx": round(adx, 2),
                "plus_di": round(plus_di, 2),
                "minus_di": round(minus_di, 2),
                "regime": regime,
                "di_direction": di_direction,
            }
            self._cache[symbol] = result
            return result

        except Exception as e:
            logger.error(f"Regime analysis error for {symbol}: {e}")
            return {"adx": 0, "plus_di": 0, "minus_di": 0,
                    "regime": "UNKNOWN", "di_direction": "UNKNOWN"}

    def should_trade(self, df: pd.DataFrame, symbol: str,
                     direction: str) -> Tuple[bool, str, int]:
        """
        Determine if market conditions are suitable for trading.

        Returns:
            (should_trade: bool, reason: str, confidence_adjustment: int)
        """
        regime_data = self.analyze(df, symbol)
        adx = regime_data["adx"]
        regime = regime_data["regime"]
        di_dir = regime_data["di_direction"]

        if regime == "RANGING":
            return (False,
                    f"Market ranging (ADX {adx:.0f} < {self.ADX_NO_TREND}) — no trend",
                    0)

        if regime == "WEAK_TREND":
            return (True,
                    f"Weak trend (ADX {adx:.0f}) — proceed with caution",
                    -5)

        if regime == "EXHAUSTION":
            if ((direction == "BUY" and di_dir == "BULL") or
                    (direction == "SELL" and di_dir == "BEAR")):
                return (False,
                        f"Trend exhaustion (ADX {adx:.0f}) — reversal risk",
                        0)
            return (True,
                    f"Trend exhaustion (ADX {adx:.0f}) — counter-trend possible",
                    -3)

        # TRENDING or STRONG_TREND
        di_aligned = ((direction == "BUY" and di_dir == "BULL") or
                      (direction == "SELL" and di_dir == "BEAR"))

        if di_aligned:
            bonus = 5 if regime == "STRONG_TREND" else 3
            return (True,
                    f"{regime} (ADX {adx:.0f}), DI confirms {direction}",
                    bonus)
        else:
            return (True,
                    f"{regime} (ADX {adx:.0f}) but DI diverges",
                    -5)

    def get_regime_summary(self, symbol: str) -> str:
        """Human-readable regime summary."""
        data = self._cache.get(symbol, {})
        if not data:
            return "Regime: Unknown"
        emoji_map = {"RANGING": "⏸", "WEAK_TREND": "〰", "TRENDING": "📈",
                     "STRONG_TREND": "🚀", "EXHAUSTION": "⚠", "UNKNOWN": "?"}
        e = emoji_map.get(data['regime'], '')
        return (f"Regime: {e} {data['regime']} "
                f"(ADX:{data['adx']:.0f} +DI:{data['plus_di']:.0f} -DI:{data['minus_di']:.0f})")
