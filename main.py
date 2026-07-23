"""
main.py - Exness AutoTrader v2.0 Entry Point
===============================================================
Next-generation forex bot with 6-layer trade filtering:
  1. Rule-based indicators (EMA + RSI + MACD + BB + Stoch + Vol)
  2. ADX Market Regime Filter
  3. Multi-Timeframe Confirmation (H4)
  4. Session Filter (optimal trading hours)
  5. Self-Learning ML Model (ensemble)
  6. Gemini AI Advisor (human-like trade review)

Run:  python main.py
Stop: Ctrl+C  (open trades stay in MT5)
===============================================================
"""

import ssl

# Aggressive global monkey-patch to force aiohttp/discord/urllib to bypass SSL verification
# MUST happen BEFORE any other imports because aiohttp caches the SSL context on load!
orig_create_default_context = ssl.create_default_context

def patched_create_default_context(*args, **kwargs):
    ctx = orig_create_default_context(*args, **kwargs)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

ssl.create_default_context = patched_create_default_context

# Also patch urllib's unverified context for legacy requests
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

import sys
import os
import time
import signal
import schedule
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from core.logger import get_logger
from core.mt5_connector import MT5Connector
from strategy.indicators import add_indicators
from strategy.signal_engine import SignalEngine
from strategy.regime_filter import RegimeFilter
from strategy.session_filter import SessionFilter
from strategy.gemini_advisor import GeminiAdvisor
from risk.risk_manager import RiskManager
from risk.news_filter import NewsFilter
from execution.executor import TradeExecutor
from execution.discord_notifier import DiscordNotifier
from dashboard.terminal_dashboard import render

logger  = get_logger("Main")
running = True
signals = {}
connector = None
executor  = None


def graceful_shutdown(sig=None, frame=None):
    global running
    print("\nShutting down gracefully...")
    running = False

signal.signal(signal.SIGINT,  graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

def close_all_open_trades():
    """Emergency callback from GUI to flatten all positions."""
    if not connector:
        print("Connector not initialized.")
        return
    
    positions = connector.get_open_positions()
    if not positions:
        print("No open positions to close.")
        return
        
    for pos in positions:
        ticket = pos["ticket"]
        print(f"Closing position #{ticket}...")
        connector.close_position(ticket)
    print("All positions closed.")

def trading_cycle(conn, engine, risk_mgr, exec_, news_filter):
    global signals
    for symbol in settings.SYMBOLS:
        try:
            # Blocklist filter
            if symbol in settings.BLOCKED_SYMBOLS:
                continue

            # News filter
            safe, reason = news_filter.is_safe_to_trade(symbol)
            if not safe:
                logger.info(f"[{symbol}] News pause: {reason}")
                continue

            # Fetch data
            df = conn.get_candles(symbol, settings.TIMEFRAME, count=500)
            if df is None or len(df) < 50:
                logger.warning(f"[{symbol}] Not enough data")
                continue

            # Generate signal (all 6 layers run inside engine.analyze)
            sig = engine.analyze(df, symbol)
            signals[symbol] = sig

            # Execute
            exec_.execute(sig)

            # Check for closed positions (ML feedback)
            exec_.check_closed_positions()

        except Exception as e:
            logger.error(f"[{symbol}] Cycle error: {e}", exc_info=True)


def main():
    global connector, executor

    print("\n" + "="*60)
    print("  * Exness AutoTrader v2.0 - Next-Gen AI-Powered")
    print("  6-Layer Filter: Rules -> ADX -> H4 -> Session -> ML -> Gemini")
    print("="*60 + "\n")

    # Validate config
    try:
        settings.validate()
    except ValueError as e:
        logger.error(str(e))
        logger.error("Fill in config/.env with your MT5 credentials.")
        sys.exit(1)

    # Connect to MT5
    connector = MT5Connector(
        login    = settings.MT5_LOGIN,
        password = settings.MT5_PASSWORD,
        server   = settings.MT5_SERVER,
        path     = settings.MT5_PATH,
    )
    if not connector.connect():
        sys.exit(1)

    # Start Discord Interactive Bot in background
    from execution.discord_bot import run_discord_bot
    import threading
    discord_thread = threading.Thread(target=run_discord_bot, args=(connector, settings), daemon=True)
    discord_thread.start()

    # -- Init all components -----------------------------------------------

    # Layer 2: ADX Regime Filter
    regime_filter = None
    if settings.ADX_FILTER_ENABLED:
        regime_filter = RegimeFilter(min_adx=settings.ADX_MIN_TREND)
        logger.info(f"? ADX Regime Filter active (min ADX: {settings.ADX_MIN_TREND})")
    else:
        logger.info("? ADX Regime Filter disabled")

    # Layer 4: Session Filter
    session_filter = None
    if settings.SESSION_FILTER_ENABLED:
        session_filter = SessionFilter(enabled=True)
        logger.info(f"? Session Filter active ({session_filter.get_session_info()})")
    else:
        logger.info("? Session Filter disabled")

    # Layer 6: Gemini AI Advisor
    gemini_advisor = None
    if settings.GEMINI_ENABLED and settings.GEMINI_API_KEY:
        gemini_advisor = GeminiAdvisor(
            api_key=settings.GEMINI_API_KEY,
            model_name=settings.GEMINI_MODEL,
        )
        if gemini_advisor.enabled:
            logger.info(f"? Gemini AI Advisor active (model: {settings.GEMINI_MODEL})")
        else:
            logger.info("? Gemini AI Advisor failed to initialize")
            gemini_advisor = None
    else:
        logger.info("? Gemini AI Advisor disabled (no API key)")

    risk_mgr    = RiskManager(settings, connector)
    news_filter = NewsFilter(settings)
    discord     = DiscordNotifier(settings)

    engine = SignalEngine(
        settings,
        regime_filter  = regime_filter,
        session_filter = session_filter,
        gemini_advisor = gemini_advisor,
        connector      = connector,
        risk_manager   = risk_mgr,
    )

    executor    = TradeExecutor(settings, connector, risk_mgr,
                                notifier=None,
                                discord=discord)

    risk_mgr.initialize_day()
    account = connector.get_account_info()
    discord.send_startup(settings.SYMBOLS, account["balance"], account["currency"])

    # Print active filters summary
    filters_active = []
    if regime_filter:    filters_active.append("ADX")
    if session_filter:   filters_active.append("Session")
    if gemini_advisor:   filters_active.append("Gemini-AI")

    logger.info(
        f"Watching: {settings.SYMBOLS} | TF: {settings.TIMEFRAME}"
    )
    logger.info(f"Active filters: {' -> '.join(filters_active)}")

    # -- Schedules ---------------------------------------------------------
    schedule.every(1).minutes.do(
        trading_cycle, connector, engine, risk_mgr, executor, news_filter
    )
    schedule.every(1).minutes.do(risk_mgr.update_trailing_stops)
    schedule.every().day.at("00:01").do(risk_mgr.initialize_day)
    schedule.every().day.at("23:50").do(
        lambda: (
            discord.send_daily_summary(
                risk_mgr.get_daily_summary(), connector.get_account_info()
            )
        )
    )

    # First cycle immediately
    trading_cycle(connector, engine, risk_mgr, executor, news_filter)

    # Main loop (Run in background thread by GUI)
    while running:
        schedule.run_pending()
        time.sleep(1)

    logger.info("Bot thread stopped.")
    connector.disconnect()

def start_bot_thread():
    global running
    running = True
    # main() will run the infinite schedule loop
    main()

def stop_bot_thread():
    global running
    running = False

def get_gui_data():
    """Returns live connector and signals for the GUI to poll."""
    global connector, signals
    return connector, signals

if __name__ == "__main__":
    # Import here to avoid circular imports during startup
    from dashboard.gui_app import run_dashboard
    
    print("Launching Exness AutoTrader GUI...")

    run_dashboard(
        start_cb=start_bot_thread, 
        stop_cb=stop_bot_thread, 
        close_cb=close_all_open_trades,
        data_cb=get_gui_data
    )
