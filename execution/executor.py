"""
execution/executor.py
Executes trades, logs them to CSV, feeds results back to ML model.
"""

import csv
import os
from datetime import datetime
from typing import Optional
from strategy.signal_engine import TradeSignal
from core.logger import get_logger

logger   = get_logger("Executor")
TRADE_LOG = os.path.join(os.path.dirname(__file__), "..", "logs", "trades.csv")
HEADERS   = [
    "timestamp", "symbol", "direction", "confidence", "risk_level",
    "entry", "stop_loss", "take_profit", "lot", "ticket",
    "ml_active", "ml_win_prob", "reasons", "daily_pnl_before"
]


class TradeExecutor:
    def __init__(self, settings, connector, risk_manager,
                 notifier=None, discord=None):
        self.settings     = settings
        self.connector    = connector
        self.risk_manager = risk_manager
        self.notifier     = notifier
        self.discord      = discord
        self._open_trades = {}  # ticket -> signal (for ML feedback on close)
        self._ensure_log()

    def execute(self, signal: TradeSignal) -> Optional[dict]:
        if signal.direction == "HOLD":
            return None

        if signal.confidence <= 0:
            logger.info(f"Skip {signal.symbol}: confidence is {signal.confidence}% (vetoed or invalid)")
            return None

        can, reason = self.risk_manager.can_trade()
        if not can:
            logger.info(f"Trade blocked: {reason}")
            return None

        sl_distance = abs(signal.entry - signal.stop_loss)
        lot         = self.risk_manager.calculate_lot(signal.symbol, sl_distance, signal.risk_level)
        daily       = self.risk_manager.get_daily_summary()
        pnl_before  = daily["pnl_pct"]

        result = self.connector.place_order(
            symbol     = signal.symbol,
            order_type = signal.direction,
            lot        = lot,
            sl         = signal.stop_loss,
            tp         = signal.take_profit,
            comment    = f"bot_c{signal.confidence}",
        )

        # MT5 success retcodes
        if result["retcode"] not in (10009, 10008, 999999):
            logger.error(f"Order rejected: {result}")
            return None

        ticket = result["ticket"]

        # Store for ML feedback when trade closes
        if signal.indicators:
            self._open_trades[ticket] = signal

        trade = {
            "timestamp":    signal.timestamp,
            "symbol":       signal.symbol,
            "direction":    signal.direction,
            "confidence":   signal.confidence,
            "risk_level":   signal.risk_level,
            "entry":        signal.entry,
            "stop_loss":    signal.stop_loss,
            "take_profit":  signal.take_profit,
            "lot":          lot,
            "ticket":       ticket,
            "ml_active":    getattr(signal, "ml_active", False),
            "ml_win_prob":  getattr(signal, "ml_win_prob", 0.0),
            "reasons":      " | ".join(signal.reasons),
            "daily_pnl_before": pnl_before,
        }

        self._log_trade(trade)
        self.risk_manager.register_trade()

        if self.notifier:
            self.notifier.send_trade_alert(signal, lot, ticket, pnl_before)

        if self.discord:
            self.discord.send_trade_alert(signal, lot, ticket, pnl_before)

        logger.info(
            f"Trade executed: {signal.direction} {signal.symbol} "
            f"Lot:{lot} Ticket:#{ticket} Conf:{signal.confidence}%"
        )
        return trade

    def record_closed_trade(self, ticket: int, exit_price: float, hit_tp: bool):
        """
        Call when a trade closes (TP or SL hit).
        This feeds the result back into the ML model for learning.
        """
        if ticket not in self._open_trades:
            return
        signal = self._open_trades.pop(ticket)

        # Send Discord notification for closed trade
        if self.discord:
            profit = exit_price - signal.entry if signal.direction == "BUY" else signal.entry - exit_price
            self.discord.send_trade_closed(
                symbol=signal.symbol, direction=signal.direction,
                ticket=ticket, profit=profit, hit_tp=hit_tp,
            )

    def check_closed_positions(self):
        """
        Detect positions that closed since last check and send ML feedback.
        Now properly queries MT5 deal history for actual exit price and result.
        """
        if not self._open_trades:
            return

        open_tickets = {
            p.get("ticket") for p in self.connector.get_open_positions()
        }

        closed = [t for t in list(self._open_trades.keys()) if t not in open_tickets]
        for ticket in closed:
            signal = self._open_trades.get(ticket)
            if signal:
                # Query MT5 for actual trade result
                exit_price, hit_tp = self.connector.get_deal_result(ticket)

                if exit_price > 0:
                    self.record_closed_trade(ticket, exit_price, hit_tp)
                else:
                    # Can't get deal history — skip to avoid data corruption
                    logger.warning(
                        f"Could not get deal result for #{ticket} — "
                        f"skipping ML feedback to avoid data corruption"
                    )
                    self._open_trades.pop(ticket, None)

    def get_trade_history(self) -> list:
        if not os.path.exists(TRADE_LOG):
            return []
        with open(TRADE_LOG, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _ensure_log(self):
        os.makedirs(os.path.dirname(TRADE_LOG), exist_ok=True)
        if not os.path.exists(TRADE_LOG):
            with open(TRADE_LOG, "w", newline="") as f:
                csv.writer(f).writerow(HEADERS)

    def _log_trade(self, trade: dict):
        with open(TRADE_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([trade.get(h, "") for h in HEADERS])
