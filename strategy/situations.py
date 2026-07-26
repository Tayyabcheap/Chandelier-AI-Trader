import uuid
import threading
from dataclasses import dataclass
from typing import List, Optional
from core.logger import get_logger

logger = get_logger("Watchdog")

@dataclass
class WatchdogSituation:
    id: str
    symbol: str
    side: str          # "BUY" or "SELL"
    condition: str     # "ABOVE" or "BELOW"
    trigger_price: float
    sl: float
    tp: float
    lot_size: float = 0.01
    
    # Live tracking state
    dist_pct: float = 0.0  # 0 to 100 for visual bar
    exec_status: str = "Pending"
    
class SituationsEngine:
    def __init__(self, connector):
        self.connector = connector
        self.active_situations: List[WatchdogSituation] = []
        self._lock = threading.Lock()
        
    def add_situation(self, symbol: str, side: str, condition: str, trigger_price: float, sl: float, tp: float, lot: float = 0.01):
        with self._lock:
            # Generate a 6-digit ID like the screenshot
            short_id = str(uuid.uuid4().int)[:6]
            sit = WatchdogSituation(
                id=short_id,
                symbol=symbol,
                side=side.upper(),
                condition=condition.upper(),
                trigger_price=float(trigger_price),
                sl=float(sl),
                tp=float(tp),
                lot_size=float(lot)
            )
            self.active_situations.append(sit)
            logger.info(f"Added Watchdog Situation #{sit.id}: {sit.side} {sit.symbol} {sit.condition} {sit.trigger_price}")
            return sit.id
            
    def remove_situation(self, sit_id: str):
        with self._lock:
            self.active_situations = [s for s in self.active_situations if s.id != str(sit_id)]
            logger.info(f"Removed Watchdog Situation #{sit_id}")
            
    def get_all(self) -> List[WatchdogSituation]:
        with self._lock:
            return list(self.active_situations)
            
    def evaluate_live_prices(self):
        """Update proximity bars based on live tick data. Does NOT execute trades."""
        if not self.connector or not self.connector.connected:
            return
            
        with self._lock:
            for sit in self.active_situations:
                try:
                    # In a real setup, we'd cache point values to avoid rapid MT5 calls
                    tick = self.connector.mt5.symbol_info_tick(sit.symbol) if hasattr(self.connector, 'mt5') else None
                    if not tick: continue
                    
                    live_price = tick.ask if sit.side == "BUY" else tick.bid
                    
                    point = self.connector.get_symbol_info(sit.symbol).get("point", 0.00001)
                    pip_dist = abs(live_price - sit.trigger_price) / (point * 10)
                    
                    max_track_pips = 50.0
                    fill_pct = max(0.0, min(100.0, 100.0 * (1.0 - (pip_dist / max_track_pips))))
                    sit.dist_pct = fill_pct
                    
                    if pip_dist > 25:
                        sit.exec_status = "Too far"
                    elif pip_dist > 10:
                        sit.exec_status = "Hopeful"
                    else:
                        sit.exec_status = "Very Close"
                except Exception as e:
                    logger.error(f"Error evaluating live prices for Watchdog: {e}")
                
    def evaluate_candle_close(self, symbol: str, close_price: float):
        """Called strictly on H1/H4 candle close. Executes the trade if conditions are met."""
        if not self.connector or not self.connector.connected:
            return
            
        triggered = []
        with self._lock:
            for sit in self.active_situations:
                if sit.symbol != symbol:
                    continue
                    
                is_met = False
                if sit.condition == "ABOVE" and close_price > sit.trigger_price:
                    is_met = True
                elif sit.condition == "BELOW" and close_price < sit.trigger_price:
                    is_met = True
                    
                if is_met:
                    logger.info(f"Watchdog Triggered! {sit.symbol} closed at {close_price}, which is {sit.condition} {sit.trigger_price}")
                    triggered.append(sit)
                    
        # Execute outside the lock
        for sit in triggered:
            comment = f"Watchdog #{sit.id}"
            ticket, err = self.connector.open_position(
                symbol=sit.symbol,
                order_type=sit.side,
                lot=sit.lot_size,
                sl=sit.sl,
                tp=sit.tp,
                comment=comment
            )
            if ticket:
                logger.info(f"Watchdog executed trade #{ticket}")
                self.remove_situation(sit.id)
            else:
                logger.error(f"Watchdog execution failed: {err}")
