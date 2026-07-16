"""
core/mt5_connector.py
MT5 connection with retry logic, detailed error messages, and simulation fallback.
Fully compatible with Python 3.9+.
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, Dict, List
from core.logger import get_logger

logger = get_logger("MT5Connector")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not found. Running in SIMULATION mode.")
    logger.warning("To install: pip install MetaTrader5  (Windows only)")


MT5_ERROR_HELP = {
    10013: "Invalid request — check symbol name (e.g. 'EURUSD' not 'EUR/USD')",
    10014: "Invalid volume — check lot size limits for your account",
    10018: "Market is closed — no trading outside market hours",
    10019: "Not enough money — reduce lot size or add funds",
    10024: "Too many requests — bot is sending orders too fast",
    10027: "AutoTrading disabled — enable it in MT5: Tools → Options → Expert Advisors",
    10030: "Order placed by EA is prohibited — enable Algo Trading in MT5 toolbar",
    -10004: "MT5 terminal not found — make sure MetaTrader5 is open and logged in",
}

TIMEFRAME_MAP_STR = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 16385, "H4": 16388, "D1": 16408,
}


class MT5Connector:
    def __init__(self, login: int, password: str, server: str, path: str = ""):
        self.login     = login
        self.password  = password
        self.server    = server
        self.path      = path
        self.connected = False

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, retries: int = 3) -> bool:
        if not MT5_AVAILABLE:
            logger.warning("MT5 not installed - simulation mode active.")
            self.connected = True
            return True

        for attempt in range(1, retries + 1):
            logger.info(f"Connecting to MT5 (attempt {attempt}/{retries})...")

            # Explicitly pass credentials to avoid attaching to the wrong MT5 instance
            if self.path:
                init_res = mt5.initialize(path=self.path, login=self.login, password=self.password, server=self.server)
            else:
                init_res = mt5.initialize(login=self.login, password=self.password, server=self.server)
                
            if not init_res:
                code, msg = mt5.last_error()
                hint = MT5_ERROR_HELP.get(code, "")
                logger.error(
                    f"MT5 initialize failed [{code}]: {msg}\n"
                    f"  Fix: {hint or 'Make sure MetaTrader5 terminal is running.'}"
                )
                if attempt < retries:
                    time.sleep(3)
                continue

            ok = mt5.login(self.login, password=self.password, server=self.server)
            if not ok:
                code, msg = mt5.last_error()
                logger.error(
                    f"MT5 login failed [{code}]: {msg}\n"
                    f"  Server tried: '{self.server}'\n"
                    f"  Common Exness servers:\n"
                    f"    Exness-MT5Real    (live accounts)\n"
                    f"    Exness-MT5Trial   (demo accounts)\n"
                    f"    Exness-MT5Real2   (some live accounts)\n"
                    f"  Tip: Open MT5 manually, check File→Open Account to see your exact server name."
                )
                mt5.shutdown()
                if attempt < retries:
                    time.sleep(3)
                continue

            info = mt5.account_info()
            logger.info(
                f"Connected! Account: {self.login} | "
                f"Server: {self.server} | "
                f"Balance: {info.balance:.2f} {info.currency} | "
                f"Leverage: 1:{info.leverage}"
            )
            self.connected = True
            return True

        logger.error(
            "All MT5 connection attempts failed.\n"
            "Checklist:\n"
            "  1. MetaTrader5 terminal is open on your PC\n"
            "  2. You are logged in to your Exness account in MT5\n"
            "  3. Tools → Options → Expert Advisors → 'Allow automated trading' is ticked\n"
            "  4. The green robot icon is showing in the MT5 toolbar\n"
            "  5. Your login/password/server in config/.env are correct\n"
            "  6. You are on Windows (MT5 Python library only works on Windows)"
        )
        return False

    def disconnect(self):
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected.")

    # ── Market Data ───────────────────────────────────────────────────────────

    def get_candles(self, symbol: str, timeframe: str, count: int = 500) -> Optional[pd.DataFrame]:
        if not MT5_AVAILABLE:
            return self._simulate_candles(symbol, count)

        tf = self._resolve_tf(timeframe)
        mt5.symbol_select(symbol, True)  # Ensure symbol is active in Market Watch
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        
        if rates is None or len(rates) == 0:
            code, msg = mt5.last_error()
            
            # If IPC is broken, try to auto-reconnect silently
            if code == -1:
                logger.warning(f"MT5 IPC broken (code -1). Attempting auto-reconnect...")
                mt5.shutdown()
                time.sleep(1)
                self.connect(retries=1)
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
                
            if rates is None or len(rates) == 0:
                logger.error(
                    f"No candle data for {symbol} @ {timeframe} [{code}]: {msg}\n"
                    f"  Tip: Check MT5 connection to broker (bottom right corner in MT5)."
                )
                return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        return df[["open", "high", "low", "close", "volume"]]

    def get_account_info(self) -> dict:
        if not MT5_AVAILABLE:
            return {"balance": 10000.0, "equity": 10000.0, "currency": "USD", "profit": 0.0}
        info = mt5.account_info()
        if info is None:
            return {"balance": 0.0, "equity": 0.0, "currency": "USD", "profit": 0.0}
        return {
            "balance":  info.balance,
            "equity":   info.equity,
            "currency": info.currency,
            "profit":   info.profit,
        }

    def get_open_positions(self) -> list:
        if not MT5_AVAILABLE:
            return []
        positions = mt5.positions_get()
        return [p._asdict() for p in positions] if positions else []

    def get_symbol_info(self, symbol: str) -> dict:
        if not MT5_AVAILABLE:
            return {"point": 0.00001, "trade_tick_value": 1.0,
                    "volume_min": 0.01, "volume_max": 100.0}
        mt5.symbol_select(symbol, True)  # Ensure symbol is in Market Watch
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(
                f"Symbol '{symbol}' not found.\n"
                f"  Tip: Some Exness accounts suffix symbols with 'm' e.g. 'EURUSDm'.\n"
                f"  Check your MT5 Market Watch for exact symbol names."
            )
            return {}
        return info._asdict()

    # ── Order Execution ───────────────────────────────────────────────────────

    def place_order(self, symbol: str, order_type: str, lot: float,
                    sl: float, tp: float, comment: str = "") -> dict:
        if not MT5_AVAILABLE:
            logger.info(f"[SIM] {order_type} {lot} lots {symbol} SL={sl:.5f} TP={tp:.5f}")
            return {"ticket": 999999, "retcode": 10009, "comment": "Simulated"}

        tick    = mt5.symbol_info_tick(symbol)
        price   = tick.ask if order_type == "BUY" else tick.bid
        mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(lot),
            "type":         mt5_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "deviation":    20,
            "magic":        20240101,
            "comment":      comment[:31],
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            code, msg = mt5.last_error()
            hint = MT5_ERROR_HELP.get(code, "")
            logger.error(f"order_send returned None [{code}]: {msg}. {hint}")
            return {"ticket": 0, "retcode": code, "comment": msg}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            hint = MT5_ERROR_HELP.get(result.retcode, "")
            logger.error(
                f"Order failed [{result.retcode}]: {result.comment}\n"
                f"  {hint}"
            )
        else:
            logger.info(f"Order placed: ticket={result.order} {order_type} {lot}L {symbol}")

        return {"ticket": result.order, "retcode": result.retcode, "comment": result.comment}

    def modify_trailing_stop(self, ticket: int, new_sl: float) -> bool:
        if not MT5_AVAILABLE:
            return True
        request = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "sl": new_sl}
        result  = mt5.order_send(request)
        return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

    def close_position(self, ticket: int) -> bool:
        if not MT5_AVAILABLE:
            logger.info(f"[SIM] Close position #{ticket}")
            return True
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
        pos      = positions[0]
        mt5_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick     = mt5.symbol_info_tick(pos.symbol)
        price    = tick.bid if pos.type == 0 else tick.ask
        request  = {
            "action": mt5.TRADE_ACTION_DEAL, "position": ticket,
            "symbol": pos.symbol, "volume": pos.volume, "type": mt5_type,
            "price": price, "deviation": 20, "magic": 20240101,
            "comment": "bot_close", "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

    def get_deal_result(self, ticket: int) -> tuple:
        """
        Get the actual result of a closed trade from MT5 deal history.
        Returns (exit_price: float, hit_tp: bool)
        """
        if not MT5_AVAILABLE:
            return 0.0, False

        try:
            from datetime import timedelta
            now = datetime.now()
            from_date = now - timedelta(days=30)
            deals = mt5.history_deals_get(from_date, now, position=ticket)

            if not deals or len(deals) < 2:
                logger.warning(f"No deal history found for ticket #{ticket}")
                return 0.0, False

            close_deal = deals[-1]
            exit_price = close_deal.price
            profit = close_deal.profit
            hit_tp = profit > 0

            logger.info(
                f"Deal result #{ticket}: exit={exit_price:.5f} "
                f"profit={profit:.2f} {'WIN' if hit_tp else 'LOSS'}"
            )
            return exit_price, hit_tp

        except Exception as e:
            logger.error(f"get_deal_result error for #{ticket}: {e}")
            return 0.0, False

    def get_spread(self, symbol: str) -> float:
        """
        Get current spread for a symbol in price units.
        """
        if not MT5_AVAILABLE:
            return 0.00015

        try:
            mt5.symbol_select(symbol, True)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return 0.0
            spread = tick.ask - tick.bid
            return max(spread, 0.0)
        except Exception as e:
            logger.error(f"get_spread error for {symbol}: {e}")
            return 0.0

    def get_avg_spread(self, symbol: str, samples: int = 1) -> float:
        """Get average spread. Returns current spread."""
        return self.get_spread(symbol)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_tf(self, timeframe: str):
        if not MT5_AVAILABLE:
            return None
        mapping = {
            "M1":  mt5.TIMEFRAME_M1,  "M5":  mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1":  mt5.TIMEFRAME_H1,  "H4":  mt5.TIMEFRAME_H4,
            "D1":  mt5.TIMEFRAME_D1,
        }
        tf = mapping.get(timeframe.upper())
        if tf is None:
            logger.warning(f"Unknown timeframe '{timeframe}', defaulting to H1")
            return mt5.TIMEFRAME_H1
        return tf

    def _simulate_candles(self, symbol: str, count: int) -> pd.DataFrame:
        np.random.seed(abs(hash(symbol)) % 999)
        dates  = pd.date_range(end=datetime.now(), periods=count, freq="1h")
        close  = 1.1000 + np.cumsum(np.random.randn(count) * 0.0008)
        high   = close + np.random.uniform(0.0002, 0.0015, count)
        low    = close - np.random.uniform(0.0002, 0.0015, count)
        open_  = close + np.random.randn(count) * 0.0004
        vol    = np.random.randint(500, 3000, count).astype(float)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
            index=dates
        )
