"""
dashboard/terminal_dashboard.py - Live terminal UI v2.0
Shows all 6 filter layers, Gemini AI status, regime info, and session.
"""

import sys
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)
CLEAR = "\033[2J\033[H"


def _bar(value, max_val, width=20, color=Fore.GREEN):
    if max_val <= 0:
        return Fore.WHITE + " " * width + Style.RESET_ALL
    filled = max(0, min(int((value / max_val) * width), width))
    return color + "#" * filled + Fore.WHITE + " " * (width - filled) + Style.RESET_ALL


def render(symbols, account, daily_summary, open_positions,
           recent_trades, signals, gemini_stats=None):

    sys.stdout.write(CLEAR)
    sys.stdout.flush()

    now    = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
    pnl    = daily_summary.get("pnl_pct", 0.0)
    trades = daily_summary.get("trades", 0)
    stopped = daily_summary.get("stopped", False)
    bal    = account.get("balance", 0)
    eq     = account.get("equity", 0)
    curr   = account.get("currency", "USD")

    print(Fore.CYAN + "="*62 + Style.RESET_ALL)
    print(Fore.CYAN + "  * EXNESS AUTOTRADER v2.0  " + Fore.WHITE + f"-  {now}" + Style.RESET_ALL)
    print(Fore.CYAN + "  3-Layer: Chandelier -> ADX -> Gemini AI" + Style.RESET_ALL)
    print(Fore.CYAN + "="*62 + Style.RESET_ALL)

    # Account
    print(f"\n  {'Balance':<20} {Fore.WHITE}{bal:,.2f} {curr}{Style.RESET_ALL}"
          f"   Equity: {eq:,.2f}")

    # P&L
    pnl_col    = Fore.GREEN if pnl >= 0 else Fore.RED
    status_str = (Fore.YELLOW + "? PAUSED") if stopped else (Fore.GREEN + "* RUNNING")
    print(f"  {'Daily P&L':<20} {pnl_col}{pnl:+.2f}%{Style.RESET_ALL}   {status_str}{Style.RESET_ALL}")
    print(f"  {'Trades Today':<20} {trades}")

    if pnl >= 0:
        print(f"  Profit  [{_bar(pnl, 4.0, 24, Fore.GREEN)}] {pnl:.2f}% / 4%")
    else:
        print(f"  Loss    [{_bar(abs(pnl), 2.0, 24, Fore.RED)}] {abs(pnl):.2f}% / 2%")

    # Gemini AI stats
    if gemini_stats:
        if gemini_stats.get("enabled"):
            model = gemini_stats.get("model", "")
            total = gemini_stats.get("total_reviews", 0)
            approved = gemini_stats.get("approved", 0)
            rejected = gemini_stats.get("rejected", 0)
            rate = gemini_stats.get("approval_rate", 0)
            print(f"  {'[AI] Gemini AI':<20} {Fore.GREEN}ACTIVE{Style.RESET_ALL}  "
                  f"Reviews:{total} [OK]{approved} [FAIL]{rejected}  Rate:{rate}%")
        else:
            print(f"  {'[AI] Gemini AI':<20} {Fore.YELLOW}Disabled{Style.RESET_ALL}")

    # Signal table
    print(f"\n  {Fore.CYAN}{'-'*58}{Style.RESET_ALL}")
    print(f"  {'PAIR':<10} {'DIR':<8} {'RATING':>6} {'RISK':<8} {'RSI':>6} "
          f"{'REGIME':<10} {'AI':>6}")
    print(f"  {Fore.CYAN}{'-'*58}{Style.RESET_ALL}")

    for sym in symbols:
        sig = signals.get(sym)
        if sig:
            d = sig.direction
            dc = Fore.GREEN if d == "BUY" else (Fore.RED if d == "SELL" else Fore.WHITE)
            rc = Fore.GREEN if sig.risk_level == "LOW" else (
                 Fore.YELLOW if sig.risk_level == "MEDIUM" else Fore.RED)
            regime_str = sig.regime[:8] if hasattr(sig, 'regime') else "-"
            ai_str = sig.gemini_decision[:4] if hasattr(sig, 'gemini_decision') and sig.gemini_decision else "-"
            print(f"  {sym:<10} {dc}{d:<8}{Style.RESET_ALL} "
                  f"{sig.confidence:>4}/10  "
                  f"{rc}{sig.risk_level:<8}{Style.RESET_ALL} "
                  f"{sig.rsi:>5.1f}  "
                  f"{regime_str:<10} "
                  f" {ai_str:>5}")
        else:
            print(f"  {sym:<10} {'-'}")

    # Open positions
    if open_positions:
        print(f"\n  {Fore.CYAN}{'-'*58}{Style.RESET_ALL}")
        print(f"  OPEN POSITIONS")
        for pos in open_positions[:5]:
            ptype  = "BUY" if pos.get("type") == 0 else "SELL"
            profit = pos.get("profit", 0)
            pc     = Fore.GREEN if profit >= 0 else Fore.RED
            print(f"  #{pos.get('ticket')}  {pos.get('symbol',''):<10} {ptype}  "
                  f"{pos.get('volume',0)}L  P&L:{pc}{profit:+.2f}{Style.RESET_ALL}  "
                  f"SL:{pos.get('sl',0):.5f}")

    # Recent trades
    if recent_trades:
        print(f"\n  {Fore.CYAN}{'-'*58}{Style.RESET_ALL}")
        print(f"  RECENT TRADES")
        for t in recent_trades[-5:]:
            d  = t.get("direction","")
            dc = Fore.GREEN if d=="BUY" else Fore.RED
            ml = " [AI]" if str(t.get("ml_active","")).lower() == "true" else ""
            print(f"  {t.get('timestamp','')[:16]}  "
                  f"{dc}{d:<5}{Style.RESET_ALL} {t.get('symbol',''):<10} "
                  f"Conf:{t.get('confidence','')}%  "
                  f"Risk:{t.get('risk_level','')}{ml}")

    print(f"\n  {Fore.CYAN}{'='*58}{Style.RESET_ALL}")
    print(f"  Ctrl+C to stop bot safely.")
    print(f"  {Fore.CYAN}{'='*58}{Style.RESET_ALL}\n")
