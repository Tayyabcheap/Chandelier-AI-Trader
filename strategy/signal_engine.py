"""
strategy/signal_engine.py
═══════════════════════════════════════════════════════════════
Chandelier Exit + ADX + Gemini AI Signal Engine
═══════════════════════════════════════════════════════════════
"""

import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from strategy.indicators import add_indicators, get_latest
from core.logger import get_logger

logger = get_logger("SignalEngine")


@dataclass
class TradeSignal:
    symbol:      str
    direction:   str          # "BUY" | "SELL" | "HOLD"
    confidence:  int          # 0-100 (Now based on Gemini rating 1-10 * 10)
    reasons:     List[str]
    risk_level:  str          # "LOW" | "MEDIUM" | "HIGH"
    entry:       float = 0.0
    stop_loss:   float = 0.0
    take_profit: float = 0.0
    atr:         float = 0.0
    rsi:         float = 0.0
    timestamp:   str   = ""
    indicators:  dict  = field(default_factory=dict)
    regime:      str   = "UNKNOWN"
    adx:         float = 0.0
    session:     str   = ""
    gemini_decision: str = ""
    gemini_reasoning: str = ""


    def summary(self) -> str:
        regime_tag = f" | Regime: {self.regime} (ADX:{self.adx:.0f})" if self.regime != "UNKNOWN" else ""
        ai_tag = f" | AI:{self.gemini_decision}" if self.gemini_decision else ""

        lines = [
            f"{'─'*54}",
            f"  {self.direction} {self.symbol}",
            f"  Confidence : {self.confidence}%  |  Risk: {self.risk_level}",
            f"  Entry      : {self.entry:.5f}",
            f"  Stop Loss  : {self.stop_loss:.5f}  |  TP: {self.take_profit:.5f}",
            f"  RSI: {self.rsi:.1f}  |  ATR: {self.atr:.5f}{regime_tag}{ai_tag}",
            f"  Session    : {self.session}" if self.session else "",
            f"  Time: {self.timestamp}",
            f"  Reasons:",
        ]
        for r in self.reasons:
            lines.append(f"    ✓ {r}")
        lines.append(f"{'─'*54}")
        return "\n".join(line for line in lines if line)


class SignalEngine:
    def __init__(self, settings, regime_filter=None, session_filter=None,
                 gemini_advisor=None, connector=None):
        self.settings       = settings
        self.regime_filter  = regime_filter
        self.session_filter = session_filter
        self.gemini         = gemini_advisor
        self.connector      = connector
        self._last_candle   = {}

    def analyze(self, df: pd.DataFrame, symbol: str) -> TradeSignal:
        df  = add_indicators(df, self.settings)
        ind = get_latest(df)

        candle_time = ind["timestamp"]
        if self._last_candle.get(symbol) == candle_time:
            return TradeSignal(
                symbol=symbol, direction="HOLD", confidence=0,
                reasons=["Same candle - waiting for new data"],
                risk_level="HIGH", timestamp=candle_time, indicators=ind
            )
        self._last_candle[symbol] = candle_time

        # ══ Layer 1: Chandelier Exit Signal ══════════════════════════════
        rule_dir = "HOLD"
        reasons = []
        
        # We look for a fresh cross or a very strong ongoing trend
        trend = ind["chandelier_trend"]
        cross = ind["chandelier_cross"]

        if trend == 1:
            rule_dir = "BUY"
            if cross == 1:
                reasons.append("Chandelier: Bullish Cross (Fresh Trend)")
            else:
                reasons.append("Chandelier: Bullish Trend Active")
        elif trend == -1:
            rule_dir = "SELL"
            if cross == -1:
                reasons.append("Chandelier: Bearish Cross (Fresh Trend)")
            else:
                reasons.append("Chandelier: Bearish Trend Active")

        if rule_dir == "HOLD":
            return TradeSignal(symbol=symbol, direction="HOLD", confidence=0, reasons=["No Chandelier Trend"], risk_level="HIGH")

        # ══ Layer 2: ADX Regime Filter ═══════════════════════════════════
        regime_data = {"regime": "UNKNOWN", "adx": 0.0}
        if self.regime_filter and self.settings.ADX_FILTER_ENABLED:
            regime_data = self.regime_filter.analyze(df, symbol)
            adx_val = float(regime_data.get("adx", 0))
            
            if adx_val < self.settings.ADX_MIN_TREND:
                logger.info(f"[{symbol}] ADX filter blocked (ADX {adx_val:.0f} < {self.settings.ADX_MIN_TREND})")
                return TradeSignal(
                    symbol=symbol, direction="HOLD", confidence=0,
                    reasons=[f"⏸ Sideways Market: ADX {adx_val:.0f}"], risk_level="HIGH",
                    timestamp=candle_time, indicators=ind,
                    regime=regime_data["regime"], adx=adx_val
                )
            reasons.append(f"ADX Trending (ADX {adx_val:.0f} > {self.settings.ADX_MIN_TREND})")

        # ══ Layer 3: Session Filter ══════════════════════════════════════
        session_info = ""
        if self.session_filter and self.settings.SESSION_FILTER_ENABLED:
            in_session, session_reason = self.session_filter.is_optimal_session(symbol)
            session_info = session_reason

            if not in_session:
                logger.info(f"[{symbol}] Session filter: {session_reason}")
                return TradeSignal(
                    symbol=symbol, direction="HOLD", confidence=0,
                    reasons=[f"⏸ {session_reason}"], risk_level="HIGH",
                    timestamp=candle_time, indicators=ind,
                    session=session_info, regime=regime_data.get("regime"), adx=regime_data.get("adx")
                )
            reasons.append(f"✓ {session_reason}")

        # ══ Initial SL / TP ══════════════════════════════════════════════
        atr   = ind["atr"]
        price = ind["close"]

        # Use Chandelier line directly as SL, or fallback to ATR trail if Chandelier is too tight
        if rule_dir == "BUY":
            stop_loss = ind["chandelier_long"]
            # Enforce minimum distance just in case
            if price - stop_loss < atr * 0.5:
                stop_loss = price - atr * 1.5
            sl_dist = price - stop_loss
            take_profit = round(price + (sl_dist * 2.0), 5)  # 1:2 R:R
        else:
            stop_loss = ind["chandelier_short"]
            if stop_loss - price < atr * 0.5:
                stop_loss = price + atr * 1.5
            sl_dist = stop_loss - price
            take_profit = round(price - (sl_dist * 2.0), 5)  # 1:2 R:R

        # Default confidence before Gemini
        confidence = 50 
        risk_level = "MEDIUM"

        signal = TradeSignal(
            symbol      = symbol,
            direction   = rule_dir,
            confidence  = confidence,
            reasons     = reasons,
            risk_level  = risk_level,
            entry       = price,
            stop_loss   = round(stop_loss, 5),
            take_profit = take_profit,
            atr         = round(atr, 6),
            rsi         = round(ind["rsi"], 2),
            timestamp   = ind["timestamp"],
            indicators  = ind,
            regime      = regime_data.get("regime", "UNKNOWN"),
            adx         = regime_data.get("adx", 0),
            session     = session_info,
        )

        # ══ Layer 4: Gemini AI Advisor (Senior Risk Manager) ═════════════
        if self.gemini and self.settings.GEMINI_ENABLED:
            trade_context = {
                "symbol": symbol,
                "direction": rule_dir,
                "entry": price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "chandelier_trend": ind["chandelier_trend"],
                "chandelier_cross": ind["chandelier_cross"],
                "rsi": ind["rsi"],
                "atr": atr,
                "adx": regime_data.get("adx", 0),
                "session": session_info,
                "daily_pnl": 0.0,
            }

            veto, rating, reasoning = self.gemini.review_trade(trade_context)

            signal.gemini_reasoning = reasoning

            if veto:
                logger.info(f"[{symbol}] Gemini VETOED: {reasoning}")
                signal.direction = "HOLD"
                signal.confidence = 0
                signal.reasons = [f"🤖 Gemini AI VETOED: {reasoning}"]
                signal.gemini_decision = "VETO"
                return signal
            
            # Use rating (1-10) for risk level and confidence
            signal.gemini_decision = f"RATE:{rating}/10"
            signal.confidence = rating * 10
            
            # Reject weak setups outright
            if rating <= 4:
                logger.info(f"[{symbol}] Gemini AI rated {rating}/10 (<= 4). Trade REJECTED.")
                signal.direction = "HOLD"
                signal.confidence = 0
                signal.reasons = [f"🤖 Gemini Rated {rating}/10 — Too weak, trade rejected."]
                signal.gemini_decision = f"REJECT:{rating}/10"
                return signal

            signal.reasons.append(f"🤖 Gemini Rated {rating}/10: {reasoning}")

            if rating >= 8:
                signal.risk_level = "LOW"     # means 2.0% risk (high confidence)
            else:
                signal.risk_level = "MEDIUM"  # 1.0% risk (standard confidence)

        if signal.direction != "HOLD":
            logger.info(f"\n{signal.summary()}")

        return signal
