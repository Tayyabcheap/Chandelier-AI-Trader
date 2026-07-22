"""
risk/risk_manager.py
Daily P&L limits, position sizing, trailing stop management.
Fixed: Python 3.9 compatible type hints.
"""

import json
import os
import pandas as pd
from datetime import datetime, date
from typing import Optional, Tuple
from core.logger import get_logger

logger = get_logger("RiskManager")

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "daily_state.json")


class RiskManager:
    def __init__(self, settings, connector):
        self.settings  = settings
        self.connector = connector
        self._state    = self._load_state()

    # ── Daily State ───────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        today = str(date.today())
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    state = json.load(f)
                if state.get("date") == today:
                    return state
            except Exception:
                pass
        return {
            "date":          today,
            "start_balance": 0.0,
            "trades_taken":  0,
            "daily_pnl":     0.0,
            "stopped":       False,
            "stop_reason":   "",
        }

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def initialize_day(self):
        info = self.connector.get_account_info()
        self._state["start_balance"] = info["balance"]
        self._save_state()
        logger.info(
            f"Day initialized | Balance: {info['balance']:.2f} {info['currency']} | "
            f"Target: +{self.settings.DAILY_PROFIT_TARGET_PCT}% | "
            f"Loss limit: -{self.settings.DAILY_LOSS_LIMIT_PCT}%"
        )

    # ── Checks ────────────────────────────────────────────────────────────────

    def update_pnl(self) -> float:
        info  = self.connector.get_account_info()
        start = self._state["start_balance"]
        if start == 0:
            self.initialize_day()
            return 0.0
        pnl = ((info["equity"] - start) / start) * 100
        self._state["daily_pnl"] = round(pnl, 3)
        self._save_state()
        return pnl

    def can_trade(self, symbol: str = None) -> Tuple[bool, str]:
        """Returns (allowed, reason_string). Python 3.9 compatible."""
        if self._state["stopped"]:
            return False, self._state["stop_reason"]

        # Update PnL first so we check against live equity
        pnl = self.update_pnl()
        s   = self.settings

        if pnl >= s.DAILY_PROFIT_TARGET_PCT:
            reason = f"Daily target reached: +{pnl:.2f}%"
            self._state["stopped"]     = True
            self._state["stop_reason"] = reason
            self._save_state()
            logger.info(f"Target hit — bot paused. {reason}")
            return False, reason

        if pnl <= -s.DAILY_LOSS_LIMIT_PCT:
            reason = f"Daily loss limit hit: {pnl:.2f}%"
            self._state["stopped"]     = True
            self._state["stop_reason"] = reason
            self._save_state()
            logger.warning(f"Loss limit hit — bot paused. {reason}")
            return False, reason

        open_pos = self.connector.get_open_positions()
        if len(open_pos) >= s.MAX_OPEN_TRADES:
            return False, f"Max total positions open ({s.MAX_OPEN_TRADES})"

        if symbol:
            symbol_pos = [p for p in open_pos if p.get("symbol") == symbol]
            if len(symbol_pos) >= s.MAX_TRADES_PER_SYMBOL:
                return False, f"Max positions open for {symbol} ({s.MAX_TRADES_PER_SYMBOL})"

        return True, ""

    # ── Position Sizing ───────────────────────────────────────────────────────

    def calculate_lot(self, symbol: str, sl_distance: float, risk_level: str = "MEDIUM") -> float:
        try:
            info        = self.connector.get_account_info()
            balance     = info["balance"]
            
            # Dynamic risk based on Gemini AI confidence
            if risk_level == "LOW":      # Gemini Rating 8-10 (High Confidence = High Risk %)
                risk_pct = self.settings.GEMINI_HIGH_RISK_PCT
            elif risk_level == "MEDIUM": # Gemini Rating 4-7
                risk_pct = self.settings.GEMINI_MEDIUM_RISK_PCT
            else:                        # Gemini Rating 1-3 (Blocked by engine, fallback 0.5)
                risk_pct = 0.5
                
            risk_amount = balance * (risk_pct / 100)
            sym_info    = self.connector.get_symbol_info(symbol)
            point       = sym_info.get("point", 0.00001)
            tick_val    = sym_info.get("trade_tick_value", 1.0)

            pip_size          = point * 10
            pips              = sl_distance / pip_size if pip_size > 0 else 0
            pip_value_per_lot = tick_val * 10

            if pips <= 0 or pip_value_per_lot <= 0:
                return float(sym_info.get("volume_min", 0.01))

            lot     = risk_amount / (pips * pip_value_per_lot)
            vol_min = float(sym_info.get("volume_min", 0.01))
            vol_max = float(sym_info.get("volume_max", 100.0))
            lot     = max(vol_min, min(round(lot, 2), vol_max))

            logger.info(f"Lot size: {lot} | Risk: ${risk_amount:.2f} | SL pips: {pips:.1f}")
            return lot

        except Exception as e:
            logger.error(f"Lot calculation error: {e}")
            return 0.01

    # ── Trailing Stop ─────────────────────────────────────────────────────────

    def update_trailing_stops(self):
        positions = self.connector.get_open_positions()
        s         = self.settings

        for pos in positions:
            symbol     = pos.get("symbol", "")
            ticket     = pos.get("ticket", 0)
            pos_type   = pos.get("type", 0)
            current_sl = pos.get("sl", 0.0)
            current_tp = pos.get("tp", 0.0)

            df = self.connector.get_candles(symbol, s.TIMEFRAME, 50)
            if df is None:
                continue

            hl  = df["high"] - df["low"]
            hc  = (df["high"] - df["close"].shift()).abs()
            lc  = (df["low"]  - df["close"].shift()).abs()
            tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
            atr = tr.ewm(span=s.ATR_PERIOD, adjust=False).mean().iloc[-1]

            price      = df["close"].iloc[-1]
            trail_dist = atr * s.ATR_TRAIL_MULTIPLIER

            if pos_type == 0:  # BUY
                new_sl = round(price - trail_dist, 5)
                if new_sl > current_sl:
                    if self.connector.modify_trailing_stop(ticket, symbol, new_sl, current_tp):
                        logger.info(f"Trail raised #{ticket} {symbol}: {current_sl:.5f}→{new_sl:.5f}")
            else:  # SELL
                new_sl = round(price + trail_dist, 5)
                if new_sl < current_sl or current_sl == 0:
                    if self.connector.modify_trailing_stop(ticket, symbol, new_sl, current_tp):
                        logger.info(f"Trail lowered #{ticket} {symbol}: {current_sl:.5f}→{new_sl:.5f}")

    def register_trade(self):
        self._state["trades_taken"] += 1
        self._save_state()

    def get_daily_summary(self) -> dict:
        self.update_pnl()
        return {
            "date":        self._state["date"],
            "pnl_pct":     self._state["daily_pnl"],
            "trades":      self._state["trades_taken"],
            "stopped":     self._state["stopped"],
            "stop_reason": self._state["stop_reason"],
        }
