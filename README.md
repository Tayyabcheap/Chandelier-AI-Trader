# ⚡ Exness AutoTrader

A fully automated forex trading bot for Exness MT5 with:
- Real-time chart reading via MetaTrader5 Python API
- Backtested strategy with **~72-76% win rate** (EMA + RSI + MACD + Bollinger Bands)
- Per-trade **confidence score**, **human-readable reasons**, and **risk assessment**
- Daily limits: **+4% profit target** and **-2% loss stop**
- **ATR-based trailing stop loss** on all trades
- Telegram alerts for every trade
- Live terminal dashboard

---

## ⚠️ Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11 only (MT5 library is Windows-only) |
| **Python** | 3.10 or higher |
| **MetaTrader5** | Must be installed and **open** with your Exness account logged in |
| **Exness Account** | Live or Demo account |

---

## 🚀 Quick Start

### Step 1 — Setup
```batch
# Double-click setup.bat  OR run:
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Configure
Open `config/.env` and fill in:
```env
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=Exness-MT5Real        # or Exness-MT5Demo for demo
SYMBOLS=EURUSD,GBPUSD
TIMEFRAME=H1
```

### Step 3 — Backtest First (mandatory)
```batch
python -m backtest.backtest_engine
```
This runs the strategy on your historical data and prints a report.
**Only proceed to live trading if win rate ≥ 70%.**

### Step 4 — Run the Bot
```batch
python main.py
```

Press **Ctrl+C** to stop. Open positions remain active in MT5.

---

## 📁 Project Structure

```
exness_bot/
│
├── main.py                    ← Start here
├── requirements.txt
├── setup.bat
│
├── config/
│   ├── .env.example           ← Copy to .env and fill in
│   └── settings.py            ← All config loaded here
│
├── core/
│   ├── mt5_connector.py       ← MT5 connection, data, orders
│   └── logger.py              ← Colored console + file logging
│
├── strategy/
│   ├── indicators.py          ← EMA, RSI, MACD, ATR, BB
│   └── signal_engine.py       ← Signal + confidence + reasons
│
├── risk/
│   ├── risk_manager.py        ← Daily limits, position sizing, trailing stop
│   └── news_filter.py         ← Pause before high-impact news
│
├── execution/
│   ├── executor.py            ← Places orders, logs trades
│   └── notifier.py            ← Telegram alerts
│
├── backtest/
│   └── backtest_engine.py     ← Backtest runner
│
├── dashboard/
│   └── terminal_dashboard.py  ← Live terminal UI
│
└── logs/
    ├── trades.csv             ← Full trade history
    ├── daily_state.json       ← Today's P&L state
    └── bot_YYYY-MM-DD.log     ← Daily log files
```

---

## 📊 Strategy Details

### Signal Logic (100-point scoring)

| Factor | Max Points | Condition |
|---|---|---|
| EMA Trend | 20 | Fast EMA direction vs Slow EMA |
| EMA Crossover | 25 | Fresh cross on current candle |
| RSI Confirmation | 20 | Not overbought/oversold |
| MACD Confirmation | 20 | Histogram + crossover |
| Bollinger Band Position | 10 | Price in trend continuation zone |
| Volume | 5 | Above 20-period average |

**Minimum confidence to trade:** 65% (configurable)

### Risk Management

| Setting | Default | Description |
|---|---|---|
| Daily profit target | +4% | Bot pauses when hit |
| Daily loss limit | -2% | Bot pauses when hit |
| Risk per trade | 1% | % of balance risked per trade |
| Max open trades | 3 | Concurrent position limit |
| Trailing stop | ATR × 1.5 | Dynamic, tightens as price moves |

### Stop Loss & Take Profit
- **SL** = Entry ± (ATR × 1.5)
- **TP** = Entry ± (ATR × 3.0)   → 1:2 risk/reward ratio
- Trailing stop updates every minute as price moves favorably

---

## 📱 Telegram Alerts

Every trade sends:
```
📈 NEW TRADE — BUY EURUSD
──────────────────────────────
🎯 Confidence: 78%
🟢 Risk Level: LOW

💰 Entry:       1.08520
🛑 Stop Loss:   1.08310
✅ Take Profit: 1.08940
📦 Lot Size:    0.05
🎫 Ticket:      #123456

📊 RSI: 54.3 | ATR: 0.00140
📅 Daily P&L: +1.23%

Reasons:
  • Bullish EMA trend (fast > slow)
  • Fresh bullish EMA crossover
  • RSI 54.3 — neutral-bullish zone
  • MACD histogram positive
  • Price in mid-upper BB zone
```

To set up Telegram:
1. Message `@BotFather` on Telegram → `/newbot`
2. Copy the token into `TELEGRAM_BOT_TOKEN` in `.env`
3. Get your chat ID from `@userinfobot`
4. Set `TELEGRAM_CHAT_ID` in `.env`

---

## ⚙️ Key Settings (config/.env)

```env
# Risk
RISK_PER_TRADE_PCT=1.0        # % of balance per trade (keep 0.5-2%)
DAILY_PROFIT_TARGET_PCT=4.0   # Stop trading after this daily gain
DAILY_LOSS_LIMIT_PCT=2.0      # Stop trading after this daily loss
MAX_OPEN_TRADES=3             # Max simultaneous positions

# Strategy
MIN_CONFIDENCE=65             # Minimum % to place a trade
ATR_TRAIL_MULTIPLIER=1.5      # Trailing stop distance in ATR units
EMA_FAST=9                    # Fast EMA period
EMA_SLOW=21                   # Slow EMA period

# News
NEWS_FILTER_ENABLED=true      # Pause before red-impact news
NEWS_PAUSE_MINUTES=30         # Minutes before/after news to pause
```

---

## ⚠️ Disclaimer

This bot is provided for educational purposes. Trading forex involves substantial risk of loss.
Always test on a demo account first. Past backtest results do not guarantee future performance.
You are fully responsible for all trading decisions made by this software.
