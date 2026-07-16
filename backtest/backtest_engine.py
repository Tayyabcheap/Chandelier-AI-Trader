"""
backtest/backtest_engine.py
====================================================================
Pure Mathematical Baseline Backtester for Chandelier Exit + ADX

Simulates the core strategy without any AI/ML components to
establish the baseline mathematical edge of the strategy.
====================================================================
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from typing import List, Dict, Optional, Tuple
from config.settings import settings
from strategy.indicators import add_indicators
from strategy.regime_filter import compute_adx
from core.logger import get_logger

logger = get_logger("Backtest")

class TradeRecord:
    __slots__ = ["time","direction","entry","exit_price",
                 "pnl_pct","result","equity_after"]

    def __init__(self, time, direction, entry, exit_price,
                 pnl_pct, result, equity_after):
        self.time         = time
        self.direction    = direction
        self.entry        = entry
        self.exit_price   = exit_price
        self.pnl_pct      = pnl_pct
        self.result       = result       # "WIN" or "LOSS"
        self.equity_after = equity_after


def _score_row(row: pd.Series) -> Tuple[str, list]:
    direction = "HOLD"
    reasons   = []

    trend = row.get("chandelier_trend", 0)
    cross = row.get("chandelier_cross", 0)
    adx = row.get("adx", 0)

    # ADX regime filter
    if adx < settings.ADX_MIN_TREND:
        return "HOLD", ["ADX Ranging"]

    if trend == 1:
        if cross == 1:
            direction = "BUY"
            reasons.append("Bullish Chandelier Cross")
    elif trend == -1:
        if cross == -1:
            direction = "SELL"
            reasons.append("Bearish Chandelier Cross")

    return direction, reasons


def simulate_window(df: pd.DataFrame, symbol: str = "TEST", cooldown_bars: int = 3) -> List[TradeRecord]:
    """
    Simulate all trades in df.
    """
    df = add_indicators(df, settings)
    df = compute_adx(df)
    df = df.dropna()
    if len(df) < 30:
        return []

    trades: List[TradeRecord] = []
    in_trade   = False
    direction  = None
    entry = sl = tp = 0.0
    equity     = 100.0
    peak_eq    = 100.0
    max_dd     = 0.0
    spread = 0.015 if "JPY" in symbol.upper() else 0.00015
    last_entry_bar = -cooldown_bars

    for i in range(1, len(df)):
        row   = df.iloc[i]
        price = float(row["close"])
        atr   = float(row["atr"])

        if in_trade:
            if direction == "BUY":
                # Trailing stop update (Chandelier line)
                new_sl = float(row["chandelier_long"])
                # Fallback to ATR trail if chandelier line is missing/weird
                if pd.isna(new_sl) or new_sl > price:
                    new_sl = price - atr * 1.5

                if new_sl > sl:
                    sl = new_sl
                
                # Check hits
                if float(row["low"]) <= sl:
                    pnl = (sl - entry) / entry * 100
                    equity += pnl
                    trades.append(TradeRecord(str(df.index[i]), "BUY", entry, sl, pnl, "LOSS" if pnl < 0 else "WIN", equity))
                    in_trade = False
                elif float(row["high"]) >= tp:
                    pnl = (tp - entry) / entry * 100
                    equity += pnl
                    trades.append(TradeRecord(str(df.index[i]), "BUY", entry, tp, pnl, "WIN", equity))
                    in_trade = False

            else:  # SELL
                new_sl = float(row["chandelier_short"])
                if pd.isna(new_sl) or new_sl < price:
                    new_sl = price + atr * 1.5

                if new_sl < sl or sl == 0:
                    sl = new_sl
                
                # Check hits
                if float(row["high"]) >= sl:
                    pnl = (entry - sl) / entry * 100
                    equity -= pnl
                    trades.append(TradeRecord(str(df.index[i]), "SELL", entry, sl, -pnl, "LOSS" if -pnl < 0 else "WIN", equity))
                    in_trade = False
                elif float(row["low"]) <= tp:
                    pnl = (entry - tp) / entry * 100
                    equity += pnl
                    trades.append(TradeRecord(str(df.index[i]), "SELL", entry, tp, pnl, "WIN", equity))
                    in_trade = False

            if not in_trade:
                peak_eq = max(peak_eq, equity)
                dd      = (peak_eq - equity) / peak_eq * 100 if peak_eq > 0 else 0
                max_dd  = max(max_dd, dd)
            continue

        # -- Look for entry ----------------------------------------------------
        if i - last_entry_bar < cooldown_bars:
            continue

        direction_cand, _ = _score_row(row)
        if direction_cand == "HOLD":
            continue

        # -- v2.0 Session Filter --
        from strategy.session_filter import SESSION_MAP, DEFAULT_HOURS
        normalized = symbol.replace(".", "").upper()
        for suffix in ["M", "R", "Z", "X", "C"]:
            if normalized.endswith(suffix) and len(normalized) > 6:
                normalized = normalized[:-1]
        windows = SESSION_MAP.get(normalized, SESSION_MAP.get(symbol, DEFAULT_HOURS))
        current_hour = df.index[i].hour
        
        if df.index[i].weekday() >= 5:
            continue
            
        in_session = False
        for start_h, end_h in windows:
            if start_h <= current_hour < end_h:
                in_session = True
                break
        if not in_session:
            continue

        # Enter trade
        in_trade       = True
        direction      = direction_cand
        entry          = price + spread if direction == "BUY" else price - spread
        last_entry_bar = i

        if direction == "BUY":
            sl = float(row["chandelier_long"])
            if pd.isna(sl) or price - sl < atr * 0.5:
                sl = price - atr * 1.5
            sl_dist = price - sl
            tp = round(price + (sl_dist * 2.0), 5)
        else:
            sl = float(row["chandelier_short"])
            if pd.isna(sl) or sl - price < atr * 0.5:
                sl = price + atr * 1.5
            sl_dist = sl - price
            tp = round(price - (sl_dist * 2.0), 5)

    return trades

def _calc_max_drawdown(trades: List[TradeRecord]) -> float:
    eq = peak = 100.0
    mdd = 0.0
    for t in trades:
        eq  += t.pnl_pct
        peak = max(peak, eq)
        dd   = (peak - eq) / peak * 100 if peak > 0 else 0
        mdd  = max(mdd, dd)
    return round(mdd, 2)

def _profit_factor(trades: List[TradeRecord]) -> float:
    gp = sum(t.pnl_pct for t in trades if t.pnl_pct > 0)
    gl = abs(sum(t.pnl_pct for t in trades if t.pnl_pct <= 0))
    return round(gp / gl, 2) if gl > 0 else 0.0

def run_backtest(df: pd.DataFrame, symbol: str = "TEST"):
    print(f"\n========================================================")
    print(f"  CHANDELIER BASELINE BACKTEST - {symbol}")
    print(f"========================================================")
    
    trades = simulate_window(df, symbol=symbol)
    if not trades:
        print("  No trades generated.")
        return

    total = len(trades)
    wins = sum(1 for t in trades if t.result == "WIN")
    wr = (wins / total) * 100
    net_pnl = sum(t.pnl_pct for t in trades)
    max_dd = _calc_max_drawdown(trades)
    pf = _profit_factor(trades)

    avg_win = sum(t.pnl_pct for t in trades if t.pnl_pct > 0) / max(wins, 1)
    avg_loss = abs(sum(t.pnl_pct for t in trades if t.pnl_pct <= 0)) / max(total - wins, 1)

    print(f"  Total Trades      : {total}")
    print(f"  Win Rate          : {wr:.1f}%")
    print(f"  Wins / Losses     : {wins} / {total - wins}")
    print(f"  Net P&L           : {net_pnl:+.3f}%")
    print(f"  Profit Factor     : {pf}   (>1.5 is good)")
    print(f"  Max Drawdown      : {max_dd:.2f}%")
    print(f"  Avg Win / Avg Loss: +{avg_win:.3f}% / -{avg_loss:.3f}%")
    print(f"========================================================\n")

if __name__ == "__main__":
    from core.mt5_connector import MT5Connector
    from config.settings import settings

    print("Connecting to MT5 to fetch data...")
    connector = MT5Connector(settings.MT5_LOGIN, settings.MT5_PASSWORD, settings.MT5_SERVER, settings.MT5_PATH)
    if not connector.connect():
        sys.exit(1)
    
    for symbol in settings.SYMBOLS:
        df = connector.get_candles(symbol, settings.TIMEFRAME, count=5000)
        if df is not None and not df.empty:
            run_backtest(df, symbol)
        else:
            print(f"Failed to fetch data for {symbol}")
    
    connector.disconnect()
