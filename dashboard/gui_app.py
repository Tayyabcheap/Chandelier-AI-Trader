"""
dashboard/gui_app.py
A modern CustomTkinter 3-Pane Desktop Dashboard with Analytics.
"""

import customtkinter as ctk
import threading
import sys
import time
import tkinter as tk
import numpy as np
import pandas as pd
from config.settings import settings

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.ticker as mticker
    import matplotlib.dates as mdates
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

        # 3-Pane Resizable IDE Layout
        self.paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#1e1e2e", sashwidth=8, borderwidth=0, sashrelief=tk.FLAT)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()
        
        # Add to paned window instead of grid
        self.paned_window.add(self.left_master, minsize=320)
        self.paned_window.add(self.center_frame, minsize=400)
        self.paned_window.add(self.right_frame, minsize=400)

        # Start background poller
        self.after(2000, self.poll_live_data)
        
        # Load analytics once on startup if available
        self.after(3000, self.refresh_analytics)

    # ── Left Panel (Settings & Symbols) ───────────────────────────────────
    def _build_left_panel(self):
        self.left_master = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.sidebar = ctk.CTkScrollableFrame(self.left_master, width=320, corner_radius=0)
        self.sidebar.pack(fill="both", expand=True)
        
        # Logo
        logo = ctk.CTkLabel(self.sidebar, text="PRO TERMINAL", font=ctk.CTkFont(size=24, weight="bold"))
        logo.pack(pady=(20, 20))

        # Controls
        self.start_btn = ctk.CTkButton(self.sidebar, text="▶ START TRADING", font=ctk.CTkFont(size=16, weight="bold"), height=45, command=self.toggle_bot, fg_color="#2ECC71", hover_color="#27AE60")
        self.start_btn.pack(fill="x", padx=20, pady=(0, 10))

        self.close_btn = ctk.CTkButton(self.sidebar, text="EMERGENCY: CLOSE ALL", command=self.close_all_trades, fg_color="#E74C3C", hover_color="#C0392B", height=40)
        self.close_btn.pack(fill="x", padx=20, pady=(0, 20))

        # Checkbox Toggle Manager (Top)
        ctk.CTkLabel(self.sidebar, text="Active Symbols (Uncheck to Block)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(0,5))
        self.checkbox_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.checkbox_frame.pack(fill="x", padx=10, pady=2)
        
        self.symbol_checkboxes = {}
        self._refresh_checkboxes()

        # Settings
        ctk.CTkLabel(self.sidebar, text="Risk Management (%)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20,5))
        
        self.profit_entry = self._make_input_row("Daily Profit Target", settings.DAILY_PROFIT_TARGET_PCT)
        self.loss_entry = self._make_input_row("Daily Loss Limit", settings.DAILY_LOSS_LIMIT_PCT)
        self.max_trades_entry = self._make_input_row("Max Total Trades", settings.MAX_OPEN_TRADES)
        self.max_per_pair_entry = self._make_input_row("Max Trades / Pair", settings.MAX_TRADES_PER_SYMBOL)
        
        ctk.CTkLabel(self.sidebar, text="Gemini AI Dynamic Risk (%)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20,5))
        
        self.high_risk_entry = self._make_input_row("High Confidence (8-10)", settings.GEMINI_HIGH_RISK_PCT)
        self.med_risk_entry = self._make_input_row("Medium Confidence (5-7)", settings.GEMINI_MEDIUM_RISK_PCT)
        self.min_conf_entry = self._make_input_row("Minimum AI Rating", settings.MIN_GEMINI_CONFIDENCE)

        # Manage Master Pairs (Bottom)
        ctk.CTkLabel(self.sidebar, text="Manage Master Pairs", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(20,5))
        
        add_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=5)
        
        self.symbol_entry = ctk.CTkEntry(add_frame, placeholder_text="e.g. EURUSDc")
        self.symbol_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.add_sym_btn = ctk.CTkButton(add_frame, text="Add", width=50, command=self.add_symbol)
        self.add_sym_btn.pack(side="right")
        
        self.master_list_frame = ctk.CTkFrame(self.sidebar, fg_color="gray12", corner_radius=5)
        self.master_list_frame.pack(fill="x", padx=20, pady=5)
        self._refresh_master_list()

        self.save_btn = ctk.CTkButton(self.sidebar, text="Save Config", command=self.save_settings, fg_color="transparent", border_width=2)
        self.save_btn.pack(fill="x", padx=20, pady=(30, 20))

    def _refresh_checkboxes(self):
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
            
        self.symbol_checkboxes = {}
        for sym in settings.SYMBOLS:
            var = ctk.BooleanVar(value=sym not in settings.BLOCKED_SYMBOLS)
            cb = ctk.CTkCheckBox(self.checkbox_frame, text=sym, variable=var)
            cb.pack(anchor="w", padx=20, pady=2)
            self.symbol_checkboxes[sym] = var

    def _refresh_master_list(self):
        for widget in self.master_list_frame.winfo_children():
            widget.destroy()
            
        if not settings.SYMBOLS:
            ctk.CTkLabel(self.master_list_frame, text="No active pairs", text_color="gray50").pack(pady=5)
            
        for sym in settings.SYMBOLS:
            row = ctk.CTkFrame(self.master_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            
            ctk.CTkLabel(row, text=sym, font=ctk.CTkFont(weight="bold")).pack(side="left")
            remove_btn = ctk.CTkButton(row, text="❌", width=30, fg_color="#E74C3C", hover_color="#C0392B",
                                       command=lambda s=sym: self.remove_symbol(s))
            remove_btn.pack(side="right")
            
    def add_symbol(self):
        sym = self.symbol_entry.get().strip()
        if not sym: return
        
        # Validate with MT5
        connector, _, _, _ = self.data_cb()
        if connector and connector.connected:
            info = connector.get_symbol_info(sym)
            if not info:
                self.symbol_entry.delete(0, 'end')
                self.symbol_entry.insert(0, "Invalid Symbol")
                return
        
        if sym not in settings.SYMBOLS:
            settings.SYMBOLS.append(sym)
            settings.update_setting("SYMBOLS", ",".join(settings.SYMBOLS), list)
            
        self.symbol_entry.delete(0, 'end')
        self._refresh_master_list()
        self._refresh_checkboxes()
        
    def remove_symbol(self, sym):
        if sym in settings.SYMBOLS:
            settings.SYMBOLS.remove(sym)
            settings.update_setting("SYMBOLS", ",".join(settings.SYMBOLS), list)
            self._refresh_master_list()
            self._refresh_checkboxes()

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
        
        header = ctk.CTkLabel(self.center_frame, text="Active Positions", font=ctk.CTkFont(size=20, weight="bold"))
        header.pack(pady=(20, 5))

        self.account_label = ctk.CTkLabel(self.center_frame, text="Balance: --- | Equity: ---", font=ctk.CTkFont(size=15, weight="bold"), text_color="#2ECC71")
        self.account_label.pack(pady=(0, 5))
        
        self.pnl_label = ctk.CTkLabel(self.center_frame, text="Today's P&L: --- | Open P&L: ---", font=ctk.CTkFont(size=13), text_color="gray70")
        self.pnl_label.pack(pady=(0, 15))

        self.cards_frame = ctk.CTkScrollableFrame(self.center_frame, fg_color="transparent")
        self.cards_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.status_label = ctk.CTkLabel(self.cards_frame, text="Bot Offline. Click Start Trading.", text_color="gray50")
        self.status_label.pack(pady=50)

    # ── Right Panel (Inspector & Analytics Tabs) ──────────────────────────
    def _build_right_panel(self):
        self.right_frame = ctk.CTkFrame(self, fg_color="gray12", corner_radius=0)

        self.tabs = ctk.CTkTabview(self.right_frame)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.tabs.add("Performance Analytics")
        self.tabs.add("Latest AI Scan")
        self.tabs.add("📜 Trade History")
        self.tabs.add("🎯 Watchdog")
        
        self.tab_analytics = self.tabs.tab("Performance Analytics")
        self.tab_inspector = self.tabs.tab("Latest AI Scan")
        self.tab_watchdog = self.tabs.tab("🎯 Watchdog")
        
        self._build_watchdog_tab()
        
        self.inspect_content = ctk.CTkTextbox(self.tab_inspector, font=("Consolas", 14), wrap="word", fg_color="transparent")
        self.inspect_content.pack(fill="both", expand=True, padx=10, pady=10)
        self.inspect_content.insert("0.0", "Click 'Inspect Logic' on a trade to see the LATEST market scan for that pair.\n\nNote: This shows the CURRENT live AI reasoning, not the historical reasoning from when the trade was opened.")
        self.inspect_content.configure(state="disabled")

        # --- Analytics Tab ---
        self.analytics_filter = ctk.CTkSegmentedButton(
            self.tab_analytics, 
            values=["Overall", "CE Bot", "Watchdog", "Manual"],
            command=self.refresh_analytics
        )
        self.analytics_filter.pack(fill="x", pady=(0, 10))
        self.analytics_filter.set("Overall")

        self.analytics_scroll = ctk.CTkScrollableFrame(self.tab_analytics, fg_color="transparent")
        self.analytics_scroll.pack(fill="both", expand=True)

        if not MATPLOTLIB_AVAILABLE:
            ctk.CTkLabel(self.analytics_scroll, text="Missing Dependency: matplotlib\n\nPlease run 'pip install matplotlib' to view graphs.", text_color="red").pack(pady=50)
        else:
            # KPI Stats row
            self.kpi_frame = ctk.CTkFrame(self.analytics_scroll, fg_color="transparent")
            self.kpi_frame.pack(fill="x", padx=10, pady=(10, 5))
            self.kpi_labels = {}
            kpi_defs = [
                ("total_pnl", "Total P&L", "$0.00", "#00FFCC"),
                ("win_rate", "Win Rate", "0%", "#FFD700"),
                ("total_trades", "Trades", "0", "#87CEEB"),
                ("profit_factor", "Profit Factor", "0.0", "#DA70D6"),
                ("avg_win", "Avg Win", "$0.00", "#2ECC71"),
                ("avg_loss", "Avg Loss", "$0.00", "#E74C3C"),
                ("max_dd", "Max Drawdown", "0%", "#FF6347"),
                ("sharpe", "Sharpe Ratio", "0.0", "#00BFFF"),
            ]
            for i, (key, label, default, color) in enumerate(kpi_defs):
                card = ctk.CTkFrame(self.kpi_frame, fg_color="#1e1e2e", corner_radius=8)
                card.grid(row=i // 4, column=i % 4, padx=4, pady=4, sticky="nsew")
                self.kpi_frame.grid_columnconfigure(i % 4, weight=1)
                ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10), text_color="gray60").pack(pady=(8, 0))
                val_lbl = ctk.CTkLabel(card, text=default, font=ctk.CTkFont(size=16, weight="bold"), text_color=color)
                val_lbl.pack(pady=(0, 8))
                self.kpi_labels[key] = val_lbl

            self.refresh_btn = ctk.CTkButton(self.analytics_scroll, text="⟳ Refresh Analytics", command=self.refresh_analytics, fg_color="#2d2d44", hover_color="#3d3d5c", height=32)
            self.refresh_btn.pack(pady=(5, 5))
            self.canvas_widget = None

    def _build_watchdog_tab(self):
        # Top input row
        input_frame = ctk.CTkFrame(self.tab_watchdog, fg_color="transparent")
        input_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        self.wd_sym = ctk.CTkEntry(input_frame, placeholder_text="Symbol", width=80)
        self.wd_sym.pack(side="left", padx=2)
        
        self.wd_side = ctk.CTkOptionMenu(input_frame, values=["BUY", "SELL"], width=70)
        self.wd_side.pack(side="left", padx=2)
        
        self.wd_cond = ctk.CTkOptionMenu(input_frame, values=["ABOVE", "BELOW"], width=80)
        self.wd_cond.pack(side="left", padx=2)
        
        self.wd_trig = ctk.CTkEntry(input_frame, placeholder_text="Trigger Price", width=100)
        self.wd_trig.pack(side="left", padx=2)
        
        self.wd_sl = ctk.CTkEntry(input_frame, placeholder_text="Stop Loss", width=80)
        self.wd_sl.pack(side="left", padx=2)
        
        self.wd_tp = ctk.CTkEntry(input_frame, placeholder_text="Take Profit", width=80)
        self.wd_tp.pack(side="left", padx=2)
        
        self.wd_lot = ctk.CTkEntry(input_frame, placeholder_text="Lot", width=50)
        self.wd_lot.pack(side="left", padx=2)
        
        add_btn = ctk.CTkButton(input_frame, text="Add", width=50, command=self.add_watchdog)
        add_btn.pack(side="left", padx=(10, 0))
        
        # Grid frame
        self.wd_scroll = ctk.CTkScrollableFrame(self.tab_watchdog, fg_color="transparent")
        self.wd_scroll.pack(fill="both", expand=True, pady=10)

    def add_watchdog(self):
        connector, _, _, watchdog = self.data_cb()
        if watchdog:
            try:
                watchdog.add_situation(
                    self.wd_sym.get(),
                    self.wd_side.get(),
                    self.wd_cond.get(),
                    float(self.wd_trig.get()),
                    float(self.wd_sl.get()),
                    float(self.wd_tp.get()),
                    float(self.wd_lot.get() or "0.01")
                )
            except Exception as e:
                print(f"Watchdog add error: {e}")

    # ── Analytics Logic ───────────────────────────────────────────────────
    def refresh_analytics(self, filter_type=None):
        if not MATPLOTLIB_AVAILABLE: return
        
        connector, _, _, _ = self.data_cb()
        if not connector or not connector.connected: return
        
        self.refresh_btn.configure(text="Loading...", state="disabled")
        selected_filter = self.analytics_filter.get() if hasattr(self, 'analytics_filter') else "Overall"
        threading.Thread(target=self._plot_analytics_thread, args=(connector, selected_filter), daemon=True).start()

    def _plot_analytics_thread(self, connector, filter_type="Overall"):
        deals = connector.get_all_closed_deals(days=30)
        
        filtered_deals = []
        if deals:
            for d in deals:
                magic = d.get("magic", 0)
                comment = d.get("comment", "")
                if filter_type == "CE Bot":
                    if magic == 20240101 and not comment.startswith("Watchdog"):
                        filtered_deals.append(d)
                elif filter_type == "Watchdog":
                    if comment.startswith("Watchdog"):
                        filtered_deals.append(d)
                elif filter_type == "Manual":
                    if magic != 20240101:
                        filtered_deals.append(d)
                else:
                    filtered_deals.append(d)
                    
        deals = filtered_deals
        
        if not deals:
            self.after(0, lambda: self.refresh_btn.configure(text="⟳ Refresh Analytics", state="normal"))
            self.after(0, self._zero_analytics_ui)
            return
        
        df = pd.DataFrame(deals)
        
    def _zero_analytics_ui(self):
        # Update KPI labels to zero/defaults
        zero_kpis = {
            "total_pnl": "$0.00", "win_rate": "0%", "total_trades": "0", 
            "profit_factor": "0.0", "avg_win": "$0.00", "avg_loss": "$0.00",
            "max_dd": "0%", "sharpe": "0.0"
        }
        for key, val in zero_kpis.items():
            if key in self.kpi_labels:
                self.kpi_labels[key].configure(text=val, text_color="gray50")
        
        # Clear the canvas if it exists
        if self.canvas_widget:
            self.canvas_widget.destroy()
            self.canvas_widget = None
        df = df.sort_values("time").reset_index(drop=True)
        df["cumulative_profit"] = df["profit"].cumsum()
        df["win"] = df["profit"] > 0
        
        # Compute KPIs
        total_pnl = df["profit"].sum()
        wins = df[df["profit"] > 0]
        losses = df[df["profit"] <= 0]
        total_trades = len(df)
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
        avg_win = wins["profit"].mean() if len(wins) > 0 else 0
        avg_loss = losses["profit"].mean() if len(losses) > 0 else 0
        gross_profit = wins["profit"].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses["profit"].sum()) if len(losses) > 0 else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Max drawdown
        cummax = df["cumulative_profit"].cummax()
        drawdown = df["cumulative_profit"] - cummax
        max_dd = drawdown.min()
        max_dd_pct = (max_dd / cummax.replace(0, 1).max() * 100) if cummax.max() != 0 else 0
        
        # Sharpe ratio (daily returns approximation)
        if len(df) > 1:
            daily_rets = df.groupby(df["time"].dt.date)["profit"].sum()
            sharpe = (daily_rets.mean() / daily_rets.std() * np.sqrt(252)) if daily_rets.std() > 0 else 0
        else:
            sharpe = 0
        
        kpi_data = {
            "total_pnl": f"${total_pnl:+.2f}",
            "win_rate": f"{win_rate:.1f}%",
            "total_trades": str(total_trades),
            "profit_factor": f"{profit_factor:.2f}",
            "avg_win": f"${avg_win:+.2f}",
            "avg_loss": f"${avg_loss:.2f}",
            "max_dd": f"{max_dd_pct:.1f}%",
            "sharpe": f"{sharpe:.2f}",
        }
        
        self.after(0, self._render_graph, df, drawdown, kpi_data)

    def _refresh_trade_history(self, df):
        tab = self.tabs.tab("📜 Trade History")
        for widget in tab.winfo_children():
            widget.destroy()
            
        if df.empty:
            ctk.CTkLabel(tab, text="No closed trades found.", text_color="gray50").pack(pady=50)
            return
            
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        
        # Sort by time descending (newest first)
        df_sorted = df.sort_values("time", ascending=False)
        
        for _, row in df_sorted.iterrows():
            card = ctk.CTkFrame(scroll, fg_color="gray15", corner_radius=5)
            card.pack(fill="x", pady=5)
            
            sym = row["symbol"]
            prof = row["profit"]
            tck = row["ticket"]
            t = row["time"].strftime("%Y-%m-%d %H:%M")
            color = "#2ECC71" if prof >= 0 else "#E74C3C"
            
            left = ctk.CTkFrame(card, fg_color="transparent")
            left.pack(side="left", padx=15, pady=10)
            ctk.CTkLabel(left, text=f"#{tck} | {sym}", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
            ctk.CTkLabel(left, text=f"Closed: {t}", text_color="gray60").pack(anchor="w")
            
            ctk.CTkLabel(card, text=f"${prof:+.2f}", font=ctk.CTkFont(size=16, weight="bold"), text_color=color).pack(side="right", padx=20)

    def _render_graph(self, df, drawdown, kpi_data):
        self._refresh_trade_history(df)
        # Update KPI cards
        for key, val in kpi_data.items():
            if key in self.kpi_labels:
                self.kpi_labels[key].configure(text=val)
        
        if self.canvas_widget:
            self.canvas_widget.destroy()

        # Color palette
        BG = "#0d1117"
        GRID = "#21262d"
        CYAN = "#00FFCC"
        RED = "#FF003C"
        GOLD = "#FFD700"
        PURPLE = "#BD93F9"
        BLUE = "#58A6FF"
        ORANGE = "#FF9F43"
        PINK = "#FF6B9D"
        GRAY = "#8B949E"
        
        fig = Figure(figsize=(7, 14), dpi=100, facecolor=BG)
        fig.subplots_adjust(hspace=0.45, left=0.12, right=0.95, top=0.97, bottom=0.03)

        # ─── Chart 1: Equity Curve with Gradient Fill ────────────────────
        ax1 = fig.add_subplot(611)
        ax1.set_facecolor(BG)
        
        final_pnl = df["cumulative_profit"].iloc[-1]
        line_color = CYAN if final_pnl >= 0 else RED
        ax1.plot(df["time"], df["cumulative_profit"], color=line_color, linewidth=1.8, zorder=3)
        ax1.fill_between(df["time"], df["cumulative_profit"], 0,
                         where=(df["cumulative_profit"] >= 0), facecolor=CYAN, alpha=0.08)
        ax1.fill_between(df["time"], df["cumulative_profit"], 0,
                         where=(df["cumulative_profit"] < 0), facecolor=RED, alpha=0.08)
        ax1.axhline(y=0, color=GRAY, linewidth=0.5, linestyle="-", alpha=0.3)
        ax1.set_title("EQUITY CURVE", color="white", fontsize=10, fontweight="bold", loc="left")
        ax1.set_ylabel("P&L ($)", color=GRAY, fontsize=8)
        
        # ─── Chart 2: Drawdown ───────────────────────────────────────────
        ax2 = fig.add_subplot(612)
        ax2.set_facecolor(BG)
        ax2.fill_between(df["time"], drawdown, 0, facecolor=RED, alpha=0.3)
        ax2.plot(df["time"], drawdown, color=RED, linewidth=1.0, alpha=0.7)
        ax2.axhline(y=0, color=GRAY, linewidth=0.5, alpha=0.3)
        ax2.set_title("DRAWDOWN", color="white", fontsize=10, fontweight="bold", loc="left")
        ax2.set_ylabel("DD ($)", color=GRAY, fontsize=8)

        # ─── Chart 3: Profit by Pair (Horizontal Bar) ────────────────────
        ax3 = fig.add_subplot(613)
        ax3.set_facecolor(BG)
        if "symbol" in df.columns:
            pair_profit = df.groupby("symbol")["profit"].sum().sort_values()
            colors = [CYAN if p >= 0 else RED for p in pair_profit]
            bars = ax3.barh(pair_profit.index, pair_profit.values, color=colors, height=0.6, edgecolor="none")
            # Add value labels
            for bar, val in zip(bars, pair_profit.values):
                ax3.text(val + (0.2 if val >= 0 else -0.2), bar.get_y() + bar.get_height() / 2,
                         f"${val:.2f}", color="white", fontsize=7, va="center",
                         ha="left" if val >= 0 else "right")
        ax3.set_title("P&L BY INSTRUMENT", color="white", fontsize=10, fontweight="bold", loc="left")
        ax3.axvline(x=0, color=GRAY, linewidth=0.5, alpha=0.3)

        # ─── Chart 4: Win/Loss Distribution (Pie/Donut) ──────────────────
        ax4 = fig.add_subplot(614)
        ax4.set_facecolor(BG)
        wins = len(df[df["profit"] > 0])
        losses_count = len(df[df["profit"] <= 0])
        if wins + losses_count > 0:
            wedges, texts, autotexts = ax4.pie(
                [wins, losses_count],
                labels=[f"Wins ({wins})", f"Losses ({losses_count})"],
                colors=[CYAN, RED],
                autopct="%1.0f%%",
                startangle=90,
                pctdistance=0.75,
                wedgeprops=dict(width=0.35, edgecolor=BG, linewidth=2),
                textprops={"color": "white", "fontsize": 8}
            )
            for t in autotexts:
                t.set_color("white")
                t.set_fontsize(9)
                t.set_fontweight("bold")
            ax4.set_title("WIN / LOSS RATIO", color="white", fontsize=10, fontweight="bold", loc="left")

        # ─── Chart 5: Daily PnL Bars ─────────────────────────────────────
        ax5 = fig.add_subplot(615)
        ax5.set_facecolor(BG)
        daily_pnl = df.groupby(df["time"].dt.date)["profit"].sum()
        if len(daily_pnl) > 0:
            day_colors = [CYAN if p >= 0 else RED for p in daily_pnl]
            x_pos = range(len(daily_pnl))
            ax5.bar(x_pos, daily_pnl.values, color=day_colors, edgecolor="none", width=0.7)
            # X-axis labels
            if len(daily_pnl) <= 15:
                ax5.set_xticks(list(x_pos))
                ax5.set_xticklabels([str(d)[-5:] for d in daily_pnl.index], rotation=45, fontsize=6)
            else:
                step = max(1, len(daily_pnl) // 8)
                ax5.set_xticks(list(x_pos)[::step])
                ax5.set_xticklabels([str(d)[-5:] for d in daily_pnl.index[::step]], rotation=45, fontsize=6)
            ax5.axhline(y=0, color=GRAY, linewidth=0.5, alpha=0.3)
        ax5.set_title("DAILY P&L", color="white", fontsize=10, fontweight="bold", loc="left")
        ax5.set_ylabel("$", color=GRAY, fontsize=8)

        # ─── Chart 6: Trade Size Distribution (Histogram) ────────────────
        ax6 = fig.add_subplot(616)
        ax6.set_facecolor(BG)
        if len(df) > 2:
            profit_vals = df["profit"].values
            bins = min(25, max(5, len(df) // 3))
            n, bin_edges, patches = ax6.hist(profit_vals, bins=bins, edgecolor=BG, linewidth=0.5)
            for patch, left_edge in zip(patches, bin_edges):
                patch.set_facecolor(CYAN if left_edge >= 0 else RED)
                patch.set_alpha(0.7)
            ax6.axvline(x=0, color=GOLD, linewidth=1.0, linestyle="--", alpha=0.6)
            median_val = np.median(profit_vals)
            ax6.axvline(x=median_val, color=PURPLE, linewidth=1.0, linestyle=":", alpha=0.8)
        ax6.set_title("TRADE P&L DISTRIBUTION", color="white", fontsize=10, fontweight="bold", loc="left")
        ax6.set_xlabel("Profit ($)", color=GRAY, fontsize=8)
        ax6.set_ylabel("Frequency", color=GRAY, fontsize=8)

        # ─── Global Styling ──────────────────────────────────────────────
        for ax in [ax1, ax2, ax3, ax4, ax5, ax6]:
            ax.tick_params(colors=GRAY, labelsize=7)
            ax.grid(color=GRID, linestyle="-", linewidth=0.3, alpha=0.5)
            for spine in ax.spines.values():
                spine.set_color(GRID)
                spine.set_linewidth(0.5)

        canvas = FigureCanvasTkAgg(fig, master=self.analytics_scroll)
        canvas.draw()
        self.canvas_widget = canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True, padx=5, pady=(0, 10))
        
        self.refresh_btn.configure(text="⟳ Refresh Analytics", state="normal")

    # ── Polling & Trade Cards ─────────────────────────────────────────────
    def poll_live_data(self):
        if self.bot_running and self.data_cb:
            connector, signals, risk_mgr, watchdog = self.data_cb()
            if connector and connector.connected:
                # Update live account balance
                info = connector.get_account_info()
                self.account_label.configure(text=f"Balance: {info['balance']:.2f} {info['currency']} | Equity: {info['equity']:.2f} {info['currency']}")
                
                # Update P&L Labels
                today_pnl = risk_mgr.get_daily_summary()['pnl_pct'] if risk_mgr else 0.0
                open_pnl = info['profit']
                
                pnl_text = f"Today's P&L: {today_pnl:+.2f}% | Open P&L: ${open_pnl:+.2f}"
                self.pnl_label.configure(text=pnl_text)

                positions = connector.get_open_positions()
                self._refresh_trade_cards(positions, signals, connector)
                
                if watchdog:
                    watchdog.evaluate_live_prices()
                    self._refresh_watchdog_list(watchdog)
        
        self.after(2000, self.poll_live_data)

    def _refresh_watchdog_list(self, watchdog):
        if self.tabs.get() != "🎯 Watchdog":
            return # Save CPU if tab not active
            
        for widget in self.wd_scroll.winfo_children():
            widget.destroy()
            
        situations = watchdog.get_all()
        if not situations:
            ctk.CTkLabel(self.wd_scroll, text="No active situations.", text_color="gray50").pack(pady=50)
            return
            
        for sit in situations:
            card = ctk.CTkFrame(self.wd_scroll, corner_radius=5, fg_color="gray15")
            card.pack(fill="x", pady=5)
            
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(5,0))
            
            ctk.CTkLabel(top, text=f"#{sit.id} | {sit.side} {sit.symbol} {sit.condition} {sit.trigger_price}", font=ctk.CTkFont(weight="bold")).pack(side="left")
            
            filled = int(sit.dist_pct / 10)
            bar_str = f"Dist: [{'|'*filled}{' '*(10-filled)}]"
            color = "#2ECC71" if sit.exec_status == "Very Close" else ("#F1C40F" if sit.exec_status == "Hopeful" else "#E74C3C")
            
            bot = ctk.CTkFrame(card, fg_color="transparent")
            bot.pack(fill="x", padx=10, pady=(0,5))
            
            ctk.CTkLabel(bot, text=f"SL: {sit.sl} | TP: {sit.tp} | {bar_str} | Exec: {sit.exec_status}", text_color=color).pack(side="left")
            
            del_btn = ctk.CTkButton(top, text="❌", width=30, fg_color="#E74C3C", hover_color="#C0392B", command=lambda i=sit.id: watchdog.remove_situation(i))
            del_btn.pack(side="right")

    def _refresh_trade_cards(self, positions, signals, connector):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        if not positions:
            ctk.CTkLabel(self.cards_frame, text="No active trades. Scanning market...", text_color="gray50").pack(pady=50)
            return
            
        if not hasattr(self, '_point_cache'):
            self._point_cache = {}

        for pos in positions:
            sym = pos["symbol"]
            ticket = pos["ticket"]
            profit = pos["profit"]
            typ = "BUY" if pos["type"] == 0 else "SELL"
            color = "#2ECC71" if profit >= 0 else "#E74C3C"
            
            # Pip Calculation
            if sym not in self._point_cache:
                info = connector.get_symbol_info(sym)
                self._point_cache[sym] = info.get("point", 0.00001)
            
            point = self._point_cache[sym]
            price_open = pos["price_open"]
            price_current = pos["price_current"]
            
            # Standard calculation: 1 pip = 10 points
            if typ == "BUY":
                pips = (price_current - price_open) / (point * 10)
            else:
                pips = (price_open - price_current) / (point * 10)
                
            pip_str = f"{pips:+.1f} pips"
            pip_color = "#2ECC71" if pips >= 0 else "#E74C3C"
            
            magic = pos.get("magic", 0)
            comment = pos.get("comment", "")
            
            if comment.startswith("Watchdog"):
                tag = "[🎯 WATCHDOG]"
                tag_color = "#9B59B6" # Purple
            elif magic == 20240101:
                tag = "[🤖 CE BOT]"
                tag_color = "#3498DB" # Blue
            else:
                tag = "[🖐 MANUAL]"
                tag_color = "#F39C12" # Orange
            
            card = ctk.CTkFrame(self.cards_frame, corner_radius=8, fg_color="gray15")
            card.pack(fill="x", pady=10)
            
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=15, pady=(15, 5))
            
            ctk.CTkLabel(top_row, text=f"{tag} {typ} {sym}", font=ctk.CTkFont(size=18, weight="bold"), text_color=tag_color).pack(side="left")
            ctk.CTkLabel(top_row, text=f"${profit:.2f}", font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(side="right")
            
            btm_row = ctk.CTkFrame(card, fg_color="transparent")
            btm_row.pack(fill="x", padx=15, pady=(5, 15))
            
            # Show Volume, Ticket, and Live Pips
            ctk.CTkLabel(btm_row, text=f"Vol: {pos['volume']} | Ticket: #{ticket} | ").pack(side="left")
            ctk.CTkLabel(btm_row, text=pip_str, font=ctk.CTkFont(weight="bold"), text_color=pip_color).pack(side="left")
            
            # Action buttons
            close_btn = ctk.CTkButton(btm_row, text="❌ Close", width=70, fg_color="#E74C3C", hover_color="#C0392B", 
                                      command=lambda t=ticket: self.close_single_trade(t))
            close_btn.pack(side="right", padx=(10, 0))
            
            inspect_btn = ctk.CTkButton(btm_row, text="Inspect Logic", width=100, 
                                        command=lambda s=sym: self.inspect_trade(s, signals))
            inspect_btn.pack(side="right", padx=(0, 10))

    def inspect_trade(self, symbol, signals):
        self.tabs.set("Latest AI Scan")
        self.inspect_content.configure(state="normal")
        self.inspect_content.delete("0.0", "end")
        
        connector, _, _, _ = self.data_cb()
        # Find the active position for this symbol to get exact SL/TP dollar values
        positions = connector.get_open_positions() if connector else []
        sym_pos = [p for p in positions if p["symbol"] == symbol]
        
        report = f"=== CURRENT LIVE {symbol} SCAN ===\n\n"
        
        if sym_pos:
            p = sym_pos[0] # Just take the first one if multiple
            sl_val = p.get("sl", 0.0)
            tp_val = p.get("tp", 0.0)
            vol = p.get("volume", 0.0)
            entry = p.get("price_open", 0.0)
            typ = p.get("type", 0) # 0=BUY, 1=SELL
            
            sl_dlr = connector.calc_profit(typ, symbol, vol, entry, sl_val) if sl_val > 0 else 0.0
            tp_dlr = connector.calc_profit(typ, symbol, vol, entry, tp_val) if tp_val > 0 else 0.0
            
            report += (
                f"[ LIVE POSITION LIMITS ]\n"
                f"Entry Price      : {entry:.5f}\n"
                f"Stop Loss (SL)   : {sl_val:.5f}  (≈ {sl_dlr:+.2f} USD)\n"
                f"Take Profit (TP) : {tp_val:.5f}  (≈ {tp_dlr:+.2f} USD)\n\n"
            )

        sig = signals.get(symbol)
        if not sig:
            report += f"No AI logic recorded. Trade was placed manually or bot was restarted."
        else:
            ai_text = sig.gemini_reasoning if sig.gemini_reasoning else "No AI logic recorded (Signal was HOLD)."
            report += (
                f"[ ALGORITHMIC FILTERS ]\n"
                f"Chandelier Trend : {sig.direction}\n"
                f"ADX Momentum     : {sig.adx:.1f}\n\n"
                f"[ GEMINI AI ADVISOR ]\n"
                f"Decision Rating  : {sig.gemini_decision}\n"
                f"Risk Level       : {sig.risk_level}\n\n"
                f"[ REASONING LOG ]\n{ai_text}\n"
            )
            
        self.inspect_content.insert("0.0", report)
        self.inspect_content.configure(state="disabled")

    # ── User Actions ──────────────────────────────────────────────────────
    def close_single_trade(self, ticket):
        connector, _, _, _ = self.data_cb()
        if connector:
            print(f"Force closing ticket #{ticket} from GUI...")
            threading.Thread(target=connector.close_position, args=(ticket,), daemon=True).start()

    def save_settings(self):
        try:
            # Save Risk Limits
            settings.update_setting("DAILY_PROFIT_TARGET_PCT", self.profit_entry.get(), float)
            settings.update_setting("DAILY_LOSS_LIMIT_PCT", self.loss_entry.get(), float)
            settings.update_setting("MAX_OPEN_TRADES", self.max_trades_entry.get(), int)
            settings.update_setting("MAX_TRADES_PER_SYMBOL", self.max_per_pair_entry.get(), int)
            settings.update_setting("GEMINI_HIGH_RISK_PCT", self.high_risk_entry.get(), float)
            settings.update_setting("GEMINI_MEDIUM_RISK_PCT", self.med_risk_entry.get(), float)
            settings.update_setting("MIN_GEMINI_CONFIDENCE", self.min_conf_entry.get(), int)
            
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
