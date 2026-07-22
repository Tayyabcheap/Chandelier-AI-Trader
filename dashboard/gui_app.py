"""
dashboard/gui_app.py
A modern CustomTkinter 3-Pane Desktop Dashboard with Analytics.
"""

import customtkinter as ctk
import threading
import sys
import time
import pandas as pd
from config.settings import settings

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ExnessDashboard(ctk.CTk):
    def __init__(self, start_bot_callback, stop_bot_callback, close_trades_callback, data_cb):
        super().__init__()

        self.start_bot_callback = start_bot_callback
        self.stop_bot_callback = stop_bot_callback
        self.close_trades_callback = close_trades_callback
        self.data_cb = data_cb
        self.bot_running = False
        
        self.title("Exness Pro Terminal v3.5 - Analytics Edition")
        self.geometry("1400x850")

        # 3-Pane Grid layout
        self.grid_columnconfigure(0, weight=0, minsize=320) # Left Settings
        self.grid_columnconfigure(1, weight=1)              # Center Active Trades
        self.grid_columnconfigure(2, weight=1)              # Right Tabs
        self.grid_rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

        # Start background poller
        self.after(2000, self.poll_live_data)
        
        # Load analytics once on startup if available
        self.after(3000, self.refresh_analytics)

    # ── Left Panel (Settings & Symbols) ───────────────────────────────────
    def _build_left_panel(self):
        self.sidebar = ctk.CTkScrollableFrame(self, width=320, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        # Logo
        logo = ctk.CTkLabel(self.sidebar, text="PRO TERMINAL", font=ctk.CTkFont(size=24, weight="bold"))
        logo.pack(pady=(20, 20))

        # Controls
        self.start_btn = ctk.CTkButton(self.sidebar, text="▶ START TRADING", font=ctk.CTkFont(size=16, weight="bold"), height=45, command=self.toggle_bot, fg_color="#2ECC71", hover_color="#27AE60")
        self.start_btn.pack(fill="x", padx=20, pady=(0, 10))

        self.close_btn = ctk.CTkButton(self.sidebar, text="EMERGENCY: CLOSE ALL", command=self.close_all_trades, fg_color="#E74C3C", hover_color="#C0392B", height=40)
        self.close_btn.pack(fill="x", padx=20, pady=(0, 20))

        # Symbol Manager
        ctk.CTkLabel(self.sidebar, text="Active Symbols (Uncheck to Block)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(0,5))
        self.symbol_checkboxes = {}
        for sym in settings.SYMBOLS:
            var = ctk.BooleanVar(value=sym not in settings.BLOCKED_SYMBOLS)
            cb = ctk.CTkCheckBox(self.sidebar, text=sym, variable=var)
            cb.pack(anchor="w", padx=30, pady=2)
            self.symbol_checkboxes[sym] = var

        # Settings
        ctk.CTkLabel(self.sidebar, text="Risk Management (%)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20,5))
        
        self.profit_entry = self._make_input_row("Daily Profit Target", settings.DAILY_PROFIT_TARGET_PCT)
        self.loss_entry = self._make_input_row("Daily Loss Limit", settings.DAILY_LOSS_LIMIT_PCT)
        
        ctk.CTkLabel(self.sidebar, text="Gemini AI Dynamic Risk (%)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20,5))
        
        self.high_risk_entry = self._make_input_row("High Confidence (8-10)", settings.GEMINI_HIGH_RISK_PCT)
        self.med_risk_entry = self._make_input_row("Medium Confidence (5-7)", settings.GEMINI_MEDIUM_RISK_PCT)

        self.save_btn = ctk.CTkButton(self.sidebar, text="Save Config", command=self.save_settings, fg_color="transparent", border_width=2)
        self.save_btn.pack(fill="x", padx=20, pady=(30, 20))

    def _make_input_row(self, label_text, default_val):
        frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=5)
        ctk.CTkLabel(frame, text=label_text).pack(side="left")
        entry = ctk.CTkEntry(frame, width=60)
        entry.insert(0, str(default_val))
        entry.pack(side="right")
        return entry

    # ── Center Panel (Active Trades) ──────────────────────────────────────
    def _build_center_panel(self):
        self.center_frame = ctk.CTkFrame(self, fg_color="gray10", corner_radius=0)
        self.center_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=0)
        
        header = ctk.CTkLabel(self.center_frame, text="Active Positions", font=ctk.CTkFont(size=20, weight="bold"))
        header.pack(pady=20)

        self.cards_frame = ctk.CTkScrollableFrame(self.center_frame, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.status_label = ctk.CTkLabel(self.cards_frame, text="Bot Offline. Click Start Trading.", text_color="gray50")
        self.status_label.pack(pady=50)

    # ── Right Panel (Inspector & Analytics Tabs) ──────────────────────────
    def _build_right_panel(self):
        self.right_frame = ctk.CTkFrame(self, fg_color="gray12", corner_radius=0)
        self.right_frame.grid(row=0, column=2, sticky="nsew")

        self.tabs = ctk.CTkTabview(self.right_frame)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tab_inspector = self.tabs.add("AI Inspector")
        self.tab_analytics = self.tabs.add("Performance Analytics")
        
        # --- Inspector Tab ---
        self.inspect_content = ctk.CTkTextbox(self.tab_inspector, font=("Consolas", 14), wrap="word", fg_color="transparent")
        self.inspect_content.pack(fill="both", expand=True, padx=10, pady=10)
        self.inspect_content.insert("0.0", "Select an active trade from the center panel to inspect the AI reasoning.")
        self.inspect_content.configure(state="disabled")

        # --- Analytics Tab ---
        self.analytics_inner = ctk.CTkFrame(self.tab_analytics, fg_color="transparent")
        self.analytics_inner.pack(fill="both", expand=True)
        
        if not MATPLOTLIB_AVAILABLE:
            ctk.CTkLabel(self.analytics_inner, text="Missing Dependency: matplotlib\n\nPlease run 'pip install matplotlib' to view graphs.", text_color="red").pack(pady=50)
        else:
            self.refresh_btn = ctk.CTkButton(self.analytics_inner, text="Refresh Graph", command=self.refresh_analytics)
            self.refresh_btn.pack(pady=(10, 0))
            self.canvas_widget = None

    # ── Analytics Logic ───────────────────────────────────────────────────
    def refresh_analytics(self):
        if not MATPLOTLIB_AVAILABLE: return
        
        connector, _ = self.data_cb()
        if not connector or not connector.connected: return
        
        # Run MT5 history fetch in background to avoid freezing GUI
        threading.Thread(target=self._plot_analytics_thread, args=(connector,), daemon=True).start()

    def _plot_analytics_thread(self, connector):
        deals = connector.get_all_closed_deals(days=30)
        if not deals: return
        
        df = pd.DataFrame(deals)
        df = df.sort_values("time")
        df["cumulative_profit"] = df["profit"].cumsum()
        
        # Draw on main thread using 'after'
        self.after(0, self._render_graph, df)

    def _render_graph(self, df):
        if self.canvas_widget:
            self.canvas_widget.destroy()

        fig = Figure(figsize=(5, 4), dpi=100, facecolor="#1a1a1a")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        
        ax.plot(df["time"], df["cumulative_profit"], color="#2ECC71" if df["cumulative_profit"].iloc[-1] >= 0 else "#E74C3C", linewidth=2)
        
        ax.set_title("30-Day Cumulative PnL ($)", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("gray")
            
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self.analytics_inner)
        canvas.draw()
        self.canvas_widget = canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True, padx=10, pady=10)

    # ── Polling & Trade Cards ─────────────────────────────────────────────
    def poll_live_data(self):
        if self.bot_running and self.data_cb:
            connector, signals = self.data_cb()
            if connector and connector.connected:
                positions = connector.get_open_positions()
                self._refresh_trade_cards(positions, signals)
        
        self.after(2000, self.poll_live_data)

    def _refresh_trade_cards(self, positions, signals):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        if not positions:
            ctk.CTkLabel(self.cards_frame, text="No active trades. Scanning market...", text_color="gray50").pack(pady=50)
            return

        for pos in positions:
            sym = pos["symbol"]
            ticket = pos["ticket"]
            profit = pos["profit"]
            typ = "BUY" if pos["type"] == 0 else "SELL"
            color = "#2ECC71" if profit >= 0 else "#E74C3C"
            
            card = ctk.CTkFrame(self.cards_frame, corner_radius=8, fg_color="gray15")
            card.pack(fill="x", pady=10)
            
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=15, pady=(15, 5))
            
            ctk.CTkLabel(top_row, text=f"{typ} {sym}", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
            ctk.CTkLabel(top_row, text=f"${profit:.2f}", font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(side="right")
            
            btm_row = ctk.CTkFrame(card, fg_color="transparent")
            btm_row.pack(fill="x", padx=15, pady=(5, 15))
            
            ctk.CTkLabel(btm_row, text=f"Vol: {pos['volume']} | Ticket: #{ticket}").pack(side="left")
            
            # Action buttons
            close_btn = ctk.CTkButton(btm_row, text="❌ Close", width=70, fg_color="#E74C3C", hover_color="#C0392B", 
                                      command=lambda t=ticket: self.close_single_trade(t))
            close_btn.pack(side="right", padx=(10, 0))
            
            inspect_btn = ctk.CTkButton(btm_row, text="Inspect Logic", width=100, 
                                        command=lambda s=sym: self.inspect_trade(s, signals))
            inspect_btn.pack(side="right")

    def inspect_trade(self, symbol, signals):
        self.tabs.set("AI Inspector")
        self.inspect_content.configure(state="normal")
        self.inspect_content.delete("0.0", "end")
        
        sig = signals.get(symbol)
        if not sig:
            self.inspect_content.insert("0.0", f"No internal signal data found for {symbol}. It may have been placed manually.")
        else:
            ai_text = sig.gemini_reasoning if sig.gemini_reasoning else "No AI logic recorded."
            report = (
                f"=== {symbol} ANALYSIS ===\n\n"
                f"[ ALGORITHMIC FILTERS ]\n"
                f"Chandelier Trend : {sig.direction}\n"
                f"ADX Momentum     : {sig.adx:.1f}\n"
                f"Stop Loss Setup  : {sig.stop_loss:.5f}\n"
                f"Take Profit Set  : {sig.take_profit:.5f}\n\n"
                f"[ GEMINI AI ADVISOR ]\n"
                f"Decision Rating  : {sig.gemini_decision}\n"
                f"Risk Level       : {sig.risk_level}\n\n"
                f"[ REASONING LOG ]\n{ai_text}\n"
            )
            self.inspect_content.insert("0.0", report)
            
        self.inspect_content.configure(state="disabled")

    # ── User Actions ──────────────────────────────────────────────────────
    def close_single_trade(self, ticket):
        connector, _ = self.data_cb()
        if connector:
            print(f"Force closing ticket #{ticket} from GUI...")
            threading.Thread(target=connector.close_position, args=(ticket,), daemon=True).start()

    def save_settings(self):
        try:
            # Save Risk Limits
            settings.update_setting("DAILY_PROFIT_TARGET_PCT", self.profit_entry.get(), float)
            settings.update_setting("DAILY_LOSS_LIMIT_PCT", self.loss_entry.get(), float)
            settings.update_setting("GEMINI_HIGH_RISK_PCT", self.high_risk_entry.get(), float)
            settings.update_setting("GEMINI_MEDIUM_RISK_PCT", self.med_risk_entry.get(), float)
            
            # Save Blocked Symbols
            blocked = []
            for sym, var in self.symbol_checkboxes.items():
                if not var.get(): # Unchecked means blocked
                    blocked.append(sym)
                    
            settings.update_setting("BLOCKED_SYMBOLS", ",".join(blocked), list)
            
            self.save_btn.configure(text="Saved!", fg_color="#2ECC71")
            self.after(2000, lambda: self.save_btn.configure(text="Save Config", fg_color="transparent"))
        except ValueError:
            self.save_btn.configure(text="Error: Numbers Only", fg_color="#E74C3C")
            self.after(2000, lambda: self.save_btn.configure(text="Save Config", fg_color="transparent"))

    def toggle_bot(self):
        if not self.bot_running:
            self.bot_running = True
            self.start_btn.configure(text="⏸ PAUSE TRADING", fg_color="#F1C40F", hover_color="#F39C12")
            self.status_label.destroy() if hasattr(self, 'status_label') and self.status_label.winfo_exists() else None
            threading.Thread(target=self.start_bot_callback, daemon=True).start()
            self.refresh_analytics()
        else:
            self.bot_running = False
            self.start_btn.configure(text="▶ START TRADING", fg_color="#2ECC71", hover_color="#27AE60")
            self.stop_bot_callback()

    def close_all_trades(self):
        threading.Thread(target=self.close_trades_callback, daemon=True).start()

def run_dashboard(start_cb, stop_cb, close_cb, data_cb):
    app = ExnessDashboard(start_cb, stop_cb, close_cb, data_cb)
    app.mainloop()
