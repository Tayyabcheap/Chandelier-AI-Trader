"""
dashboard/gui_app.py
A modern CustomTkinter Desktop Dashboard for the Exness AutoTrader.
"""

import customtkinter as ctk
import threading
import sys
import time
from config.settings import settings

# Must be imported here to prevent circular imports if main.py imports gui
# We will pass the main start function to the GUI instead.

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, str):
        self.widget.configure(state="normal")
        self.widget.insert("end", str)
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def flush(self):
        pass


class ExnessDashboard(ctk.CTk):
    def __init__(self, start_bot_callback, stop_bot_callback, close_trades_callback):
        super().__init__()

        self.start_bot_callback = start_bot_callback
        self.stop_bot_callback = stop_bot_callback
        self.close_trades_callback = close_trades_callback
        self.bot_running = False

        self.title("Exness AutoTrader v2.0 - Dashboard")
        self.geometry("1100x700")

        # Grid layout (1 row, 2 columns)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # -- Left Sidebar (Settings) --
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(8, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Exness AutoTrader", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Profit/Loss targets
        self.profit_label = ctk.CTkLabel(self.sidebar_frame, text="Daily Profit Target (%)")
        self.profit_label.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="w")
        self.profit_entry = ctk.CTkEntry(self.sidebar_frame)
        self.profit_entry.insert(0, str(settings.DAILY_PROFIT_TARGET_PCT))
        self.profit_entry.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        self.loss_label = ctk.CTkLabel(self.sidebar_frame, text="Daily Loss Limit (%)")
        self.loss_label.grid(row=3, column=0, padx=20, pady=(10, 0), sticky="w")
        self.loss_entry = ctk.CTkEntry(self.sidebar_frame)
        self.loss_entry.insert(0, str(settings.DAILY_LOSS_LIMIT_PCT))
        self.loss_entry.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Toggles
        self.gemini_switch = ctk.CTkSwitch(self.sidebar_frame, text="Gemini AI Filter")
        self.gemini_switch.grid(row=5, column=0, padx=20, pady=10, sticky="w")
        if settings.GEMINI_ENABLED:
            self.gemini_switch.select()

        self.adx_switch = ctk.CTkSwitch(self.sidebar_frame, text="ADX Regime Filter")
        self.adx_switch.grid(row=6, column=0, padx=20, pady=10, sticky="w")
        if settings.ADX_FILTER_ENABLED:
            self.adx_switch.select()

        # Save Settings
        self.save_btn = ctk.CTkButton(self.sidebar_frame, text="Save Settings to .env", command=self.save_settings, fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"))
        self.save_btn.grid(row=7, column=0, padx=20, pady=20, sticky="ew")

        # Emergency Close
        self.close_btn = ctk.CTkButton(self.sidebar_frame, text="EMERGENCY: Close All", command=self.close_all_trades, fg_color="#E74C3C", hover_color="#C0392B")
        self.close_btn.grid(row=9, column=0, padx=20, pady=20, sticky="ew")

        # -- Right Main Window (Logs & Controls) --
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Top Control Bar
        self.control_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        
        self.start_btn = ctk.CTkButton(self.control_frame, text="▶ START TRADING", font=ctk.CTkFont(size=18, weight="bold"), height=50, command=self.toggle_bot, fg_color="#2ECC71", hover_color="#27AE60")
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))

        # Live Terminal output
        self.log_box = ctk.CTkTextbox(self.main_frame, wrap="word", font=("Consolas", 12))
        self.log_box.grid(row=1, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")

        # Redirect standard output
        sys.stdout = TextRedirector(self.log_box)

    def save_settings(self):
        try:
            profit = float(self.profit_entry.get())
            loss = float(self.loss_entry.get())
            settings.update_setting("DAILY_PROFIT_TARGET_PCT", str(profit), float)
            settings.update_setting("DAILY_LOSS_LIMIT_PCT", str(loss), float)
            
            gemini_on = "true" if self.gemini_switch.get() else "false"
            adx_on = "true" if self.adx_switch.get() else "false"
            
            settings.update_setting("GEMINI_ENABLED", gemini_on, bool)
            settings.update_setting("ADX_FILTER_ENABLED", adx_on, bool)
            
            print(f"✅ Settings saved to .env! Profit: {profit}% | Loss: {loss}%")
        except ValueError:
            print("❌ Error: Profit/Loss must be numbers.")

    def toggle_bot(self):
        if not self.bot_running:
            self.bot_running = True
            self.start_btn.configure(text="⏸ PAUSE TRADING", fg_color="#F1C40F", hover_color="#F39C12")
            print("\n🚀 Starting bot...")
            threading.Thread(target=self.start_bot_callback, daemon=True).start()
        else:
            self.bot_running = False
            self.start_btn.configure(text="▶ START TRADING", fg_color="#2ECC71", hover_color="#27AE60")
            print("\n⏸ Bot Paused.")
            self.stop_bot_callback()

    def close_all_trades(self):
        print("\n🚨 EMERGENCY: Attempting to close all open trades!")
        threading.Thread(target=self.close_trades_callback, daemon=True).start()


def run_dashboard(start_cb, stop_cb, close_cb):
    app = ExnessDashboard(start_cb, stop_cb, close_cb)
    app.mainloop()
